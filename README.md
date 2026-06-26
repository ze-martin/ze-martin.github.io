# ze-martin.github.io

Sitio GitHub Pages para visualizar reportes HTML del protocolo de apuestas.

## Publicación

Cada vez que se suben cambios a `main` en estos archivos:

- `outputs/**/*.html`
- `outputs/**/*.csv`
- `tools/build_pages_site.py`

GitHub Actions reconstruye el sitio y publica:

- Página principal: `https://ze-martin.github.io/`
- Último reporte: `https://ze-martin.github.io/latest.html`

## Flujo local

1. Generar o actualizar reportes HTML en `outputs/`.
2. Verificar localmente:

```bash
python tools/build_pages_site.py
```

3. Subir cambios:

```bash
git add outputs/*.html outputs/*.csv tools/build_pages_site.py .github/workflows/deploy-pages.yml .gitignore .nojekyll README.md
git commit -m "Actualizar reportes del protocolo"
git push
```
