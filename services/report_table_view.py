"""Table report. Display validity separately from immutable historical values."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from pathlib import Path
import html,json,hashlib,math
from services.report_labels import spanish_market
from services.quote_review import observed_quote,review_quote
from services.report_template import esc,lima,number,_fresh,_current_selection_view

ADVANCED=('CORNERS','SHOTS','CARDS','FIRST_HALF_TOTALS','PLAYER','WIN_BTTS','CLEAN_SHEET','TOTAL_RANGE')

def probability_view(match,market,evidence=None):
    p=market.get('probability');family=market.get('key','').split(':')[0];audit=match.get('model_audit') or {}
    if p is None or isinstance(p,bool) or not isinstance(p,(int,float)) or not math.isfinite(p) or not 0<=p<=1:return 'Datos insuficientes','No se conserva una probabilidad numérica válida.'
    if evidence:
        return evidence['despues'],'Muestra propia mínima: '+str(evidence['muestra_minima_real'])+'. Nulos sin imputar; familia sin validación temporal.'
    if family.startswith(ADVANCED):
        counts=audit.get('advanced_metric_sample_min',{});own=counts.get(family)
        if own is not None and own<6:return 'Datos insuficientes','Muestra propia de la métrica: '+str(own)+'; mínimo provisional existente: 6.'
        generic='CORNERS' if family.startswith('CORNERS') else 'SHOTS' if family.startswith('SHOTS') else 'CARDS' if family.startswith('CARDS') else family
        bound=(audit.get('advanced_sample_min') or {}).get(generic)
        if own is None and bound is not None and bound<6:return 'Datos insuficientes','Muestra histórica declarada ≤'+str(bound)+'; no acredita observaciones válidas por métrica.'
        return 'Estimación no validada','Sin validación temporal de esta familia'+('; denominador propio no conservado.' if own is None else '; muestra propia: '+str(own)+'.')
    inputs=audit.get('team_inputs',{});samples=[(inputs.get(side) or {}).get('matches') for side in ['home','away']]
    if any(n is not None and n<6 for n in samples):return 'Datos insuficientes','Muestra del modelo de goles menor al mínimo provisional existente.'
    if f'{p:.1%}'=='100.0%':return 'Estimación no validada','El redondeo oculta la distancia a uno; ver el valor histórico en Auditoría.'
    return f'{p:.2%}'.replace('.',','),'Estimación no validada prospectivamente; no es certeza.'

def render_tables(data,path,title,*,now=None,metric_evidence=None):
    now=now or datetime.now(timezone.utc);original=json.dumps(data,ensure_ascii=False,sort_keys=True)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    evidence={(str(x['fixture_id']),x['mercado']):x for x in (metric_evidence or [])}
    def state(r,m):return probability_view(r,m,evidence.get((str(r['match_id']),m['key'])))
    try:cutoff=datetime.fromisoformat(data['generated_at'].replace('Z','+00:00'))
    except (KeyError,ValueError):cutoff=None
    quote_audit=[]
    def odds(m,source):return observed_quote(m,source)['odds']
    def quote(m,source):
        o=observed_quote(m,source)
        ev=m.get('ev_api' if source=='API' else 'ev_betano')
        ev_text=f'{ev:+.2%}'.replace('.',',') if isinstance(ev,(int,float)) else 'No disponible'
        return esc(o.get('bookmaker') or 'No conservado')+'<br><b>'+number(o['odds'])+'</b><br><span class="small">Precio observado HISTÓRICO · no usar para recomendar<br>EV almacenado al corte: '+esc(ev_text)+'<br>Captura Perú: '+esc(lima(o['captured_at']))+'</span>'
    def clocks(o):
        return 'Consulta histórica Perú:<br>'+esc(lima(o['captured_at']))+'<br>Actualización original del proveedor Perú:<br>'+esc(lima(o['provider_updated_at']))
    def discarded(q):
        o=q['observed'];parts=[]
        if o.get('original_discard_reason'):parts.append('<b>Descarte conservado:</b> '+esc(o['original_discard_reason']))
        if q['observed_at_cutoff'] and o['odds'] is not None:
            parts.append('<b>Al corte original:</b> '+esc('; '.join(q['observed_at_cutoff']['reasons']) or 'Dentro de la guarda temporal; sin validar modelo'))
        parts.append('<b>Al verificar esta vista:</b> '+esc('; '.join(q['eligibility']['reasons']) or 'Fuente temporalmente válida; no valida EV/modelo'))
        return '<div class="discard-reason">'+'<br>'.join(parts)+'</div>'
    def eligible(q,m,source):
        if q['eligible_price'] is None:return '<span class="discard-badge">— No elegible</span><br><span class="small">El precio histórico no rellena este campo.<br>EV '+('API-Football' if source=='API' else 'Betano')+': no evaluable como oportunidad.</span>'
        keys=['api_captured_at','api_updated_at'] if source=='API' else ['betano_captured_at']
        expiry=min(datetime.fromisoformat(m[k].replace('Z','+00:00'))+timedelta(seconds=600) for k in keys).isoformat()
        ev=m.get('ev_api' if source=='API' else 'ev_betano')
        ev_text=(f'{ev:+.2%}'.replace('.',',') if isinstance(ev,(int,float)) else 'No disponible')
        return '<span data-price-expiry="'+esc(expiry)+'"><b>'+esc(q['eligible_bookmaker'])+' · '+number(q['eligible_price'])+'</b><br>EV estimado al corte: '+esc(ev_text)+'<br>Elegible por fuente al verificar; no es recomendación.</span>'
    def trace(m):
        a=observed_quote(m,'API');b=observed_quote(m,'Betano');url=b['source_url']
        method='Chrome asistido' if m.get('betano_source_method')=='assisted_chrome_visible' else 'Método Betano según auditoría'
        text='<details class="trace"><summary>Ver fuente y relojes</summary><p>API-Football · '+esc(a['bookmaker'] or 'No conservado')+'<br>Precio observado HISTÓRICO: '+number(a['odds'])+'<br>'+clocks(a)+'</p><p>Betano · '+esc(method)+'<br>Captura histórica Perú: '+esc(lima(b['captured_at']))+'</p>'
        if url and url.startswith('https://'):text+='<a href="'+esc(url)+'" rel="noopener">URL original Betano</a>'
        return text+'<p>Máximo 600 s por fuente. No se renovaron capturas. Revalidar antes de usar.</p></details>'
    def fixture(r):return '<b>'+esc(r.get('match'))+'</b><br><time>'+esc(lima(r.get('kickoff_lima'))) +' Perú</time>'
    def probability(r,m):
        value,reason=state(r,m);return '<b>'+esc(value)+'</b><br><span class="small">'+esc(reason)+'</span>'
    def alerts(m):
        flags=m.get('anomaly_flags') or []
        extra=''
        if flags:
            f=max(flags,key=lambda x:x.get('estimated_ev',0));extra=' · EV aritmético histórico '+f"{f.get('estimated_ev',0):+.2%}".replace('.',',')+' · '+str(f.get('source'))
        return '<br><span class="warning-text">Revisión pendiente; no accionable'+esc(extra)+'</span>' if any(m.get(k) for k in ['manual_review_required','model_review_required','anomaly_flags','alerta_valor']) else ''
    def table(headers,rows,identifier=''):
        return '<div class="tablewrap'+(' market-scroll' if identifier=='all-markets' else '')+'" tabindex="0" aria-label="Tabla desplazable"><table '+('id="'+identifier+'"' if identifier else '')+'><thead><tr>'+''.join('<th scope="col">'+esc(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'
    def selections(dataset,role,include_abstentions=False,live=False,t60=False):
        rows=[]
        for r in dataset.get('results',[]):
            picks=([r['recommended_pick']] if r.get('recommended_pick') else []) if role=='Principal' else r.get('alternative_picks',[])
            if not picks and include_abstentions:
                rows.append('<tr><td>'+fixture(r)+'</td><td colspan="7">Sin apuesta al corte. Sin selección histórica principal.</td></tr>')
            for m in picks:
                source=m.get('selection_quote_source');method='Chrome asistido' if source=='Betano' and m.get('betano_source_method')=='assisted_chrome_visible' else 'API-Football' if source=='API' else 'Betano según auditoría'
                cells=[fixture(r),esc(spanish_market(m['key']))+alerts(m),probability(r,m),quote(m,'API'),quote(m,'Betano'),esc(m.get('selection_bookmaker'))+'<br><b>'+number(m.get('selection_odds'))+'</b><br>'+esc(method),'<span class="badge">Histórica · no vigente</span><br>Captura individual Perú: '+esc(lima(m.get('selection_quote_captured_at'))),trace(m)]
                expiry=''
                if live:
                    clocks=[m.get('selection_quote_captured_at')]
                    if source=='API':clocks.append(m.get('api_updated_at'))
                    ends=[datetime.fromisoformat(x.replace('Z','+00:00'))+timedelta(seconds=600) for x in clocks if x]
                    if r.get('kickoff_lima'):
                        start=datetime.fromisoformat(r['kickoff_lima']);ends.append(start-timedelta(minutes=45) if t60 else start)
                    expiry=' data-live-expiry="'+esc(min(ends).isoformat() if ends else '')+'"'
                rows.append('<tr class="historical-'+role.lower()+'"'+expiry+'>'+''.join('<td>'+x+'</td>' for x in cells)+'</tr>')
        if not rows:return '<p class="empty">Sin apuesta. No hay selecciones en esta vista.</p>'
        rendered=table(['Partido / inicio Perú','Selección histórica','Probabilidad / respaldo','API-Football · observado histórico','Betano · observado histórico','Casa / cuota seleccionada al corte','Vigencia individual','Trazabilidad'],rows)
        return '<div data-current-candidates><p class="live-status" aria-live="polite"></p>'+rendered+'</div>' if live else rendered
    allrows=[];families=set();markets=[]
    for r in data.get('results',[]):
        for m in r.get('all_markets',[]):
            markets.append(m);family=m['key'].split(':')[0];families.add(family)
            api=review_quote(m,'API',now,cutoff);betano=review_quote(m,'Betano',now,cutoff)
            quote_audit.append({'fixture_id':str(r['match_id']),'market':m['key'],'API':api,'Betano':betano})
            cells=[fixture(r),esc(spanish_market(m['key']))+alerts(m)+'<br>'+probability(r,m),esc(api['observed']['bookmaker'] or 'No conservado'),'<b>'+number(api['observed']['odds'])+'</b><br><span class="small">Observado HISTÓRICO; no es precio elegible.</span>',clocks(api['observed']),discarded(api),eligible(api,m,'API'),quote(m,'Betano')+trace(m),eligible(betano,m,'Betano')+discarded(betano)]
            search=(str(r.get('match'))+' '+spanish_market(m['key'])+' '+state(r,m)[0]).lower()
            allrows.append('<tr data-api-observed="'+('1' if api['observed']['odds'] is not None else '0')+'" data-family="'+esc(family)+'" data-search="'+esc(search)+'">'+''.join('<td>'+x+'</td>' for x in cells)+'</tr>')
    players=[]
    for r in data.get('results',[]):
        for p in (r.get('player_analysis') or {}).get('options',[]):
            values=[fixture(r),esc(p.get('player')),esc(p.get('market')),esc(p.get('appearances'))+' partidos · minutos: '+esc(p.get('minutes')),'Estimación no validada · condicionada a minutos','; '.join(esc(q.get('bookmaker'))+' '+number(q.get('odds')) for q in p.get('api_quotes',[])) or 'Sin cuota exacta']
            players.append('<tr>'+''.join('<td>'+v+'</td>' for v in values)+'</tr>')
    market_fields=['key','market','probability','push_probability','fair_odds','odds_api','odds','odds_betano','ev_api','ev_betano','bookmaker_api','bookmaker','betano_source_method','betano_source_url','betano_captured_at','api_captured_at','api_updated_at','api_quote_observation','betano_quote_observation','selection_odds','selection_bookmaker','selection_quote_source','selection_quote_captured_at','selection_role','selection_reasons','anomaly_flags','manual_review_required','model_review_required','sample_min']
    audit={'schema':'sporting-report-audit-v1','original_cutoff':data.get('generated_at'),'model_version':data.get('model_version'),'policy_version':data.get('selection_policy'),'historical_selections':[{'fixture_id':r['match_id'],'principal_key':(r.get('recommended_pick') or {}).get('key'),'alternative_keys':[m['key'] for m in r.get('alternative_picks',[])]} for r in data.get('results',[])],'matches':[{'fixture_id':r['match_id'],'match':r['match'],'kickoff_peru':r.get('kickoff_lima'),'model_audit':r.get('model_audit',{}),'markets':[{k:m[k] for k in market_fields if k in m} for m in r.get('all_markets',[])]} for r in data.get('results',[])],'metric_extremes_review':metric_evidence or [],'quote_review':quote_audit}
    audit_name=path.stem+'_auditoria.json';(path.parent/audit_name).write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')
    original_rows=[]
    for r in data.get('results',[]):
        for m in r.get('all_markets',[]):original_rows.append('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in [r['match'],m['key'],repr(m.get('probability')),m.get('sample_min'),m.get('selection_role')])+'</tr>')
    original_table='<details><summary>Valores históricos originales · probabilidades y muestras declaradas sin corregir</summary>'+table(['Partido','Mercado original','Probabilidad original guardada','Muestra declarada original','Rol histórico'],original_rows)+'</details>'
    metadata={'source_semantic_sha256':hashlib.sha256(original.encode()).hexdigest(),'view_generated_at':now.isoformat(),'note':'Datos históricos originales intactos. Los estados de respaldo no reemplazan sus números ni sus selecciones.'}
    audit_panel='<h2>Auditoría</h2><p>Las muestras de goles no prueban muestras de córners/remates. Una estimación no es certeza.</p><details id="audit-json"><summary>JSON de auditoría · cerrado por defecto</summary><p><a href="'+esc(audit_name)+'" download>Descargar JSON de auditoría completo</a></p><pre>'+esc(json.dumps(metadata,ensure_ascii=False,indent=2))+'</pre></details>'+original_table
    audit_panel+='<details id="source-age-policy"><summary>Política de antigüedad por fuente · provisional, no optimizada</summary><p>API-Football: máximo 600 s tanto para consulta como actualización original del bloque del proveedor. Si falta un reloj, la cuota no es elegible. El update del bloque no prueba el instante de cambio de cada selección.</p><p>Betano Chrome asistido: máximo 600 s desde la captura directa, cruce exacto de partido/mercado/periodo/línea/selección, HTTPS válido, sin promociones ni fuente denegada. El scraper autónomo sigue no verificado por HTTP 403.</p><p>La caché HTTP de odds puede conservar respuestas 900 s; eso reduce llamadas, no amplía la elegibilidad de 600 s. Se conserva la captura original al leer caché. La tolerancia de reloj futuro de 5 s ya existente no renueva capturas. Una descarga nueva no rejuvenece update.</p><p>La documentación publicada de prematch indica actualizaciones de horas, no una confirmación ejecutable en diez minutos. Esto explica la baja cobertura elegible, no autoriza ampliar el TTL. <a href="https://www.api-football.com/documentation_v3">Documentación publicada</a> · <a href="https://www.api-football.com/terms">Frecuencias orientativas, no garantizadas</a>.</p><p>Guarda de datos ≠ mejora predictiva. Las probabilidades históricas no cambian. No se declara un EV oportunidad sin modelo y cuota validados.</p></details>'
    if metric_evidence:
        erows=['<tr>'+''.join('<td>'+esc(v)+'</td>' for v in [x['partido'],spanish_market(x['mercado']),x['antes'],repr(x['probabilidad_original_guardada']),repr(x['probabilidad_sin_redondeo_reconstruida']),x['lambda_historica'],x['muestra_minima_real'],x['despues']])+'</tr>' for x in metric_evidence]
        audit_panel+='<details id="extreme-audit"><summary>Comparación de las 13 filas antes/después</summary><p>Valor sin redondear RECONSTRUIDO, no registrado como tal en el snapshot. Todas las probabilidades originales se conservan.</p>'+table(['Partido','Mercado','Antes','P guardada','P reconstruida','Media histórica','N real mínimo','Después'],erows)+'</details>'
    audit_panel+='<details><summary>Auditoría del modelo: últimos partidos usados</summary>'+''.join('<details><summary>'+esc(r['match'])+'</summary><pre>'+esc(json.dumps(r.get('model_audit',{}),ensure_ascii=False,indent=2))+'</pre></details>' for r in data.get('results',[]))+'</details>'
    excluded=data.get('previously_started_or_expired') or []
    if excluded:
        audit_panel+='<details><summary>Partidos iniciados, finalizados o fuera del prepartido · '+str(len(excluded))+'</summary>'+table(['Partido','Inicio Perú','Estado consultado','Tratamiento'],['<tr><td>'+esc(x.get('home'))+' – '+esc(x.get('away'))+'</td><td>'+esc(lima(x.get('kickoff')))+'</td><td>'+esc(x.get('status'))+'</td><td>Sin cálculo prepartido nuevo ni selección</td></tr>' for x in excluded])+'</details>'
    controls='<div class="filters"><label>Buscar partido o mercado <input id="market-search" type="search"></label><label>Familia <select id="family-filter"><option value="">Todas</option>'+''.join('<option value="'+esc(f)+'">'+esc(spanish_market(f).split(' · ')[0])+'</option>' for f in sorted(families))+'</select></label><label><input type="checkbox" id="only-api-observed"> Solo cuotas API observadas</label><span id="market-count" aria-live="polite"></span></div>'
    current=_current_selection_view(data,now);auto=_current_selection_view(data,now,automatic=True)
    manual='<details id="current-review"><summary>Revisión actual separada · manuales y T−60</summary><p>No se recalculan picks ni se renuevan cuotas al abrir este archivo. Revalidar fuentes antes de usar cualquier selección.</p><h3>Candidatos manuales</h3>'+selections(current,'Principal',live=True)+'<h3>Oportunidades T−60</h3>'
    for r in auto.get('results',[]):
        minutes=(datetime.fromisoformat(r['kickoff_lima'])-now).total_seconds()/60 if r.get('kickoff_lima') else -1
        if not 45<=minutes<=60:r['recommended_pick']=None;r['alternative_picks']=[]
    manual+=selections(auto,'Principal',live=True,t60=True)+'</details>'
    tabs=[('principales','Principales'),('alternativas','Alternativas'),('mercados','Todos los mercados'),('jugadores','Jugadores'),('auditoria','Auditoría')]
    content={'principales':'<h2>Principales históricas</h2><p class="notice">Se conserva la selección original, incluida la abstención. No son recomendaciones vigentes. Probabilidades sin calibración validada.</p>'+manual+selections(data,'Principal',True),'alternativas':'<h2>Alternativas históricas</h2><p>No son una combinada ni una probabilidad conjunta. No se cambian las selecciones originales.</p>'+selections(data,'Alternativa'),'mercados':'<h2>Todos los mercados</h2><p>Cuotas históricas por casa. Los valores no sustentados se conservan exclusivamente en Auditoría, sin recortarlos a 99,9%. Observado histórico y elegible son campos distintos: el histórico nunca rellena una cuota activa. Ambos relojes API siguen siendo los originales.</p>'+controls+table(['Partido / inicio Perú','Mercado / estimación','Book API-Football HISTÓRICO','Precio API observado HISTÓRICO','Relojes API HISTÓRICOS','Motivo del descarte API','Precio API elegible al verificar','Betano observado HISTÓRICO / fuente','Precio Betano elegible / descarte'],allrows,'all-markets')+'<div class="pager"><button id="previous-page" type="button">Anterior</button><span id="page-number"></span><button id="next-page" type="button">Siguiente</button></div>','jugadores':'<h2>Jugadores</h2><p>Observaciones condicionadas a minutos; sin probabilidad calibrada ni EV de jugador.</p>'+(table(['Partido','Jugador','Mercado','Muestra propia','Estado','Casa / cuota exacta'],players) if players else '<p class="empty">Datos insuficientes. Este snapshot no contiene observaciones individuales de jugadores. No se recuperan de otro corte.</p>'),'auditoria':audit_panel}
    nav=''.join('<button class="tab" type="button" role="tab" id="tab-'+k+'" aria-controls="panel-'+k+'" aria-selected="'+('true' if i==0 else 'false')+'" tabindex="'+('0' if i==0 else '-1')+'">'+label+'</button>' for i,(k,label) in enumerate(tabs))
    panels=''.join('<section id="panel-'+k+'" role="tabpanel" aria-labelledby="tab-'+k+'" '+('hidden' if i else '')+'>'+content[k]+'</section>' for i,(k,label) in enumerate(tabs))
    css='''*{box-sizing:border-box}body{margin:0;background:#0c1422;color:#e9f0fa;font:14px/1.5 system-ui,sans-serif}a{color:#8acbff}header{position:static;max-width:1480px;margin:auto;padding:24px 20px 16px}h1{font-size:clamp(22px,4vw,30px);margin:0 0 10px}h2{font-size:20px}p{margin:9px 0}.small,time{font-size:12px;color:#b5c6db}.badge{border:1px solid #657a94;padding:3px 8px;border-radius:12px;display:inline-block;font-size:12px}.coverage{display:flex;gap:12px 25px;flex-wrap:wrap;margin:14px 0}.coverage span{color:#b5c6db}.coverage b{font-size:20px}.tab-shell{position:sticky;top:0;z-index:10;background:#0c1422;border-block:1px solid #334358}.tabs{max-width:1480px;margin:auto;display:flex;flex-wrap:nowrap;gap:8px;padding:10px 20px;overflow-x:auto}.tab,button{flex:0 0 auto;width:auto;white-space:nowrap;border:1px solid #52677f;border-radius:18px;padding:8px 14px;color:#dfeafa;background:#1a2b42;cursor:pointer;font:inherit}.tab[aria-selected=true]{background:#d8e9ff;color:#142135}.tab:focus-visible,summary:focus-visible,input:focus-visible{outline:3px solid #ffcf70;outline-offset:2px}main{max-width:1480px;margin:auto;padding:18px 20px 45px}[hidden]{display:none!important}.tablewrap{overflow-x:auto;max-width:100%;border:1px solid #334358;border-radius:8px;scroll-margin-top:85px}table{border-collapse:collapse;width:100%;min-width:1020px;table-layout:fixed}th,td{border-bottom:1px solid #334358;padding:11px 10px;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#20324b;font-size:12px}td{font-size:13px}tbody tr:nth-child(even){background:#111f32}.historical-principal td:first-child{border-left:4px solid #e8c16a}.historical-alternativa td:first-child{border-left:3px solid #718ba9}.notice{padding:10px 13px;border-left:4px solid #e9b95f;background:#302b23;color:#ffe0a1}.warning-text{color:#ffcf82}#all-markets{min-width:1800px}.market-scroll{max-height:68vh;overflow:auto}.market-scroll th{position:sticky;top:0;z-index:2}.discard-badge{color:#ffbdab;font-weight:700}.discard-reason{font-size:12px;border-left:3px solid #df927d;padding-left:7px;color:#f3c4b8}.empty{padding:15px;border:1px dashed #718297;border-radius:8px}details{border:1px solid #334358;border-radius:8px;padding:12px;margin:12px 0}details.trace{font-size:12px;margin:0;padding:7px}summary{cursor:pointer;font-weight:650}details:not([open])>:not(summary){display:none}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:480px;overflow:auto;font:12px/1.5 ui-monospace,monospace}.filters,.pager{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin:14px 0}.filters label{display:flex;gap:8px;align-items:center}input,select{max-width:100%;padding:8px;background:#16253c;border:1px solid #52677f;border-radius:6px;color:#e9f0fa}.pager button:disabled{opacity:.4;cursor:default}footer{max-width:1480px;margin:auto;padding:20px;color:#b5c6db}@media(max-width:600px){header{padding:18px 14px 12px}main{padding:14px}.tabs{padding-inline:14px}.filters label{display:block}.coverage{gap:8px 16px}table{min-width:1050px}th,td{padding:9px}.coverage b{font-size:18px}}'''
    script='''const tabs=[...document.querySelectorAll('[role=tab]')];function activate(t){tabs.forEach(b=>{const on=b===t;b.setAttribute('aria-selected',on);b.tabIndex=on?0:-1;document.getElementById(b.getAttribute('aria-controls')).hidden=!on;});t.scrollIntoView({block:'nearest',inline:'nearest'});}tabs.forEach((t,i)=>{t.addEventListener('click',()=>activate(t));t.addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const j=e.key==='Home'?0:e.key==='End'?tabs.length-1:(i+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;activate(tabs[j]);tabs[j].focus();}});});const rows=[...document.querySelectorAll('#all-markets tbody tr')];let page=0;function norm(s){return s.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();}function filter(){const q=norm(document.getElementById('market-search').value),f=document.getElementById('family-filter').value;const only=document.getElementById('only-api-observed').checked;const selected=rows.filter(r=>norm(r.dataset.search).includes(q)&&(!f||r.dataset.family===f)&&(!only||r.dataset.apiObserved==='1'));const pages=Math.max(1,Math.ceil(selected.length/50));page=Math.min(page,pages-1);rows.forEach(r=>r.hidden=true);selected.slice(page*50,page*50+50).forEach(r=>r.hidden=false);document.getElementById('market-count').textContent=selected.length+' mercados';document.getElementById('page-number').textContent='Página '+(page+1)+' de '+pages;document.getElementById('previous-page').disabled=page===0;document.getElementById('next-page').disabled=page>=pages-1;}document.getElementById('market-search').addEventListener('input',()=>{page=0;filter();});document.getElementById('family-filter').addEventListener('change',()=>{page=0;filter();});document.getElementById('only-api-observed').addEventListener('change',()=>{page=0;filter();});document.getElementById('previous-page').addEventListener('click',()=>{page--;filter();});document.getElementById('next-page').addEventListener('click',()=>{page++;filter();});filter();'''
    script+="""function expire(){document.querySelectorAll('[data-price-expiry]').forEach(e=>{if(Date.now()>Date.parse(e.dataset.priceExpiry)){e.textContent='— No elegible: captura vencida; revalidar.';e.className='discard-badge';}});document.querySelectorAll('[data-current-candidates]').forEach(g=>{let n=0;g.querySelectorAll('[data-live-expiry]').forEach(r=>{r.hidden=!Number.isFinite(Date.parse(r.dataset.liveExpiry))||Date.now()>Date.parse(r.dataset.liveExpiry);if(!r.hidden)n++;});g.querySelector('.live-status').textContent=n?'Revalidar antes de usar; sin consulta en vivo.':'Sin apuesta: las capturas vencieron o se cerró la ventana.';});}expire();setInterval(expire,1000);"""
    principal=sum(bool(r.get('recommended_pick')) for r in data.get('results',[]));alt=sum(len(r.get('alternative_picks',[])) for r in data.get('results',[]));api=sum(odds(m,'API') is not None for m in markets);betano=sum(odds(m,'Betano') is not None for m in markets)
    header='<header><h1>'+esc(title)+'</h1><p>Fecha: <b>'+esc(data.get('date_lima_filter') or data.get('from_date'))+'</b> · Corte original Perú: <b>'+esc(lima(data.get('generated_at')))+'</b> · <span class="badge">Reporte histórico · no vigente</span></p><p>Las capturas no se renuevan. Revalidar cada cuota antes de usar. Las guardas no cambian probabilidades ni demuestran mejora predictiva. EV histórico no acredita una oportunidad; ajuste de rivales aún sin mejora validada.</p><div class="coverage">'+''.join('<span><b>'+str(n)+'</b> '+label+'</span>' for n,label in [(len(data.get('results',[])),'partidos'),(len(markets),'mercados'),(principal,'principales históricas'),(alt,'alternativas históricas'),(api,'observaciones API'),(betano,'observaciones Betano')])+'</div></header>'
    header=header.removesuffix('</header>')
    header+='<p>Betano autónomo: <b>no verificado (HTTP 403)</b>. Chrome asistido es una fuente separada; no prueba funcionamiento autónomo.</p>'
    if not principal:header+='<p class="notice"><b>Sin apuesta al corte.</b> Ninguna selección cumple todos los controles.</p>'
    downloads=[]
    for candidate,label in [(path.with_name(path.stem+'_todos_los_mercados.csv'),'Descargar CSV · foto histórica'),(path.with_suffix('.csv'),'Descargar CSV · foto histórica'),(path.with_name(path.stem+'_descartes_betano.csv'),'Promociones y mercados no mapeados · CSV')]:
        if candidate.exists():downloads.append('<a href="'+esc(candidate.name)+'" download>'+label+'</a>')
    header+='<p>'+' · '.join(downloads)+'</p>'
    header+='</header>'
    page='<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(title)+'</title><style>'+css+'</style></head><body data-report-matches="'+str(len(data.get('results',[])))+'" data-report-markets="'+str(len(markets))+'">'+header+'<div class="tab-shell"><nav class="tabs" role="tablist" aria-label="Secciones del reporte">'+nav+'</nav></div><main>'+panels+'</main><footer>Foto histórica en tablas · Datos y selecciones del corte intactos. Sin actualización en vivo. Modelo experimental desactivado.</footer><script>'+script+'</script></body></html>'
    path.write_text(page,encoding='utf-8',newline='\n');assert json.dumps(data,ensure_ascii=False,sort_keys=True)==original
    return {'html':str(path),'audit_json':str(path.parent/audit_name),'source_unchanged':True,'historical_selections':principal+alt}
