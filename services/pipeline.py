from __future__ import annotations

import os
from dataclasses import asdict
from datetime import date
from typing import Any

from analysis.evaluator import ValueBet, find_value_bets
from analysis.model import PoissonModel, TeamStats
from apis.football_api import FootballAPI
from db.database import Database, SavedPick
from scrapers.betano_scraper import BetanoScraper


class BettingPipeline:
    def __init__(
        self,
        football_api: FootballAPI | None = None,
        scraper: BetanoScraper | None = None,
        database: Database | None = None,
    ) -> None:
        self.football_api = football_api or FootballAPI()
        self.scraper = scraper or BetanoScraper()
        self.database = database or Database()
        self.model = PoissonModel()
        self.min_ev = float(os.getenv("MIN_EV", "0.02"))

    def run(self, from_date: date, to_date: date, leagues: list[str], persist: bool = True) -> dict[str, Any]:
        if from_date > to_date:
            raise ValueError("from_date must be earlier than or equal to to_date")

        messages: list[str] = []
        matches = self.football_api.get_matches(from_date, to_date, leagues)
        api_errors = getattr(self.football_api, "last_errors", [])
        messages.extend(api_errors)
        if not matches:
            messages.append(
                "No matches returned by football data source. Configure FOOTBALL_API_KEY or FOOTBALL_DATA_FILE in .env."
            )
            return {"matches": 0, "picks": [], "messages": messages}

        if persist:
            self._try_db(messages, lambda: self.database.initialize())
            self._try_db(messages, lambda: self.database.save_matches(matches))

        odds_by_match = self.football_api.get_embedded_odds(matches)
        missing_odds_matches = [match for match in matches if match["id"] not in odds_by_match]
        if odds_by_match:
            messages.append(f"Using embedded odds for {len(odds_by_match)} matches from the football data source.")
        if missing_odds_matches:
            if getattr(self.football_api, "source", "") == "api-football":
                messages.append(f"No API odds available for {len(missing_odds_matches)} matches.")
            else:
                scraped_odds = self.scraper.get_odds(missing_odds_matches)
                odds_by_match.update(scraped_odds)
        if not odds_by_match:
            messages.append(
                "No odds extracted. Check BETANO_URL, Playwright browser installation, or use FOOTBALL_SOURCE=football-data."
            )

        picks: list[ValueBet] = []
        skipped = 0
        for match in matches:
            stats = self.football_api.get_team_stats(match)
            try:
                home_stats = self._team_stats(match["home_team"], stats.get("home", {}))
                away_stats = self._team_stats(match["away_team"], stats.get("away", {}))
                probabilities = self.model.match_probabilities(home_stats, away_stats)
            except (KeyError, ValueError, TypeError):
                fallback_stats = self.football_api.get_fallback_team_stats(match)
                try:
                    home_stats = self._team_stats(match["home_team"], fallback_stats.get("home", {}))
                    away_stats = self._team_stats(match["away_team"], fallback_stats.get("away", {}))
                    probabilities = self.model.match_probabilities(home_stats, away_stats)
                except (KeyError, ValueError, TypeError):
                    skipped += 1
                    continue
            probabilities.update(self.model.advanced_market_probabilities(match))
            picks.extend(find_value_bets(match, probabilities, odds_by_match.get(match["id"], {}), self.min_ev))

        if skipped:
            messages.append(f"Skipped {skipped} matches because required team statistics were missing or invalid.")

        if persist and picks:
            self._try_db(messages, lambda: self.database.save_picks(self._to_saved_pick(picks)))

        return {
            "matches": len(matches),
            "picks": [asdict(pick) for pick in picks],
            "messages": messages,
        }

    def list_matches(self, from_date: date, to_date: date, leagues: list[str]) -> dict[str, Any]:
        if from_date > to_date:
            raise ValueError("from_date must be earlier than or equal to to_date")

        matches = sorted(
            self.football_api.list_matches(from_date, to_date, leagues),
            key=lambda item: (item["kickoff"], item["league"], item["home_team"], item["away_team"]),
        )
        api_errors = getattr(self.football_api, "last_errors", [])

        enumerated_matches = [
            {
                "selection_number": index,
                "match_id": match["id"],
                "league": match["league"],
                "kickoff": match["kickoff"],
                "home_team": match["home_team"],
                "away_team": match["away_team"],
            }
            for index, match in enumerate(matches, start=1)
        ]
        return {
            "matches": len(enumerated_matches),
            "available_matches": enumerated_matches,
            "messages": api_errors,
        }

    def latest_results(self, limit: int = 100) -> list[dict[str, Any]]:
        try:
            self.database.initialize()
            return self.database.latest_results(limit)
        except Exception:
            return []

    def _team_stats(self, team: str, stats: dict[str, Any]) -> TeamStats:
        return TeamStats(
            team=team,
            matches=int(stats["matches"]),
            goals_for=float(stats["goals_for"]),
            goals_against=float(stats["goals_against"]),
        )

    def _to_saved_pick(self, picks: list[ValueBet]) -> list[SavedPick]:
        return [
            SavedPick(
                match_id=pick.match_id,
                league=pick.league,
                kickoff=pick.kickoff,
                home_team=pick.home_team,
                away_team=pick.away_team,
                market=pick.market,
                selection=pick.selection,
                probability=pick.probability,
                odds=pick.odds,
                ev=pick.ev,
                bookmaker=pick.bookmaker,
            )
            for pick in picks
        ]

    def _try_db(self, messages: list[str], operation) -> None:
        try:
            operation()
        except Exception as exc:
            messages.append(f"Database operation skipped: {exc}")
