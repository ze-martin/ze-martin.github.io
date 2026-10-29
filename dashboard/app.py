"""Private dashboard: actual tickets never go to GitHub Pages."""
import json
import sqlite3
import sys
import os
import requests
from pathlib import Path
from datetime import datetime,timezone,date
import streamlit as st
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import load_environment
from db.performance_store import PerformanceStore
from analysis.policy import apply_policy
load_environment()
st.set_page_config(page_title='Protocolo · control de decisiones',layout='wide')
st.title('Protocolo · control de decisiones')
st.caption('El acierto histórico cuenta un pick principal por partido y versión, no todas las opciones.')
store=PerformanceStore();store.initialize()
with sqlite3.connect(ROOT/'data/protocol_memory.sqlite') as conn:
    reports=conn.execute('SELECT report_date,enriched_json FROM protocol_report ORDER BY report_date DESC').fetchall()
if not reports:
    st.info('Genera un protocolo para empezar.');st.stop()
with st.sidebar:
    day=st.selectbox('Fecha',[r[0] for r in reports])
    query=st.text_input('Buscar equipo')
    st.warning('Estimaciones no calibradas: ninguna apuesta es segura.')
    st.caption('Vista privada local. GitHub Pages no recibe tickets ni importes.')
    with st.expander('Ejecutar sistema base por API'):
        start=st.date_input('Desde',value=date.today());end=st.date_input('Hasta',value=date.today())
        leagues=st.text_input('IDs de ligas, separados por coma')
        if st.button('Ejecutar pipeline base'):
            try:
                response=requests.get(os.getenv('API_URL','http://127.0.0.1:8000')+'/run',params={'from':start.isoformat(),'to':end.isoformat(),'leagues':leagues},timeout=120)
                response.raise_for_status();st.json(response.json())
            except Exception as exc:st.error(str(exc))
        st.caption('Para generar/publicar el protocolo completo usa tools/run_published_protocol.py.')
data=apply_policy(json.loads(Path(dict(reports)[day]).read_text(encoding='utf-8')))
tabs=st.tabs(['★ Principales','Alternativas','Todos los mercados','Jugadores','Histórico','Apuestas reales · privado'])
matches=[r for r in data['results'] if query.lower() in r['match'].lower()]
def row(r,m):
    return {'Partido':r['match'],'Mercado':m.get('market',m.get('key')),'Rol':m.get('selection_role'),
            'Probabilidad estimada':m.get('probability'),'Casa API':m.get('bookmaker_api') or r.get('bookmaker'),
            'Cuota API':m.get('odds_api',m.get('odds')),'EV API':m.get('ev_api',m.get('ev')),
            'Cuota Betano':m.get('odds_betano'),'EV Betano':m.get('ev_betano'),
            'Motivo':'; '.join(m.get('selection_reasons') or [])}
with tabs[0]:
    st.info('Principal = candidato provisional que pasa los filtros, no el más seguro. Si ninguno los cumple, Sin apuesta.')
    st.dataframe([row(r,r['recommended_pick']) if r.get('recommended_pick') else {'Partido':r['match'],'Mercado':'Sin apuesta'} for r in matches],hide_index=True,use_container_width=True)
with tabs[1]:
    st.warning('Opciones para elegir, no una combinada con probabilidad conjunta calculada.')
    st.dataframe([row(r,m) for r in matches for m in r.get('alternative_picks',[])],hide_index=True,use_container_width=True)
with tabs[2]:
    role=st.selectbox('Rol',['Todos','Principal','Alternativa','Solo análisis'])
    st.dataframe([row(r,m) for r in matches for m in r.get('all_markets',[]) if role=='Todos' or m.get('selection_role')==role],hide_index=True,use_container_width=True)
with tabs[3]:
    st.info('Rachas y escenarios por minutos: no cuentan como aciertos principales. Verificar muestra, titularidad y cuota exacta.')
    players=[]
    for r in matches:
        for p in (r.get('player_analysis') or {}).get('options',[]):
            players.append({'Partido':r['match'],'Jugador':p['player'],'Mercado':p['market'],'Minutos':p['minutes'],
                            'Partidos':p['appearances'],'Últimos 3':p['last3'],'Por 90':p['per90'],
                            'P si juega 60':p['p_if_60_minutes'],'P si juega 90':p['p_if_90_minutes'],
                            'Cuotas API / casa':'; '.join(f"{q['bookmaker']} {q['odds']}" for q in p['api_quotes']),
                            'Titular confirmado':p['starter_confirmed'],'Estado':p['status']})
    st.dataframe(players,hide_index=True,use_container_width=True)
with tabs[4]:
    perf=store.public_summary();st.caption(perf['scope'])
    for group in perf['groups']:
        st.subheader(group['model_version']+' · '+group['role'])
        a,b,c=st.columns(3)
        a.metric('Ganados / evaluados',f"{group['won']} / {group['n']}")
        b.metric('Acierto',f"{group['hit_rate']:.1%}" if group['hit_rate'] is not None else 'Sin datos')
        c.metric('Pendientes',group['pending'])
        st.dataframe([{'Casa':house,**values} for house,values in group['houses'].items()],hide_index=True)
        st.dataframe(group['reliability'],hide_index=True)
with tabs[5]:
    st.warning('Registrar NO coloca apuestas. Guarda solo un ticket que confirmas haber realizado.')
    st.caption('Registro de principales y alternativas congeladas. Las observaciones de jugadores no se atribuyen automáticamente a este modelo.')
    st.json(store.actual_summary());picks=store.rows()+store.rows('alternativa')
    if picks:
        with st.form('actual_bet'):
            index=st.selectbox('Pick registrado',range(len(picks)),format_func=lambda i:picks[i]['report_date']+' · '+picks[i]['model_version']+' · '+picks[i]['role']+' · '+picks[i]['match_name']+' · '+picks[i]['market_key'])
            ticket=st.text_input('ID de ticket único');bookmaker=st.text_input('Casa utilizada')
            odds=st.number_input('Cuota tomada',min_value=1.01,value=1.50)
            stake=st.number_input('Importe real',min_value=.01,value=1.0)
            placed=st.text_input('Hora real de colocación, ISO con zona',value=datetime.now(timezone.utc).isoformat())
            confirmed=st.checkbox('Confirmo que este ticket ya fue colocado por mí')
            submit=st.form_submit_button('Registrar ticket privado')
        if submit:
            try:
                if not confirmed:raise ValueError('Debes confirmar que la apuesta existe')
                store.record_bet(ticket,picks[index]['id'],bookmaker,odds,stake,placed)
                st.success('Ticket registrado localmente, no publicado.')
            except Exception as exc:st.error(str(exc))
