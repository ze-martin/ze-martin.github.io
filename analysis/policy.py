"""Conservative, auditable selection. Thresholds are guardrails, not promises."""
from copy import deepcopy
import math
from datetime import datetime, timezone

POLICY_VERSION = 'selection-v2'
MIN_SAMPLE = 6
MIN_EV = .02


def offered(market):
    quotes = []
    for house, odds, ev in [('API', market.get('odds_api', market.get('odds')), market.get('ev_api', market.get('ev'))),
                            ('Betano', market.get('odds_betano'), market.get('ev_betano'))]:
        if isinstance(odds, (int, float)) and math.isfinite(odds) and odds > 1:
            quotes.append((house, odds, ev))
    return quotes


def reasons(market, sample, eligible=True):
    why = []
    if not eligible:
        why.append('Partido iniciado o no elegible para prepartido')
    if sample < MIN_SAMPLE:
        why.append(f'Muestra insuficiente: {sample}; mínimo provisional {MIN_SAMPLE}')
    quotes = offered(market)
    if not quotes:
        why.append('Sin cuota verificable')
    positive = [q for q in quotes if q[2] is not None and q[2] >= MIN_EV]
    if not positive:
        why.append('Sin EV estimado de al menos 2% en una casa disponible')
    p = market.get('probability', 0)
    if not .55 <= p <= .95:
        why.append('Probabilidad fuera del rango provisional 55–95%')
    if positive and all(q[1] * p >= 1.75 for q in positive):
        why.append('Ventaja extraordinaria: requiere revisión manual')
    if market.get('key', '').startswith('PLAYER_'):
        why.append('Jugador: requiere cuota exacta, minutos y titularidad verificados')
    if market.get('key', '').startswith(('CARDS_', 'SHOTS_')):
        why.append('Familia avanzada aún no validada fuera de muestra')
    if market.get('key', '').split(':')[0] in {'WIN_BTTS','TOTAL_RANGE','CLEAN_SHEET'}:
        why.append('Mercado nuevo: análisis exploratorio hasta validación temporal propia')
    return why


def apply_policy(data):
    result = deepcopy(data)
    result['results'] = sorted(result.get('results',[]), key=lambda r:(r.get('kickoff_lima') or '',r.get('match') or ''))
    result['selection_policy'] = POLICY_VERSION
    result.setdefault('calibration_status', 'Pendiente de validación temporal; probabilidades no garantizadas')
    for match in result.get('results', []):
        if 'legacy_recommended_pick' not in match:
            match['legacy_recommended_pick'] = deepcopy(match.get('recommended_pick'))
        inputs = (match.get('model_audit') or {}).get('team_inputs') or {}
        sample = min((inputs.get(s) or {}).get('matches') or 0 for s in ['home', 'away'])
        eligible = match.get('pre_match_eligible') is not False
        if match.get('kickoff_lima'):
            eligible = eligible and datetime.fromisoformat(match['kickoff_lima']) > datetime.now(timezone.utc)
        candidates = []
        for market in match.get('all_markets', []):
            family = market.get('key','').split(':')[0]
            advanced_family = 'FIRST_HALF_TOTALS' if family=='FIRST_HALF_TOTALS' else next((f for f in ['CORNERS','SHOTS','CARDS'] if family.startswith(f)), None)
            market_sample = min(sample, (match.get('model_audit') or {}).get('advanced_sample_min',{}).get(advanced_family,0)) if advanced_family else sample
            market['selection_reasons'] = reasons(market, market_sample, eligible)
            market['sample_min'] = market_sample
            market['calibration_status'] = result['calibration_status']
            market['selection_role'] = 'Solo análisis'
            market['recommendation_tier'] = 'Solo modelo' if not offered(market) else 'Revisar' if market['selection_reasons'] else 'Valor estimado'
            quotes = [q for q in offered(market) if q[2] is not None and q[2]>=MIN_EV and q[1]*market.get('probability',0)<1.75]
            chosen = max(quotes,key=lambda q:q[2]) if quotes and not market['selection_reasons'] else None
            market['selection_bookmaker'] = ('Betano' if chosen[0]=='Betano' else market.get('bookmaker_api') or market.get('bookmaker') or match.get('bookmaker')) if chosen else None
            market['selection_odds'] = chosen[1] if chosen else None
            if not market['selection_reasons']:
                market['selection_score_v2'] = market.get('combined_recommendation_score', market.get('recommendation_score', 0))
                candidates.append(market)
        candidates.sort(key=lambda m: m.get('selection_score_v2', 0), reverse=True)
        selected = []
        families = set()
        for market in candidates:
            family = market['key'].split(':')[0]
            if family in families:
                continue
            families.add(family)
            selected.append(market)
            if len(selected) == 3:
                break
        for index, market in enumerate(selected):
            market['selection_role'] = 'Principal' if index == 0 else 'Alternativa'
        match['recommended_pick'] = deepcopy(selected[0]) if selected else None
        match['alternative_picks'] = deepcopy(selected[1:])
        match['selection_status'] = 'Candidato provisional; no apuesta automática' if selected else 'Sin apuesta'
    return result


def compatible_keys(keys):
    """Alternatives are not a joint-price bet. Remove nesting/opposites too."""
    families = [key.split(':')[0] for key in keys]
    if len(set(families)) != len(families):
        return False
    if 'BTTS:YES' in keys and any(k.startswith('TOTALS:OVER_1_5') for k in keys):
        return False
    if len(set(families) & {'1X2', 'DOUBLE_CHANCE', 'DRAW_NO_BET'}) > 1:
        return False
    return True
