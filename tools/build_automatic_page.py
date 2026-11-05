"""Export only public fixtures and forecasts, never credentials or tickets."""
import html
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT = Path(__file__).resolve().parents[1]

def build():
    now = datetime.now(ZoneInfo('America/Lima'))
    tomorrow = (now.date()+timedelta(days=1)).isoformat()
    agenda, picks = [], []
    db = sqlite3.connect(f'file:{(ROOT/"data/automatic_protocol.sqlite").as_posix()}?mode=ro',uri=True)
    try:
        for kickoff, raw in db.execute('SELECT kickoff,payload FROM jobs ORDER BY kickoff'):
            local = datetime.fromisoformat(kickoff).astimezone(ZoneInfo('America/Lima'))
            if local.date().isoformat() == tomorrow:
                f=json.loads(raw)
                agenda.append([local.strftime('%H:%M'),f['league']['name'],f['teams']['home']['name']+' — '+f['teams']['away']['name'],f['fixture']['status']['short']])
        for raw, in db.execute('SELECT payload FROM outbox ORDER BY fixture DESC'):
            p=json.loads(raw); q=p['pick']
            picks.append([p['match'],q['market'],q.get('selection_bookmaker',''),q.get('selection_odds',''),p['captured']])
    finally:
        db.close()
    def table(headers, rows):
        esc=lambda x:html.escape(str(x))
        return '<div class="scroll"><table><tr>'+''.join('<th>'+esc(x)+'</th>' for x in headers)+'</tr>'+''.join('<tr>'+''.join('<td>'+esc(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</table></div>' if rows else '<p>No hay sugerencias T−60 registradas todavía.</p>'
    page='<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Agenda y sugerencias T−60</title><style>body{background:#0b1220;color:#eef3ff;font:16px system-ui;max-width:1100px;margin:24px auto;padding:16px}a{color:#74baff}section{background:#172238;padding:20px;margin:20px 0;border-radius:12px}.scroll{overflow:auto}table{border-collapse:collapse;width:100%}td,th{padding:12px;border-bottom:1px solid #40516b;text-align:left}</style><a href="index.html">Inicio</a> · <a href="dashboard.html">Dashboard</a><h1>Agenda y sugerencias T−60</h1><p>Horario Perú. Actualizado: '+html.escape(now.isoformat())+'</p><section id="agenda"><h2>Partidos de mañana: '+tomorrow+'</h2>'+table(['Hora','Competición','Partido','Estado'],agenda)+'</section><section id="sugerencias"><h2>Sugerencias T−60</h2><p>Capturas históricas, no cuotas en vivo. Comprueba horario y vigencia. Ninguna selección es segura.</p>'+table(['Partido','Mercado','Casa','Cuota capturada','Captura UTC'],picks)+'</section></html>'
    (ROOT/'automatico.html').write_text(page,encoding='utf-8')

if __name__=='__main__': build()
