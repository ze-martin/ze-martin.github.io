"""Freeze existing reports and settle supported picks against API-Football."""
import argparse
import json
import sqlite3
import sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import load_environment
from apis.football_api import FootballAPI
from db.performance_store import PerformanceStore
from analysis.settlement import grade
from analysis.calibration import temporal_diagnostic


def update(start,end):
    store=PerformanceStore();store.initialize()
    with sqlite3.connect(ROOT/'data/protocol_memory.sqlite') as c:
        reports=c.execute('SELECT report_date,enriched_json FROM protocol_report WHERE report_date BETWEEN ? AND ? ORDER BY report_date',(start,end)).fetchall()
    for day,path in reports:
        data=json.loads(Path(path).read_text(encoding='utf-8'))
        store.freeze(data,day,'recovered_latest_version')
    api=FootballAPI();api.cache_enabled=False
    fixture_cache={};stat_cache={};errors=[]
    for row in store.pending():
        if not start<=row['report_date']<=end:continue
        try:
            day=row['report_date']
            if day not in fixture_cache:
                payload=api._api_get('fixtures',{'date':day,'timezone':'America/Lima'})
                if payload.get('errors'):raise ValueError(str(payload['errors']))
                fixture_cache[day]={str(f['fixture']['id']):f for f in payload.get('response',[])}
            fixture=fixture_cache[day].get(row['fixture_id'])
            if not fixture:
                payload=api._api_get('fixtures',{'id':row['fixture_id']})
                fixture=next(iter(payload.get('response',[])),None)
            if not fixture:continue
            kickoff=datetime.fromisoformat(fixture['fixture']['date'].replace('Z','+00:00'))
            if datetime.fromisoformat(row['generated_at'].replace('Z','+00:00'))>=kickoff:
                errors.append({'pick_id':row['id'],'reason':'Snapshot posterior al inicio; no liquidado como prepartido'})
                continue
            statistics=None
            if row['market_key'].startswith(('CORNERS_','SHOTS_')) and fixture['fixture']['status']['short']=='FT':
                if row['fixture_id'] not in stat_cache:
                    stat_cache[row['fixture_id']]=api._api_get('fixtures/statistics',{'fixture':row['fixture_id']}).get('response',[])
                statistics=stat_cache[row['fixture_id']]
            outcome=grade(row['market_key'],fixture,statistics)
            if outcome:
                store.settle(row['id'],outcome,{'fixture_id':row['fixture_id'],'status':fixture['fixture']['status']['short'],
                                               'score':fixture.get('score'),'statistics':statistics,'period':'90 minutes; no extra time'})
        except Exception as exc:
            errors.append({'pick_id':row['id'],'reason':str(exc)[:200]})
    result=store.public_summary()
    groups={}
    for row in store.rows():groups.setdefault(row['model_version'],[]).append(row)
    result['calibration_diagnostics']={version:temporal_diagnostic(rows) for version,rows in groups.items()}
    result['errors']=errors
    output=ROOT/'outputs/performance_summary.json'
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    try:store.mirror_postgres();print('Auditoría sincronizada con PostgreSQL')
    except Exception as exc:print('AVISO PostgreSQL: '+str(exc)[:180])
    print(json.dumps(result,ensure_ascii=False))
    return result


if __name__=='__main__':
    load_environment()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from',dest='start',required=True)
    parser.add_argument('--to',dest='end',required=True)
    args=parser.parse_args()
    update(args.start,args.end)
