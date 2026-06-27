from __future__ import annotations

import argparse
import csv
import html
import json
from datetime import datetime
from pathlib import Path


REPLACEMENTS = [
    ("CARDS_TOTALS OVER.", "Tarjetas total +"),
    ("CARDS_TOTALS UNDER.", "Tarjetas total -"),
    ("CARDS_HOME OVER.", "Local tarjetas +"),
    ("CARDS_HOME UNDER.", "Local tarjetas -"),
    ("CARDS_AWAY OVER.", "Visita tarjetas +"),
    ("CARDS_AWAY UNDER.", "Visita tarjetas -"),
    ("FIRST_HALF_TOTALS OVER.", "1T +"),
    ("FIRST_HALF_TOTALS UNDER.", "1T -"),
    ("CORNERS_TOTALS OVER.", "Corners total +"),
    ("CORNERS_TOTALS UNDER.", "Corners total -"),
    ("CORNERS_HOME OVER.", "Local corners +"),
    ("CORNERS_HOME UNDER.", "Local corners -"),
    ("CORNERS_AWAY OVER.", "Visita corners +"),
    ("CORNERS_AWAY UNDER.", "Visita corners -"),
    ("TOTALS OVER.", "Goles +"),
    ("TOTALS UNDER.", "Goles -"),
    ("DRAW_NO_BET HOME", "DNB local"),
    ("DRAW_NO_BET AWAY", "DNB visita"),
    ("1X2 HOME", "Gana local"),
    ("1X2 AWAY", "Gana visita"),
    ("BTTS YES", "BTTS sí"),
    ("BTTS NO", "BTTS no"),
]


def clean(value: str | None) -> str:
    text = value or ""
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    return text


def pct(value):
    return "" if value is None else f"{value * 100:.1f}%"


def dec(value):
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def money(value):
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def build_rows(data: dict):
    rows = []
    summary = []
    top_ev = {}
    for result in data["results"]:
        rec = result.get("recommended_pick") or {}
        markets = result.get("all_markets", [])
        with_odds = [m for m in markets if m.get("odds") is not None]
        ev_pos = [m for m in markets if m.get("ev") is not None and m.get("ev") > 0]
        summary.append(
            {
                "hora": result.get("time_lima", ""),
                "partido": result.get("match", ""),
                "pick": clean(rec.get("market")),
                "prob": pct(rec.get("probability")),
                "cuota": money(rec.get("odds")),
                "ev": money(rec.get("ev")),
                "mercados": len(markets),
                "con_cuota": len(with_odds),
                "ev_pos": len(ev_pos),
            }
        )
        top = [m for m in with_odds if m.get("ev") is not None and m.get("ev") > 0]
        top_ev[result.get("match", "")] = sorted(
            top,
            key=lambda m: ((m.get("probability") or 0), (m.get("ev") or 0)),
            reverse=True,
        )
        for market in markets:
            rows.append(
                {
                    "fecha": result.get("date_lima", ""),
                    "hora": result.get("time_lima", ""),
                    "partido": result.get("match", ""),
                    "bookmaker": market.get("bookmaker") or result.get("bookmaker") or "",
                    "pick": clean(market.get("market")),
                    "market_original": market.get("market") or "",
                    "probabilidad": pct(market.get("probability")),
                    "prob_num": dec(market.get("probability")),
                    "cuota": money(market.get("odds")),
                    "ev": money(market.get("ev")),
                    "ev_num": dec(market.get("ev")),
                    "estado": market.get("status") or "",
                    "confianza": market.get("confidence") or "",
                    "fuente": market.get("source") or "",
                    "razon": market.get("reason") or "",
                    "riesgo": market.get("risk") or "",
                }
            )
    return rows, summary, top_ev


def write_csv(rows: list[dict], path: Path) -> None:
    fields = [
        "fecha",
        "hora",
        "partido",
        "bookmaker",
        "pick",
        "market_original",
        "probabilidad",
        "prob_num",
        "cuota",
        "ev",
        "ev_num",
        "estado",
        "confianza",
        "fuente",
        "razon",
        "riesgo",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_html(rows: list[dict], summary: list[dict], src: Path, title: str, path: Path) -> None:
    summary_rows = "\n".join(
        "<tr>"
        + "".join(
            f"<td>{html.escape(str(item[key]))}</td>"
            for key in ["hora", "partido", "pick", "prob", "cuota", "ev", "mercados", "con_cuota", "ev_pos"]
        )
        + "</tr>"
        for item in summary
    )
    options = "\n".join(
        f'<option value="{html.escape(item["partido"])}">{html.escape(item["partido"])}</option>'
        for item in summary
    )
    body_rows = []
    for idx, row in enumerate(rows, 1):
        ev_value = row["ev_num"]
        ev_class = "evpos" if ev_value and float(ev_value) > 0 else ("evneg" if ev_value and float(ev_value) < 0 else "noev")
        cells = [
            idx,
            row["hora"],
            row["partido"],
            row["pick"],
            row["probabilidad"],
            row["cuota"],
            row["ev"],
            row["estado"],
            row["confianza"],
            row["fuente"],
            row["riesgo"],
        ]
        body_rows.append(
            '<tr class="{cls}" data-match="{match}" data-ev="{ev}" data-odds="{odds}">{cells}</tr>'.format(
                cls=ev_class,
                match=html.escape(row["partido"], quote=True),
                ev=html.escape(row["ev_num"], quote=True),
                odds="1" if row["cuota"] else "0",
                cells="".join(f"<td>{html.escape(str(value))}</td>" for value in cells),
            )
        )

    html_text = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)}</title><style>
:root {{--bg:#0b1020;--panel:#121a2c;--line:#26344f;--text:#e9eefb;--muted:#9fb0d0}}body{{margin:0;font-family:Inter,Segoe UI,system-ui,Arial,sans-serif;background:var(--bg);color:var(--text)}}header{{padding:24px 28px;border-bottom:1px solid var(--line);background:linear-gradient(135deg,#101a34,#0b1020);position:sticky;top:0;z-index:4}}h1{{margin:0 0 8px;font-size:24px}}.meta{{color:var(--muted);font-size:13px}}main{{padding:22px 28px 50px}}.card{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;margin-bottom:18px;box-shadow:0 10px 30px rgba(0,0,0,.18)}}.controls{{display:grid;grid-template-columns:2fr 1.3fr 1fr 1fr;gap:10px;align-items:end}}label{{display:block;color:var(--muted);font-size:12px;margin-bottom:5px}}input,select,button{{width:100%;box-sizing:border-box;border:1px solid var(--line);background:#0e1628;color:var(--text);border-radius:10px;padding:10px 12px;font-size:14px}}button{{cursor:pointer;background:#1f6feb;border-color:#388bfd;font-weight:650}}.tablewrap{{overflow:auto;max-height:72vh;border:1px solid var(--line);border-radius:12px}}table{{border-collapse:collapse;width:100%;min-width:1100px}}th,td{{border-bottom:1px solid var(--line);padding:8px 10px;text-align:left;font-size:13px;vertical-align:top}}th{{position:sticky;top:0;background:#18233a;z-index:2;color:#cfe0ff;cursor:pointer;white-space:nowrap}}tr:hover td{{background:#182238}}.evpos td{{background:rgba(29,108,70,.22)}}.evneg td{{background:rgba(120,40,52,.16)}}.noev td{{color:#aab5ca}}.badge{{display:inline-block;padding:2px 7px;border-radius:999px;font-size:12px;background:#203253;color:#cfe0ff}}.small{{color:var(--muted);font-size:12px}}.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:12px}}.kpi{{background:#0e1628;border:1px solid var(--line);border-radius:12px;padding:12px}}.kpi b{{display:block;font-size:22px}}@media(max-width:900px){{.controls,.kpis{{grid-template-columns:1fr}}main,header{{padding-left:14px;padding-right:14px}}}}
</style></head><body><header><h1>{html.escape(title)}</h1><div class="meta">Generado: {html.escape(datetime.now().strftime("%Y-%m-%d %H:%M"))} · Fuente: {html.escape(str(src))} · {len(summary)} partidos · {len(rows)} mercados totales</div></header><main><section class="card"><h2>Resumen</h2><div class="kpis"><div class="kpi"><span class="small">Partidos</span><b>{len(summary)}</b></div><div class="kpi"><span class="small">Mercados totales</span><b>{len(rows)}</b></div><div class="kpi"><span class="small">Con cuota</span><b>{sum(1 for row in rows if row["cuota"])}</b></div><div class="kpi"><span class="small">EV positivo</span><b>{sum(1 for row in rows if row["ev_num"] and float(row["ev_num"]) > 0)}</b></div></div><div class="tablewrap" style="max-height:none;margin-top:14px"><table id="summary"><thead><tr><th>Hora</th><th>Partido</th><th>Pick principal</th><th>Prob</th><th>Cuota</th><th>EV</th><th>Mercados</th><th>Con cuota</th><th>EV+</th></tr></thead><tbody>{summary_rows}</tbody></table></div></section><section class="card"><h2>Todos los mercados</h2><div class="controls"><div><label>Buscar</label><input id="q" placeholder="Ej: corners, goles +1.5, Canada"></div><div><label>Partido</label><select id="match"><option value="">Todos</option>{options}</select></div><div><label>Filtro</label><select id="filter"><option value="all">Todos</option><option value="evpos">Solo EV positivo</option><option value="odds">Solo con cuota</option><option value="noodds">Sin cuota</option></select></div><div><label>Acción</label><button onclick="resetFilters()">Limpiar filtros</button></div></div><p class="small"><span class="badge">Tip</span> Click en encabezados para ordenar. Verde = EV positivo. Gris = sin cuota/EV.</p><div class="tablewrap"><table id="markets"><thead><tr><th>#</th><th>Hora</th><th>Partido</th><th>Pick</th><th>Prob</th><th>Cuota</th><th>EV</th><th>Estado</th><th>Confianza</th><th>Fuente</th><th>Riesgo</th></tr></thead><tbody>{"".join(body_rows)}</tbody></table></div></section></main><script>
const q=document.getElementById('q');const match=document.getElementById('match');const filter=document.getElementById('filter');const rows=Array.from(document.querySelectorAll('#markets tbody tr'));function applyFilters(){{const term=q.value.toLowerCase().trim();const m=match.value;const f=filter.value;for(const tr of rows){{const txt=tr.innerText.toLowerCase();let ok=(!term||txt.includes(term))&&(!m||tr.dataset.match===m);if(f==='evpos')ok=ok&&parseFloat(tr.dataset.ev||'-999')>0;if(f==='odds')ok=ok&&tr.dataset.odds==='1';if(f==='noodds')ok=ok&&tr.dataset.odds==='0';tr.style.display=ok?'':'none';}}}}function resetFilters(){{q.value='';match.value='';filter.value='all';applyFilters();}}[q,match,filter].forEach(el=>el.addEventListener('input',applyFilters));document.querySelectorAll('th').forEach((th,idx)=>{{th.addEventListener('click',()=>{{const table=th.closest('table');const tbody=table.querySelector('tbody');const trs=Array.from(tbody.querySelectorAll('tr'));const asc=th.dataset.asc!=='1';trs.sort((a,b)=>{{const av=a.children[idx]?.innerText||'';const bv=b.children[idx]?.innerText||'';const an=parseFloat(av.replace('%',''));const bn=parseFloat(bv.replace('%',''));if(!Number.isNaN(an)&&!Number.isNaN(bn))return asc?an-bn:bn-an;return asc?av.localeCompare(bv):bv.localeCompare(av);}});th.dataset.asc=asc?'1':'0';trs.forEach(tr=>tbody.appendChild(tr));}});}});
</script></body></html>"""
    path.write_text(html_text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--output-dir", default="outputs")
    args = parser.parse_args()

    src = Path(args.source)
    out = Path(args.output_dir)
    out.mkdir(exist_ok=True)
    data = json.load(open(src, encoding="utf-8"))
    rows, summary, top_ev = build_rows(data)

    html_path = out / f"{args.prefix}.html"
    csv_path = out / f"{args.prefix}_todos_los_mercados.csv"
    write_csv(rows, csv_path)
    write_html(rows, summary, src, f"Protocolo completo - Mundial 2026 - {args.date}", html_path)

    print(html_path.resolve())
    print(csv_path.resolve())
    print("matches", len(summary))
    print("markets", len(rows))
    print("with_odds", sum(1 for row in rows if row["cuota"]))
    print("ev_positive", sum(1 for row in rows if row["ev_num"] and float(row["ev_num"]) > 0))
    print("summary")
    for item in summary:
        print(item)
    print("top_ev")
    for match, markets in top_ev.items():
        print("###", match)
        for market in markets[:8]:
            print(clean(market.get("market")), pct(market.get("probability")), money(market.get("odds")), money(market.get("ev")))


if __name__ == "__main__":
    main()
