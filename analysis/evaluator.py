from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValueBet:
    match_id: str
    league: str
    kickoff: str
    home_team: str
    away_team: str
    market: str
    selection: str
    probability: float
    odds: float
    ev: float
    bookmaker: str


def expected_value(probability: float, decimal_odds: float) -> float:
    if not 0 <= probability <= 1:
        raise ValueError("probability must be between 0 and 1")
    if decimal_odds <= 1:
        raise ValueError("decimal_odds must be greater than 1")
    return (probability * decimal_odds) - 1


def find_value_bets(
    match: dict,
    probabilities: dict[str, float],
    odds: dict[str, dict[str, float]],
    min_ev: float = 0.02,
) -> list[ValueBet]:
    picks: list[ValueBet] = []
    bookmaker = odds.get("bookmaker", "unknown")
    markets = odds.get("markets", {})
    for key, probability in probabilities.items():
        offered_odds = markets.get(key)
        if offered_odds is None:
            continue
        ev = expected_value(probability, offered_odds)
        if ev >= min_ev:
            market, selection = key.split(":", 1)
            picks.append(
                ValueBet(
                    match_id=match["id"],
                    league=match["league"],
                    kickoff=match["kickoff"],
                    home_team=match["home_team"],
                    away_team=match["away_team"],
                    market=market,
                    selection=selection,
                    probability=round(probability, 6),
                    odds=round(offered_odds, 3),
                    ev=round(ev, 6),
                    bookmaker=bookmaker,
                )
            )
    return sorted(picks, key=lambda item: item.ev, reverse=True)
