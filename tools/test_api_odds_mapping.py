"""Regression checks for full-time versus period/team API prices."""
import sys
import unittest
from unittest.mock import patch
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apis.football_api import FootballAPI
from tools.generate_protocol_probabilities import generate


class OddsMappingTest(unittest.TestCase):
    def parse(self, bets):
        return FootballAPI.__new__(FootballAPI)._markets_from_api_bookmaker(
            {"name": "Test", "bets": bets})["markets"]

    def test_periods_cannot_overwrite_full_time(self):
        def bet(name, label, odd):
            return {"name": name, "values": [{"value": label, "odd": str(odd)}]}
        markets = self.parse([
            bet("Match Winner", "Home", 1.4),
            bet("First Half Winner", "Home", 2.5),
            bet("Corners 1x2", "Home", 9),
            bet("Both Teams Score", "Yes", 1.75),
            bet("Both Teams Score - First Half", "Yes", 4.4),
            bet("Goals Over/Under", "Over 1.5", 1.3),
            bet("Goals Over/Under - Second Half", "Over 1.5", 2.1),
            bet("Home Team Over/Under", "Over 1.5", 3.1),
            bet("Goals Over/Under First Half", "Over 1.5", 2.3),
            bet("Double Chance", "Home/Draw", 1.1),
            bet("Double Chance - First Half", "Home/Draw", 1.8),
        ])
        self.assertEqual(markets["1X2:HOME"], 1.4)
        self.assertEqual(markets["BTTS:YES"], 1.75)
        self.assertEqual(markets["TOTALS:OVER_1_5"], 1.3)
        self.assertEqual(markets["TEAM_TOTAL_HOME:OVER_1_5"], 3.1)
        self.assertEqual(markets["FIRST_HALF_TOTALS:OVER_1_5"], 2.3)
        self.assertEqual(markets["DOUBLE_CHANCE:1X"], 1.1)

    def test_no_full_time_total_is_invented(self):
        markets = self.parse([{"name": "Goals Over/Under - Second Half", "values": [
            {"value": "Over 1.5", "odd": "2.1"}]},
            {"name": "Match Winner", "values": [{"value": "Home", "odd": "1.4"}]}])
        self.assertNotIn("TOTALS:OVER_1_5", markets)


class FixtureEligibilityTest(unittest.TestCase):
    def test_live_fixture_is_not_recommended_and_date_is_narrowed(self):
        class FakeAPI:
            fixture_timezone = "America/Lima"
            local_file = ""
            source = "api-football"
            cache_dir = Path("data/api_cache")

            def get_matches(self, start, end, leagues):
                self.queried = (start, end)
                return [{"id": "1", "league": "Test", "home_team": "A", "away_team": "B",
                         "kickoff": "2026-10-22T15:00:00Z",
                         "raw": {"fixture": {"status": {"short": "1H", "elapsed": 10}},
                                 "goals": {"home": 0, "away": 1}}}]

            def get_embedded_odds(self, matches):
                return {}

        api = FakeAPI()
        with patch("tools.generate_protocol_probabilities.FootballAPI", return_value=api):
            data = generate(date(2026, 10, 22), date(2026, 10, 23), ["3"], "2026-10-22")
        row = data["results"][0]
        self.assertEqual(api.queried, (date(2026, 10, 22), date(2026, 10, 22)))
        self.assertFalse(row["pre_match_eligible"])
        self.assertEqual(row["all_markets"], [])
        self.assertIsNone(row["recommended_pick"])
        self.assertIn("0-1", row["note"])


if __name__ == "__main__":
    unittest.main()
