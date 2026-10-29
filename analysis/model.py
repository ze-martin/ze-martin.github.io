from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TeamStats:
    team: str
    matches: int
    goals_for: float
    goals_against: float

    @property
    def attack_rate(self) -> float:
        return self.goals_for / self.matches if self.matches > 0 else 0.0

    @property
    def defense_rate(self) -> float:
        return self.goals_against / self.matches if self.matches > 0 else 0.0


def poisson_probability(goals: int, expected_goals: float) -> float:
    if goals < 0 or expected_goals < 0:
        raise ValueError("goals and expected_goals must be non-negative")
    return (math.exp(-expected_goals) * expected_goals**goals) / math.factorial(goals)


class PoissonModel:
    version = 'poisson-shrink-v2'
    def __init__(self, max_goals: int = 8, home_advantage: float = 1.08) -> None:
        if max_goals < 3:
            raise ValueError("max_goals must be at least 3")
        self.max_goals = max_goals
        self.home_advantage = home_advantage

    def expected_goals(self, home: TeamStats, away: TeamStats) -> tuple[float, float]:
        if home.matches <= 0 or away.matches <= 0:
            raise ValueError("both teams need historical matches")
        # Six virtual matches at a neutral 1.3-goal prior are a provisional
        # regularizer, not a fitted league benchmark. Keep that distinction visible.
        def rate(goals, matches):
            return (goals + 6 * 1.3) / (matches + 6)
        home_xg = max(0.05, ((rate(home.goals_for, home.matches) + rate(away.goals_against, away.matches)) / 2) * self.home_advantage)
        away_xg = max(0.05, (rate(away.goals_for, away.matches) + rate(home.goals_against, home.matches)) / 2)
        return home_xg, away_xg

    def match_probabilities(self, home: TeamStats, away: TeamStats) -> dict[str, float]:
        home_xg, away_xg = self.expected_goals(home, away)
        bound = max(self.max_goals, int(math.ceil(max(home_xg, away_xg) + 10 * math.sqrt(max(home_xg, away_xg)) + 10)))
        home_win = draw = away_win = both_score = 0.0
        totals = {
            1.5: 0.0,
            2.5: 0.0,
            3.5: 0.0,
        }
        home_team_totals = {
            0.5: 0.0,
            1.5: 0.0,
            2.5: 0.0,
        }
        away_team_totals = {
            0.5: 0.0,
            1.5: 0.0,
            2.5: 0.0,
        }

        for home_goals in range(bound + 1):
            hp = poisson_probability(home_goals, home_xg)
            for away_goals in range(bound + 1):
                probability = hp * poisson_probability(away_goals, away_xg)
                if home_goals > away_goals:
                    home_win += probability
                elif home_goals == away_goals:
                    draw += probability
                else:
                    away_win += probability
                for line in totals:
                    if home_goals + away_goals > line:
                        totals[line] += probability
                for line in home_team_totals:
                    if home_goals > line:
                        home_team_totals[line] += probability
                for line in away_team_totals:
                    if away_goals > line:
                        away_team_totals[line] += probability
                if home_goals > 0 and away_goals > 0:
                    both_score += probability

        total = home_win + draw + away_win
        if total > 0:
            home_win, draw, away_win = home_win / total, draw / total, away_win / total

        probabilities = {
            "1X2:HOME": home_win,
            "1X2:DRAW": draw,
            "1X2:AWAY": away_win,
            "BTTS:YES": min(both_score, 1.0),
            "BTTS:NO": max(0.0, min(1.0, 1 - both_score)),
            "DOUBLE_CHANCE:1X": min(home_win + draw, 1.0),
            "DOUBLE_CHANCE:X2": min(draw + away_win, 1.0),
            "DOUBLE_CHANCE:12": min(home_win + away_win, 1.0),
            "DRAW_NO_BET:HOME": home_win / (home_win + away_win) if (home_win + away_win) > 0 else 0.0,
            "DRAW_NO_BET:AWAY": away_win / (home_win + away_win) if (home_win + away_win) > 0 else 0.0,
        }
        for line, probability in totals.items():
            line_key = str(line).replace(".", "_")
            probabilities[f"TOTALS:OVER_{line_key}"] = min(probability, 1.0)
            probabilities[f"TOTALS:UNDER_{line_key}"] = max(0.0, min(1.0, 1 - probability))
        for line, probability in home_team_totals.items():
            line_key = str(line).replace(".", "_")
            probabilities[f"TEAM_TOTAL_HOME:OVER_{line_key}"] = min(probability, 1.0)
            probabilities[f"TEAM_TOTAL_HOME:UNDER_{line_key}"] = max(0.0, min(1.0, 1 - probability))
        for line, probability in away_team_totals.items():
            line_key = str(line).replace(".", "_")
            probabilities[f"TEAM_TOTAL_AWAY:OVER_{line_key}"] = min(probability, 1.0)
            probabilities[f"TEAM_TOTAL_AWAY:UNDER_{line_key}"] = max(0.0, min(1.0, 1 - probability))
        # Joint events use the same score grid, never multiplication of correlated marginals.
        for side in ['HOME', 'AWAY']:
            for answer in ['YES', 'NO']:
                probabilities[f'WIN_BTTS:{side}_{answer}'] = 0.0
        for lo, hi in [(1, 3), (2, 3), (2, 4)]:
            probabilities[f'TOTAL_RANGE:{lo}_{hi}'] = 0.0
        for hg in range(bound + 1):
            for ag in range(bound + 1):
                mass = poisson_probability(hg, home_xg) * poisson_probability(ag, away_xg)
                for side, won in [('HOME', hg > ag), ('AWAY', ag > hg)]:
                    if won:
                        answer = 'YES' if hg > 0 and ag > 0 else 'NO'
                        probabilities[f'WIN_BTTS:{side}_{answer}'] += mass
                for lo, hi in [(1, 3), (2, 3), (2, 4)]:
                    if lo <= hg + ag <= hi:
                        probabilities[f'TOTAL_RANGE:{lo}_{hi}'] += mass
        for side, lam in [('HOME', away_xg), ('AWAY', home_xg)]:
            p = math.exp(-lam)
            probabilities[f'CLEAN_SHEET:{side}_YES'] = p
            probabilities[f'CLEAN_SHEET:{side}_NO'] = 1 - p
        return probabilities

    def advanced_market_probabilities(self, match: dict[str, Any]) -> dict[str, float]:
        context = match.get("raw", {}).get("analysis_context", {})
        home = context.get("attacking_quality", {}).get("home", {})
        away = context.get("attacking_quality", {}).get("away", {})
        home_def = context.get("defensive_quality", {}).get("home", {})
        away_def = context.get("defensive_quality", {}).get("away", {})
        first_half_home = context.get("first_half_goals", {}).get("home", {})
        first_half_away = context.get("first_half_goals", {}).get("away", {})

        probabilities: dict[str, float] = {}
        probabilities.update(self._metric_over_under_market("CORNERS_TOTALS", self._expected_total(home.get("corners_for"), away.get("corners_for"), home_def.get("corners_against"), away_def.get("corners_against")), [7.5, 8.5, 9.5, 10.5, 11.5]))
        probabilities.update(self._metric_over_under_market("CORNERS_HOME", self._expected_side(home.get("corners_for"), away_def.get("corners_against")), [3.5, 4.5, 5.5, 6.5]))
        probabilities.update(self._metric_over_under_market("CORNERS_AWAY", self._expected_side(away.get("corners_for"), home_def.get("corners_against")), [3.5, 4.5, 5.5, 6.5]))
        probabilities.update(self._metric_over_under_market("CARDS_TOTALS", self._expected_total(context.get("defensive_quality", {}).get("home", {}).get("yellow_cards_avg"), context.get("defensive_quality", {}).get("away", {}).get("yellow_cards_avg"), None, None, use_sum_only=True), [2.5, 3.5, 4.5, 5.5, 6.5]))
        probabilities.update(self._metric_over_under_market("CARDS_HOME", self._expected_side(context.get("defensive_quality", {}).get("home", {}).get("yellow_cards_avg"), None, passthrough=True), [0.5, 1.5, 2.5, 3.5]))
        probabilities.update(self._metric_over_under_market("CARDS_AWAY", self._expected_side(context.get("defensive_quality", {}).get("away", {}).get("yellow_cards_avg"), None, passthrough=True), [0.5, 1.5, 2.5, 3.5]))
        probabilities.update(self._metric_over_under_market("SHOTS_TOTAL", self._expected_total(home.get("shots_total"), away.get("shots_total"), home_def.get("shots_against"), away_def.get("shots_against")), [18.5, 20.5, 22.5, 24.5, 26.5]))
        probabilities.update(self._metric_over_under_market("SHOTS_ON_TARGET_TOTAL", self._expected_total(home.get("shots_on_target"), away.get("shots_on_target"), home_def.get("shots_on_target_against"), away_def.get("shots_on_target_against")), [6.5, 7.5, 8.5, 9.5]))
        first_half_expected = self._expected_total(
            first_half_home.get("goals_for_avg"),
            first_half_away.get("goals_for_avg"),
            first_half_home.get("goals_against_avg"),
            first_half_away.get("goals_against_avg"),
        )
        probabilities.update(self._metric_over_under_market("FIRST_HALF_TOTALS", first_half_expected, [0.5, 1.5]))
        return probabilities

    def _expected_total(self, home_for: float | None, away_for: float | None, home_against: float | None, away_against: float | None, use_sum_only: bool = False) -> float | None:
        if use_sum_only:
            values = [value for value in (home_for, away_for) if value is not None]
            return sum(values) if values else None
        home_side = self._expected_side(home_for, away_against)
        away_side = self._expected_side(away_for, home_against)
        if home_side is None or away_side is None:
            return None
        return home_side + away_side

    def _expected_side(self, for_value: float | None, against_value: float | None, passthrough: bool = False) -> float | None:
        if passthrough:
            return for_value
        values = [value for value in (for_value, against_value) if value is not None]
        if not values:
            return None
        return sum(values) / len(values)

    def _metric_over_under_market(self, prefix: str, expected_value: float | None, lines: list[float]) -> dict[str, float]:
        if expected_value is None or expected_value <= 0:
            return {}
        probabilities: dict[str, float] = {}
        for line in lines:
            over = self._poisson_tail(expected_value, line)
            under = max(0.0, min(1.0, 1 - over))
            line_key = str(line).replace(".", "_")
            probabilities[f"{prefix}:OVER_{line_key}"] = over
            probabilities[f"{prefix}:UNDER_{line_key}"] = under
        return probabilities

    def _poisson_tail(self, expected_value: float, line: float) -> float:
        threshold = int(math.floor(line)) + 1
        cumulative = 0.0
        for value in range(threshold):
            cumulative += poisson_probability(value, expected_value)
        return max(0.0, min(1.0, 1 - cumulative))
