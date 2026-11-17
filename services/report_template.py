"""Responsive report template: immutable historical values, compact cards, audit-only JSON."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
import hashlib,html,json
from services.report_labels import spanish_market

def esc(x):return html.escape(str(x if x is not None else ''))
def lima(x):
    try:return datetime.fromisoformat(x.replace('Z','+00:00')).astimezone(ZoneInfo('America/Lima')).strftime('%d/%m/%Y · %H:%M:%S')
    except (ValueError,AttributeError):return 'No registrada'
def number(x):return '—' if x is None else f'{x:.2f}'

def _fresh(m,source,now):
    # Display gate only: never renew clocks, mutate data or choose another quote.
    odds=m.get('odds_api',m.get('odds')) if source=='API' else m.get('odds_betano')
    if not isinstance(odds,(int,float)) or isinstance(odds,bool) or odds<=1:return False
    if m.get('quote_type')=='promotional' or (source=='Betano' and m.get('betano_promotion')):return False
    if m.get('api_fetch_error' if source=='API' else 'betano_fetch_error'):return False
    if source=='Betano' and m.get('betano_http_status',200)>=400:return False
    if source=='Betano' and m.get('betano_source_method')=='assisted_chrome_visible' and not m.get('betano_quote_valid'):return False
    clocks=[m.get('api_captured_at' if source=='API' else 'betano_captured_at')]
    if source=='API':clocks.append(m.get('api_updated_at'))
    try:return all(v and -5<=(now-datetime.fromisoformat(v.replace('Z','+00:00'))).total_seconds()<=600 for v in clocks)
    except (ValueError,TypeError):return False


def _current_selection_view(data,now,automatic=False):
    """Filter only the original selections for display; do not rerun a policy."""
    view=deepcopy(data)
    for r in view.get('results',[]):
        def visible(m):
            if not m:return False
            try:
                if datetime.fromisoformat(r['kickoff_lima'])<=now:return False
            except (ValueError,KeyError):return False
            if any(m.get(k) for k in ['manual_review_required','model_review_required','anomaly_flags']):return False
            if automatic and not .70<m.get('probability',0)<=.95:return False
            source=m.get('selection_quote_source')
            selected_odds=m.get('selection_odds');original_odds=m.get('odds_betano') if source=='Betano' else m.get('odds_api',m.get('odds'))
            return source in ['API','Betano'] and selected_odds==original_odds and _fresh(m,source,now)
        r['recommended_pick']=r.get('recommended_pick') if visible(r.get('recommended_pick')) else None
        r['alternative_picks']=[m for m in r.get('alternative_picks',[]) if visible(m)] if r['recommended_pick'] else []
    return view


def render_report(data,path,title,*,now=None):
    now=now or datetime.now(timezone.utc);original=json.dumps(data,sort_keys=True,ensure_ascii=False)
    current=_current_selection_view(data,now);automatic=_current_selection_view(data,now,automatic=True)
    all_markets=[]
    for r in data.get('results',[]):all_markets.extend(r.get('all_markets',[]))
    current_quote_count=sum(_fresh(m,source,now) for m in all_markets for source in ['API','Betano'])
    api_count=sum(m.get('odds_api',m.get('odds')) is not None or (m.get('api_quote_observation') or {}).get('odds') is not None for m in all_markets)
    betano_count=sum(m.get('odds_betano') is not None or (m.get('betano_quote_observation') or {}).get('odds') is not None for m in all_markets)
    def selection(m,role,historical,r,t60=False):
        source=m.get('selection_quote_source');house=m.get('selection_bookmaker') or ('Betano' if source=='Betano' else m.get('bookmaker_api') or m.get('bookmaker'))
        price=m.get('selection_odds');capture=m.get('selection_quote_captured_at') or m.get('betano_captured_at' if source=='Betano' else 'api_captured_at')
        expiry=''
        if capture:
            clocks=[datetime.fromisoformat(capture.replace('Z','+00:00'))+timedelta(seconds=600)]
            if source=='API' and m.get('api_updated_at'):clocks.append(datetime.fromisoformat(m['api_updated_at'].replace('Z','+00:00'))+timedelta(seconds=600))
            clocks.append(datetime.fromisoformat(r['kickoff_lima']))
            if t60:clocks.append(datetime.fromisoformat(r['kickoff_lima'])-timedelta(minutes=45))
            expiry=min(clocks).isoformat()
        state='Histórica · no vigente' if historical else 'TTL abierto al verificar; sin consulta en vivo'
        provenance='Chrome asistido' if source=='Betano' and m.get('betano_source_method')=='assisted_chrome_visible' else 'Betano · método según auditoría' if source=='Betano' else 'API-Football' if source=='API' else 'No registrada'
        trace='<p class="small">Captura individual Perú: '+esc(lima(capture))+'. Revalidar antes de usar.</p>'
        if source=='API':trace+='<p class="small">Actualización del proveedor Perú: '+esc(lima(m.get('api_updated_at')))+'</p>'
        url=m.get('betano_source_url') if source=='Betano' else None
        if url and url.startswith('https://'):trace+='<p class="small"><a href="'+esc(url)+'" rel="noopener">Página de origen de la cuota</a></p>'
        return '<div class="selection '+('principal' if role=='Principal' else 'alternative')+'" '+('data-live-expiry="'+esc(expiry)+'"' if not historical else '')+'><div class="selection-heading"><b>'+esc(role+(' al corte' if historical else ''))+'</b><span class="badge">'+esc(state)+'</span></div><h3>'+esc(spanish_market(m['key']))+'</h3><dl><div><dt>Probabilidad estimada</dt><dd>'+f"{m.get('probability',0):.1%}"+'</dd></div><div><dt>Casa / fuente</dt><dd>'+esc(house)+' · '+esc(provenance)+'</dd></div><div><dt>Cuota '+('histórica' if historical else 'al verificar')+'</dt><dd>'+number(price)+'</dd></div></dl>'+trace+'</div>'
    def cards(dataset,*,historical=False,t60=False):
        content=[]
        for r in dataset.get('results',[]):
            minutes=(datetime.fromisoformat(r['kickoff_lima'])-now).total_seconds()/60 if r.get('kickoff_lima') else -1
            pick=r.get('recommended_pick');alts=r.get('alternative_picks',[])
            if t60 and not 45<=minutes<=60:pick=None;alts=[]
            if not historical and not pick:continue
            choices=selection(pick,'Principal',historical,r,t60) if pick else '<p class="no-bet"><b>Sin apuesta'+(' al corte' if historical else '')+'.</b></p>'
            choices+=''.join(selection(m,'Alternativa',historical,r,t60) for m in alts)
            reasons=r.get('model_quality_review_reasons',[])
            warnings=[m for m in r.get('all_markets',[]) if m.get('anomaly_flags') or m.get('manual_review_required')]
            warning='<p class="warning">Alerta: '+str(len(warnings))+' mercados pendientes de revisión; fuera de selección.</p>' if warnings else ''
            flagged=[(m,f) for m in warnings for f in m.get('anomaly_flags',[])]
            if flagged:
                m,f=max(flagged,key=lambda pair:pair[1].get('estimated_ev',0))
                warning+='<p class="warning">EV extraordinario histórico: '+esc(spanish_market(m['key']))+' · '+esc(f['source'])+' · cuota '+number(f['odds'])+' · EV aritmético '+f"{f['estimated_ev']:+.2%}"+'. Revisión pendiente; fuera de principales, alternativas y avisos. Guarda provisional p×cuota ≥1,75, no optimizada.</p>'
            if reasons:warning+='<p class="warning">Modelo en revisión: '+esc('; '.join(reasons))+'</p>'
            content.append('<article class="match-card"><div class="match-heading"><h2>'+esc(r.get('match'))+'</h2><time>'+esc(lima(r.get('kickoff_lima'))) +' Perú</time></div><p class="small">'+esc(r.get('league'))+' · '+esc(r.get('fixture_status'))+'</p>'+warning+choices+'</article>')
        return ''.join(content) or '<p class="no-bet">Sin apuesta. No hay selecciones con cuota vigente que cumplan las guardas.</p>'
    market_details=[]
    for r in data.get('results',[]):
        trs=[]
        for m in sorted(r.get('all_markets',[]),key=lambda m:m.get('probability',0),reverse=True):
            fields=[spanish_market(m['key']),f"{m.get('probability',0):.1%}",m.get('bookmaker_api') or m.get('bookmaker') or '—',number(m.get('odds_api',m.get('odds'))),number(m.get('odds_betano')),'Revisión pendiente' if m.get('anomaly_flags') or m.get('manual_review_required') else m.get('selection_role','Solo análisis')]
            trs.append('<tr>'+''.join('<td>'+esc(x)+'</td>' for x in fields)+'</tr>')
        market_details.append('<details><summary>'+esc(r['match'])+' · '+str(len(trs))+' mercados históricos</summary><div class="tablewrap"><table><thead><tr><th>Mercado</th><th>Probabilidad</th><th>Book API-Football</th><th>Cuota API-Football</th><th>Cuota Betano</th><th>Estado al corte</th></tr></thead><tbody>'+''.join(trs)+'</tbody></table></div></details>')
    # Only sporting forecast/audit fields; no databases, credentials, tickets or operational paths.
    market_fields=['key','market','probability','push_probability','fair_odds','odds_api','odds','odds_betano','ev_api','ev_betano','bookmaker_api','bookmaker','betano_source_method','betano_source_url','betano_captured_at','api_captured_at','api_updated_at','api_quote_observation','betano_quote_observation','selection_odds','selection_bookmaker','selection_quote_source','selection_quote_captured_at','selection_role','selection_reasons','anomaly_flags','manual_review_required','model_review_required']
    audit={'schema':'sporting-report-audit-v1','original_cutoff':data.get('generated_at'),'model_version':data.get('model_version'),'policy_version':data.get('selection_policy'),'historical_selections':[{'fixture_id':r['match_id'],'principal_key':(r.get('recommended_pick') or {}).get('key'),'alternative_keys':[m['key'] for m in r.get('alternative_picks',[])]} for r in data.get('results',[])],'matches':[]}
    for r in data.get('results',[]):audit['matches'].append({'fixture_id':r['match_id'],'match':r['match'],'kickoff_peru':r.get('kickoff_lima'),'model_audit':r.get('model_audit',{}),'markets':[{k:m[k] for k in market_fields if k in m} for m in r.get('all_markets',[])]})
    path=Path(path);audit_name=path.stem+'_auditoria.json';audit_raw=json.dumps(audit,ensure_ascii=False,indent=2);(path.parent/audit_name).write_text(audit_raw,encoding='utf-8',newline='\n')
    metadata={'original_cutoff':data.get('generated_at'),'view_generated_at':now.isoformat(),'forecast_sha256':hashlib.sha256(original.encode()).hexdigest(),'audit_file':audit_name,'note':'La generación de la vista no renueva las capturas ni altera probabilidades.'}
    tabs=[('partidos','Partidos · histórico'),('manual','Manuales'),('t60','T−60'),('mercados','Mercados'),('auditoria','Auditoría')]
    nav=''.join('<button type="button" class="tab" role="tab" id="tab-'+k+'" aria-controls="panel-'+k+'" aria-selected="'+('true' if i==0 else 'false')+'" tabindex="'+('0' if i==0 else '-1')+'" data-target="'+k+'">'+label+'</button>' for i,(k,label) in enumerate(tabs))
    content={'partidos':'<p class="warning">Reporte histórico: las selecciones siguientes pertenecen al archivo fuente. No son oportunidades actuales.</p>'+cards(data,historical=True),
        'manual':'<h2>Candidatos manuales</h2><p>Cuota verificable, muestra propia ≥6, EV ≥2%, probabilidad provisional 55–95% y sin revisiones pendientes.</p><div data-current-candidates>'+cards(current)+'</div>',
        't60':'<h2>Oportunidades T−60</h2><p>Ventana T−60 a T−45, probabilidad >70%, techo 95% y demás guardas. Sin activar tareas ni envíos.</p><div data-current-candidates>'+cards(automatic,t60=True)+'</div>',
        'mercados':'<h2>Todos los mercados históricos</h2><p>Probabilidades y cuotas del corte original, en orden descendente de probabilidad. Sin actualización en vivo.</p>'+''.join(market_details),
        'auditoria':'<h2>Auditoría</h2><p>Las probabilidades no tienen calibración validada. Las anomalías y abstenciones se conservan.</p><details id="audit-json"><summary>JSON de auditoría · cerrado por defecto</summary><p><a href="'+esc(audit_name)+'" download>Descargar JSON de auditoría completo</a></p><pre>'+esc(json.dumps(metadata,ensure_ascii=False,indent=2))+'</pre></details><details><summary>Auditoría del modelo: últimos partidos usados y comparabilidad</summary>'+''.join('<details><summary>'+esc(r['match'])+'</summary><pre>'+esc(json.dumps(r.get('model_audit',{}),ensure_ascii=False,indent=2))+'</pre></details>' for r in data.get('results',[]))+'</details>'}
    panels=''.join('<section class="panel" id="panel-'+k+'" role="tabpanel" aria-labelledby="tab-'+k+'" '+('hidden' if i else '')+'>'+content[k]+'</section>' for i,(k,_) in enumerate(tabs))
    css='''*{box-sizing:border-box}body{margin:0;background:#0c1422;color:#e9f0fa;font:15px/1.5 system-ui,sans-serif}a{color:#8acbff}header{position:static;max-width:1160px;margin:auto;padding:28px 22px 18px}h1{font-size:clamp(23px,4vw,34px);margin:0 0 12px}h2{font-size:19px;margin:0}h3{font-size:17px;margin:8px 0}p{margin:9px 0}.badge{font-size:12px;border:1px solid #67798c;border-radius:20px;padding:3px 9px;display:inline-block}.small,dt,time{font-size:13px;color:#b2c2d5}.coverage{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:18px}.coverage div,.match-card{border:1px solid #334358;background:#142135;border-radius:12px;padding:16px}.coverage b{display:block;font-size:24px}.tab-shell{position:sticky;top:0;z-index:10;background:#0c1422;border-block:1px solid #334358}.tabs{max-width:1160px;margin:auto;display:flex;flex-wrap:nowrap;gap:8px;padding:10px 18px;overflow-x:auto;scrollbar-width:thin}.tab{flex:0 0 auto;width:auto;min-width:0;white-space:nowrap;border:1px solid #52677f;border-radius:18px;padding:8px 14px;color:#dfeafa;background:#1a2b42;cursor:pointer;font:inherit}.tab[aria-selected=true]{background:#d8e9ff;color:#142135;border-color:#d8e9ff}.tab:focus-visible,summary:focus-visible{outline:3px solid #ffcf70;outline-offset:2px}main{max-width:1160px;margin:auto;padding:20px 22px 50px}.panel{scroll-margin-top:76px}.panel[hidden],[hidden]{display:none!important}.match-card{margin:14px 0;overflow-wrap:anywhere}.match-heading{display:flex;justify-content:space-between;gap:14px;align-items:baseline}.selection{margin-top:12px;padding:14px;border-radius:10px;background:#1b2d44}.selection.principal{border-left:5px solid #e8c16a;background:#263247}.selection.alternative{margin-left:18px;border-left:3px solid #667f9d}.selection-heading{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}dl{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:8px 0}dd{margin:2px 0;font-weight:650;overflow-wrap:anywhere}.warning{border-left:4px solid #e9b95f;padding:10px 13px;background:#302b23;color:#ffe0a1}.no-bet{padding:16px;border:1px dashed #718297;border-radius:9px}details{border:1px solid #334358;border-radius:9px;padding:13px;margin:12px 0}summary{cursor:pointer;font-weight:650}details:not([open])>:not(summary){display:none}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.5 ui-monospace,monospace;max-height:480px;overflow:auto}.tablewrap{overflow-x:auto;max-width:100%}table{border-collapse:collapse;min-width:730px;width:100%;font-size:13px}td,th{text-align:left;border-bottom:1px solid #334358;padding:9px;vertical-align:top}th{position:static;background:#1a2b42}footer{max-width:1160px;margin:auto;padding:20px;color:#b2c2d5}@media(max-width:600px){header{padding:20px 14px 14px}.coverage{grid-template-columns:repeat(2,minmax(0,1fr))}.coverage div{padding:11px}main{padding:16px 14px 40px}.tabs{padding-inline:14px}.match-heading{display:block}.match-heading time{display:block;margin-top:5px}dl{grid-template-columns:1fr;gap:7px}.selection.alternative{margin-left:8px}.match-card{padding:13px}}'''
    script='''const tabs=[...document.querySelectorAll('[role=tab]')];function activate(t){tabs.forEach(b=>{const on=b===t;b.setAttribute('aria-selected',on);b.tabIndex=on?0:-1;document.getElementById(b.getAttribute('aria-controls')).hidden=!on;});t.scrollIntoView({block:'nearest',inline:'nearest'});}tabs.forEach((t,i)=>{t.addEventListener('click',()=>activate(t));t.addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();let j=e.key==='Home'?0:e.key==='End'?tabs.length-1:(i+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;activate(tabs[j]);tabs[j].focus();}});});function expire(){document.querySelectorAll('[data-current-candidates]').forEach(g=>{g.querySelectorAll('[data-live-expiry]').forEach(s=>{s.hidden=!Number.isFinite(Date.parse(s.dataset.liveExpiry))||Date.now()>Date.parse(s.dataset.liveExpiry);});g.querySelectorAll('.match-card').forEach(c=>{c.hidden=!c.querySelector('.selection:not([hidden])');});if(!g.querySelector('.match-card:not([hidden])')&&!g.querySelector('.no-bet')){g.insertAdjacentHTML('beforeend','<p class="no-bet">Sin apuesta: las capturas vencieron o se cerró la ventana.</p>');}});}expire();setInterval(expire,1000);'''
    date=data.get('date_lima_filter') or data.get('from_date') or 'Ver partidos';state='Reporte histórico' if current_quote_count==0 else 'Foto al corte · revalidar individualmente'
    page='<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(title)+'</title><style>'+css+'</style></head><body data-report-matches="'+str(len(data.get('results',[])))+'" data-report-markets="'+str(len(all_markets))+'"><header><h1>'+esc(title)+'</h1><p>Fecha de partidos: <b>'+esc(date)+'</b> · Hora de corte Perú: <b>'+esc(lima(data.get('generated_at')))+'</b></p><span class="badge" id="report-state">'+state+'</span><p class="small">El análisis y esta vista no renuevan ninguna captura. Las cuotas pueden moverse; revalidar antes de usar.</p><div class="coverage">'+''.join('<div><b>'+str(n)+'</b><span>'+label+'</span></div>' for n,label in [(len(data.get('results',[])),'Partidos'),(len(all_markets),'Mercados'),(api_count,'Observaciones API históricas'),(betano_count,'Observaciones Betano históricas')])+'</div><p class="small">Cuotas dentro del TTL al generar esta vista: '+str(current_quote_count)+'. No es una consulta en vivo.</p></header><div class="tab-shell"><nav class="tabs" role="tablist" aria-label="Vistas del protocolo">'+nav+'</nav></div><main>'+panels+'</main><footer>Vista del reporte · Modelo '+esc(data.get('model_version'))+' · No calibrado prospectivamente. El modelo experimental no está activado.</footer><script>'+script+'</script></body></html>'
    path.write_text(page,encoding='utf-8',newline='\n');assert json.dumps(data,sort_keys=True,ensure_ascii=False)==original
    return {'html':str(path),'audit_json':str(path.parent/audit_name),'source_unchanged':True}
