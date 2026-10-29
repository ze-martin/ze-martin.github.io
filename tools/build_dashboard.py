"""Build the public, privacy-preserving dashboard from local protocol artifacts."""
import json
import sqlite3
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from analysis.policy import apply_policy


def build(target):
    performance_path=ROOT/'outputs/performance_summary.json'
    performance=json.loads(performance_path.read_text(encoding='utf-8')) if performance_path.exists() else {'groups':[]}
    portable=ROOT/'outputs/dashboard_data.json'
    reports=json.loads(portable.read_text(encoding='utf-8')).get('reports',[]) if portable.exists() else []
    try:
        with sqlite3.connect(f'file:{(ROOT/"data/protocol_memory.sqlite").as_posix()}?mode=ro',uri=True) as conn:
            sources=conn.execute('SELECT report_date,enriched_json,public_html_url FROM protocol_report ORDER BY report_date DESC LIMIT 2').fetchall()
    except sqlite3.Error:
        sources=[]
    local_reports=[]
    for day,path,url in sources:
        if not Path(path).exists():continue
        data=apply_policy(json.loads(Path(path).read_text(encoding='utf-8')))
        local_reports.append({'date':day,'url':url,'results':data.get('results',[]),
                        'version':data.get('model_version','legacy-exact-v1'),'calibration':data['calibration_status']})
    if local_reports:
        reports=local_reports
    public_data={'reports':reports,'performance':performance}
    if local_reports:portable.write_text(json.dumps(public_data,ensure_ascii=False),encoding='utf-8')
    payload=json.dumps(public_data,ensure_ascii=False).replace('<','\\u003c')
    template=Path(__file__).resolve().parents[1]/'dashboard/public.html'
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(template.read_text(encoding='utf-8').replace('__DASHBOARD_DATA__',payload),encoding='utf-8')
    return target


if __name__=='__main__':
    print(build(ROOT/'dashboard.html'))
