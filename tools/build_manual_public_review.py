"""Package an authorized manual revision and restyle an immutable original.

Offline only: no publishing, network, database, Telegram or task activation.
"""
import argparse,csv,hashlib,json,sys
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.report_template import render_report
from tools.export_protocol_html import build_rows,write_csv,build_title
from services.quote_review import observed_quote

def build(manual_source,historical_source,evidence_path,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    manual_source=Path(manual_source);historical_source=Path(historical_source)
    raw=historical_source.read_bytes();old=json.loads(raw)
    newraw=manual_source.read_bytes();new=json.loads(newraw)
    evidence=json.loads(Path(evidence_path).read_text(encoding='utf-8'))
    if evidence['source_sha256']!=hashlib.sha256(raw).hexdigest():raise ValueError('Auditoría de métricas ajena al original')
    compact=new['date_lima_filter'].replace('-','')
    original_name=f'protocolo_{compact}_full_pc'
    revision_name=f'protocolo_{compact}_manual_{new["generated_at"][11:19].replace(":","")}_pc'
    sources=[(original_name,old,evidence['rows']),(revision_name,new,None)]
    excluded=list(new.get('betano_assisted_integration',{}).get('excluded',[]))
    extra=manual_source.parent/'chrome_unmapped.json'
    if extra.exists():excluded+=json.loads(extra.read_text(encoding='utf-8'))
    fields=['match','market','period','line','selection','selection_label','odds','promotion','source_url','captured_at','reason']
    reject_name=revision_name+'_descartes_betano.csv'
    with (output/reject_name).open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(excluded)
    cutoff=datetime.fromisoformat(new['generated_at']).astimezone(ZoneInfo('America/Lima')).strftime('%H:%M:%S')
    for name,data,metrics in sources:
        rows,_,_=build_rows(data)
        write_csv(rows,output/(name+'_todos_los_mercados.csv'))
        path=output/(name+'.html')
        render_report(data,path,build_title(data,new['date_lima_filter']),metric_evidence=metrics)
        # Both independent cuts remain directly accessible; no snapshot is merged.
        links='<p><a href="'+original_name+'.html">Reporte histórico original · tablas restauradas</a> · <a href="'+revision_name+'.html">Nueva prueba manual · corte '+cutoff+' Perú</a></p>'
        if name==revision_name:
            matched=new.get('betano_assisted_integration',{}).get('matched_count',0)
            promotions=sum(bool(x.get('promotion')) for x in excluded)
            unmapped=len(excluded)-promotions
            captured_matches=[r['match'] for r in new['results'] if r.get('betano_source_method')=='assisted_chrome_visible']
            api_observations=[observed_quote(m,'API') for r in new['results'] for m in r.get('all_markets',[]) if observed_quote(m,'API')['odds'] is not None]
            from collections import Counter
            books=', '.join(str(n)+' '+str(b) for b,n in Counter(q['bookmaker'] for q in api_observations).items())
            eligible_api=sum(m.get('odds_api') is not None for r in new['results'] for m in r.get('all_markets',[]))
            links+='<p>Captura Betano verificada únicamente en '+', '.join(captured_matches)+': '+str(matched+len(excluded))+' precios visibles, '+str(matched)+' coincidencias exactas, '+str(promotions)+' promociones y '+str(unmapped)+' sin mapeo utilizable. Los otros partidos no tienen captura Betano nueva. <a href="'+reject_name+'">CSV de promociones y mercados no mapeados</a>.</p>'
            links+='<p>Consulta API: '+books+' observados; '+str(eligible_api)+' elegibles al corte. Las cuotas descartadas conservan el motivo y sus relojes históricos; no se amplía el TTL. Los '+str(len(new.get('previously_started_or_expired',[])))+' encuentros iniciados/finalizados o fuera de hora se detallan en Auditoría.</p>'
        text=path.read_text(encoding='utf-8').replace('</header>',links+'</header>',1)
        path.write_text(text,encoding='utf-8',newline='\n')
    assert historical_source.read_bytes()==raw and manual_source.read_bytes()==newraw
    receipt={'original':original_name,'manual':revision_name,'historical_source_sha256':hashlib.sha256(raw).hexdigest(),'manual_source_sha256':hashlib.sha256(newraw).hexdigest(),'promotions':sum(bool(x.get('promotion')) for x in excluded),'unmapped':sum(not x.get('promotion') for x in excluded),'files':[x.name for x in output.iterdir()]}
    (output/'packaging_receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for x in ['manual-source','historical-source','evidence','output']:p.add_argument('--'+x,required=True,type=Path)
    a=p.parse_args();print(json.dumps(build(a.manual_source,a.historical_source,a.evidence,a.output)))
