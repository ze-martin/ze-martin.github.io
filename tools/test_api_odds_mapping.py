"""Regression checks for full-time versus period/team API prices."""
import sys
import unittest
from unittest.mock import patch, AsyncMock
from types import SimpleNamespace
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apis.football_api import FootballAPI
from tools.generate_protocol_probabilities import generate
from tools.enrich_protocol_with_betano import betano_coverage_status, discover_event_links, BETANO_HOME


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
            bet('Results/Both Teams Score','Home/Yes',2.88),
        ])
        self.assertEqual(markets["1X2:HOME"], 1.4)
        self.assertEqual(markets["BTTS:YES"], 1.75)
        self.assertEqual(markets["TOTALS:OVER_1_5"], 1.3)
        self.assertEqual(markets["TEAM_TOTAL_HOME:OVER_1_5"], 3.1)
        self.assertEqual(markets["FIRST_HALF_TOTALS:OVER_1_5"], 2.3)
        self.assertEqual(markets["DOUBLE_CHANCE:1X"], 1.1)
        self.assertEqual(markets['WIN_BTTS:HOME_YES'],2.88)

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


class BetanoDenialTest(unittest.IsolatedAsyncioTestCase):
    async def test_tls_error_stops_navigation_without_weakening_https(self):
        page = SimpleNamespace(context=SimpleNamespace(browser=None),
                               on=lambda *args: None,
                               goto=AsyncMock(side_effect=RuntimeError('net::ERR_CERT_AUTHORITY_INVALID')))
        with patch('tools.enrich_protocol_with_betano.discovery_urls_for_matches', return_value=[BETANO_HOME, BETANO_HOME + 'sport/futbol/']):
            await discover_event_links(page, [])
        self.assertEqual(page.goto.await_count, 1)
        self.assertIn('ERR_CERT_AUTHORITY_INVALID', page._betano_discovery_errors[0])
        self.assertEqual(betano_coverage_status({'error': 'net::ERR_CERT_AUTHORITY_INVALID'}, []), 'Betano no verificado (error TLS)')

    async def test_denied_feed_is_not_retried_on_other_competitions(self):
        class Page:
            context = SimpleNamespace(browser=None)

            def __init__(self):
                self.visited = []
                self.handlers = []

            def on(self, event, handler):
                self.handlers.append(handler)

            async def goto(self, url, **kwargs):
                self.visited.append(url)
                if url != BETANO_HOME:
                    for handler in self.handlers:
                        handler(SimpleNamespace(status=403, url='https://www.betano.pe/api/league/hot/upcoming'))

            async def wait_for_timeout(self, ms):
                pass

        page = Page()
        routes = ['https://www.betano.pe/sport/futbol/test-one/', 'https://www.betano.pe/sport/futbol/test-two/', BETANO_HOME]
        with patch('tools.enrich_protocol_with_betano.discovery_urls_for_matches', return_value=routes), patch('tools.enrich_protocol_with_betano.collect_event_links_from_page', new=AsyncMock(return_value=[])):
            await discover_event_links(page, [{'match': 'A vs B', 'home': 'A', 'away': 'B'}])
        self.assertEqual(page.visited, [routes[0], BETANO_HOME])
        self.assertEqual(page._betano_discovery_denied_paths, ['/api/league/hot/upcoming'])
        self.assertEqual(betano_coverage_status({'error': 'HTTP 403'}, []), 'Betano no verificado (HTTP 403)')


if __name__ == "__main__":
    unittest.main()
