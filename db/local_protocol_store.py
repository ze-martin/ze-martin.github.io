from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "data" / "protocol_memory.sqlite"


class LocalProtocolStore:
    """SQLite fallback for protocol memory when PostgreSQL is not available."""

    def __init__(self, path: str | Path = DEFAULT_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_memory (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS protocol_report (
                    report_date TEXT PRIMARY KEY,
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
                    raw_summary TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS protocol_market (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_date TEXT NOT NULL,
                    match_id TEXT,
                    match_name TEXT NOT NULL,
                    kickoff_lima TEXT,
                    market_key TEXT,
                    market_name TEXT,
                    probability REAL,
                    bookmaker_api TEXT,
                    odds_api REAL,
                    ev_api REAL,
                    bookmaker_betano TEXT,
                    odds_betano REAL,
                    ev_betano REAL,
                    raw_market TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_protocol_market_date ON protocol_market(report_date);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_protocol_market_match ON protocol_market(match_name);")

    def seed_agent_memory(self) -> None:
        memory = {
            "project": "D:\\CODEX\\APUESTAS",
            "single_command": "python tools\\run_published_protocol.py --dates YYYY-MM-DD --leagues 1 --publish",
            "entrypoint": "python run.py --from YYYY-MM-DD --to YYYY-MM-DD --leagues 1 --published-protocol --publish",
            "public_base": "https://ze-martin.github.io/reports",
            "workflow": [
                "generate protocol",
                "scrape Betano",
                "export HTML/CSV",
                "save SQLite/PostgreSQL",
                "publish GitHub Pages",
                "verify HTTP 200",
            ],
            "rules": [
                "No inventar partidos ni cuotas.",
                "Separar cuotas API-Football y Betano.",
                "Publicar en GitHub Pages salvo instrucción contraria.",
            ],
        }
        self.save_agent_memory("published_protocol_workflow", memory)

    def save_agent_memory(self, key: str, value: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_memory (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at;
                """,
                (key, json.dumps(value, ensure_ascii=False), now),
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
        stats = self.protocol_stats(protocol_json)
        now = datetime.now(timezone.utc).isoformat()
        day = report_date.isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO protocol_report (
                    report_date, source_json, enriched_json, html_path, csv_path,
                    public_html_url, public_csv_url, matches_count, markets_count,
                    api_odds_count, betano_odds_count, ev_api_positive_count,
                    ev_betano_positive_count, published_commit, raw_summary, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_date) DO UPDATE SET
                    source_json = excluded.source_json,
                    enriched_json = excluded.enriched_json,
                    html_path = excluded.html_path,
                    csv_path = excluded.csv_path,
                    public_html_url = excluded.public_html_url,
                    public_csv_url = excluded.public_csv_url,
                    matches_count = excluded.matches_count,
                    markets_count = excluded.markets_count,
                    api_odds_count = excluded.api_odds_count,
                    betano_odds_count = excluded.betano_odds_count,
                    ev_api_positive_count = excluded.ev_api_positive_count,
                    ev_betano_positive_count = excluded.ev_betano_positive_count,
                    published_commit = COALESCE(excluded.published_commit, protocol_report.published_commit),
                    raw_summary = excluded.raw_summary,
                    updated_at = excluded.updated_at;
                """,
                (
                    day,
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
                    now,
                ),
            )
            conn.execute("DELETE FROM protocol_market WHERE report_date = ?;", (day,))
            for result in protocol_json.get("results", []):
                for market in result.get("all_markets", []):
                    conn.execute(
                        """
                        INSERT INTO protocol_market (
                            report_date, match_id, match_name, kickoff_lima, market_key, market_name,
                            probability, bookmaker_api, odds_api, ev_api, bookmaker_betano,
                            odds_betano, ev_betano, raw_market, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            day,
                            str(result.get("match_id") or ""),
                            result.get("match") or "",
                            result.get("kickoff_lima") or "",
                            market.get("key") or "",
                            market.get("market") or "",
                            market.get("probability"),
                            market.get("bookmaker_api") or market.get("bookmaker"),
                            market.get("odds_api", market.get("odds")),
                            market.get("ev_api", market.get("ev")),
                            market.get("bookmaker_betano"),
                            market.get("odds_betano"),
                            market.get("ev_betano"),
                            json.dumps(market, ensure_ascii=False),
                            now,
                        ),
                    )
        return stats

    def update_protocol_report_commit(self, report_date: date, commit: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE protocol_report SET published_commit = ?, updated_at = ? WHERE report_date = ?;",
                (commit, datetime.now(timezone.utc).isoformat(), report_date.isoformat()),
            )

    def latest_protocol_reports(self, limit: int = 30) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM protocol_report ORDER BY report_date DESC LIMIT ?;",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def protocol_stats(self, protocol_json: dict[str, Any]) -> dict[str, int]:
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
