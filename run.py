from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date

from config import load_environment
from services.pipeline import BettingPipeline


load_environment()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ejecuta el pipeline de value bets.")
    parser.add_argument("--from", dest="from_date", required=True, help="Fecha inicial YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", required=True, help="Fecha final YYYY-MM-DD")
    parser.add_argument("--leagues", default="", help='Ligas separadas por coma, por ejemplo "Liga1,Liga2"')
    parser.add_argument("--no-db", action="store_true", help="Ejecuta sin guardar en PostgreSQL")
    parser.add_argument(
        "--published-protocol",
        action="store_true",
        help="Usa el flujo operativo completo: protocolo base + Betano + HTML/CSV + memoria DB.",
    )
    parser.add_argument("--publish", action="store_true", help="Publica el protocolo en GitHub Pages.")
    parser.add_argument("--betano-python", help="Python alternativo con Playwright instalado para scraping Betano.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.published_protocol or args.publish:
        command = [
            sys.executable,
            "tools\\run_published_protocol.py",
            "--from",
            args.from_date,
            "--to",
            args.to_date,
            "--leagues",
            args.leagues or "1",
        ]
        if args.publish:
            command.append("--publish")
        if args.no_db:
            command.append("--no-db")
        if args.betano_python:
            command.extend(["--betano-python", args.betano_python])
        completed = subprocess.run(command, text=True)
        return completed.returncode

    from_date = date.fromisoformat(args.from_date)
    to_date = date.fromisoformat(args.to_date)
    leagues = [item.strip() for item in args.leagues.split(",") if item.strip()]
    result = BettingPipeline().run(from_date, to_date, leagues, persist=not args.no_db)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
