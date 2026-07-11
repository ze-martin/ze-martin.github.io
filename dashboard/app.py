from __future__ import annotations

import os
from datetime import date

import requests
import streamlit as st

from config import load_environment


load_environment()


API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")


st.set_page_config(page_title="Sistema de Apuestas", layout="wide")
st.title("Sistema de Apuestas")

with st.sidebar:
    from_date = st.date_input("Desde", value=date.today())
    to_date = st.date_input("Hasta", value=date.today())
    leagues = st.text_input("Ligas", value="")
    auto_refresh = st.checkbox("Actualizacion en tiempo real", value=True)
    run_now = st.button("Ejecutar pipeline")

if auto_refresh:
    st.caption("La vista se actualiza automaticamente.")
    st.markdown("<meta http-equiv='refresh' content='30'>", unsafe_allow_html=True)

if run_now:
    response = requests.get(
        f"{API_URL}/run",
        params={"from": from_date.isoformat(), "to": to_date.isoformat(), "leagues": leagues},
        timeout=120,
    )
    if response.ok:
        payload = response.json()
        for message in payload.get("messages", []):
            st.warning(message)
        st.success(f"Pipeline ejecutado. Partidos: {payload.get('matches', 0)} Picks: {len(payload.get('picks', []))}")
    else:
        st.error(response.text)

try:
    results = requests.get(f"{API_URL}/results", params={"limit": 200}, timeout=20)
    results.raise_for_status()
    rows = results.json().get("results", [])
except Exception as exc:
    rows = []
    st.warning(f"No se pudieron cargar resultados: {exc}")

if rows:
    ev_values = [float(row["ev"]) for row in rows if row.get("ev") is not None]
    st.metric("EV promedio", f"{(sum(ev_values) / len(ev_values)):.2%}" if ev_values else "0.00%")
    st.dataframe(rows, use_container_width=True, hide_index=True)
else:
    st.metric("EV promedio", "0.00%")
    st.info("No hay picks guardados todavia.")
