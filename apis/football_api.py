from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import time as time_module
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any


class FootballAPI:
    def __init__(self) -> None:
        self.source = os.getenv("FOOTBALL_SOURCE", "api-football").strip().lower()
        self.base_url = os.getenv("FOOTBALL_API_BASE_URL", "https://v3.football.api-sports.io")
        self.api_key = os.getenv("FOOTBALL_API_KEY", "")
        self.local_file = os.getenv("FOOTBALL_DATA_FILE", "")
        self.timeout = int(os.getenv("FOOTBALL_API_TIMEOUT", "20"))
        self.default_leagues = self._csv(os.getenv("FOOTBALL_LEAGUES", ""))
        self.default_api_leagues = self._csv(os.getenv("API_FOOTBALL_LEAGUES", "2,3,39,140,135,78,281,11,13"))
        self.season = os.getenv("FOOTBALL_SEASON", "2026")
        self.seasons_by_league = self._mapping(os.getenv("API_FOOTBALL_SEASONS_BY_LEAGUE", ""))
        self.include_premium_context = os.getenv("API_FOOTBALL_PREMIUM_CONTEXT", "true").lower() == "true"
        self.request_delay_seconds = float(os.getenv("API_FOOTBALL_REQUEST_DELAY_SECONDS", "0.25"))
        self.last_errors: list[str] = []
        self._response_cache: dict[str, dict[str, Any]] = {}
        self.cache_enabled = os.getenv("API_FOOTBALL_CACHE_ENABLED", "true").lower() != "false"
        self.cache_dir = Path(os.getenv("API_FOOTBALL_CACHE_DIR", "data/api_cache"))
        self.cache_hits = 0
        self.cache_misses = 0
        self.football_data_fixtures_url = os.getenv(
            "FOOTBALL_DATA_FIXTURES_URL",
            "https://www.football-data.co.uk/fixtures.csv",
        )
        self.football_data_history_url = os.getenv(
            "FOOTBALL_DATA_HISTORY_URL",
            "https://www.football-data.co.uk/mmz4281/{season}/{league}.csv",
        )
        self.football_data_leagues = self._csv(
            os.getenv("FOOTBALL_DATA_LEAGUES", "") or os.getenv("FOOTBALL_LEAGUES", "")
        )

    def get_matches(self, from_date: date, to_date: date, leagues: list[str]) -> list[dict[str, Any]]:
        self.last_errors = []
        requested_leagues = leagues or self.default_leagues
        if self.local_file:
            return self._matches_from_file(from_date, to_date, requested_leagues)
        if self.source in {"football-data", "footballdata", "csv"}:
            return self._matches_from_football_data(from_date, to_date, leagues or self.football_data_leagues)
        if not self.api_key:
            return []
        return self._matches_from_api_football(
            from_date,
            to_date,
            requested_leagues or self.default_api_leagues,
            enrich=True,
        )

    def list_matches(self, from_date: date, to_date: date, leagues: list[str]) -> list[dict[str, Any]]:
        self.last_errors = []
        requested_leagues = leagues or self.default_leagues
        if self.local_file:
            return self._matches_from_file(from_date, to_date, requested_leagues)
        if self.source in {"football-data", "footballdata", "csv"}:
            return self._matches_from_football_data(from_date, to_date, leagues or self.football_data_leagues)
        if not self.api_key:
            return []
        return self._matches_from_api_football(
            from_date,
            to_date,
            requested_leagues or self.default_api_leagues,
            enrich=False,
        )

    def get_team_stats(self, match: dict[str, Any]) -> dict[str, dict[str, Any]]:
        raw_stats = match.get("raw", {}).get("stats")
        if isinstance(raw_stats, dict):
            return raw_stats
        return {}

    def get_embedded_odds(self, matches: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        odds_by_match: dict[str, dict[str, Any]] = {}
        for match in matches:
            raw_odds = match.get("raw", {}).get("odds")
            if isinstance(raw_odds, dict) and raw_odds.get("markets"):
                odds_by_match[match["id"]] = raw_odds
        return odds_by_match

    def _matches_from_file(self, from_date: date, to_date: date, leagues: list[str]) -> list[dict[str, Any]]:
        path = Path(self.local_file)
        data = json.loads(path.read_text(encoding="utf-8"))
        source = data.get("matches", data if isinstance(data, list) else [])
        wanted_leagues = {item.strip() for item in leagues if item.strip()}
        matches = []
        for item in source:
            normalized = self._normalize_local_match(item)
            if not normalized:
                continue
            kickoff_day = date.fromisoformat(normalized["kickoff"][:10])
            if from_date <= kickoff_day <= to_date and (not wanted_leagues or normalized["league"] in wanted_leagues):
                matches.append(normalized)
        return matches

    def _normalize_fixture(self, fixture: dict[str, Any], fallback_league: str) -> dict[str, Any] | None:
        try:
            return {
                "id": str(fixture["fixture"]["id"]),
                "league": str(fixture.get("league", {}).get("name") or fallback_league),
                "kickoff": fixture["fixture"]["date"],
                "home_team": fixture["teams"]["home"]["name"],
                "away_team": fixture["teams"]["away"]["name"],
                "raw": fixture,
            }
        except KeyError:
            return None

    def _matches_from_api_football(
        self,
        from_date: date,
        to_date: date,
        leagues: list[str],
        enrich: bool,
    ) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        for league in leagues:
            payload = self._api_get(
                "fixtures",
                {
                    "from": from_date.isoformat(),
                    "to": to_date.isoformat(),
                    "league": league,
                    "season": self._season_for_league(league),
                },
            )
            self._remember_api_errors(payload, f"fixtures league {league}")
            for fixture in payload.get("response", []):
                normalized = self._normalize_fixture(fixture, fallback_league=league)
                if not normalized:
                    continue
                if enrich:
                    normalized["raw"] = self._enrich_api_football_fixture(fixture, self._season_for_league(league))
                matches.append(normalized)
        return matches

    def _enrich_api_football_fixture(self, fixture: dict[str, Any], season: str) -> dict[str, Any]:
        raw = dict(fixture)
        league_id = fixture.get("league", {}).get("id")
        home_id = fixture.get("teams", {}).get("home", {}).get("id")
        away_id = fixture.get("teams", {}).get("away", {}).get("id")
        fixture_id = fixture.get("fixture", {}).get("id")

        team_payloads: dict[str, dict[str, Any]] = {}
        stats = {}
        if league_id and home_id:
            team_payloads["home"] = self._api_team_statistics_payload(league_id, home_id, season)
            stats["home"] = self._normalize_api_team_stats(team_payloads["home"])
        if league_id and away_id:
            team_payloads["away"] = self._api_team_statistics_payload(league_id, away_id, season)
            stats["away"] = self._normalize_api_team_stats(team_payloads["away"])
        if stats:
            raw["stats"] = stats
            raw["stats_source"] = "current_tournament"
            if not self._has_complete_team_stats(stats):
                raw["fallback_stats"] = self._fallback_recent_team_stats(home_id, away_id)
                raw["stats_source"] = "current_tournament_incomplete"

        if fixture_id:
            odds = self._api_fixture_odds(fixture_id)
            if odds:
                raw["odds"] = odds
            if self.include_premium_context:
                raw["premium_context"] = self._api_premium_context(fixture_id)

        if self.include_premium_context and league_id and home_id and away_id:
            raw["analysis_context"] = self._api_analysis_context(
                fixture=fixture,
                fixture_odds=raw.get("odds"),
                season=season,
                home_stats_payload=team_payloads.get("home", {}),
                away_stats_payload=team_payloads.get("away", {}),
            )
        return raw

    def get_fallback_team_stats(self, match: dict[str, Any]) -> dict[str, Any]:
        fallback_stats = match.get("raw", {}).get("fallback_stats")
        return fallback_stats if isinstance(fallback_stats, dict) else {}

    def _has_complete_team_stats(self, stats: dict[str, Any]) -> bool:
        try:
            return int(stats.get("home", {}).get("matches") or 0) > 0 and int(stats.get("away", {}).get("matches") or 0) > 0
        except (TypeError, ValueError):
            return False

    def _fallback_recent_team_stats(self, home_id: int | str | None, away_id: int | str | None) -> dict[str, Any]:
        return {
            "source": "recent_all_competitions",
            "home": self._team_stats_from_recent_fixtures(home_id),
            "away": self._team_stats_from_recent_fixtures(away_id),
        }

    def _team_stats_from_recent_fixtures(self, team_id: int | str | None) -> dict[str, Any]:
        fixtures = self._api_recent_fixtures_any_competition(team_id)
        form = self._recent_form(fixtures, team_id)
        return {
            "matches": int(form.get("played") or 0),
            "goals_for": float(form.get("goals_for") or 0),
            "goals_against": float(form.get("goals_against") or 0),
            "source": "recent_all_competitions",
            "sample_fixtures": [
                {
                    "fixture_id": item.get("fixture", {}).get("id"),
                    "date": item.get("fixture", {}).get("date"),
                    "league": item.get("league", {}).get("name"),
                    "home": item.get("teams", {}).get("home", {}).get("name"),
                    "away": item.get("teams", {}).get("away", {}).get("name"),
                    "goals": item.get("goals", {}),
                }
                for item in fixtures
            ],
        }

    def _api_team_statistics_payload(self, league_id: int | str, team_id: int | str, season: str) -> dict[str, Any]:
        payload = self._api_get(
            "teams/statistics",
            {"league": league_id, "season": season, "team": team_id},
        )
        self._remember_api_errors(payload, f"team statistics {team_id}")
        return payload.get("response", {})

    def _normalize_api_team_stats(self, response: dict[str, Any]) -> dict[str, Any]:
        fixtures = response.get("fixtures", {})
        goals = response.get("goals", {})
        return {
            "matches": int(fixtures.get("played", {}).get("total") or 0),
            "goals_for": float(goals.get("for", {}).get("total", {}).get("total") or 0),
            "goals_against": float(goals.get("against", {}).get("total", {}).get("total") or 0),
        }

    def _api_fixture_odds(self, fixture_id: int | str) -> dict[str, Any] | None:
        payload = self._api_get("odds", {"fixture": fixture_id})
        self._remember_api_errors(payload, f"odds fixture {fixture_id}")
        for item in payload.get("response", []):
            for bookmaker in item.get("bookmakers", []):
                markets = self._markets_from_api_bookmaker(bookmaker)
                if markets:
                    return markets
        return None

    def _markets_from_api_bookmaker(self, bookmaker: dict[str, Any]) -> dict[str, float] | None:
        markets: dict[str, float] = {}
        for bet in bookmaker.get("bets", []):
            name = self._normalize_bet_name(bet.get("name", ""))
            values = bet.get("values", [])
            if not values:
                continue
            if any(token in name for token in ("match winner", "1x2", "winner")):
                self._parse_match_winner_markets(markets, values)
            elif "double chance" in name:
                self._parse_double_chance_markets(markets, values)
            elif "draw no bet" in name:
                self._parse_draw_no_bet_markets(markets, values)
            elif "both teams score" in name:
                self._parse_yes_no_markets(markets, values, "BTTS")
            elif (
                any(token in name for token in ("first half", "1st half", "1st-half", "1st_half"))
                and any(token in name for token in ("goals over/under", "goals over under", "over/under", "total goals"))
            ):
                self._parse_over_under_markets(markets, values, "FIRST_HALF_TOTALS")
            elif any(token in name for token in ("goals over/under", "goals over under", "over/under")) and "corners" not in name and "cards" not in name and "shots" not in name:
                self._parse_over_under_markets(markets, values, "TOTALS")
            elif any(token in name for token in ("home team over/under", "home team over under")):
                self._parse_over_under_markets(markets, values, "TEAM_TOTAL_HOME")
            elif any(token in name for token in ("away team over/under", "away team over under")):
                self._parse_over_under_markets(markets, values, "TEAM_TOTAL_AWAY")
            elif "corners over under" in name:
                self._parse_over_under_markets(markets, values, "CORNERS_TOTALS")
            elif "home corners over/under" in name or "home corners over under" in name:
                self._parse_over_under_markets(markets, values, "CORNERS_HOME")
            elif "away corners over/under" in name or "away corners over under" in name:
                self._parse_over_under_markets(markets, values, "CORNERS_AWAY")
            elif "cards over/under" in name or "cards over under" in name:
                self._parse_over_under_markets(markets, values, "CARDS_TOTALS")
            elif "home team total cards" in name:
                self._parse_over_under_markets(markets, values, "CARDS_HOME")
            elif "away team total cards" in name:
                self._parse_over_under_markets(markets, values, "CARDS_AWAY")
            elif "shots on goal over/under" in name or "shots on goal over under" in name:
                self._parse_over_under_markets(markets, values, "SHOTS_ON_TARGET_TOTAL")
            elif "shots over/under" in name or "shots over under" in name:
                self._parse_over_under_markets(markets, values, "SHOTS_TOTAL")
        return {"bookmaker": bookmaker.get("name", "API-Football"), "markets": markets} if markets else None

    def _parse_match_winner_markets(self, markets: dict[str, float], values: list[dict[str, Any]]) -> None:
        for value in values:
            label = str(value.get("value", "")).strip().lower()
            odd = self._float(str(value.get("odd", "")))
            if not odd:
                continue
            if label in {"home", "1"}:
                markets["1X2:HOME"] = odd
            elif label in {"draw", "x"}:
                markets["1X2:DRAW"] = odd
            elif label in {"away", "2"}:
                markets["1X2:AWAY"] = odd

    def _parse_double_chance_markets(self, markets: dict[str, float], values: list[dict[str, Any]]) -> None:
        mapping = {"1x": "DOUBLE_CHANCE:1X", "x2": "DOUBLE_CHANCE:X2", "12": "DOUBLE_CHANCE:12"}
        for value in values:
            label = str(value.get("value", "")).strip().lower().replace(" ", "")
            odd = self._float(str(value.get("odd", "")))
            if odd and label in mapping:
                markets[mapping[label]] = odd

    def _parse_draw_no_bet_markets(self, markets: dict[str, float], values: list[dict[str, Any]]) -> None:
        for value in values:
            label = str(value.get("value", "")).strip().lower()
            odd = self._float(str(value.get("odd", "")))
            if not odd:
                continue
            if label in {"home", "1"}:
                markets["DRAW_NO_BET:HOME"] = odd
            elif label in {"away", "2"}:
                markets["DRAW_NO_BET:AWAY"] = odd

    def _parse_yes_no_markets(self, markets: dict[str, float], values: list[dict[str, Any]], prefix: str) -> None:
        for value in values:
            label = str(value.get("value", "")).strip().lower()
            odd = self._float(str(value.get("odd", "")))
            if not odd:
                continue
            if label == "yes":
                markets[f"{prefix}:YES"] = odd
            elif label == "no":
                markets[f"{prefix}:NO"] = odd

    def _parse_over_under_markets(self, markets: dict[str, float], values: list[dict[str, Any]], prefix: str) -> None:
        for value in values:
            label = str(value.get("value", "")).strip().lower()
            odd = self._float(str(value.get("odd", "")))
            if not odd:
                continue
            parsed = self._parse_over_under_value(label)
            if not parsed:
                continue
            side, line = parsed
            markets[f"{prefix}:{side}_{line}"] = odd

    def _parse_over_under_value(self, label: str) -> tuple[str, str] | None:
        parts = label.replace("-", " ").split()
        if len(parts) < 2:
            return None
        side = parts[0]
        if side not in {"over", "under"}:
            return None
        try:
            line = str(float(parts[1])).replace(".", "_")
        except ValueError:
            return None
        return side.upper(), line

    def _normalize_bet_name(self, value: str) -> str:
        return " ".join(str(value).strip().lower().split())

    def _api_premium_context(self, fixture_id: int | str) -> dict[str, Any]:
        context = {}
        for name, endpoint in (
            ("predictions", "predictions"),
            ("injuries", "injuries"),
            ("lineups", "fixtures/lineups"),
        ):
            try:
                payload = self._api_get(endpoint, {"fixture": fixture_id})
                self._remember_api_errors(payload, f"{endpoint} fixture {fixture_id}")
                context[name] = payload.get("response", [])
            except Exception as exc:
                context[name] = {"error": str(exc)}
        return context

    def _api_analysis_context(
        self,
        fixture: dict[str, Any],
        fixture_odds: dict[str, Any] | None,
        season: str,
        home_stats_payload: dict[str, Any],
        away_stats_payload: dict[str, Any],
    ) -> dict[str, Any]:
        fixture_id = fixture.get("fixture", {}).get("id")
        league_id = fixture.get("league", {}).get("id")
        home = fixture.get("teams", {}).get("home", {})
        away = fixture.get("teams", {}).get("away", {})
        home_id = home.get("id")
        away_id = away.get("id")

        home_recent = self._api_recent_fixtures(home_id, league_id, season)
        away_recent = self._api_recent_fixtures(away_id, league_id, season)
        home_recent_source = "current_tournament"
        away_recent_source = "current_tournament"
        if not home_recent:
            home_recent = self._api_recent_fixtures_any_competition(home_id)
            home_recent_source = "recent_all_competitions"
        if not away_recent:
            away_recent = self._api_recent_fixtures_any_competition(away_id)
            away_recent_source = "recent_all_competitions"
        home_recent_stats = self._recent_fixture_statistics(home_recent)
        away_recent_stats = self._recent_fixture_statistics(away_recent)
        injuries = self._safe_api_response("injuries", {"fixture": fixture_id}, f"injuries fixture {fixture_id}")
        lineups = self._safe_api_response("fixtures/lineups", {"fixture": fixture_id}, f"lineups fixture {fixture_id}")
        standings = self._safe_api_response("standings", {"league": league_id, "season": season}, f"standings league {league_id}")
        h2h = self._safe_api_response("fixtures/headtohead", {"h2h": f"{home_id}-{away_id}", "last": 10}, f"h2h {home_id}-{away_id}")

        return {
            "home_away_split": {
                "home_team": self._home_away_split(home_stats_payload, "home"),
                "away_team": self._home_away_split(away_stats_payload, "away"),
            },
            "recent_form": {
                "home_last_5": self._recent_form(home_recent[:5], home_id),
                "home_last_10": self._recent_form(home_recent[:10], home_id),
                "away_last_5": self._recent_form(away_recent[:5], away_id),
                "away_last_10": self._recent_form(away_recent[:10], away_id),
            },
            "attacking_quality": {
                "home": self._attacking_quality(home_stats_payload, home_recent_stats, home_id),
                "away": self._attacking_quality(away_stats_payload, away_recent_stats, away_id),
            },
            "defensive_quality": {
                "home": self._defensive_quality(home_stats_payload, home_recent_stats, home_id),
                "away": self._defensive_quality(away_stats_payload, away_recent_stats, away_id),
            },
            "first_half_goals": {
                "home": self._first_half_goal_profile(home_recent, home_id),
                "away": self._first_half_goal_profile(away_recent, away_id),
            },
            "squad_availability": self._squad_availability(injuries, home_id, away_id),
            "lineups": {
                "source": "fixtures/lineups",
                "available": bool(lineups),
                "items": lineups,
            },
            "standings_motivation": self._standings_motivation(standings, home_id, away_id),
            "schedule_fatigue": {
                "home": self._schedule_fatigue(home_recent, home_id),
                "away": self._schedule_fatigue(away_recent, away_id),
            },
            "head_to_head": {
                "matches": len(h2h),
                "last_10": self._summarize_h2h(h2h, home_id, away_id),
                "raw": h2h,
            },
            "market_context": self._market_context(fixture_odds),
            "data_sources": {
                "home_recent": home_recent_source,
                "away_recent": away_recent_source,
            },
            "request_budget": {
                "conservative_requests_per_match_before": 10,
                "conservative_requests_per_match_after": 20,
                "notes": [
                    "Advanced card and corner markets require recent fixture statistics aggregation.",
                    "This estimate assumes 5 fixture-statistics requests per team in addition to the existing 10-request premium baseline.",
                ],
            },
            "availability_notes": [
                "xG/xGA are included only when the provider returns them; API-Football team statistics may not expose xG for all competitions.",
                "Opening odds and odds movement are included only when the provider exposes bookmaker history for the fixture.",
                "Shots and shots-on-target market picks are only activated when the bookmaker publishes match or team shot markets, not only player props.",
            ],
        }

    def _safe_api_response(self, endpoint: str, params: dict[str, Any], context: str) -> list[dict[str, Any]]:
        try:
            payload = self._api_get(endpoint, params)
            self._remember_api_errors(payload, context)
            response = payload.get("response", [])
            return response if isinstance(response, list) else [response]
        except Exception as exc:
            self.last_errors.append(f"API-Football {context}: {exc}")
            return []

    def _api_recent_fixtures(self, team_id: int | str | None, league_id: int | str | None, season: str) -> list[dict[str, Any]]:
        if not team_id or not league_id:
            return []
        response = self._safe_api_response(
            "fixtures",
            {"team": team_id, "league": league_id, "season": season, "last": 5},
            f"recent fixtures team {team_id}",
        )
        return sorted(response, key=lambda item: item.get("fixture", {}).get("date", ""), reverse=True)

    def _api_recent_fixtures_any_competition(self, team_id: int | str | None, last: int = 10) -> list[dict[str, Any]]:
        if not team_id:
            return []
        response = self._safe_api_response(
            "fixtures",
            {"team": team_id, "last": last},
            f"recent all-competition fixtures team {team_id}",
        )
        completed = [
            item
            for item in response
            if item.get("goals", {}).get("home") is not None and item.get("goals", {}).get("away") is not None
        ]
        return sorted(completed, key=lambda item: item.get("fixture", {}).get("date", ""), reverse=True)

    def _recent_fixture_statistics(self, fixtures: list[dict[str, Any]]) -> list[dict[str, Any]]:
        samples: list[dict[str, Any]] = []
        for fixture in fixtures:
            fixture_id = fixture.get("fixture", {}).get("id")
            if not fixture_id:
                continue
            response = self._safe_api_response("fixtures/statistics", {"fixture": fixture_id}, f"fixture statistics {fixture_id}")
            for row in response:
                sample = dict(row)
                sample["_fixture_id"] = fixture_id
                samples.append(sample)
        return samples

    def _home_away_split(self, stats: dict[str, Any], side: str) -> dict[str, Any]:
        fixtures = stats.get("fixtures", {})
        goals = stats.get("goals", {})
        wins = fixtures.get("wins", {})
        draws = fixtures.get("draws", {})
        loses = fixtures.get("loses", {})
        played = fixtures.get("played", {})
        gf = goals.get("for", {}).get("total", {})
        ga = goals.get("against", {}).get("total", {})
        played_side = int(played.get(side) or 0)
        points = (int(wins.get(side) or 0) * 3) + int(draws.get(side) or 0)
        return {
            "played": played_side,
            "wins": int(wins.get(side) or 0),
            "draws": int(draws.get(side) or 0),
            "losses": int(loses.get(side) or 0),
            "goals_for": int(gf.get(side) or 0),
            "goals_against": int(ga.get(side) or 0),
            "points_per_match": round(points / played_side, 3) if played_side else None,
        }

    def _recent_form(self, fixtures: list[dict[str, Any]], team_id: int | str | None) -> dict[str, Any]:
        wins = draws = losses = goals_for = goals_against = clean_sheets = failed_to_score = 0
        for item in fixtures:
            teams = item.get("teams", {})
            goals = item.get("goals", {})
            is_home = teams.get("home", {}).get("id") == team_id
            own_goals = goals.get("home") if is_home else goals.get("away")
            opp_goals = goals.get("away") if is_home else goals.get("home")
            if own_goals is None or opp_goals is None:
                continue
            goals_for += int(own_goals)
            goals_against += int(opp_goals)
            if own_goals > opp_goals:
                wins += 1
            elif own_goals == opp_goals:
                draws += 1
            else:
                losses += 1
            clean_sheets += int(opp_goals == 0)
            failed_to_score += int(own_goals == 0)
        played = wins + draws + losses
        return {
            "played": played,
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "goals_for": goals_for,
            "goals_against": goals_against,
            "clean_sheets": clean_sheets,
            "failed_to_score": failed_to_score,
        }

    def _first_half_goal_profile(self, fixtures: list[dict[str, Any]], team_id: int | str | None) -> dict[str, Any]:
        goals_for = goals_against = total_goals = over_0_5 = over_1_5 = samples = 0
        for item in fixtures:
            teams = item.get("teams", {})
            halftime = item.get("score", {}).get("halftime", {})
            home_goals = halftime.get("home")
            away_goals = halftime.get("away")
            if home_goals is None or away_goals is None:
                continue
            is_home = teams.get("home", {}).get("id") == team_id
            own_goals = int(home_goals if is_home else away_goals)
            opp_goals = int(away_goals if is_home else home_goals)
            match_total = int(home_goals) + int(away_goals)
            samples += 1
            goals_for += own_goals
            goals_against += opp_goals
            total_goals += match_total
            over_0_5 += int(match_total > 0.5)
            over_1_5 += int(match_total > 1.5)
        return {
            "samples": samples,
            "goals_for_avg": round(goals_for / samples, 3) if samples else None,
            "goals_against_avg": round(goals_against / samples, 3) if samples else None,
            "match_total_avg": round(total_goals / samples, 3) if samples else None,
            "over_0_5_rate": round(over_0_5 / samples, 3) if samples else None,
            "over_1_5_rate": round(over_1_5 / samples, 3) if samples else None,
        }

    def _attacking_quality(self, stats: dict[str, Any], recent_stats: list[dict[str, Any]], team_id: int | str | None) -> dict[str, Any]:
        goals_for = stats.get("goals", {}).get("for", {})
        fixtures = stats.get("fixtures", {}).get("played", {})
        total_played = int(fixtures.get("total") or 0)
        total_goals = float(goals_for.get("total", {}).get("total") or 0)
        recent = self._aggregate_fixture_statistics(recent_stats, team_id)
        return {
            "goals_for_total": total_goals,
            "goals_for_avg": float(goals_for.get("average", {}).get("total") or 0),
            "goals_per_match": round(total_goals / total_played, 3) if total_played else None,
            "minute_distribution": goals_for.get("minute", {}),
            "xg": stats.get("xg") or stats.get("expected_goals"),
            "shots_total": recent.get("shots_total_for_avg"),
            "shots_on_target": recent.get("shots_on_goal_for_avg"),
            "big_chances": stats.get("big_chances"),
            "corners_for": recent.get("corners_for_avg"),
        }

    def _defensive_quality(self, stats: dict[str, Any], recent_stats: list[dict[str, Any]], team_id: int | str | None) -> dict[str, Any]:
        goals_against = stats.get("goals", {}).get("against", {})
        fixtures = stats.get("fixtures", {}).get("played", {})
        total_played = int(fixtures.get("total") or 0)
        total_goals = float(goals_against.get("total", {}).get("total") or 0)
        clean_sheet = stats.get("clean_sheet", {})
        failed_to_score = stats.get("failed_to_score", {})
        recent = self._aggregate_fixture_statistics(recent_stats, team_id)
        return {
            "goals_against_total": total_goals,
            "goals_against_avg": float(goals_against.get("average", {}).get("total") or 0),
            "goals_against_per_match": round(total_goals / total_played, 3) if total_played else None,
            "minute_distribution": goals_against.get("minute", {}),
            "clean_sheets_total": clean_sheet.get("total"),
            "failed_to_score_total": failed_to_score.get("total"),
            "xga": stats.get("xga") or stats.get("expected_goals_against"),
            "shots_against": recent.get("shots_total_against_avg"),
            "big_chances_conceded": stats.get("big_chances_conceded"),
            "shots_on_target_against": recent.get("shots_on_goal_against_avg"),
            "corners_against": recent.get("corners_against_avg"),
            "yellow_cards_avg": recent.get("yellow_cards_avg"),
        }

    def _squad_availability(self, injuries: list[dict[str, Any]], home_id: int | str | None, away_id: int | str | None) -> dict[str, Any]:
        by_side = {"home": [], "away": [], "unknown": []}
        for item in injuries:
            team_id = item.get("team", {}).get("id")
            side = "home" if team_id == home_id else "away" if team_id == away_id else "unknown"
            by_side[side].append(
                {
                    "player": item.get("player", {}).get("name"),
                    "type": item.get("player", {}).get("type"),
                    "reason": item.get("player", {}).get("reason"),
                    "fixture": item.get("fixture", {}).get("id"),
                }
            )
        return {
            "home_absences": by_side["home"],
            "away_absences": by_side["away"],
            "unknown_absences": by_side["unknown"],
        }

    def _standings_motivation(self, standings: list[dict[str, Any]], home_id: int | str | None, away_id: int | str | None) -> dict[str, Any]:
        rows = []
        for league in standings:
            for group in league.get("league", {}).get("standings", []):
                rows.extend(group)
        return {
            "home": self._standing_row(rows, home_id),
            "away": self._standing_row(rows, away_id),
        }

    def _standing_row(self, rows: list[dict[str, Any]], team_id: int | str | None) -> dict[str, Any] | None:
        for row in rows:
            if row.get("team", {}).get("id") == team_id:
                return {
                    "rank": row.get("rank"),
                    "points": row.get("points"),
                    "goals_diff": row.get("goalsDiff"),
                    "description": row.get("description"),
                    "form": row.get("form"),
                    "status": row.get("status"),
                }
        return None

    def _schedule_fatigue(self, recent: list[dict[str, Any]], team_id: int | str | None) -> dict[str, Any]:
        dated = [self._parse_iso_datetime(item.get("fixture", {}).get("date", "")) for item in recent]
        dated = [item for item in dated if item]
        days_between = []
        for previous, current in zip(dated[1:], dated):
            days_between.append((current - previous).days)
        return {
            "recent_matches_count": len(recent),
            "days_since_last_match": days_between[0] if days_between else None,
            "average_rest_days_last_10": round(sum(days_between) / len(days_between), 2) if days_between else None,
            "team_id": team_id,
        }

    def _summarize_h2h(self, fixtures: list[dict[str, Any]], home_id: int | str | None, away_id: int | str | None) -> dict[str, Any]:
        home_wins = away_wins = draws = goals_home_team = goals_away_team = 0
        for item in fixtures:
            teams = item.get("teams", {})
            goals = item.get("goals", {})
            home_fixture_team = teams.get("home", {}).get("id")
            away_fixture_team = teams.get("away", {}).get("id")
            home_goals = goals.get("home")
            away_goals = goals.get("away")
            if home_goals is None or away_goals is None:
                continue
            if home_fixture_team == home_id:
                goals_home_team += home_goals
                goals_away_team += away_goals
                if home_goals > away_goals:
                    home_wins += 1
                elif home_goals < away_goals:
                    away_wins += 1
                else:
                    draws += 1
            elif away_fixture_team == home_id:
                goals_home_team += away_goals
                goals_away_team += home_goals
                if away_goals > home_goals:
                    home_wins += 1
                elif away_goals < home_goals:
                    away_wins += 1
                else:
                    draws += 1
        return {
            "home_team_wins": home_wins,
            "away_team_wins": away_wins,
            "draws": draws,
            "home_team_goals": goals_home_team,
            "away_team_goals": goals_away_team,
            "home_id": home_id,
            "away_id": away_id,
        }

    def _market_context(self, odds: dict[str, Any] | None) -> dict[str, Any]:
        markets = (odds or {}).get("markets", {})
        numeric_markets = {}
        for key, value in markets.items():
            try:
                numeric_markets[key] = float(value)
            except (TypeError, ValueError):
                continue
        implied = {key: round(1 / value, 6) for key, value in numeric_markets.items() if value > 1}
        overround = sum(implied.values()) - 1 if implied else None
        no_vig = {}
        if implied and overround is not None:
            total = sum(implied.values())
            no_vig = {key: round(value / total, 6) for key, value in implied.items()}
        return {
            "bookmaker": (odds or {}).get("bookmaker"),
            "current_odds": numeric_markets,
            "implied_probabilities": implied,
            "no_vig_probabilities": no_vig,
            "overround": round(overround, 6) if overround is not None else None,
            "opening_odds": None,
            "odds_movement": None,
        }

    def _aggregate_fixture_statistics(self, recent_stats: list[dict[str, Any]], team_id: int | str | None) -> dict[str, Any]:
        if not team_id:
            return {}
        totals = {
            "samples": 0,
            "shots_total_for": 0.0,
            "shots_total_against": 0.0,
            "shots_on_goal_for": 0.0,
            "shots_on_goal_against": 0.0,
            "corners_for": 0.0,
            "corners_against": 0.0,
            "yellow_cards": 0.0,
        }
        grouped: dict[Any, dict[int | str, dict[str, Any]]] = {}
        for row in recent_stats:
            fixture_id = row.get("_fixture_id")
            team = row.get("team", {})
            team_row_id = team.get("id")
            if fixture_id is None or team_row_id is None:
                continue
            grouped.setdefault(fixture_id, {})[team_row_id] = row

        for teams in grouped.values():
            current = teams.get(team_id)
            if not current or len(teams) < 2:
                continue
            opponent = next((item for other_team_id, item in teams.items() if other_team_id != team_id), None)
            if not opponent:
                continue
            totals["samples"] += 1
            current_map = self._statistics_map(current.get("statistics", []))
            opponent_map = self._statistics_map(opponent.get("statistics", []))
            totals["shots_total_for"] += current_map.get("total_shots", 0.0)
            totals["shots_total_against"] += opponent_map.get("total_shots", 0.0)
            totals["shots_on_goal_for"] += current_map.get("shots_on_goal", 0.0)
            totals["shots_on_goal_against"] += opponent_map.get("shots_on_goal", 0.0)
            totals["corners_for"] += current_map.get("corner_kicks", 0.0)
            totals["corners_against"] += opponent_map.get("corner_kicks", 0.0)
            totals["yellow_cards"] += current_map.get("yellow_cards", 0.0)

        samples = totals["samples"] or 0
        if not samples:
            return {}
        return {
            "samples": samples,
            "shots_total_for_avg": round(totals["shots_total_for"] / samples, 3),
            "shots_total_against_avg": round(totals["shots_total_against"] / samples, 3),
            "shots_on_goal_for_avg": round(totals["shots_on_goal_for"] / samples, 3),
            "shots_on_goal_against_avg": round(totals["shots_on_goal_against"] / samples, 3),
            "corners_for_avg": round(totals["corners_for"] / samples, 3),
            "corners_against_avg": round(totals["corners_against"] / samples, 3),
            "yellow_cards_avg": round(totals["yellow_cards"] / samples, 3),
        }

    def _statistics_map(self, statistics: list[dict[str, Any]]) -> dict[str, float]:
        mapping = {}
        for item in statistics:
            key = str(item.get("type", "")).strip().lower().replace(" ", "_")
            value = item.get("value")
            if value is None:
                continue
            if isinstance(value, str) and value.endswith("%"):
                try:
                    mapping[key] = float(value.rstrip("%"))
                except ValueError:
                    continue
                continue
            try:
                mapping[key] = float(value)
            except (TypeError, ValueError):
                continue
        return mapping

    def _parse_iso_datetime(self, value: str) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _api_get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v not in ("", None)})
        url = f"{self.base_url.rstrip('/')}/{endpoint}?{query}"
        cache_key = f"{endpoint}?{query}"
        if cache_key in self._response_cache:
            self.cache_hits += 1
            return self._response_cache[cache_key]
        cached_payload = self._read_disk_cache(endpoint, query, cache_key)
        if cached_payload is not None:
            return cached_payload
        self.cache_misses += 1
        if self.request_delay_seconds > 0:
            time_module.sleep(self.request_delay_seconds)
        request = urllib.request.Request(url, headers={"x-apisports-key": self.api_key})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self._response_cache[cache_key] = payload
        self._write_disk_cache(endpoint, query, cache_key, payload)
        return payload

    def _read_disk_cache(self, endpoint: str, query: str, cache_key: str) -> dict[str, Any] | None:
        if not self.cache_enabled:
            return None
        path = self._cache_path(endpoint, query)
        if not path.exists():
            return None
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        fetched_at = self._parse_iso_datetime(str(envelope.get("fetched_at", "")))
        if not fetched_at:
            return None
        age_seconds = (datetime.now(timezone.utc) - fetched_at.astimezone(timezone.utc)).total_seconds()
        if age_seconds > self._cache_ttl_seconds(endpoint):
            return None
        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            return None
        self.cache_hits += 1
        self._response_cache[cache_key] = payload
        return payload

    def _write_disk_cache(self, endpoint: str, query: str, cache_key: str, payload: dict[str, Any]) -> None:
        if not self.cache_enabled:
            return
        path = self._cache_path(endpoint, query)
        path.parent.mkdir(parents=True, exist_ok=True)
        envelope = {
            "endpoint": endpoint,
            "query": query,
            "cache_key": cache_key,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "ttl_seconds": self._cache_ttl_seconds(endpoint),
            "payload": payload,
        }
        path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def _cache_path(self, endpoint: str, query: str) -> Path:
        digest = hashlib.sha256(f"{endpoint}?{query}".encode("utf-8")).hexdigest()
        safe_endpoint = endpoint.replace("/", "_")
        return self.cache_dir / safe_endpoint / f"{digest}.json"

    def _cache_ttl_seconds(self, endpoint: str) -> int:
        custom_ttl = os.getenv(f"API_FOOTBALL_CACHE_TTL_{endpoint.upper().replace('/', '_')}")
        if custom_ttl:
            try:
                return int(custom_ttl)
            except ValueError:
                pass
        if endpoint == "status":
            return 60
        if endpoint == "odds":
            return 15 * 60
        if endpoint in {"fixtures", "fixtures/statistics", "fixtures/headtohead", "teams/statistics", "standings"}:
            return 7 * 24 * 60 * 60
        if endpoint in {"injuries", "fixtures/lineups", "predictions"}:
            return 6 * 60 * 60
        return 24 * 60 * 60

    def _remember_api_errors(self, payload: dict[str, Any], context: str) -> None:
        errors = payload.get("errors")
        if not errors:
            return
        if isinstance(errors, dict):
            detail = "; ".join(f"{key}: {value}" for key, value in errors.items())
        else:
            detail = str(errors)
        message = f"API-Football {context}: {detail}"
        if message not in self.last_errors:
            self.last_errors.append(message)

    def _normalize_local_match(self, item: dict[str, Any]) -> dict[str, Any] | None:
        required = ["id", "league", "kickoff", "home_team", "away_team"]
        if any(not item.get(field) for field in required):
            return None
        return {
            "id": str(item["id"]),
            "league": str(item["league"]),
            "kickoff": str(item["kickoff"]),
            "home_team": str(item["home_team"]),
            "away_team": str(item["away_team"]),
            "raw": item.get("raw", item),
        }

    def _csv(self, value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]

    def _mapping(self, value: str) -> dict[str, str]:
        mapping = {}
        for item in self._csv(value):
            if ":" not in item:
                continue
            key, mapped_value = item.split(":", 1)
            mapping[key.strip()] = mapped_value.strip()
        return mapping

    def _season_for_league(self, league: int | str) -> str:
        return self.seasons_by_league.get(str(league), self.season)

    def _matches_from_football_data(self, from_date: date, to_date: date, leagues: list[str]) -> list[dict[str, Any]]:
        fixture_rows = self._read_csv_url(self.football_data_fixtures_url)
        wanted_leagues = {item.upper() for item in leagues}
        candidates: list[dict[str, Any]] = []
        for row in fixture_rows:
            league = (row.get("Div") or row.get("League") or "").strip().upper()
            if wanted_leagues and league not in wanted_leagues:
                continue
            match_date = self._parse_date(row.get("Date", ""))
            if not match_date or not from_date <= match_date <= to_date:
                continue
            home_team = (row.get("HomeTeam") or "").strip()
            away_team = (row.get("AwayTeam") or "").strip()
            if not league or not home_team or not away_team:
                continue
            candidates.append(
                {
                    "row": row,
                    "league": league,
                    "match_date": match_date,
                    "kickoff": self._kickoff_iso(match_date, row.get("Time", "")),
                    "home_team": home_team,
                    "away_team": away_team,
                }
            )

        histories = {
            league: self._team_stats_from_history(league, self._season_code(to_date))
            for league in sorted({item["league"] for item in candidates})
        }

        matches: list[dict[str, Any]] = []
        for item in candidates:
            stats = self._stats_for_match(histories.get(item["league"], []), item["match_date"], item["home_team"], item["away_team"])
            odds = self._odds_from_football_data_row(item["row"])
            raw = {"source": "football-data.co.uk", "fixture": item["row"], "stats": stats}
            if odds:
                raw["odds"] = odds
            matches.append(
                {
                    "id": self._match_id(item["league"], item["match_date"], item["home_team"], item["away_team"]),
                    "league": item["league"],
                    "kickoff": item["kickoff"],
                    "home_team": item["home_team"],
                    "away_team": item["away_team"],
                    "raw": raw,
                }
            )
        return matches

    def _read_csv_url(self, url: str) -> list[dict[str, str]]:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = response.read()
        try:
            content = payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            content = payload.decode("latin-1")
        reader = csv.DictReader(io.StringIO(content))
        return [{(key or "").lstrip("\ufeff"): value for key, value in row.items()} for row in reader]

    def _team_stats_from_history(self, league: str, season: str) -> list[dict[str, Any]]:
        url = self.football_data_history_url.format(season=season, league=urllib.parse.quote(league))
        try:
            rows = self._read_csv_url(url)
        except Exception:
            return []
        history: list[dict[str, Any]] = []
        for row in rows:
            match_date = self._parse_date(row.get("Date", ""))
            home_team = (row.get("HomeTeam") or "").strip()
            away_team = (row.get("AwayTeam") or "").strip()
            if not match_date or not home_team or not away_team:
                continue
            try:
                home_goals = int(row.get("FTHG", ""))
                away_goals = int(row.get("FTAG", ""))
            except ValueError:
                continue
            history.append(
                {
                    "date": match_date,
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_goals": home_goals,
                    "away_goals": away_goals,
                }
            )
        return history

    def _stats_for_match(
        self,
        history: list[dict[str, Any]],
        match_date: date,
        home_team: str,
        away_team: str,
    ) -> dict[str, dict[str, Any]]:
        return {
            "home": self._aggregate_team(history, match_date, home_team),
            "away": self._aggregate_team(history, match_date, away_team),
        }

    def _aggregate_team(self, history: list[dict[str, Any]], before_date: date, team: str) -> dict[str, Any]:
        matches = goals_for = goals_against = 0
        for row in history:
            if row["date"] >= before_date:
                continue
            if row["home_team"] == team:
                matches += 1
                goals_for += row["home_goals"]
                goals_against += row["away_goals"]
            elif row["away_team"] == team:
                matches += 1
                goals_for += row["away_goals"]
                goals_against += row["home_goals"]
        return {"matches": matches, "goals_for": goals_for, "goals_against": goals_against}

    def _odds_from_football_data_row(self, row: dict[str, str]) -> dict[str, Any] | None:
        for bookmaker, home_col, draw_col, away_col in (
            ("Football-Data Avg", "AvgH", "AvgD", "AvgA"),
            ("Football-Data Max", "MaxH", "MaxD", "MaxA"),
            ("Bet365", "B365H", "B365D", "B365A"),
            ("William Hill", "WHH", "WHD", "WHA"),
        ):
            odds = {
                "1X2:HOME": self._float(row.get(home_col, "")),
                "1X2:DRAW": self._float(row.get(draw_col, "")),
                "1X2:AWAY": self._float(row.get(away_col, "")),
            }
            if all(value and value > 1 for value in odds.values()):
                return {"bookmaker": bookmaker, "markets": odds}
        return None

    def _parse_date(self, value: str) -> date | None:
        value = value.strip()
        for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        return None

    def _kickoff_iso(self, match_date: date, kickoff_time: str) -> str:
        kickoff_time = kickoff_time.strip()
        for fmt in ("%H:%M", "%H.%M"):
            try:
                parsed = datetime.strptime(kickoff_time, fmt).time()
                return datetime.combine(match_date, parsed).isoformat()
            except ValueError:
                continue
        return datetime.combine(match_date, time()).isoformat()

    def _season_code(self, day: date) -> str:
        start_year = day.year if day.month >= 7 else day.year - 1
        end_year = start_year + 1
        return f"{start_year % 100:02d}{end_year % 100:02d}"

    def _match_id(self, league: str, match_date: date, home_team: str, away_team: str) -> str:
        seed = f"{league}|{match_date.isoformat()}|{home_team}|{away_team}".lower()
        return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]

    def _float(self, value: str) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
