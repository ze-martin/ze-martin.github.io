from __future__ import annotations

import html
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
SITE = ROOT / "site"
REPORTS = SITE / "reports"


def human_size(size: int) -> str:
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def report_title(path: Path) -> str:
    report_date = extract_report_date(path)
    if report_date:
        return f"Protocolo {report_date}"
    name = path.stem
    return name.replace("protocolo_", "Protocolo ").replace("_pc", "").replace("_", " ").title()


def extract_report_date(path: Path) -> str | None:
    match = re.search(r"(20\d{6})", path.name)
    return match.group(1) if match else None


def extract_report_scope(path: Path) -> str:
    report_date = extract_report_date(path)
    if not report_date:
        return "sin_fecha"
    stem = path.stem
    legacy_stem = f"protocolo_{report_date}_pc"
    if stem == legacy_stem:
        return "legacy"
    prefix = f"protocolo_{report_date}_"
    suffix = "_pc"
    if stem.startswith(prefix) and stem.endswith(suffix):
        return stem[len(prefix) : -len(suffix)].strip("_") or "legacy"
    return "custom"


def report_sort_key(path: Path) -> tuple[str, float]:
    date_key = extract_report_date(path) or "00000000"
    return date_key, path.stat().st_mtime


def report_content_score(path: Path) -> tuple[int, int, int]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    matches = re.search(r"Partidos</span><b>(\d+)</b>", text)
    markets = re.search(r"Mercados</span><b>(\d+)</b>", text)
    has_audit = 1 if "Auditoría del modelo" in text else 0
    return (
        has_audit,
        int(matches.group(1)) if matches else 0,
        int(markets.group(1)) if markets else 0,
    )


def canonical_report_key(path: Path) -> tuple[str, int, int, int, int, int, int, str]:
    """Return a score for choosing one visible report per date.

    All HTML/CSV files are still copied to ``site/reports`` so old direct links
    continue working. The public index, however, should not duplicate the same
    calendar day when a league or cup is added later. We choose the most useful
    report by visible content first, then by scope and filesystem freshness.
    """
    report_date = extract_report_date(path) or "00000000"
    scope = extract_report_scope(path)
    scope_priority = {
        "full": 30,
        "legacy": 20,
    }.get(scope, 10)
    has_audit, matches, markets = report_content_score(path)
    return (
        report_date,
        has_audit,
        matches,
        markets,
        path.stat().st_size,
        scope_priority,
        int(path.stat().st_mtime),
        path.name,
    )


def select_visible_reports(html_files: list[Path]) -> list[Path]:
    by_date: dict[str, Path] = {}
    for source in html_files:
        report_date = extract_report_date(source) or source.name
        current = by_date.get(report_date)
        if current is None or canonical_report_key(source) > canonical_report_key(current):
            by_date[report_date] = source
    return sorted(by_date.values(), key=report_sort_key, reverse=True)


def copy_reports() -> list[dict[str, str]]:
    REPORTS.mkdir(parents=True, exist_ok=True)
    reports: list[dict[str, str]] = []

    html_files = sorted(
        OUTPUTS.glob("*.html"),
        key=report_sort_key,
        reverse=True,
    )
    visible_html_files = select_visible_reports(html_files)

    for source in html_files:
        target = REPORTS / source.name
        shutil.copy2(source, target)

    for source in visible_html_files:
        reports.append(
            {
                "title": report_title(source),
                "href": f"reports/{source.name}",
                "name": source.name,
                "mtime": datetime.fromtimestamp(source.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                "size": human_size(source.stat().st_size),
            }
        )

    for source in sorted(OUTPUTS.glob("*.csv")):
        shutil.copy2(source, REPORTS / source.name)

    if visible_html_files:
        shutil.copy2(visible_html_files[0], SITE / "latest.html")

    return reports


def write_index(reports: list[dict[str, str]]) -> None:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if reports:
        latest_link = f'<a class="primary" href="{html.escape(reports[0]["href"])}">Abrir último reporte</a>'
        rows = "\n".join(
            f"""
            <tr>
              <td><a href="{html.escape(report["href"])}">{html.escape(report["title"])}</a></td>
              <td>{html.escape(report["mtime"])}</td>
              <td>{html.escape(report["size"])}</td>
              <td><code>{html.escape(report["name"])}</code></td>
            </tr>
            """
            for report in reports
        )
    else:
        latest_link = '<span class="empty">No hay reportes HTML en outputs/ todavía.</span>'
        rows = """
        <tr>
          <td colspan="4">No se encontraron archivos <code>outputs/*.html</code>.</td>
        </tr>
        """

    index = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Reportes protocolo apuestas</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg:#0b1020; --panel:#121a2c; --line:#26344f;
      --text:#e9eefb; --muted:#9fb0d0; --accent:#58a6ff;
    }}
    body {{
      margin:0; font-family:Inter,Segoe UI,system-ui,Arial,sans-serif;
      background:var(--bg); color:var(--text);
    }}
    header {{
      padding:28px; border-bottom:1px solid var(--line);
      background:linear-gradient(135deg,#101a34,#0b1020);
    }}
    main {{ padding:24px 28px 60px; max-width:1100px; }}
    h1 {{ margin:0 0 8px; font-size:28px; }}
    .meta {{ color:var(--muted); font-size:14px; }}
    .card {{
      background:var(--panel); border:1px solid var(--line);
      border-radius:16px; padding:18px; margin-top:18px;
      box-shadow:0 10px 30px rgba(0,0,0,.18);
    }}
    .primary {{
      display:inline-block; background:#1f6feb; border:1px solid #388bfd;
      color:white; text-decoration:none; font-weight:700;
      padding:11px 14px; border-radius:12px;
    }}
    table {{ border-collapse:collapse; width:100%; margin-top:14px; }}
    th, td {{
      border-bottom:1px solid var(--line); padding:10px 12px;
      text-align:left; vertical-align:top; font-size:14px;
    }}
    th {{ color:#cfe0ff; background:#18233a; }}
    a {{ color:var(--accent); }}
    code {{ color:#cfe0ff; }}
    .empty {{ color:#ffcf70; }}
    @media (max-width:760px) {{
      header, main {{ padding-left:16px; padding-right:16px; }}
      table {{ display:block; overflow:auto; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Reportes del protocolo</h1>
    <div class="meta">Publicado automáticamente con GitHub Pages · Generado: {html.escape(generated)}</div>
  </header>
  <main>
    <section class="card">
      {latest_link}
      <p class="meta">El botón abre el HTML más reciente copiado desde <code>outputs/</code>.</p>
    </section>
    <section class="card">
      <h2>Reportes disponibles</h2>
      <table>
        <thead>
          <tr><th>Reporte</th><th>Fecha local del archivo</th><th>Tamaño</th><th>Archivo</th></tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "index.html").write_text(index, encoding="utf-8")


def main() -> None:
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)
    reports = copy_reports()
    write_index(reports)
    print(f"site built: {SITE}")
    print(f"html reports: {len(reports)}")


if __name__ == "__main__":
    main()
