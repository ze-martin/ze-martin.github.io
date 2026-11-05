"""Local, opt-in T-60 worker. No scheduler or Telegram enabled implicitly."""
from __future__ import annotations
import argparse
import json
import os
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import load_environment
from apis.football_api import FootballAPI

STATE = ROOT / 'data' / 'automatic_protocol.sqlite'
LIMA = ZoneInfo('America/Lima')


@contextmanager
def worker_lock():
    """OS releases the lock on crashes; never overlap workers on Windows."""
    import msvcrt
    STATE.parent.mkdir(exist_ok=True)
    with open(STATE.parent / 'automatic_protocol.lock', 'a+b') as handle:
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError('Otro proceso automático ya está en ejecución') from None
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def connect():
    STATE.parent.mkdir(exist_ok=True)
    db = sqlite3.connect(STATE)
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY, kickoff TEXT NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT "pending", error TEXT, report TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS plans (day TEXT PRIMARY KEY, captured TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS outbox (fixture INTEGER PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT "telegram_disabled")')
    return db


def plan(db, day, config):
    api = FootballAPI()
    allowed = {int(x['id']) for x in config['leagues']}
    payload = api._api_get('fixtures', {'date': day, 'timezone': 'America/Lima'})
    if payload.get('errors'):
        raise RuntimeError('API-Football rechazó la consulta del cronograma')
    if not isinstance(payload.get('response'), list):
        raise RuntimeError('Respuesta de cronograma inválida')
    with db:
        for fixture in payload['response']:
            if fixture['league']['id'] not in allowed:
                continue
            db.execute('INSERT INTO jobs(id,kickoff,payload) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET kickoff=excluded.kickoff,payload=excluded.payload',
                       (fixture['fixture']['id'], fixture['fixture']['date'], json.dumps(fixture)))
        db.execute('INSERT OR REPLACE INTO plans VALUES(?,?)', (day, datetime.now(timezone.utc).isoformat()))


def analyze(job, db):
    # Re-fetch just this fixture, not the entire daily slate.
    import tools.generate_protocol_probabilities as generator
    from analysis.policy import apply_policy
    from db.performance_store import PerformanceStore
    started = datetime.now(timezone.utc).isoformat()
    api = FootballAPI()
    rows = api._api_get('fixtures', {'id': job['id']}).get('response', [])
    if len(rows) != 1:
        raise RuntimeError('No se pudo verificar el fixture')
    fixture = rows[0]
    kickoff = datetime.fromisoformat(fixture['fixture']['date'])
    if fixture['fixture']['status']['short'] != 'NS' or kickoff <= datetime.now(timezone.utc):
        with db:
            db.execute('UPDATE jobs SET state="expired" WHERE id=?', (job['id'],))
        return
    normalized = api._normalize_fixture(fixture, fallback_league=str(fixture['league']['id']))
    normalized['raw'] = api._enrich_api_football_fixture(fixture, str(fixture['league']['season']))
    class SingleFixtureAPI(FootballAPI):
        def get_matches(self, *args, **kwargs):
            return [normalized]
    original = generator.FootballAPI
    generator.FootballAPI = SingleFixtureAPI
    try:
        day = kickoff.astimezone(LIMA).date()
        result = generator.generate(day, day, [str(fixture['league']['id'])], day.isoformat())
    finally:
        generator.FootballAPI = original
    directory = ROOT / 'data' / 'automatic_runs'
    directory.mkdir(exist_ok=True)
    path = directory / f'{job["id"]}.json'
    path.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    for tool in ['enrich_protocol_with_betano.py', 'enrich_player_options.py']:
        subprocess.run([sys.executable, str(ROOT/'tools'/tool), '--source', str(path), '--output', str(path)], cwd=ROOT, check=True, timeout=900)
    result = apply_policy(json.loads(path.read_text(encoding='utf-8')))
    result['automatic_capture_started_at'] = started
    result['automatic_capture_completed_at'] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    # Freeze before any later evaluation. Never execute or place a bet.
    ledger = PerformanceStore()
    ledger.initialize()
    ledger.freeze(result, day.isoformat(), origin='pipeline')
    with db:
        for match in result.get('results', []):
            pick = match.get('recommended_pick')
            if pick and kickoff > datetime.now(timezone.utc):
                db.execute('INSERT OR IGNORE INTO outbox(fixture,payload) VALUES(?,?)', (job['id'], json.dumps({'match':match['match'], 'pick':pick, 'captured':result['automatic_capture_completed_at'], 'report':str(path)}, ensure_ascii=False)))
        db.execute('UPDATE jobs SET state="completed",report=? WHERE id=?', (str(path), job['id']))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', help='YYYY-MM-DD: preparar cronograma solamente')
    parser.add_argument('--tick', action='store_true', help='Procesar ventana T-60 a T-45; no activa un servicio')
    parser.add_argument('--bootstrap-from', help='Excepción manual de hoy: HH:MM en Perú, solo partidos NS futuros')
    args = parser.parse_args()
    load_environment(ROOT/'.env')
    os.environ['API_FOOTBALL_CACHE_ENABLED'] = 'false'
    config = json.loads((ROOT/'config'/'automatic_leagues.json').read_text(encoding='utf-8'))
    db = connect()
    try:
        if args.plan:
            plan(db, args.plan, config)
        if args.bootstrap_from:
            today = datetime.now(LIMA).date()
            cutoff = datetime.fromisoformat(today.isoformat()+'T'+args.bootstrap_from).replace(tzinfo=LIMA)
            plan(db, today.isoformat(), config)
            for job in db.execute('SELECT * FROM jobs WHERE state IN ("pending","missed") ORDER BY kickoff').fetchall():
                start = datetime.fromisoformat(job['kickoff'])
                fixture = json.loads(job['payload'])
                if start.astimezone(LIMA).date()!=today or start<cutoff or start<=datetime.now(timezone.utc) or fixture['fixture']['status']['short']!='NS':
                    continue
                try:
                    analyze(job, db)
                except Exception as exc:
                    with db:
                        db.execute('UPDATE jobs SET state="failed",error=? WHERE id=?', (type(exc).__name__, job['id']))
        if args.tick:
            tomorrow = (datetime.now(LIMA).date()+timedelta(days=1)).isoformat()
            if not db.execute('SELECT 1 FROM plans WHERE day=?', (tomorrow,)).fetchone():
                plan(db, tomorrow, config)
            for job in db.execute('SELECT * FROM jobs WHERE state="pending" ORDER BY kickoff').fetchall():
                minutes = (datetime.fromisoformat(job['kickoff'])-datetime.now(timezone.utc)).total_seconds()/60
                if minutes < 45:
                    with db:
                        db.execute('UPDATE jobs SET state="missed" WHERE id=?', (job['id'],))
                elif minutes <= 60:
                    try:
                        analyze(job, db)
                    except Exception as exc:
                        with db:
                            db.execute('UPDATE jobs SET state="failed",error=? WHERE id=?', (type(exc).__name__, job['id']))
        from tools.build_automatic_page import build
        build()
        print(json.dumps({'jobs':dict(db.execute('SELECT state,count(*) FROM jobs GROUP BY state').fetchall()), 'telegram':'disabled', 'scheduler':'not installed'}))
    finally:
        db.close()


if __name__ == '__main__':
    with worker_lock():
        main()
