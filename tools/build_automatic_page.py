"""Export only public fixtures and forecasts, never credentials or tickets."""
import html
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT = Path(__file__).resolve().parents[1]
COUNTRIES = {'Ukraine':'Ucrania','Belarus':'Bielorrusia','Saudi-Arabia':'Arabia Saudita','England':'Inglaterra','Peru':'Perú','Brazil':'Brasil','Germany':'Alemania','Italy':'Italia','Spain':'España','France':'Francia','Romania':'Rumanía','Slovenia':'Eslovenia','Croatia':'Croacia','Poland':'Polonia','Turkey':'Turquía','Cyprus':'Chipre','Bulgaria':'Bulgaria','World':'Internacional','USA':'Estados Unidos','Netherlands':'Países Bajos','Belgium':'Bélgica','Austria':'Austria','Czech-Republic':'República Checa','Costa-Rica':'Costa Rica','Denmark':'Dinamarca','Scotland':'Escocia','Slovakia':'Eslovaquia','Finland':'Finlandia','Greece':'Grecia','Ireland':'Irlanda','Mexico':'México','Norway':'Noruega','Sweden':'Suecia','Switzerland':'Suiza'}
STATES = {'NS':'Programado · no iniciado','TBD':'Horario por confirmar','PST':'Aplazado · sin horario confirmado','CANC':'Cancelado','SUSP':'Suspendido','INT':'Interrumpido','ABD':'Abandonado','FT':'Finalizado','AET':'Finalizado tras prórroga','PEN':'Finalizado por penales','AWD':'Resultado administrativo','WO':'Incomparecencia','1H':'En juego · primer tiempo','HT':'Descanso','2H':'En juego · segundo tiempo','ET':'En juego · prórroga','BT':'Pausa','P':'Tanda de penales','LIVE':'En juego'}

def build():
    now = datetime.now(ZoneInfo('America/Lima'))
    tomorrow = (now.date()+timedelta(days=1)).isoformat()
    agenda, picks, exceptions = [], [], []
    db = sqlite3.connect(f'file:{(ROOT/"data/automatic_protocol.sqlite").as_posix()}?mode=ro',uri=True)
    try:
        for kickoff, raw in db.execute('SELECT kickoff,payload FROM jobs ORDER BY kickoff'):
            local = datetime.fromisoformat(kickoff).astimezone(ZoneInfo('America/Lima'))
            if local.date().isoformat() == tomorrow:
                f=json.loads(raw)
                state=f['fixture']['status']['short']
                country=f['league'].get('country') or 'País no informado'
                row=[local.strftime('%H:%M') if state=='NS' else 'No confirmado',COUNTRIES.get(country,country)+' · '+f['league']['name'],f['teams']['home']['name']+' — '+f['teams']['away']['name'],STATES.get(state,'Estado no reconocido: '+state)]
                (agenda if state=='NS' else exceptions).append(row)
        for raw, kickoff in db.execute('SELECT o.payload,j.kickoff FROM outbox o JOIN jobs j ON j.id=o.fixture ORDER BY j.kickoff'):
            p=json.loads(raw); q=p['pick']
            if q.get('probability',0)<=.70:
                continue
            captured=datetime.fromisoformat(p['captured']).astimezone(ZoneInfo('America/Lima'))
            start=datetime.fromisoformat(kickoff).astimezone(ZoneInfo('America/Lima'))
            minutes=(start-captured).total_seconds()/60
            label={'DOUBLE_CHANCE X2':'Visitante o empate','DOUBLE_CHANCE 1X':'Local o empate','BTTS YES':'Ambos equipos anotan','BTTS NO':'No anotan ambos','FIRST_HALF_TOTALS UNDER.1.5':'Menos de 1,5 goles en el primer tiempo','FIRST_HALF_TOTALS OVER.0.5':'Más de 0,5 goles en el primer tiempo','TOTALS UNDER.3.5':'Menos de 3,5 goles'}.get(q['market'],q['market'])
            house=q.get('selection_bookmaker','')
            ev=q.get('ev_betano') if house=='Betano' else q.get('ev_api',q.get('ev'))
            mode='Revisión próxima al inicio' if 0<minutes<=60 else 'Análisis anticipado · no T−60'
            if start<=now: mode='Histórico · partido iniciado'
            picks.append([p['match'],start.strftime('%d/%m %H:%M'),'★ Principal: '+label,house,q.get('selection_odds',''),f"{q.get('probability',0):.1%}",f'{ev:+.1%}' if isinstance(ev,(int,float)) else 'No disponible',captured.strftime('%d/%m/%Y %H:%M'),mode])
            for alternative in p.get('alternatives',[])[:2]:
                if alternative.get('probability',0)<=.70: continue
                picks.append([p['match'],start.strftime('%d/%m %H:%M'),'Alternativa: '+alternative['market'],alternative.get('selection_bookmaker',''),alternative.get('selection_odds',''),f"{alternative['probability']:.1%}",'Ver análisis',captured.strftime('%d/%m/%Y %H:%M'),mode])
    finally:
        db.close()
    def table(headers, rows):
        esc=lambda x:html.escape(str(x))
        return '<div class="scroll"><table><tr>'+''.join('<th>'+esc(x)+'</th>' for x in headers)+'</tr>'+''.join('<tr>'+''.join('<td>'+esc(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</table></div>' if rows else '<p>No hay sugerencias T−60 registradas todavía.</p>'
    page='<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Agenda y sugerencias T−60</title><style>body{background:#0b1220;color:#eef3ff;font:16px system-ui;max-width:1100px;margin:24px auto;padding:16px}a{color:#74baff}section{background:#172238;padding:20px;margin:20px 0;border-radius:12px}.scroll{overflow:auto}table{border-collapse:collapse;width:100%}td,th{padding:12px;border-bottom:1px solid #40516b;text-align:left}</style><a href="index.html">Inicio</a> · <a href="dashboard.html">Dashboard</a><h1>Agenda y sugerencias T−60</h1><p>Horario Perú. Actualizado: '+html.escape(now.isoformat())+'</p><section id="agenda"><h2>Partidos de mañana: '+tomorrow+'</h2>'+table(['Hora','Competición','Partido','Estado'],agenda)+'</section><section id="sugerencias"><h2>Sugerencias T−60</h2><p>Capturas históricas, no cuotas en vivo. Comprueba horario y vigencia. Ninguna selección es segura.</p>'+table(['Partido','Mercado','Casa','Cuota capturada','Captura UTC'],picks)+'</section></html>'
    heading='<section id="sugerencias">'
    info='<section id="cambios"><h2>Aplazados y otros estados · fuera del calendario programado</h2><p>No se consideran confirmados para mañana. Los aplazados, cancelados y suspendidos no generan recomendaciones prepartido.</p>'+table(['Hora','País · competición','Partido','Estado'],exceptions)+'</section>'
    page=page.replace(heading,info+heading).replace('<th>Competición</th>','<th>País · competición</th>').replace('Horario Perú. Actualizado:', 'Horario Perú (UTC−5). Fuente: API-Football. Programado no garantiza que no haya cambios posteriores. Actualizado:')
    page=page.replace('<p>No hay sugerencias T−60 registradas todavía.</p></section><section id="cambios">','<p>No hay partidos programados disponibles.</p></section><section id="cambios">')
    old=table(['Partido','Mercado','Casa','Cuota capturada','Captura UTC'],picks)
    new=table(['Partido','Inicio · Perú','Selección','Casa','Cuota consultada','Probabilidad estimada','EV estimado','Análisis · hora Perú','Tipo de captura'],picks)
    page=page.replace(old,new).replace('Capturas históricas, no cuotas en vivo. Comprueba horario y vigencia. Ninguna selección es segura.','La hora de análisis indica cuándo terminó la revisión, no el instante exacto de cada cuota. Probabilidades del modelo sin calibración validada. EV +5% significa un retorno teórico medio de 0,05 por unidad apostada, no una ganancia garantizada. Los análisis anticipados del arranque no son capturas T−60. Comprueba cuota y vigencia antes de apostar.')
    page=page.replace('</style>','tr:has(td:nth-child(3):first-child){color:inherit} tr.principal{background:#153d35;border-left:4px solid #4de0ac}</style>').replace('<tr><td>','<tr><td>')
    import re
    page=re.sub(r'<tr>(?=(?:(?!</tr>).)*★ Principal:)', '<tr class="principal">',page)
    page=page.replace('<h2>Sugerencias T−60</h2>','<h2>Sugerencias T−60 · probabilidad estimada &gt;70%</h2><p>Principal resaltada en verde. Hasta dos alternativas válidas, no una combinada recomendada. No se fuerzan opciones si faltan cuotas o valor. Los registros anteriores pueden no contener alternativas.</p>')
    (ROOT/'automatico.html').write_text(page,encoding='utf-8')

if __name__=='__main__': build()
