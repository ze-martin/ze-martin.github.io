from __future__ import annotations

import html
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
    name = path.stem
    return (
        name.replace("protocolo_", "Protocolo ")
        .replace("_pc", "")
        .replace("_", " ")
        .title()
    )


def copy_reports() -> list[dict[str, str]]:
    REPORTS.mkdir(parents=True, exist_ok=True)
    reports: list[dict[str, str]] = []

    html_files = sorted(
        OUTPUTS.glob("*.html"),
        key=lambda file: file.stat().st_mtime,
        reverse=True,
    )

    for source in html_files:
        target = REPORTS / source.name
        shutil.copy2(source, target)
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

    if html_files:
        shutil.copy2(html_files[0], SITE / "latest.html")

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
