# Corrección exclusivamente visual · protocolo 17/11/2026

La corrección anterior estaba en la plantilla y vista previa locales; no se había publicado. El reporte público conservaba el HTML anterior. Esta publicación reemplaza únicamente la presentación del protocolo y sus espejos, no el snapshot ni el CSV.

Fuente SHA-256: `00522caa19c60c632c64334fbc8c9cbec3972df45a169135937e92ecbce070d9`. Se conservan 43 partidos, 4.032 mercados, 20 principales y 13 alternativas originales. No se usa el comparativo retrospectivo de ocho principales. Los picks se rotulan históricos.

Plantilla: `services/report_template.py`; etiquetas: `services/report_labels.py`; generador: `tools/export_protocol_html.py`. `tools/restyle_historical_report.py` no llama al modelo, política, API, bases ni notificaciones. Comprueba probabilidades, cuotas, relojes y claves de selección contra la auditoría descargable. La vista actual solo filtra las selecciones originales por vigencia/revisión, sin elegir reemplazos ni renovar capturas.

JSON solo dentro de Auditoría, cerrado y descargable como datos deportivos. Cabecera estática; pestañas compactas, de una fila y desplazables en móvil; principal resaltada, alternativas debajo. Constructor estático: reconoce conteos de tarjetas y copia/enlaza auditoría. No se modifican fórmulas, políticas, CSV ni workflows.

Copia previa local del HTML público, espejos y CSV; el commit padre conserva los archivos originales. Portada y auditoría experimental separada intactas. Latest sigue apuntando al mismo protocolo del 17/11 con su presentación corregida.

Pruebas previas: 25 regresiones en checkout limpio (cuatro nuevas de presentación y 21 existentes); comparación de las 4.032 filas del CSV público y ledger local intacto. Verificación final de URL pública, commit y escritorio/móvil registrada localmente tras desplegar. Sin bases, credenciales ni tickets en el commit; sin Telegram ni activación de tareas.
