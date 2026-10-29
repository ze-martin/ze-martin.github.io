import argparse
import json
import sys
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import load_environment
from apis.football_api import FootballAPI
from services.player_markets import build_player_options,enrich_availability


def enrich(source,output,availability_only=False):
    api=FootballAPI();api.cache_enabled=False
    data=json.loads(source.read_text(encoding='utf-8'))
    for r in data.get('results',[]):
        if r.get('pre_match_eligible') is False:continue
        try:
            if availability_only:
                enrich_availability(api,r['match_id'],(r.get('player_analysis') or {}).get('options',[]))
                continue
            payload=api._api_get('fixtures',{'id':r['match_id']})
            fixture=next(iter(payload.get('response',[])),None)
            if not fixture:raise ValueError('Fixture no disponible')
            if fixture['fixture']['status']['short']!='NS':
                r['player_analysis']={'options':[],'warnings':['Partido iniciado o no pendiente; no se generan recomendaciones individuales']}
                continue
            r['player_analysis']=build_player_options(api,fixture)
            print(r['match'],len(r['player_analysis']['options']),'opciones de observación',flush=True)
        except Exception as exc:
            r['player_analysis']={'options':[],'warnings':[str(exc)[:200]]}
    data['players_fetched_at']=datetime.now(timezone.utc).isoformat()
    output.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    load_environment();p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--availability-only',action='store_true')
    args=p.parse_args();enrich(args.source,args.output,args.availability_only)
