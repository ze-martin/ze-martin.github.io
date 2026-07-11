from __future__ import annotations

import argparse
import csv
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any


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
    ("TEAM_TOTAL_HOME OVER.", "Local goles +"),
    ("TEAM_TOTAL_HOME UNDER.", "Local goles -"),
    ("TEAM_TOTAL_AWAY OVER.", "Visita goles +"),
    ("TEAM_TOTAL_AWAY UNDER.", "Visita goles -"),
    ("DRAW_NO_BET HOME", "DNB local"),
    ("DRAW_NO_BET AWAY", "DNB visita"),
    ("1X2 HOME", "Gana local"),
    ("1X2 DRAW", "Empate"),
    ("1X2 AWAY", "Gana visita"),
    ("BTTS YES", "BTTS sí"),
    ("BTTS NO", "BTTS no"),
]


def clean(value: str | None) -> str:
    text = value or ""
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    return text


def pct(value: Any) -> str:
    return "" if value is None else f"{float(value) * 100:.1f}%"


def dec(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def money(value: Any) -> str:
    if value is None:
        return ""
    return f"{float(value):.2f}" if isinstance(value, (float, int)) else str(value)


def numeric(row: dict, primary: str, fallback: str | None = None) -> Any:
    value = row.get(primary)
    if value is None and fallback:
        value = row.get(fallback)
    return value


def build_rows(data: dict) -> tuple[list[dict], list[dict], dict[str, list[dict]]]:
    rows: list[dict] = []
    summary: list[dict] = []
    top_ev: dict[str, list[dict]] = {}

    for result in data["results"]:
        rec = result.get("recommended_pick") or {}
        markets = result.get("all_markets", [])
        if not rec:
            betano_candidates = [
                market
                for market in markets
                if market.get("odds_betano") is not None and market.get("ev_betano") is not None
            ]
            positive_betano = [market for market in betano_candidates if market.get("ev_betano", 0) > 0]
            pool = positive_betano or betano_candidates
            if pool:
                rec = sorted(
                    pool,
                    key=lambda market: (
                        market.get("ev_betano") or -999,
                        market.get("probability") or 0,
                    ),
                    reverse=True,
                )[0]
        with_api_odds = [m for m in markets if numeric(m, "odds_api", "odds") is not None]
        with_betano_odds = [m for m in markets if m.get("odds_betano") is not None]
        ev_api_pos = [m for m in markets if numeric(m, "ev_api", "ev") is not None and numeric(m, "ev_api", "ev") > 0]
        ev_betano_pos = [m for m in markets if m.get("ev_betano") is not None and m["ev_betano"] > 0]

        summary.append(
            {
                "hora": result.get("time_lima", ""),
                "partido": result.get("match", ""),
                "pick": clean(rec.get("market")),
                "prob": pct(rec.get("probability")),
                "cuota_api": money(numeric(rec, "odds_api", "odds")),
                "ev_api": money(numeric(rec, "ev_api", "ev")),
                "cuota_betano": money(rec.get("odds_betano")),
                "ev_betano": money(rec.get("ev_betano")),
                "mercados": len(markets),
                "con_api": len(with_api_odds),
                "con_betano": len(with_betano_odds),
                "ev_api_pos": len(ev_api_pos),
                "ev_betano_pos": len(ev_betano_pos),
            }
        )

        top = [m for m in markets if numeric(m, "ev_api", "ev") is not None and numeric(m, "ev_api", "ev") > 0]
        top_ev[result.get("match", "")] = sorted(
            top,
            key=lambda m: ((m.get("probability") or 0), (numeric(m, "ev_api", "ev") or 0)),
            reverse=True,
        )

        for market in markets:
            api_odds = numeric(market, "odds_api", "odds")
            api_ev = numeric(market, "ev_api", "ev")
            rows.append(
                {
                    "fecha": result.get("date_lima", ""),
                    "hora": result.get("time_lima", ""),
                    "partido": result.get("match", ""),
                    "bookmaker_api": market.get("bookmaker_api") or market.get("bookmaker") or result.get("bookmaker") or "",
                    "bookmaker_betano": market.get("bookmaker_betano") or ("Betano" if market.get("odds_betano") is not None else ""),
                    "pick": clean(market.get("market")),
                    "market_original": market.get("market") or "",
                    "key": market.get("key") or "",
                    "probabilidad": pct(market.get("probability")),
                    "prob_num": dec(market.get("probability")),
                    "cuota_api": money(api_odds),
                    "ev_api": money(api_ev),
                    "ev_api_num": dec(api_ev),
                    "cuota_betano": money(market.get("odds_betano")),
                    "ev_betano": money(market.get("ev_betano")),
                    "ev_betano_num": dec(market.get("ev_betano")),
                    "estado_api": market.get("status") or "",
                    "estado_betano": market.get("status_betano") or "",
                    "confianza": market.get("confidence") or "",
                    "fuente": market.get("source") or "",
                    "razon": market.get("reason") or "",
                    "riesgo": market.get("risk") or "",
                    "betano_url": market.get("betano_source_url") or result.get("betano_source_url") or "",
                }
            )
    return rows, summary, top_ev


def write_csv(rows: list[dict], path: Path) -> None:
    fields = [
        "fecha",
        "hora",
        "partido",
        "bookmaker_api",
        "bookmaker_betano",
        "pick",
        "market_original",
        "key",
        "probabilidad",
        "prob_num",
        "cuota_api",
        "ev_api",
        "ev_api_num",
        "cuota_betano",
        "ev_betano",
        "ev_betano_num",
        "estado_api",
        "estado_betano",
        "confianza",
        "fuente",
        "razon",
        "riesgo",
        "betano_url",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def ev_class(row: dict) -> str:
    values = []
    for key in ("ev_api_num", "ev_betano_num"):
        if row.get(key):
            values.append(float(row[key]))
    if any(value > 0 for value in values):
        return "evpos"
    if any(value < 0 for value in values):
        return "evneg"
    return "noev"


def write_html(rows: list[dict], summary: list[dict], src: Path, title: str, path: Path) -> None:
    summary_keys = [
        "hora",
        "partido",
        "pick",
        "prob",
        "cuota_api",
        "ev_api",
        "cuota_betano",
        "ev_betano",
        "mercados",
        "con_api",
        "con_betano",
        "ev_api_pos",
        "ev_betano_pos",
    ]
    summary_rows = "\n".join(
        "<tr>" + "".join(f"<td>{html.escape(str(item[key]))}</td>" for key in summary_keys) + "</tr>"
        for item in summary
    )
    options = "\n".join(
        f'<option value="{html.escape(item["partido"])}">{html.escape(item["partido"])}</option>'
        for item in summary
    )

    body_rows = []
    for idx, row in enumerate(rows, 1):
        cells = [
            idx,
            row["hora"],
            row["partido"],
            row["pick"],
            row["probabilidad"],
            row["bookmaker_api"],
            row["cuota_api"],
            row["ev_api"],
            row["bookmaker_betano"],
            row["cuota_betano"],
            row["ev_betano"],
            row["estado_api"],
            row["estado_betano"],
            row["confianza"],
            row["fuente"],
            row["riesgo"],
        ]
        body_rows.append(
            '<tr class="{cls}" data-match="{match}" data-ev-api="{ev_api}" data-ev-betano="{ev_betano}" data-api="{api}" data-betano="{betano}">{cells}</tr>'.format(
                cls=ev_class(row),
                match=html.escape(row["partido"], quote=True),
                ev_api=html.escape(row["ev_api_num"], quote=True),
                ev_betano=html.escape(row["ev_betano_num"], quote=True),
                api="1" if row["cuota_api"] else "0",
                betano="1" if row["cuota_betano"] else "0",
                cells="".join(f"<td>{html.escape(str(value))}</td>" for value in cells),
            )
        )

    html_text = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root{{--bg:#0b1020;--panel:#121a2c;--line:#26344f;--text:#e9eefb;--muted:#9fb0d0}}
body{{margin:0;font-family:Inter,Segoe UI,system-ui,Arial,sans-serif;background:var(--bg);color:var(--text)}}
header{{padding:24px 28px;border-bottom:1px solid var(--line);background:linear-gradient(135deg,#101a34,#0b1020);position:sticky;top:0;z-index:4}}
h1{{margin:0 0 8px;font-size:24px}}h2{{margin-top:0}}.meta,.small{{color:var(--muted);font-size:12px}}
main{{padding:22px 28px 50px}}.card{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;margin-bottom:18px;box-shadow:0 10px 30px rgba(0,0,0,.18)}}
.controls{{display:grid;grid-template-columns:2fr 1.3fr 1fr 1fr;gap:10px;align-items:end}}label{{display:block;color:var(--muted);font-size:12px;margin-bottom:5px}}
input,select,button{{width:100%;box-sizing:border-box;border:1px solid var(--line);background:#0e1628;color:var(--text);border-radius:10px;padding:10px 12px;font-size:14px}}
button{{cursor:pointer;background:#1f6feb;border-color:#388bfd;font-weight:650}}.tablewrap{{overflow:auto;max-height:72vh;border:1px solid var(--line);border-radius:12px}}
table{{border-collapse:collapse;width:100%;min-width:1450px}}th,td{{border-bottom:1px solid var(--line);padding:8px 10px;text-align:left;font-size:13px;vertical-align:top}}
th{{position:sticky;top:0;background:#18233a;z-index:2;color:#cfe0ff;cursor:pointer;white-space:nowrap}}tr:hover td{{background:#182238}}
.evpos td{{background:rgba(29,108,70,.22)}}.evneg td{{background:rgba(120,40,52,.16)}}.noev td{{color:#aab5ca}}
.badge{{display:inline-block;padding:2px 7px;border-radius:999px;font-size:12px;background:#203253;color:#cfe0ff}}.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:12px}}
.kpi{{background:#0e1628;border:1px solid var(--line);border-radius:12px;padding:12px}}.kpi b{{display:block;font-size:22px}}
@media(max-width:900px){{.controls,.kpis{{grid-template-columns:1fr}}main,header{{padding-left:14px;padding-right:14px}}}}
</style>
</head>
<body>
<header>
  <h1>{html.escape(title)}</h1>
  <div class="meta">Generado: {html.escape(datetime.now().strftime("%Y-%m-%d %H:%M"))} · Fuente: {html.escape(str(src))} · {len(summary)} partidos · {len(rows)} mercados</div>
</header>
<main>
  <section class="card">
    <h2>Resumen</h2>
    <div class="kpis">
      <div class="kpi"><span class="small">Partidos</span><b>{len(summary)}</b></div>
      <div class="kpi"><span class="small">Mercados</span><b>{len(rows)}</b></div>
      <div class="kpi"><span class="small">Con cuota 10Bet/API</span><b>{sum(1 for row in rows if row["cuota_api"])}</b></div>
      <div class="kpi"><span class="small">Con cuota Betano</span><b>{sum(1 for row in rows if row["cuota_betano"])}</b></div>
    </div>
    <p class="small"><span class="badge">Nota</span> 10Bet/API viene del proveedor del protocolo. Betano se scrapea en vivo desde betano.pe y puede cambiar.</p>
    <div class="tablewrap" style="max-height:none;margin-top:14px">
      <table id="summary">
        <thead><tr><th>Hora</th><th>Partido</th><th>Pick principal</th><th>Prob</th><th>Cuota 10Bet/API</th><th>EV 10Bet/API</th><th>Cuota Betano</th><th>EV Betano</th><th>Mercados</th><th>Con 10Bet/API</th><th>Con Betano</th><th>EV+ 10Bet/API</th><th>EV+ Betano</th></tr></thead>
        <tbody>{summary_rows}</tbody>
      </table>
    </div>
  </section>
  <section class="card">
    <h2>Todos los mercados</h2>
    <div class="controls">
      <div><label>Buscar</label><input id="q" placeholder="Ej: corners, goles +1.5, Argentina"></div>
      <div><label>Partido</label><select id="match"><option value="">Todos</option>{options}</select></div>
      <div><label>Filtro</label><select id="filter"><option value="all">Todos</option><option value="evpos">EV positivo en alguna casa</option><option value="api">Con cuota 10Bet/API</option><option value="betano">Con cuota Betano</option><option value="no_betano">Sin cuota Betano</option></select></div>
      <div><label>Acción</label><button onclick="resetFilters()">Limpiar filtros</button></div>
    </div>
    <p class="small"><span class="badge">Tip</span> Click en encabezados para ordenar. Verde = EV positivo en 10Bet/API o Betano.</p>
    <div class="tablewrap">
      <table id="markets">
        <thead><tr><th>#</th><th>Hora</th><th>Partido</th><th>Pick</th><th>Prob</th><th>Book 10Bet/API</th><th>Cuota 10Bet/API</th><th>EV 10Bet/API</th><th>Book Betano</th><th>Cuota Betano</th><th>EV Betano</th><th>Estado 10Bet/API</th><th>Estado Betano</th><th>Confianza</th><th>Fuente</th><th>Riesgo</th></tr></thead>
        <tbody>{"".join(body_rows)}</tbody>
      </table>
    </div>
  </section>
</main>
<script>
const q=document.getElementById('q');
const match=document.getElementById('match');
const filter=document.getElementById('filter');
const rows=Array.from(document.querySelectorAll('#markets tbody tr'));
function pos(v){{const n=parseFloat(v||'-999');return !Number.isNaN(n)&&n>0;}}
function applyFilters(){{
  const term=q.value.toLowerCase().trim();
  const m=match.value;
  const f=filter.value;
  for(const tr of rows){{
    const txt=tr.innerText.toLowerCase();
    let ok=(!term||txt.includes(term))&&(!m||tr.dataset.match===m);
    if(f==='evpos') ok=ok&&(pos(tr.dataset.evApi)||pos(tr.dataset.evBetano));
    if(f==='api') ok=ok&&tr.dataset.api==='1';
    if(f==='betano') ok=ok&&tr.dataset.betano==='1';
    if(f==='no_betano') ok=ok&&tr.dataset.betano==='0';
    tr.style.display=ok?'':'none';
  }}
}}
function resetFilters(){{q.value='';match.value='';filter.value='all';applyFilters();}}
[q,match,filter].forEach(el=>el.addEventListener('input',applyFilters));
document.querySelectorAll('th').forEach((th,idx)=>{{
  th.addEventListener('click',()=>{{
    const table=th.closest('table'); const tbody=table.querySelector('tbody'); const trs=Array.from(tbody.querySelectorAll('tr'));
    const asc=th.dataset.asc!=='1';
    trs.sort((a,b)=>{{
      const av=a.children[idx]?.innerText||''; const bv=b.children[idx]?.innerText||'';
      const an=parseFloat(av.replace('%','')); const bn=parseFloat(bv.replace('%',''));
      if(!Number.isNaN(an)&&!Number.isNaN(bn)) return asc?an-bn:bn-an;
      return asc?av.localeCompare(bv):bv.localeCompare(av);
    }});
    th.dataset.asc=asc?'1':'0'; trs.forEach(tr=>tbody.appendChild(tr));
  }});
}});
</script>
</body>
</html>"""
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
    print("with_api_odds", sum(1 for row in rows if row["cuota_api"]))
    print("with_betano_odds", sum(1 for row in rows if row["cuota_betano"]))
    print("ev_api_positive", sum(1 for row in rows if row["ev_api_num"] and float(row["ev_api_num"]) > 0))
    print("ev_betano_positive", sum(1 for row in rows if row["ev_betano_num"] and float(row["ev_betano_num"]) > 0))
    print("summary")
    for item in summary:
        print(item)
    print("top_ev_api")
    for match, markets in top_ev.items():
        print("###", match)
        for market in markets[:8]:
            print(
                clean(market.get("market")),
                pct(market.get("probability")),
                money(numeric(market, "odds_api", "odds")),
                money(numeric(market, "ev_api", "ev")),
                "Betano",
                money(market.get("odds_betano")),
                money(market.get("ev_betano")),
            )


if __name__ == "__main__":
    main()
