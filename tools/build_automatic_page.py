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
        for raw, in db.execute('SELECT payload FROM outbox ORDER BY fixture DESC'):
            p=json.loads(raw); q=p['pick']
            picks.append([p['match'],q['market'],q.get('selection_bookmaker',''),q.get('selection_odds',''),p['captured']])
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
    (ROOT/'automatico.html').write_text(page,encoding='utf-8')

if __name__=='__main__': build()
