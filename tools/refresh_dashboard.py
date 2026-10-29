"""Re-export the two current reports without recalculating historical forecasts."""
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from datetime import date
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import load_environment
from analysis.policy import apply_policy
from tools.run_published_protocol import save_run_to_database,build_pages
from tools.update_performance import update
from services.player_markets import deduplicate_quotes


def refresh():
    with sqlite3.connect(ROOT/'data/protocol_memory.sqlite') as c:
        reports=c.execute('SELECT report_date,source_json,enriched_json,html_path,csv_path FROM protocol_report ORDER BY report_date DESC LIMIT 2').fetchall()
    for day,base,source,html,csv in reports:
        path=Path(source)
        data=apply_policy(json.loads(path.read_text(encoding='utf-8')))
        for r in data.get('results',[]):
            deduplicate_quotes((r.get('player_analysis') or {}).get('options',[]))
            if r.get('pre_match_eligible') is False:
                r['betano_coverage_status']='Fuera del análisis prepartido; Betano no consultado'
        path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        command=[sys.executable,str(ROOT/'tools/export_protocol_html.py'),'--source',str(path),'--date',day,
                 '--prefix',Path(html).stem,'--output-dir',str(ROOT/'outputs')]
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
        if result.returncode:raise RuntimeError(result.stdout+result.stderr)
        save_run_to_database(day=date.fromisoformat(day),base_json=Path(base),enriched_json=path,
                             html_path=Path(html),csv_path=Path(csv))
        print('Actualizado',day,flush=True)
    update('2026-10-22',max(r[0] for r in reports))
    build_pages()


if __name__=='__main__':
    load_environment();refresh()
