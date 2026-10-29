"""Immutable prediction ledger; paper results are never actual wagers."""
import hashlib
import json
import sqlite3
import math
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
from analysis.settlement import profit

DEFAULT = Path(__file__).resolve().parents[1] / 'data/protocol_memory.sqlite'


class PerformanceStore:
    def __init__(self, path=DEFAULT):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self):
        with self.connect() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS prediction_snapshot (
              id TEXT PRIMARY KEY, report_date TEXT NOT NULL, generated_at TEXT NOT NULL,
              captured_at TEXT NOT NULL, model_version TEXT NOT NULL, origin TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS pick_snapshot (
              id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL, fixture_id TEXT NOT NULL,
              match_name TEXT NOT NULL, kickoff TEXT, role TEXT NOT NULL, market_key TEXT NOT NULL,
              probability REAL, quotes TEXT NOT NULL, league TEXT, sample_min INTEGER);
            CREATE TABLE IF NOT EXISTS pick_settlement (
              pick_id TEXT PRIMARY KEY, outcome TEXT NOT NULL, checked_at TEXT NOT NULL, source TEXT NOT NULL, evidence TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS actual_bet (
              id TEXT PRIMARY KEY, pick_id TEXT NOT NULL, bookmaker TEXT NOT NULL, odds REAL NOT NULL,
              stake REAL NOT NULL, placed_at TEXT NOT NULL);
            CREATE TRIGGER IF NOT EXISTS immutable_snapshot_update BEFORE UPDATE ON prediction_snapshot
              BEGIN SELECT RAISE(ABORT,'Snapshots are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_snapshot_delete BEFORE DELETE ON prediction_snapshot
              BEGIN SELECT RAISE(ABORT,'Snapshots are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_pick_update BEFORE UPDATE ON pick_snapshot
              BEGIN SELECT RAISE(ABORT,'Picks are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_pick_delete BEFORE DELETE ON pick_snapshot
              BEGIN SELECT RAISE(ABORT,'Picks are immutable'); END;
            ''')

    def freeze(self, data, report_date, origin='pipeline'):
        raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
        sid = hashlib.sha256(raw.encode()).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        generated = data.get('generated_at') or now
        version = data.get('model_version') or 'legacy-exact-v1'
        if data.get('selection_policy'):
            version += '|' + data['selection_policy']
        with self.connect() as c:
            c.execute('INSERT OR IGNORE INTO prediction_snapshot VALUES (?,?,?,?,?,?,?)',
                      (sid, str(report_date), generated, now, version, origin, raw))
            snapshot = c.execute('SELECT origin,captured_at FROM prediction_snapshot WHERE id=?',(sid,)).fetchone()
            for match in data.get('results', []):
                if snapshot['origin']=='pipeline' and match.get('kickoff_lima') and datetime.fromisoformat(match['kickoff_lima'])<=datetime.fromisoformat(snapshot['captured_at']):
                    continue
                entries = [('principal', match.get('recommended_pick'))]
                entries += [('alternativa', m) for m in match.get('alternative_picks', [])]
                for role, market in entries:
                    if not market or match.get('pre_match_eligible') is False:
                        continue
                    key = market['key']
                    pid = hashlib.sha256(f'{sid}:{match["match_id"]}:{key}:{role}'.encode()).hexdigest()
                    quotes = {'API': {'bookmaker': market.get('bookmaker_api') or match.get('bookmaker'),
                                      'odds': market.get('odds_api', market.get('odds'))},
                              'Betano': {'bookmaker': 'Betano', 'odds': market.get('odds_betano')}}
                    c.execute('INSERT OR IGNORE INTO pick_snapshot VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                              (pid, sid, str(match['match_id']), match['match'], match.get('kickoff_lima'), role, key,
                               market.get('probability'), json.dumps(quotes), match.get('league'), market.get('sample_min')))
        return sid

    def pending(self):
        with self.connect() as c:
            return [dict(r) for r in c.execute('''SELECT p.*,s.generated_at,s.report_date,s.model_version
                FROM pick_snapshot p JOIN prediction_snapshot s ON p.snapshot_id=s.id
                LEFT JOIN pick_settlement t ON t.pick_id=p.id WHERE t.pick_id IS NULL''')]

    def settle(self, pick_id, outcome, evidence):
        if outcome not in {'won', 'lost', 'void'}:
            raise ValueError('Liquidación desconocida')
        with self.connect() as c:
            c.execute('INSERT OR IGNORE INTO pick_settlement VALUES (?,?,?,?,?)',
                      (pick_id, outcome, datetime.now(timezone.utc).isoformat(), 'API-Football', json.dumps(evidence)))

    def record_bet(self, bet_id, pick_id, bookmaker, odds, stake, placed_at):
        if not bet_id.strip() or not bookmaker.strip() or not math.isfinite(stake) or not math.isfinite(odds) or stake <= 0 or odds <= 1:
            raise ValueError('ID, casa, cuota e importe válidos son obligatorios')
        placed = datetime.fromisoformat(placed_at.replace('Z', '+00:00'))
        if placed.tzinfo is None:
            raise ValueError('La hora de apuesta debe incluir zona horaria')
        with self.connect() as c:
            row = c.execute('SELECT p.kickoff,s.generated_at FROM pick_snapshot p JOIN prediction_snapshot s ON s.id=p.snapshot_id WHERE p.id=?', (pick_id,)).fetchone()
            if not row:
                raise ValueError('Pick inexistente')
            if placed > datetime.now(timezone.utc) or placed < datetime.fromisoformat(row['generated_at']):
                raise ValueError('Hora de colocación posterior al pronóstico y no futura requerida')
            if row['kickoff'] and placed >= datetime.fromisoformat(row['kickoff']):
                raise ValueError('Este registro admite solo apuestas prepartido')
            c.execute('INSERT INTO actual_bet VALUES (?,?,?,?,?,?)', (bet_id, pick_id, bookmaker, odds, stake, placed_at))

    def rows(self, role='principal'):
        with self.connect() as c:
            rows = c.execute('''SELECT p.*,s.report_date,s.model_version,s.origin,s.generated_at,
                t.outcome FROM pick_snapshot p JOIN prediction_snapshot s ON s.id=p.snapshot_id
                LEFT JOIN pick_settlement t ON t.pick_id=p.id WHERE p.role=? ORDER BY s.captured_at,p.id''', (role,)).fetchall()
        # First frozen version per fixture/model/role prevents revised reports
        # from changing historical performance or counting a match twice.
        unique = {}
        for row in rows:
            r = dict(row)
            unique.setdefault((r['fixture_id'], r['model_version'], r['role'], r['market_key'] if role!='principal' else ''), r)
        return list(unique.values())

    def public_summary(self):
        groups = {}
        for role in ['principal', 'alternativa']:
            for r in self.rows(role):
                key = (r['model_version'], role)
                groups.setdefault(key, []).append(r)
        summary = []
        for (version, role), rows in groups.items():
            settled = [r for r in rows if r['outcome'] in {'won', 'lost'}]
            wins = sum(r['outcome'] == 'won' for r in settled)
            n = len(settled)
            houses = {}
            portfolios = {}
            for r in rows:
                if r['outcome'] not in {'won','lost','void'}:continue
                for source,q in json.loads(r['quotes']).items():
                    if q.get('odds') is None:continue
                    name = (q.get('bookmaker') or 'Casa no identificada') + ' · ' + source
                    portfolios.setdefault(name,[]).append((r,q))
            for house,quoted in portfolios.items():
                pnl = sum(profit(r['outcome'], q['odds']) for r, q in quoted)
                houses[house] = {'n': len(quoted), 'profit_units': round(pnl, 4), 'roi': pnl / len(quoted) if quoted else None}
            bins = []
            for low, high in [(0, .6), (.6, .7), (.7, .8), (.8, .9), (.9, 1.000001)]:
                rs = [r for r in settled if low <= r['probability'] < high]
                if rs:
                    bins.append({'range': f'{low:.0%}–{min(high,1):.0%}', 'n': len(rs),
                                 'predicted': sum(r['probability'] for r in rs)/len(rs),
                                 'observed': sum(r['outcome']=='won' for r in rs)/len(rs)})
            summary.append({'model_version': version, 'role': role, 'n': n, 'won': wins, 'lost': n-wins,
                            'pending': sum(r['outcome'] is None for r in rows), 'void': sum(r['outcome']=='void' for r in rows),
                            'hit_rate': wins/n if n else None,
                            'brier': sum((r['probability']-(r['outcome']=='won'))**2 for r in settled)/n if n else None,
                            'expected': sum(r['probability'] for r in settled)/n if n else None,
                            'houses': houses, 'reliability': bins})
        return {'scope': 'Un pick principal por partido y versión; no son apuestas reales. Históricos recuperados no prueban primera publicación.',
                'groups': summary, 'updated_at': datetime.now(timezone.utc).isoformat()}

    def actual_summary(self):
        with self.connect() as c:
            rows = c.execute('SELECT b.*,s.outcome FROM actual_bet b LEFT JOIN pick_settlement s ON s.pick_id=b.pick_id').fetchall()
        settled = [r for r in rows if r['outcome'] is not None]
        stake = sum(r['stake'] for r in settled)
        pnl = sum(profit(r['outcome'],r['odds'],r['stake']) for r in settled)
        return {'bets':len(rows),'settled':len(settled),'stake':stake,'profit':pnl,'roi':pnl/stake if stake else None}

    def mirror_postgres(self):
        from db.database import Database
        with self.connect() as c:
            events = [(table,dict(row)) for table in ['prediction_snapshot','pick_snapshot','pick_settlement','actual_bet']
                      for row in c.execute('SELECT * FROM '+table)]
        with Database().connect() as c:
            with c.cursor() as cur:
                cur.execute('CREATE TABLE IF NOT EXISTS protocol_audit_event (kind TEXT NOT NULL,event_id TEXT NOT NULL,payload JSONB NOT NULL,PRIMARY KEY(kind,event_id))')
                for kind,row in events:
                    eid = row.get('id') or row['pick_id']
                    cur.execute('INSERT INTO protocol_audit_event VALUES (%s,%s,%s::jsonb) ON CONFLICT DO NOTHING', (kind,eid,json.dumps(row)))
