from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.local_protocol_store import LocalProtocolStore

RUNS = ROOT / "protocol" / "runs"
OUTPUTS = ROOT / "outputs"
PUBLIC_BASE = "https://ze-martin.github.io/reports"


def date_from_name(path: Path) -> str | None:
    match = re.search(r"20\d{6}", path.name)
    if not match:
        return None
    raw = match.group(0)
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga protocolos existentes en la memoria SQLite local.")
    parser.add_argument("--runs-dir", default=str(RUNS))
    parser.add_argument("--pattern", default="protocol_world_cup_*_betano.json")
    args = parser.parse_args()

    store = LocalProtocolStore()
    store.initialize()
    store.seed_agent_memory()

    loaded = []
    for path in sorted(Path(args.runs_dir).glob(args.pattern)):
        day_text = date_from_name(path)
        if not day_text:
            continue
        day = datetime.strptime(day_text, "%Y-%m-%d").date()
        compact = day.strftime("%Y%m%d")
        data = json.loads(path.read_text(encoding="utf-8"))
        html_path = OUTPUTS / f"protocolo_{compact}_pc.html"
        csv_path = OUTPUTS / f"protocolo_{compact}_pc_todos_los_mercados.csv"
        stats = store.save_protocol_run(
            report_date=day,
            protocol_json=data,
            enriched_json=path,
            html_path=html_path if html_path.exists() else None,
            csv_path=csv_path if csv_path.exists() else None,
            public_html_url=f"{PUBLIC_BASE}/protocolo_{compact}_pc.html",
            public_csv_url=f"{PUBLIC_BASE}/protocolo_{compact}_pc_todos_los_mercados.csv",
        )
        loaded.append({"date": day_text, "path": str(path), **stats})

    print(json.dumps({"sqlite": str(store.path), "loaded": loaded}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
