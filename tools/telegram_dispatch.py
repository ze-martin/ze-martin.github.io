"""Private DPAPI sender. Claim before send: uncertain deliveries are never retried."""
import argparse
import base64
import json
import sqlite3
import subprocess
import shutil
import urllib.request
from datetime import datetime,timezone,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--nightly',action='store_true')
    parser.add_argument('--opportunities',action='store_true')
    parser.add_argument('--test',action='store_true')
    parser.add_argument('--technical',action='store_true',help='Alerta técnica deduplicada por día')
    args=parser.parse_args()
    folder=ROOT/'data/telegram_private'
    config=json.loads((folder/'connection.json').read_text(encoding='utf-8-sig'))
    script="$s=([IO.File]::ReadAllText('"+str(folder/'token.dpapi')+"',[Text.Encoding]::UTF8)).Trim() | ConvertTo-SecureString; $p=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($s); try{[Console]::Write([Runtime.InteropServices.Marshal]::PtrToStringBSTR($p))}finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($p)}"
    token=subprocess.run([shutil.which('pwsh.exe') or 'powershell.exe','-NoProfile','-Command',script],capture_output=True,check=True).stdout.decode().strip()
    def api(method,payload):
        request=urllib.request.Request('https://api.telegram.org/bot'+token+'/'+method,data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),headers={'Content-Type':'application/json; charset=utf-8'})
        response=json.load(urllib.request.urlopen(request,timeout=20))
        if not response.get('ok'): raise RuntimeError('Telegram rejected request')
        return response['result']
    if api('getMe',{}).get('username')!=config['bot_username']: raise RuntimeError('Wrong bot')
    db=sqlite3.connect(ROOT/'data/automatic_protocol.sqlite')
    db.execute('CREATE TABLE IF NOT EXISTS deliveries (id TEXT PRIMARY KEY,state TEXT NOT NULL,updated TEXT NOT NULL)')
    now=datetime.now(timezone.utc)
    messages=[]
    if args.technical:
        day=now.astimezone(ZoneInfo('America/Lima')).date().isoformat()
        messages.append(('technical:'+day,'APUESTAS: una ejecución automática falló. No equivale a Sin apuesta. Las cuotas y recomendaciones de ese bloque no están confirmadas como actualizadas. Se guardó un registro técnico local para revisión.'))
    if args.test:
        messages.append(('test:'+now.isoformat(),'APUESTAS: prueba integral de conexión. No es una recomendación ni activa apuestas.'))
    if args.nightly:
        day=(now.astimezone(ZoneInfo('America/Lima')).date()+timedelta(days=1)).isoformat()
        count=sum(1 for k,p in db.execute('SELECT kickoff,payload FROM jobs') if datetime.fromisoformat(k).astimezone(ZoneInfo('America/Lima')).date().isoformat()==day and json.loads(p)['fixture']['status']['short']=='NS')
        messages.append(('agenda:'+day,f'Agenda APUESTAS para {day}: {count} partidos programados. Horario Perú. https://ze-martin.github.io/automatico.html#agenda'))
    if args.opportunities:
        for fid,raw,kickoff in db.execute('SELECT o.fixture,o.payload,j.kickoff FROM outbox o JOIN jobs j ON j.id=o.fixture'):
            p=json.loads(raw);q=p['pick'];captured=datetime.fromisoformat(p['captured']);start=datetime.fromisoformat(kickoff)
            if not (timedelta(0)<=now-captured<=timedelta(minutes=10) and now<start and timedelta(0)<start-captured<=timedelta(minutes=60)):continue
            # Verify fixture again before sending, fail closed on any API error.
            import sys
            sys.path.insert(0,str(ROOT))
            from config import load_environment
            from apis.football_api import FootballAPI
            load_environment(ROOT/'.env')
            fixtures=FootballAPI()._api_get('fixtures',{'id':fid}).get('response',[])
            if len(fixtures)!=1 or fixtures[0]['fixture']['status']['short']!='NS':continue
            house=q.get('selection_bookmaker','');ev=q.get('ev_betano') if house=='Betano' else q.get('ev_api')
            text=f"{p['match']}\nSelección: {q['market']}\n{house}: cuota {q.get('selection_odds')}\nProbabilidad estimada: {q['probability']:.1%}\nEV estimado: {ev:+.1%}\nAnálisis terminado: {captured.astimezone(ZoneInfo('America/Lima')).strftime('%H:%M')} Perú. No es hora exacta de cada cuota.\nNo garantizado. Revisa vigencia. https://ze-martin.github.io/automatico.html#sugerencias"
            messages.append(('fixture:'+str(fid),text))
    for key,text in messages:
        with db:
            inserted=db.execute('INSERT OR IGNORE INTO deliveries VALUES(?,?,?)',(key,'sending',now.isoformat())).rowcount
        if not inserted:continue
        try:api('sendMessage',{'chat_id':config['chat_id'],'text':text})
        except Exception:
            with db:db.execute('UPDATE deliveries SET state=? WHERE id=?',('uncertain',key))
            raise RuntimeError('Delivery uncertain; no automatic retry') from None
        with db:db.execute('UPDATE deliveries SET state=? WHERE id=?',('sent',key))
    db.close()
    print('Telegram dispatch completed; no secrets logged')

if __name__=='__main__':
    try:main()
    except Exception:print('Telegram dispatch failed (details suppressed for privacy)');raise SystemExit(1)
