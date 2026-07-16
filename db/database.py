from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/apuestas"


@dataclass(frozen=True)
class SavedPick:
    match_id: str
    league: str
    kickoff: str
    home_team: str
    away_team: str
    market: str
    selection: str
    probability: float
    odds: float
    ev: float
    bookmaker: str


class Database:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

    @contextmanager
    def connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("psycopg is required for PostgreSQL. Install requirements.txt first.") from exc
        conn = psycopg.connect(self.database_url, row_factory=dict_row, connect_timeout=3)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS "match" (
                        id TEXT PRIMARY KEY,
                        league TEXT NOT NULL,
                        kickoff TIMESTAMPTZ NOT NULL,
                        home_team TEXT NOT NULL,
                        away_team TEXT NOT NULL,
                        raw JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS market (
                        id BIGSERIAL PRIMARY KEY,
                        match_id TEXT NOT NULL REFERENCES "match"(id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        selection TEXT NOT NULL,
                        UNIQUE (match_id, name, selection)
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS probability (
                        id BIGSERIAL PRIMARY KEY,
                        market_id BIGINT NOT NULL REFERENCES market(id) ON DELETE CASCADE,
                        value DOUBLE PRECISION NOT NULL CHECK (value >= 0 AND value <= 1),
                        model_name TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS odds (
                        id BIGSERIAL PRIMARY KEY,
                        market_id BIGINT NOT NULL REFERENCES market(id) ON DELETE CASCADE,
                        value DOUBLE PRECISION NOT NULL CHECK (value > 1),
                        bookmaker TEXT NOT NULL,
                        captured_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ev (
                        id BIGSERIAL PRIMARY KEY,
                        market_id BIGINT NOT NULL REFERENCES market(id) ON DELETE CASCADE,
                        probability_id BIGINT NOT NULL REFERENCES probability(id) ON DELETE CASCADE,
                        odds_id BIGINT NOT NULL REFERENCES odds(id) ON DELETE CASCADE,
                        value DOUBLE PRECISION NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS agent_memory (
                        key TEXT PRIMARY KEY,
                        value JSONB NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS protocol_report (
                        report_date DATE PRIMARY KEY,
                        source_json TEXT,
                        enriched_json TEXT,
                        html_path TEXT,
                        csv_path TEXT,
                        public_html_url TEXT,
                        public_csv_url TEXT,
                        matches_count INTEGER NOT NULL DEFAULT 0,
                        markets_count INTEGER NOT NULL DEFAULT 0,
                        api_odds_count INTEGER NOT NULL DEFAULT 0,
                        betano_odds_count INTEGER NOT NULL DEFAULT 0,
                        ev_api_positive_count INTEGER NOT NULL DEFAULT 0,
                        ev_betano_positive_count INTEGER NOT NULL DEFAULT 0,
                        published_commit TEXT,
                        raw_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    """
                )

    def seed_agent_memory(self) -> None:
        memory = {
            "project": "D:\\CODEX\\APUESTAS",
            "intent": "Cuando el usuario pida protocolo completo del Mundial, ejecutar flujo publicado completo.",
            "single_command": "python tools\\run_published_protocol.py --dates YYYY-MM-DD --leagues 1 --publish",
            "workflow": [
                "generate_protocol_probabilities",
                "enrich_protocol_with_betano",
                "export_protocol_html",
                "build_pages_site",
                "copy site outputs to repo root",
                "git commit",
                "git pull --rebase origin main",
                "git push origin main",
                "verify GitHub Pages 200",
            ],
            "outputs": {
                "html": "outputs/protocolo_YYYYMMDD_pc.html",
                "csv": "outputs/protocolo_YYYYMMDD_pc_todos_los_mercados.csv",
                "public_html": "https://ze-martin.github.io/reports/protocolo_YYYYMMDD_pc.html",
                "public_csv": "https://ze-martin.github.io/reports/protocolo_YYYYMMDD_pc_todos_los_mercados.csv",
            },
            "rules": [
                "No inventar partidos si matches=0.",
                "No mezclar cuotas; mantener columnas API-Football y Betano separadas.",
                "Si Betano no tiene equivalente, dejar vacío o No encontrado en Betano.",
                "Publicar en GitHub Pages salvo instrucción contraria.",
                "Validar HTML, CSV y respuesta HTTP 200 antes de responder.",
            ],
        }
        self.save_agent_memory("published_protocol_workflow", memory)

    def save_agent_memory(self, key: str, value: dict[str, Any]) -> None:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_memory (key, value, updated_at)
                    VALUES (%s, %s::jsonb, now())
                    ON CONFLICT (key) DO UPDATE SET
                        value = EXCLUDED.value,
                        updated_at = now();
                    """,
                    (key, json.dumps(value, ensure_ascii=False)),
                )

    def get_agent_memory(self, key: str = "published_protocol_workflow") -> dict[str, Any] | None:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM agent_memory WHERE key = %s;", (key,))
                row = cur.fetchone()
        return dict(row["value"]) if row else None

    def save_matches(self, matches: Iterable[dict[str, Any]]) -> None:
        with self.connect() as conn:
            with conn.cursor() as cur:
                for item in matches:
                    cur.execute(
                        """
                        INSERT INTO "match" (id, league, kickoff, home_team, away_team, raw)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            league = EXCLUDED.league,
                            kickoff = EXCLUDED.kickoff,
                            home_team = EXCLUDED.home_team,
                            away_team = EXCLUDED.away_team,
                            raw = EXCLUDED.raw;
                        """,
                        (
                            item["id"],
                            item["league"],
                            item["kickoff"],
                            item["home_team"],
                            item["away_team"],
                            json.dumps(item.get("raw", {})),
                        ),
                    )

    def save_picks(self, picks: Iterable[SavedPick]) -> None:
        with self.connect() as conn:
            with conn.cursor() as cur:
                for pick in picks:
                    cur.execute(
                        """
                        INSERT INTO "match" (id, league, kickoff, home_team, away_team)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING;
                        """,
                        (pick.match_id, pick.league, pick.kickoff, pick.home_team, pick.away_team),
                    )
                    cur.execute(
                        """
                        INSERT INTO market (match_id, name, selection)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (match_id, name, selection) DO UPDATE SET selection = EXCLUDED.selection
                        RETURNING id;
                        """,
                        (pick.match_id, pick.market, pick.selection),
                    )
                    market_id = cur.fetchone()["id"]
                    cur.execute(
                        """
                        INSERT INTO probability (market_id, value, model_name)
                        VALUES (%s, %s, %s)
                        RETURNING id;
                        """,
                        (market_id, pick.probability, "poisson_base"),
                    )
                    probability_id = cur.fetchone()["id"]
                    cur.execute(
                        """
                        INSERT INTO odds (market_id, value, bookmaker)
                        VALUES (%s, %s, %s)
                        RETURNING id;
                        """,
                        (market_id, pick.odds, pick.bookmaker),
                    )
                    odds_id = cur.fetchone()["id"]
                    cur.execute(
                        """
                        INSERT INTO ev (market_id, probability_id, odds_id, value)
                        VALUES (%s, %s, %s, %s);
                        """,
                        (market_id, probability_id, odds_id, pick.ev),
                    )

    def save_protocol_run(
        self,
        *,
        report_date: date,
        protocol_json: dict[str, Any],
        source_json: str | Path | None = None,
        enriched_json: str | Path | None = None,
        html_path: str | Path | None = None,
        csv_path: str | Path | None = None,
        public_html_url: str | None = None,
        public_csv_url: str | None = None,
        published_commit: str | None = None,
    ) -> dict[str, int]:
        stats = self._protocol_stats(protocol_json)
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO protocol_report (
                        report_date, source_json, enriched_json, html_path, csv_path,
                        public_html_url, public_csv_url, matches_count, markets_count,
                        api_odds_count, betano_odds_count, ev_api_positive_count,
                        ev_betano_positive_count, published_commit, raw_summary, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, now())
                    ON CONFLICT (report_date) DO UPDATE SET
                        source_json = EXCLUDED.source_json,
                        enriched_json = EXCLUDED.enriched_json,
                        html_path = EXCLUDED.html_path,
                        csv_path = EXCLUDED.csv_path,
                        public_html_url = EXCLUDED.public_html_url,
                        public_csv_url = EXCLUDED.public_csv_url,
                        matches_count = EXCLUDED.matches_count,
                        markets_count = EXCLUDED.markets_count,
                        api_odds_count = EXCLUDED.api_odds_count,
                        betano_odds_count = EXCLUDED.betano_odds_count,
                        ev_api_positive_count = EXCLUDED.ev_api_positive_count,
                        ev_betano_positive_count = EXCLUDED.ev_betano_positive_count,
                        published_commit = COALESCE(EXCLUDED.published_commit, protocol_report.published_commit),
                        raw_summary = EXCLUDED.raw_summary,
                        updated_at = now();
                    """,
                    (
                        report_date,
                        str(source_json) if source_json else None,
                        str(enriched_json) if enriched_json else None,
                        str(html_path) if html_path else None,
                        str(csv_path) if csv_path else None,
                        public_html_url,
                        public_csv_url,
                        stats["matches"],
                        stats["markets"],
                        stats["api_odds"],
                        stats["betano_odds"],
                        stats["ev_api_positive"],
                        stats["ev_betano_positive"],
                        published_commit,
                        json.dumps(stats, ensure_ascii=False),
                    ),
                )
                for result in protocol_json.get("results", []):
                    match_id = str(result.get("match_id") or f"{result.get('date_lima')}:{result.get('match')}")
                    home_team, away_team = self._split_match(result.get("match", ""))
                    cur.execute(
                        """
                        INSERT INTO "match" (id, league, kickoff, home_team, away_team, raw)
                        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                        ON CONFLICT (id) DO UPDATE SET
                            league = EXCLUDED.league,
                            kickoff = EXCLUDED.kickoff,
                            home_team = EXCLUDED.home_team,
                            away_team = EXCLUDED.away_team,
                            raw = EXCLUDED.raw;
                        """,
                        (
                            match_id,
                            result.get("league") or "World Cup",
                            result.get("kickoff_lima") or f"{result.get('date_lima')}T{result.get('time_lima')}:00-05:00",
                            home_team,
                            away_team,
                            json.dumps(result, ensure_ascii=False),
                        ),
                    )
                    for market in result.get("all_markets", []):
                        probability = market.get("probability")
                        if probability is None:
                            continue
                        market_name = market.get("market") or market.get("key") or "unknown"
                        selection = market.get("key") or market_name
                        cur.execute(
                            """
                            INSERT INTO market (match_id, name, selection)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (match_id, name, selection) DO UPDATE SET selection = EXCLUDED.selection
                            RETURNING id;
                            """,
                            (match_id, market_name, selection),
                        )
                        market_id = cur.fetchone()["id"]
                        cur.execute(
                            """
                            INSERT INTO probability (market_id, value, model_name)
                            VALUES (%s, %s, %s)
                            RETURNING id;
                            """,
                            (market_id, float(probability), "protocol_probability"),
                        )
                        probability_id = cur.fetchone()["id"]
                        self._insert_protocol_odds(cur, market_id, probability_id, market, "api")
                        self._insert_protocol_odds(cur, market_id, probability_id, market, "betano")
        return stats

    def update_protocol_report_commit(self, report_date: date, commit: str) -> None:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE protocol_report
                    SET published_commit = %s, updated_at = now()
                    WHERE report_date = %s;
                    """,
                    (commit, report_date),
                )

    def latest_protocol_reports(self, limit: int = 30) -> list[dict[str, Any]]:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM protocol_report
                    ORDER BY report_date DESC
                    LIMIT %s;
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def latest_results(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        m.id AS match_id,
                        m.league,
                        m.kickoff,
                        m.home_team,
                        m.away_team,
                        mk.name AS market,
                        mk.selection,
                        p.value AS probability,
                        o.value AS odds,
                        e.value AS ev,
                        o.bookmaker,
                        e.created_at
                    FROM ev e
                    JOIN market mk ON mk.id = e.market_id
                    JOIN "match" m ON m.id = mk.match_id
                    JOIN probability p ON p.id = e.probability_id
                    JOIN odds o ON o.id = e.odds_id
                    ORDER BY e.created_at DESC
                    LIMIT %s;
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def _insert_protocol_odds(self, cur, market_id: int, probability_id: int, market: dict[str, Any], source: str) -> None:
        if source == "api":
            odds_value = market.get("odds_api", market.get("odds"))
            ev_value = market.get("ev_api", market.get("ev"))
            bookmaker = market.get("bookmaker_api") or market.get("bookmaker") or "API-Football"
        else:
            odds_value = market.get("odds_betano")
            ev_value = market.get("ev_betano")
            bookmaker = market.get("bookmaker_betano") or "Betano"
        if odds_value is None or ev_value is None:
            return
        cur.execute(
            """
            INSERT INTO odds (market_id, value, bookmaker)
            VALUES (%s, %s, %s)
            RETURNING id;
            """,
            (market_id, float(odds_value), bookmaker),
        )
        odds_id = cur.fetchone()["id"]
        cur.execute(
            """
            INSERT INTO ev (market_id, probability_id, odds_id, value)
            VALUES (%s, %s, %s, %s);
            """,
            (market_id, probability_id, odds_id, float(ev_value)),
        )

    def _protocol_stats(self, protocol_json: dict[str, Any]) -> dict[str, int]:
        results = protocol_json.get("results", [])
        markets = [market for result in results for market in result.get("all_markets", [])]
        return {
            "matches": len(results),
            "markets": len(markets),
            "api_odds": sum(1 for market in markets if market.get("odds_api", market.get("odds")) is not None),
            "betano_odds": sum(1 for market in markets if market.get("odds_betano") is not None),
            "ev_api_positive": sum(
                1
                for market in markets
                if market.get("ev_api", market.get("ev")) is not None and market.get("ev_api", market.get("ev")) > 0
            ),
            "ev_betano_positive": sum(
                1 for market in markets if market.get("ev_betano") is not None and market.get("ev_betano") > 0
            ),
        }

    def _split_match(self, match_name: str) -> tuple[str, str]:
        if " vs " in match_name:
            home, away = match_name.split(" vs ", 1)
            return home.strip(), away.strip()
        return match_name or "Unknown", "Unknown"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
