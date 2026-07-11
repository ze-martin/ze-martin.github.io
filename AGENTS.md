# AGENTE AUTÓNOMO DE SISTEMA DE APUESTAS

Estas instrucciones son la memoria operativa del proyecto `D:\CODEX\APUESTAS`.
Cuando se abra un hilo nuevo, continuar desde aquí y no desde supuestos genéricos.

## Objetivo permanente

Mantener un sistema funcional para:

1. Obtener partidos automáticamente.
2. Recopilar datos deportivos.
3. Calcular probabilidades.
4. Obtener cuotas de Betano mediante Playwright.
5. Comparar cuotas 10Bet/API vs Betano.
6. Calcular EV por casa.
7. Generar HTML/CSV navegables.
8. Publicar reportes en GitHub Pages.
9. Exponer API y dashboard del sistema base.

## Estructura obligatoria del sistema base

La estructura principal debe mantenerse:

```text
project_root/
├── app/
│   └── main.py
├── services/
│   └── pipeline.py
├── db/
│   └── database.py
├── dashboard/
│   └── app.py
├── scrapers/
│   └── betano_scraper.py
├── apis/
│   └── football_api.py
├── analysis/
│   ├── model.py
│   └── evaluator.py
├── run.py
└── requirements.txt
```

## Flujo real que se viene usando para reportes del Mundial

Cuando el usuario pida “protocolo completo”, “actualiza protocolo”, “partidos de mañana”, “partidos de X fecha” o similar, usar este flujo, salvo que pida otra cosa:

1. Generar protocolo base con:

   ```powershell
   python tools\generate_protocol_probabilities.py --from YYYY-MM-DD --to YYYY-MM-DD+1 --leagues 1 --date-lima YYYY-MM-DD --output-dir protocol\runs --name protocol_world_cup_YYYYMMDD_full
   ```

2. Si `matches` es `0`, no inventar partidos ni cuotas. Informar que no hay partidos para esa fecha.

3. Enriquecer el JSON con cuotas Betano:

   ```powershell
   python tools\enrich_protocol_with_betano.py --source protocol\runs\ARCHIVO.json --output protocol\runs\protocol_world_cup_YYYYMMDD_full_betano.json
   ```

   Si el Python del sistema no tiene Playwright, usar el runtime de Codex:

   ```powershell
   & "C:\Users\USUARIO\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" tools\enrich_protocol_with_betano.py --source ... --output ...
   ```

4. Exportar HTML/CSV:

   ```powershell
   python tools\export_protocol_html.py --source protocol\runs\protocol_world_cup_YYYYMMDD_full_betano.json --date YYYY-MM-DD --prefix protocolo_YYYYMMDD_pc --output-dir outputs
   ```

5. Publicar en GitHub Pages:

   ```powershell
   python tools\build_pages_site.py
   Copy-Item -LiteralPath site\index.html -Destination index.html -Force
   Copy-Item -LiteralPath site\latest.html -Destination latest.html -Force
   Copy-Item -Path site\reports\* -Destination reports\ -Force
   git add index.html latest.html outputs\protocolo_YYYYMMDD_pc.html outputs\protocolo_YYYYMMDD_pc_todos_los_mercados.csv reports\protocolo_YYYYMMDD_pc.html reports\protocolo_YYYYMMDD_pc_todos_los_mercados.csv tools\enrich_protocol_with_betano.py tools\export_protocol_html.py
   git commit -m "Publicar protocolo Mundial YYYY-MM-DD"
   git pull --rebase origin main
   git push origin main
   ```

6. Verificar GitHub Pages con cache-busting:

   ```powershell
   Invoke-WebRequest -Uri "https://ze-martin.github.io/reports/protocolo_YYYYMMDD_pc.html?v=COMMIT" -UseBasicParsing
   ```

## Comando único recomendado

Para no repetir pasos manuales, usar:

```powershell
python tools\run_published_protocol.py --dates YYYY-MM-DD,YYYY-MM-DD --leagues 1 --publish
```

Sin `--publish`, solo genera archivos locales.

## Salidas oficiales

Los reportes publicados viven en:

- HTML local: `outputs/protocolo_YYYYMMDD_pc.html`
- CSV local: `outputs/protocolo_YYYYMMDD_pc_todos_los_mercados.csv`
- HTML público raíz: `reports/protocolo_YYYYMMDD_pc.html`
- CSV público raíz: `reports/protocolo_YYYYMMDD_pc_todos_los_mercados.csv`
- Último reporte público: `latest.html`
- Índice público: `index.html`
- URL pública: `https://ze-martin.github.io/reports/protocolo_YYYYMMDD_pc.html`

## Reglas sobre cuotas y EV

- No mezclar cuotas de casas distintas en una sola columna.
- El HTML/CSV debe mostrar explícitamente:
  - `Cuota 10Bet/API`
  - `EV 10Bet/API`
  - `Cuota Betano`
  - `EV Betano`
- Las cuotas 10Bet/API vienen del proveedor usado por el protocolo base.
- Las cuotas Betano se scrapean desde `betano.pe` y pueden cambiar en vivo.
- Si Betano no tiene un mercado equivalente, dejarlo vacío o como “No encontrado en Betano”.
- No inventar cuotas para completar huecos.

## Scraping Betano

El scraper operativo está en:

```text
tools/enrich_protocol_with_betano.py
```

Usa Playwright con:

- navegación real;
- delays humanos;
- locale `es-PE`;
- timezone `America/Lima`;
- extracción de mercados visibles;
- aliases de equipos en español.

Si un partido existe en Betano pero no se encuentra, revisar aliases como:

- Belgium -> Bélgica
- Norway -> Noruega
- Switzerland -> Suiza
- Morocco -> Marruecos
- Spain -> España
- England -> Inglaterra

## Publicación

El repo remoto es:

```text
https://github.com/ze-martin/ze-martin.github.io.git
```

GitHub Pages publica desde la raíz del repo, no desde `site/`.
La carpeta `site/` es staging local y está ignorada.

Después de hacer `build_pages_site.py`, copiar siempre:

- `site/index.html` -> `index.html`
- `site/latest.html` -> `latest.html`
- `site/reports/*` -> `reports/`

## Validación mínima antes de responder

Para cada fecha con partidos:

1. Confirmar cantidad de partidos.
2. Confirmar cantidad de mercados.
3. Confirmar cuotas 10Bet/API.
4. Confirmar cuotas Betano.
5. Confirmar que el HTML contiene `Cuota Betano`.
6. Confirmar que el CSV tiene filas y columnas nuevas.
7. Si se publicó, confirmar que GitHub Pages responde `200`.

## Respuesta final al usuario

Responder en español con:

- partidos encontrados;
- resumen por fecha;
- pick principal por partido;
- cuotas 10Bet/API y Betano;
- enlaces HTML/CSV;
- advertencia breve: las cuotas Betano pueden moverse en vivo.

## Reglas críticas

- No dejar funciones vacías.
- No usar pseudocódigo.
- Manejar errores.
- Validar datos.
- No inventar datos.
- Preservar cambios existentes del usuario.
- No hacer `git reset --hard`.
- Si el remoto cambió, usar `git pull --rebase origin main` y resolver conflictos sin perder reportes.
