from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
RUNS = ROOT / "protocol" / "runs"
OUTPUTS = ROOT / "outputs"
REPORTS = ROOT / "reports"
SITE = ROOT / "site"
PUBLIC_BASE = "https://ze-martin.github.io/reports"


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(command))
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if check and completed.returncode != 0:
        print(completed.stdout)
        completed.check_returncode()
    return completed


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def date_range(start: date, end: date) -> list[date]:
    days: list[date] = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def find_latest_json(prefix: str) -> Path:
    files = sorted(RUNS.glob(f"{prefix}_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"No se encontró JSON generado con prefijo {prefix}")
    return files[0]


def load_matches(path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    return int(data.get("matches") or len(data.get("results", [])))


def generate_base(day: date, leagues: str) -> Path:
    day_text = day.isoformat()
    next_day = (day + timedelta(days=1)).isoformat()
    compact = day.strftime("%Y%m%d")
    prefix = f"protocol_world_cup_{compact}_full"
    result = run(
        [
            sys.executable,
            "tools\\generate_protocol_probabilities.py",
            "--from",
            day_text,
            "--to",
            next_day,
            "--leagues",
            leagues,
            "--date-lima",
            day_text,
            "--output-dir",
            "protocol\\runs",
            "--name",
            prefix,
        ]
    )
    print(result.stdout)
    return find_latest_json(prefix)


def enrich_betano(source: Path, day: date, python_bin: str | None) -> Path:
    compact = day.strftime("%Y%m%d")
    output = RUNS / f"protocol_world_cup_{compact}_full_betano.json"
    executable = python_bin or sys.executable
    result = run(
        [
            executable,
            "tools\\enrich_protocol_with_betano.py",
            "--source",
            str(source),
            "--output",
            str(output),
        ]
    )
    print(result.stdout)
    return output


def export_report(source: Path, day: date) -> tuple[Path, Path]:
    compact = day.strftime("%Y%m%d")
    result = run(
        [
            sys.executable,
            "tools\\export_protocol_html.py",
            "--source",
            str(source),
            "--date",
            day.isoformat(),
            "--prefix",
            f"protocolo_{compact}_pc",
            "--output-dir",
            "outputs",
        ]
    )
    print(result.stdout)
    html = OUTPUTS / f"protocolo_{compact}_pc.html"
    csv = OUTPUTS / f"protocolo_{compact}_pc_todos_los_mercados.csv"
    return html, csv


def build_pages() -> None:
    result = run([sys.executable, "tools\\build_pages_site.py"])
    print(result.stdout)
    shutil.copy2(SITE / "index.html", ROOT / "index.html")
    shutil.copy2(SITE / "latest.html", ROOT / "latest.html")
    REPORTS.mkdir(exist_ok=True)
    for source in (SITE / "reports").glob("*"):
        if source.is_file():
            shutil.copy2(source, REPORTS / source.name)


def validate_html(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "Cuota Betano" not in text:
        raise RuntimeError(f"El HTML no contiene la columna Cuota Betano: {path}")


def save_run_to_database(
    *,
    day: date,
    base_json: Path,
    enriched_json: Path,
    html_path: Path,
    csv_path: Path,
    commit: str | None = None,
) -> None:
    compact = day.strftime("%Y%m%d")
    data = json.loads(enriched_json.read_text(encoding="utf-8"))
    public_html_url = f"{PUBLIC_BASE}/protocolo_{compact}_pc.html"
    public_csv_url = f"{PUBLIC_BASE}/protocolo_{compact}_pc_todos_los_mercados.csv"
    try:
        from db.local_protocol_store import LocalProtocolStore

        local = LocalProtocolStore()
        local.initialize()
        local.seed_agent_memory()
        stats = local.save_protocol_run(
            report_date=day,
            protocol_json=data,
            source_json=base_json,
            enriched_json=enriched_json,
            html_path=html_path,
            csv_path=csv_path,
            public_html_url=public_html_url,
            public_csv_url=public_csv_url,
            published_commit=commit,
        )
        print(f"SQLite guardada {day.isoformat()}: {stats}")
    except Exception as exc:
        print(f"AVISO: no se pudo guardar en SQLite local: {exc}")

    try:
        from db.database import Database

        db = Database()
        db.initialize()
        db.seed_agent_memory()
        stats = db.save_protocol_run(
            report_date=day,
            protocol_json=data,
            source_json=base_json,
            enriched_json=enriched_json,
            html_path=html_path,
            csv_path=csv_path,
            public_html_url=public_html_url,
            public_csv_url=public_csv_url,
            published_commit=commit,
        )
        print(f"DB guardada {day.isoformat()}: {stats}")
    except Exception as exc:
        print(f"AVISO: no se pudo guardar en PostgreSQL: {exc}")


def update_database_commit(days: list[date], commit: str) -> None:
    try:
        from db.local_protocol_store import LocalProtocolStore

        local = LocalProtocolStore()
        local.initialize()
        local.seed_agent_memory()
        for day in days:
            local.update_protocol_report_commit(day, commit)
    except Exception as exc:
        print(f"AVISO: no se pudo actualizar commit en SQLite local: {exc}")

    try:
        from db.database import Database

        db = Database()
        db.initialize()
        db.seed_agent_memory()
        for day in days:
            db.update_protocol_report_commit(day, commit)
    except Exception as exc:
        print(f"AVISO: no se pudo actualizar commit en PostgreSQL: {exc}")


def publish(days: list[date], message: str | None) -> str:
    build_pages()
    add_paths = [
        "index.html",
        "latest.html",
        "tools\\enrich_protocol_with_betano.py",
        "tools\\export_protocol_html.py",
        "tools\\run_published_protocol.py",
    ]
    for day in days:
        compact = day.strftime("%Y%m%d")
        add_paths.extend(
            [
                f"outputs\\protocolo_{compact}_pc.html",
                f"outputs\\protocolo_{compact}_pc_todos_los_mercados.csv",
                f"reports\\protocolo_{compact}_pc.html",
                f"reports\\protocolo_{compact}_pc_todos_los_mercados.csv",
            ]
        )
    run(["git", "add", *add_paths])
    commit_msg = message or f"Publicar protocolos Mundial {', '.join(day.isoformat() for day in days)}"
    commit = run(["git", "commit", "-m", commit_msg], check=False)
    print(commit.stdout)
    if commit.returncode != 0 and "nothing to commit" not in commit.stdout.lower():
        raise RuntimeError("No se pudo crear commit")
    pull = run(["git", "pull", "--rebase", "origin", "main"], check=False)
    print(pull.stdout)
    if pull.returncode != 0:
        raise RuntimeError("git pull --rebase falló. Resolver conflictos y repetir push.")
    push = run(["git", "push", "origin", "main"])
    print(push.stdout)
    rev = run(["git", "rev-parse", "--short", "HEAD"])
    return rev.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera protocolo, Betano, HTML/CSV y opcionalmente publica en GitHub Pages.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dates", help="Fechas separadas por coma. Ej: 2026-07-10,2026-07-11")
    group.add_argument("--from", dest="from_date", help="Fecha inicial YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", help="Fecha final YYYY-MM-DD cuando se usa --from")
    parser.add_argument("--leagues", default="1", help="Ligas API-Football. Mundial = 1")
    parser.add_argument("--betano-python", help="Python alternativo con Playwright instalado")
    parser.add_argument("--publish", action="store_true", help="Publica en GitHub Pages con commit/push")
    parser.add_argument("--no-db", action="store_true", help="No guarda memoria ni resultados en PostgreSQL")
    parser.add_argument("--commit-message", help="Mensaje de commit si se usa --publish")
    args = parser.parse_args()

    if args.dates:
        days = [parse_date(item.strip()) for item in args.dates.split(",") if item.strip()]
    else:
        start = parse_date(args.from_date)
        end = parse_date(args.to_date or args.from_date)
        days = date_range(start, end)

    generated: list[dict[str, str | int]] = []
    days_with_reports: list[date] = []

    for day in days:
        print(f"\n=== Protocolo {day.isoformat()} ===")
        base_json = generate_base(day, args.leagues)
        matches = load_matches(base_json)
        if matches == 0:
            print(f"Sin partidos para {day.isoformat()}; no se genera HTML vacío.")
            generated.append({"date": day.isoformat(), "matches": 0, "base_json": str(base_json)})
            continue
        enriched_json = enrich_betano(base_json, day, args.betano_python)
        html_path, csv_path = export_report(enriched_json, day)
        validate_html(html_path)
        if not args.no_db:
            save_run_to_database(
                day=day,
                base_json=base_json,
                enriched_json=enriched_json,
                html_path=html_path,
                csv_path=csv_path,
            )
        generated.append(
            {
                "date": day.isoformat(),
                "matches": matches,
                "json": str(enriched_json),
                "html": str(html_path),
                "csv": str(csv_path),
            }
        )
        days_with_reports.append(day)

    commit = ""
    if args.publish and days_with_reports:
        commit = publish(days_with_reports, args.commit_message)
        if not args.no_db:
            update_database_commit(days_with_reports, commit)

    print("\n=== Resumen ===")
    print(json.dumps({"generated": generated, "published_commit": commit}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
