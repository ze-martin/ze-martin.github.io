"""Player form watchlist with exact bookmaker attribution and minute scenarios."""
import math
import re
import unicodedata
from collections import defaultdict
from datetime import datetime


def norm(name):
    value=''.join(c for c in unicodedata.normalize('NFD',name.lower()) if unicodedata.category(c)!='Mn')
    return re.sub(r'[^a-z0-9 ]','',value).split()


def match_player(label, players):
    target=norm(label)
    exact=[p for p in players if norm(p['name'])==target]
    if len(exact)==1:return exact[0]
    candidates=[]
    for p in players:
        tokens=norm(p['name'])
        if tokens and target and len(tokens[-1])>=4 and tokens[-1]==target[-1] and tokens[0][0]==target[0][0]:
            candidates.append(p)
    return candidates[0] if len(candidates)==1 else None


def enrich_availability(api, fixture_id, options):
    try:
        payload=api._api_get('injuries',{'fixture':fixture_id})
        if payload.get('errors'):raise ValueError(str(payload['errors']))
        reported={r['player']['id']:r['player'] for r in payload.get('response',[]) if r.get('player',{}).get('id')}
        for p in options:
            item=reported.get(p['player_id'])
            note=('API reporta '+str(item.get('type',''))+': '+str(item.get('reason',''))) if item else 'Sin incidencia reportada; no confirma disponibilidad'
            p['availability_note']=note
            p['status']=p['status'].split(' · Disponibilidad:')[0]+' · Disponibilidad: '+note
    except Exception:
        for p in options:
            p['availability_note']='No verificada por API'
    return options


def deduplicate_quotes(options):
    for p in options:
        seen=set();unique=[]
        for quote in p.get('api_quotes',[]):
            key=(quote['bookmaker'],quote['odds'])
            if key not in seen:
                seen.add(key);unique.append(quote)
        p['api_quotes']=unique
    return options


def build_player_options(api, fixture):
    cutoff=datetime.fromisoformat(fixture['fixture']['date'].replace('Z','+00:00'))
    histories=defaultdict(list);names={};teams={};warnings=[]
    starters=set();lineup_available=False
    try:
        response=api._api_get('fixtures/lineups',{'fixture':fixture['fixture']['id']})
        for team in response.get('response',[]):
            for p in team.get('startXI',[]):starters.add(p['player']['id'])
        lineup_available=len(starters)>=22
    except Exception as exc:warnings.append('Alineación no disponible: '+str(exc)[:100])
    for side in ['home','away']:
        team=fixture['teams'][side]
        try:
            payload=api._api_get('fixtures',{'team':team['id'],'last':10,'status':'FT'})
            recent=[f for f in payload.get('response',[]) if datetime.fromisoformat(f['fixture']['date'].replace('Z','+00:00'))<cutoff]
            recent=sorted(recent,key=lambda f:f['fixture']['date'],reverse=True)[:6]
            for f in recent:
                payload=api._api_get('fixtures/players',{'fixture':f['fixture']['id'],'team':team['id']})
                if payload.get('errors'):warnings.append(str(payload['errors'])[:160])
                for teamrow in payload.get('response',[]):
                    if teamrow.get('team',{}).get('id') != team['id']:continue
                    for entry in teamrow.get('players',[]):
                        stats=next(iter(entry.get('statistics',[])),{})
                        minutes=stats.get('games',{}).get('minutes')
                        if not minutes or minutes<=0:continue
                        player=entry['player'];pid=player['id'];names[pid]=player['name'];teams[pid]=team['name']
                        histories[pid].append({'fixture_id':f['fixture']['id'],'date':f['fixture']['date'],
                            'minutes':minutes,'goals':stats.get('goals',{}).get('total'),
                            'assists':stats.get('goals',{}).get('assists'),
                            'shots':stats.get('shots',{}).get('total'),'on_target':stats.get('shots',{}).get('on'),
                            'yellow':stats.get('cards',{}).get('yellow'),'key_passes':stats.get('passes',{}).get('key'),
                            'starter':stats.get('games',{}).get('substitute') is False})
        except Exception as exc:warnings.append(team['name']+': '+str(exc)[:140])
    players=[{'id':pid,'name':name} for pid,name in names.items()]
    scorer_quotes=defaultdict(list);raw_quotes=[]
    try:
        payload=api._api_get('odds',{'fixture':fixture['fixture']['id']})
        for block in payload.get('response',[]):
            for book in block.get('bookmakers',[]):
                for bet in book.get('bets',[]):
                    title=bet.get('name','')
                    if title not in {'Anytime Goal Scorer','Home Anytime Goal Scorer','Away Anytime Goal Scorer'}:
                        continue
                    for value in bet.get('values',[]):
                        player=match_player(str(value.get('value','')),players)
                        try:odd=float(value['odd'])
                        except (KeyError,TypeError,ValueError):continue
                        if player and 1<odd<100 and math.isfinite(odd):
                            scorer_quotes[player['id']].append({'bookmaker':book['name'],'odds':odd,'market':title,'label':value['value']})
    except Exception as exc:warnings.append('Cuotas individuales no disponibles: '+str(exc)[:100])
    options=[]
    for pid,history in histories.items():
        minutes=sum(h['minutes'] for h in history);games=len(history)
        if games<2:continue
        for metric,label,threshold in [('goals','Anota 1+ gol',1),('goals','Anota 2+ goles',2),
            ('assists','Da 1+ asistencia',1),('shots','Realiza 1+ remate',1),('shots','Realiza 2+ remates',2),
            ('shots','Realiza 3+ remates',3),('on_target','Realiza 1+ tiro al arco',1),
            ('on_target','Realiza 2+ tiros al arco',2),('yellow','Recibe amarilla',1)]:
            observed=[h for h in history if h[metric] is not None]
            observed_minutes=sum(h['minutes'] for h in observed)
            if not observed or not observed_minutes:continue
            total=sum(h[metric] for h in observed);rate=total*90/observed_minutes
            if total==0:continue
            # Scenarios, not a calibrated unconditional forecast or an EV.
            def tail(lam):
                return max(0.0,min(1.0,1-sum(math.exp(-lam)*lam**k/math.factorial(k) for k in range(threshold))))
            p60=tail(rate*60/90);p90=tail(rate)
            quotes=scorer_quotes[pid] if metric=='goals' and threshold==1 else []
            options.append({'player_id':pid,'player':names[pid],'team':teams[pid],'market':label,'metric':metric,
                'appearances':games,'minutes':minutes,'observed_games':len(observed),'observed_minutes':observed_minutes,
                'total':total,'last3':sum(h[metric] for h in history[:3]) if all(h[metric] is not None for h in history[:3]) else None,'per90':round(rate,3),
                'start_rate':sum(h['starter'] for h in history)/games,'starter_confirmed':pid in starters if lineup_available else None,
                'p_if_60_minutes':round(p60,4),'p_if_90_minutes':round(p90,4),'api_quotes':quotes,'odds_betano':None,
                'role':'Observación de jugador; no incluido en aciertos principales',
                'sample_sufficient':len(observed)>=5 and observed_minutes>=300,
                'status':'Requiere validación fuera de muestra, minutos previstos y reglas de la casa',
                'history':history})
    options.sort(key=lambda x:(bool(x['api_quotes']),x['sample_sufficient'],x['last3'] or 0,x['per90']),reverse=True)
    enrich_availability(api,fixture['fixture']['id'],options)
    deduplicate_quotes(options)
    return {'options':options,'warnings':warnings,'lineups_confirmed':lineup_available,
            'method':'Últimos 6 partidos terminados antes del encuentro; Poisson condicional a 60/90 minutos, no calibrado. Racha descriptiva, no garantía.'}
