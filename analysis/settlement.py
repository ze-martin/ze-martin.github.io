"""Settlement of supported markets. None means unavailable, never a loss."""
import math
def grade(key, fixture, statistics=None):
    status = fixture.get('fixture', {}).get('status', {}).get('short')
    if status in {'CANC', 'ABD', 'AWD', 'WO'}:
        return None  # House-specific void rules require manual review.
    if status not in {'FT', 'AET', 'PEN'}:
        return None
    score = fixture.get('score') or {}
    ft = score.get('fulltime') or {}
    h, a = ft.get('home'), ft.get('away')
    if h is None or a is None:
        return None
    family, selection = key.split(':', 1)
    if family == 'DOUBLE_CHANCE':
        win = {'1X': h >= a, 'X2': h <= a, '12': h != a}.get(selection)
    elif family == '1X2':
        win = {'HOME': h > a, 'AWAY': a > h, 'DRAW': h == a}.get(selection)
    elif family == 'DRAW_NO_BET':
        if h == a:
            return 'void'
        win = h > a if selection == 'HOME' else a > h
    elif family == 'BTTS':
        win = (h > 0 and a > 0) == (selection == 'YES')
    elif family == 'CLEAN_SHEET':
        side, yes = selection.split('_')
        win = ((a if side == 'HOME' else h) == 0) == (yes == 'YES')
    elif family == 'WIN_BTTS':
        side, yes = selection.split('_')
        win = (h > a if side == 'HOME' else a > h) and ((h > 0 and a > 0) == (yes == 'YES'))
    elif family == 'TOTAL_RANGE':
        lo, hi = map(int, selection.split('_'))
        win = lo <= h + a <= hi
    else:
        try:
            side, line = selection.split('_', 1)
            line = float(line.replace('_', '.'))
        except ValueError:
            return None
        value = None
        if family == 'TOTALS': value = h + a
        elif family == 'TEAM_TOTAL_HOME': value = h
        elif family == 'TEAM_TOTAL_AWAY': value = a
        elif family == 'FIRST_HALF_TOTALS':
            half = score.get('halftime') or {}
            if half.get('home') is not None and half.get('away') is not None:
                value = half['home'] + half['away']
        elif family.startswith(('CORNERS_', 'SHOTS_')) and status == 'FT' and statistics:
            name = 'Corner Kicks' if family.startswith('CORNERS_') else 'Shots on Goal' if family == 'SHOTS_ON_TARGET_TOTAL' else 'Total Shots'
            values = {}
            for team in statistics:
                value_ = next((s.get('value') for s in team.get('statistics', []) if s.get('type') == name), None)
                if value_ is not None:
                    values[team['team']['id']] = float(value_)
            if family.endswith('_HOME'): value = values.get(fixture['teams']['home']['id'])
            elif family.endswith('_AWAY'): value = values.get(fixture['teams']['away']['id'])
            elif len(values) == 2: value = sum(values.values())
        if value is None:
            return None
        if value == line:
            return 'void'
        win = value > line if side == 'OVER' else value < line if side == 'UNDER' else None
    return None if win is None else 'won' if win else 'lost'


def profit(outcome, odds, stake=1.0):
    if not math.isfinite(stake) or not math.isfinite(odds) or stake <= 0 or odds <= 1:
        raise ValueError('Importe y cuota no válidos')
    return stake * (odds - 1) if outcome == 'won' else -stake if outcome == 'lost' else 0.0 if outcome == 'void' else None
