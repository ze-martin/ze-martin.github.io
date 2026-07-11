from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "protocol" / "runs"
OUTPUTS = ROOT / "outputs"
REPORTS = ROOT / "reports"
SITE = ROOT / "site"


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(command))
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=check,
    )


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


def publish(days: list[date], message: str | None) -> str:
    build_pages()
    add_paths = ["index.html", "latest.html", "tools\\enrich_protocol_with_betano.py", "tools\\export_protocol_html.py"]
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

    print("\n=== Resumen ===")
    print(json.dumps({"generated": generated, "published_commit": commit}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
