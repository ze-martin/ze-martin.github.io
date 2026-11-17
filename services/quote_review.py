"""Keep immutable observations separate from eligible live fields. No network/DB."""
from datetime import datetime,timezone
import math

MAX_AGE_SECONDS=600
FUTURE_TOLERANCE_SECONDS=5
RULES={'API':{'required_clocks':['captured_at','provider_updated_at'],'max_age_seconds':600},'Betano':{'required_clocks':['captured_at'],'max_age_seconds':600}}

def price(value):return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>1

def observed_quote(m,source):
    key='api_quote_observation' if source=='API' else 'betano_quote_observation';o=m.get(key) or {}
    raw=m.get('odds_api',m.get('odds')) if source=='API' else m.get('odds_betano')
    historical=o.get('odds') is not None
    captured=o.get('captured_at') if historical else m.get('api_captured_at' if source=='API' else 'betano_captured_at')
    updated=o.get('provider_updated_at') if historical else m.get('api_updated_at') if source=='API' else None
    bookmaker=o.get('bookmaker') if historical else m.get('bookmaker_api') or m.get('bookmaker')
    if source=='Betano':bookmaker='Betano'
    elif not bookmaker and captured==m.get('api_captured_at') and updated==m.get('api_updated_at'):bookmaker=m.get('bookmaker_api') or m.get('bookmaker')
    return {'source':source,'odds':o.get('odds') if historical else raw,'bookmaker':bookmaker,'captured_at':captured,'provider_updated_at':updated,'source_url':o.get('source_url') or m.get('betano_source_url' if source=='Betano' else 'api_source_url'),'original_discard_reason':o.get('validation_error') or (m.get('quote_validation_errors') or {}).get(source)}

def check_quote(m,source,at,*,observation=None):
    # Active validation NEVER falls back to api_quote_observation/old prices.
    q=observation if observation is not None else {'odds':m.get('odds_api',m.get('odds')) if source=='API' else m.get('odds_betano'),'bookmaker':(m.get('bookmaker_api') or m.get('bookmaker')) if source=='API' else 'Betano','captured_at':m.get('api_captured_at' if source=='API' else 'betano_captured_at'),'provider_updated_at':m.get('api_updated_at')}
    reasons=[];ages={}
    if not price(q.get('odds')):reasons.append('Sin precio activo verificable' if observation is None else 'Sin precio observado verificable')
    if source=='API' and not q.get('bookmaker'):reasons.append('Bookmaker API no conservado')
    if m.get('quote_type')=='promotional' or (source=='Betano' and m.get('betano_promotion')):reasons.append('Promoción no equivalente')
    error=m.get('api_fetch_error' if source=='API' else 'betano_fetch_error')
    if error:reasons.append('Fuente no verificada: '+str(error))
    if source=='Betano':
        status=m.get('betano_http_status')
        if status is not None and (not isinstance(status,int) or status>=400):reasons.append('Fuente no verificada: HTTP '+str(status))
        if m.get('betano_source_method')=='assisted_chrome_visible' and not m.get('betano_quote_valid'):reasons.append('Captura asistida sin cruce exacto validado')
    labels={'captured_at':'Consulta API' if source=='API' else 'Captura directa','provider_updated_at':'Actualización del proveedor'}
    for clock in RULES[source]['required_clocks']:
        try:
            value=q.get(clock);stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
            if stamp.tzinfo is None:raise ValueError('Sin zona')
            age=(at-stamp).total_seconds();ages[clock]=age
            if age>MAX_AGE_SECONDS:reasons.append(labels[clock]+' vencida: '+str(round(age))+' s > 600 s')
            elif age < -FUTURE_TOLERANCE_SECONDS:reasons.append(labels[clock]+' futura: '+str(round(-age))+' s')
        except (ValueError,TypeError,AttributeError):reasons.append(labels[clock]+' ausente o sin zona verificable')
    return {'valid':not reasons,'reasons':reasons,'age_seconds':ages,'odds':q.get('odds'),'bookmaker':q.get('bookmaker')}

def review_quote(m,source,now=None,cutoff=None):
    now=now or datetime.now(timezone.utc);o=observed_quote(m,source);active=check_quote(m,source,now)
    observed_now=check_quote(m,source,now,observation=o)
    at_cutoff=check_quote(m,source,cutoff,observation=o) if cutoff is not None else None
    return {'observed':o,'observed_at_cutoff':at_cutoff,'observed_at_view':observed_now,'eligible_price':active['odds'] if active['valid'] else None,'eligible_bookmaker':active['bookmaker'] if active['valid'] else None,'eligibility':active,'checked_at':now.isoformat(),'note':'Elegibilidad de la cuota no acredita modelo, EV ni selección; no rescata el precio histórico.'}
