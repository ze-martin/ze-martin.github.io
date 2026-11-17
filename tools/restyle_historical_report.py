"""Presentation-only export from an immutable snapshot; no API, DB or selection calls."""
import argparse,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.report_template import render_report

def restyle(source,output,backup_dir):
    source=Path(source);output=Path(output);backup_dir=Path(backup_dir)
    raw=source.read_bytes();data=json.loads(raw)
    backup_dir.mkdir(parents=True,exist_ok=True);output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():
        backup=backup_dir/output.name
        if backup.exists() and backup.read_bytes()!=output.read_bytes():raise ValueError('Respaldo existente distinto; usar una carpeta nueva')
        backup.write_bytes(output.read_bytes())
    frozen=json.dumps(data,sort_keys=True,ensure_ascii=False)
    render_report(data,output,'Protocolo 17/11/2026 · reporte histórico')
    assert source.read_bytes()==raw and json.dumps(data,sort_keys=True,ensure_ascii=False)==frozen
    audit=json.loads(output.with_name(output.stem+'_auditoria.json').read_text(encoding='utf-8'))
    original={(str(r['match_id']),m['key']):(m['probability'],m.get('odds_api'),m.get('odds_betano'),m.get('api_captured_at'),m.get('api_updated_at'),m.get('betano_captured_at')) for r in data['results'] for m in r['all_markets']}
    visible={(str(r['fixture_id']),m['key']):(m['probability'],m.get('odds_api'),m.get('odds_betano'),m.get('api_captured_at'),m.get('api_updated_at'),m.get('betano_captured_at')) for r in audit['matches'] for m in r['markets']}
    assert original==visible
    assert audit['historical_selections']==[{'fixture_id':r['match_id'],'principal_key':(r.get('recommended_pick') or {}).get('key'),'alternative_keys':[m['key'] for m in r.get('alternative_picks',[])]} for r in data['results']]
    return {'source_sha256':hashlib.sha256(raw).hexdigest(),'source_unchanged':True,'matches':len(data['results']),'markets':len(original),'principals':sum(bool(r.get('recommended_pick')) for r in data['results']),'alternatives':sum(len(r.get('alternative_picks',[])) for r in data['results']),'data_and_selections_unchanged':True}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True);p.add_argument('--backup-dir',required=True);a=p.parse_args()
    print(json.dumps(restyle(a.source,a.output,a.backup_dir),ensure_ascii=False))
