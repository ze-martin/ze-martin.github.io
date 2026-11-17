# Cierre manual del 17/11/2026 · tablas y fuentes separadas

Autorización de esta revisión: ejecución manual real y publicación de HTML/CSV. No autoriza Telegram, tareas, cambios de proveedor ni activar el modelo experimental. Una futura publicación vuelve a requerir autorización.

## Ejecución real y resultado

Consulta actual de API-Football: 43 partidos en el alcance aprobado; 27 pendientes al consultar y 16 iniciados/finalizados o con inicio vencido. Se generaron 2.631 mercados prepartido nuevos con `poisson-shrink-v2` y los controles de calidad actuales. Corte: **17/11/2026 11:19:04 Perú**, no la hora de publicación. Resultado: **0 principales, 0 alternativas, Sin apuesta**. No se fuerza un candidato T−60.

- API: 339 precios observados de **William Hill**, 0 elegibles. Los updates del proveedor tenían aproximadamente 16 min 50 s a 4 h 17 min al corte. Las consultas fueron nuevas; los precios no se rejuvenecieron. Se mantienen precio, casa, consulta y update en columnas históricas y motivo de descarte.
- Chrome asistido, solo **Dinamarca–Noruega**, inicio confirmado 14:45 Perú: captura **11:18:29.609 Perú**, 22 controles públicos de cuotas. Nueve coincidencias exactas con el modelo: goles 2.5/3.5, doble oportunidad y ambos anotan. El EV usa su probabilidad exacta; 3 EV aritméticos positivos no superan todos los controles de selección.
- Tres cuotas de resultado con **2 GOLES DE VENTAJA** quedan como promociones, sin EV. Diez precios no se incorporan: dos de goles 4.5 sin probabilidad exacta, seis de córners fuera del parser asistido validado y dos del combo ambos anotan o más de 2.5. CSV separado con motivo, precio, URL y captura; no se aproximan líneas.
- Las nueve capturas normales fueron elegibles temporalmente al corte, con 35,234 s de edad. Expiran a **11:28:29.609 Perú**. El informe conserva la foto histórica y el navegador retira la elegibilidad al vencer; su publicación no confirma precios actuales. Los otros 26 partidos no recibieron captura Betano nueva.
- Betano autónomo sigue **no verificado (HTTP 403)**; no se ejecutó ni se intentó eludirlo. La página de Chrome no demuestra que el scraper funcione.

## Persistencia e integridad

Revisión local: `data/manual_close_20261117/protocolo_20261117_manual_4c3ebe0056f6.json`, SHA-256 de archivo `66f4dbb59073bcc681ab44437f21837927290e74017b4d0b13aab782e6df2e2f`.

SQLite congela un snapshot nuevo y una variante propia. PostgreSQL añade 2.631 probabilidades con versión `poisson-shrink-v2`, nueve cuotas Betano y sus nueve EV; ambos conservan la revisión íntegra bajo una clave nueva de memoria. Los metadatos de último reporte son mutables: se archivaron sus referencias previas antes de actualizar. La variante `full` anterior y sus snapshots no se reemplazaron. No se liquidaron apuestas ni se tocaron tickets.

Se verificaron por hash todas las 159 snapshots, 669 picks y 414 liquidaciones anteriores de SQLite. También se verificaron sin cambios las filas anteriores de probability/odds/ev de PostgreSQL. Recibos privados locales: `history_before.json`, `normalized_db_before.json`, `normalized_persistence.json` y `verification.json` en la carpeta de ejecución; no se publican bases ni esos respaldos.

El fuente histórico de 43 partidos y 4.032 mercados conserva SHA-256 `00522caa19c60c632c64334fbc8c9cbec3972df45a169135937e92ecbce070d9`. Conserva sus 20 principales y 13 alternativas originales, presentadas exclusivamente como históricas. No se recalcularon ni sustituyeron. La copia pública anterior a las tablas se conserva localmente en `data/manual_close_20261117/public_before_7e8f366/`, con manifiesto de hashes, además de Git.

## Presentación y publicación

La plantilla real `services/report_template.py` delega en `services/report_table_view.py`: tablas Principales, Alternativas, Todos los mercados, Jugadores y Auditoría. Principales y alternativas muestran ambas casas por separado, además de la casa elegida originalmente. Filtros y paginación en mercados; principal histórica resaltada. Cabecera estática y pestañas compactas/desplazables. JSON cerrado y descargable exclusivamente desde Auditoría. Los diagnósticos del cierre manual tampoco se agregan como JSON visible.

El CSV conserva probabilidades originales y añade estado/respaldo de la estimación; muestra bookmaker observado aunque el precio activo esté vacío, ambos relojes originales y la naturaleza histórica de los precios al corte. El histórico nunca rellena el precio elegible.

Se incorpora a Auditoría la comparación ya validada de las 13 filas extremas: muestras propias, datos ausentes sin convertirlos a cero y probabilidad original intacta. La falta de datos muestra **Datos insuficientes**; una familia sin validación muestra **Estimación no validada**. No se recortó a 99,9%. Las guardas no son una mejora predictiva.

Enlaces previstos y verificados tras despliegue en el recibo local `public_verification.json`:

- Histórico original, nueva presentación: `https://ze-martin.github.io/reports/protocolo_20261117_full_pc.html`.
- Nueva prueba manual: `https://ze-martin.github.io/reports/protocolo_20261117_manual_161904_pc.html`.
- CSV nuevo: `https://ze-martin.github.io/reports/protocolo_20261117_manual_161904_pc_todos_los_mercados.csv`.
- Descartes/promociones: `https://ze-martin.github.io/reports/protocolo_20261117_manual_161904_pc_descartes_betano.csv`.

El índice conserva una fila por fecha y el histórico más completo como entrada; enlaza la nueva revisión por separado. `latest.html` resuelve CSV, JSON y enlaces de revisión hacia `reports/`. La publicación usa un worktree aislado y no incluye cambios de workflows, tareas, Telegram, bases ni credenciales.

## Verificación

145 tests de controles/modelo/API/parser/presentación/experimentos más cuatro tests independientes de publicación: **149 tests de software**, sin envíos reales. Pruebas del conjunto de despliegue también ejecutadas en el worktree de publicación. Navegación verificada en Chrome a 1440×1000 y 390×844: cinco pestañas, filtros, 13 filas auditadas, ninguna vista JSON abierta, cuerpo sin desbordamiento horizontal y cabecera estática. Evidencia y verificación pública quedan en la carpeta local del cierre.

Estas pruebas verifican software y trazabilidad, **no precisión predictiva** ni mejora fuera de muestra.

## Diferencias funcionales pendientes

1. Scraper Betano autónomo bloqueado HTTP 403; Chrome asistido requiere sesión accesible y captura nueva. Cobertura actual nueva: un partido, no toda la oferta.
2. Parser asistido de córners/combos y líneas sin probabilidad exacta todavía sin integración validada. Jugadores: pestaña restaurada, esta revisión no contiene observaciones nuevas; se indica Datos insuficientes.
3. API prematch con updates de horas: baja cobertura bajo la guarda provisional de 600 s. Medir latencia/cambios prospectivos; no ampliar TTL para producir picks.
4. Fuerza de rivales, recencia/sede, convergencia de nacionales y calibración de familias avanzadas pendientes de mejora prospectiva fuera de muestra. Los modelos experimentales siguen desactivados; abstenciones y alertas continúan.

Memoria operativa en ambas bases: `manual_protocol_close_20261117_161904`; publicación y verificación se añaden con su SHA desplegado después de comprobar la URL. Entrada de continuidad: AGENTS.md → este documento → recibos locales. No se convierte ninguna hipótesis en regla activa.
