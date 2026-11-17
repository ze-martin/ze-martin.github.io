"""Spanish display labels only; no probability or selection logic."""
def spanish_market(key):
    family,_,selection=key.partition(':')
    labels={'1X2':'Resultado del partido','DOUBLE_CHANCE':'Doble oportunidad','BTTS':'Ambos equipos anotan','TOTALS':'Goles totales','FIRST_HALF_TOTALS':'Goles del primer tiempo','DRAW_NO_BET':'Apuesta sin empate',
        'TEAM_TOTAL_HOME':'Goles del local','TEAM_TOTAL_AWAY':'Goles del visitante','CORNERS_TOTALS':'Córners totales','CORNERS_HOME':'Córners local','CORNERS_AWAY':'Córners visitante','CARDS_TOTALS':'Tarjetas totales','CARDS_HOME':'Tarjetas local','CARDS_AWAY':'Tarjetas visitante','SHOTS_TOTAL':'Remates totales','SHOTS_ON_TARGET_TOTAL':'Tiros al arco totales','WIN_BTTS':'Resultado y ambos anotan','CLEAN_SHEET':'Portería a cero','TOTAL_RANGE':'Rango de goles'}
    choice={'HOME':'Gana local','AWAY':'Gana visitante','DRAW':'Empate','1X':'Local o empate','X2':'Visitante o empate','12':'Sin empate','YES':'Sí','NO':'No'}.get(selection)
    if choice is None:
        choice=selection.replace('OVER_','Más de ').replace('UNDER_','Menos de ').replace('_','.').replace('HOME','Local').replace('AWAY','Visitante').replace('YES','Sí').replace('NO','No')
    return labels.get(family,family)+' · '+choice
