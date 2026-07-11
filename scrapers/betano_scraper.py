from __future__ import annotations

import asyncio
import os
import random
from typing import Any


class BetanoScraper:
    def __init__(self) -> None:
        self.base_url = os.getenv("BETANO_URL", "https://www.betano.com")
        self.headless = os.getenv("BETANO_HEADLESS", "true").lower() != "false"
        self.timeout_ms = int(os.getenv("BETANO_TIMEOUT_MS", "25000"))

    async def get_odds_for_matches(self, matches: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        if not matches:
            return {}
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return {}

        odds_by_match: dict[str, dict[str, Any]] = {}
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            page = await browser.new_page(locale="es-PE")
            page.set_default_timeout(self.timeout_ms)
            try:
                await page.goto(self.base_url, wait_until="domcontentloaded")
                await asyncio.sleep(random.uniform(1.2, 2.8))
                for match in matches:
                    markets = await self._extract_match_markets(page, match)
                    if markets:
                        odds_by_match[match["id"]] = {"bookmaker": "Betano", "markets": markets}
                    await asyncio.sleep(random.uniform(0.8, 2.0))
            finally:
                await browser.close()
        return odds_by_match

    async def _extract_match_markets(self, page, match: dict[str, Any]) -> dict[str, float]:
        search_terms = f'{match["home_team"]} {match["away_team"]}'
        try:
            search = page.get_by_placeholder("Buscar").first
            if await search.count() > 0:
                await search.fill(search_terms)
                await asyncio.sleep(random.uniform(1.0, 2.0))
        except Exception:
            pass

        text = await page.locator("body").inner_text(timeout=self.timeout_ms)
        if match["home_team"].lower() not in text.lower() or match["away_team"].lower() not in text.lower():
            return {}

        numbers: list[float] = []
        for token in text.replace(",", ".").split():
            try:
                value = float(token)
            except ValueError:
                continue
            if 1.01 <= value <= 50:
                numbers.append(value)

        if len(numbers) < 3:
            return {}
        return {
            "1X2:HOME": numbers[0],
            "1X2:DRAW": numbers[1],
            "1X2:AWAY": numbers[2],
        }

    def get_odds(self, matches: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return asyncio.run(self.get_odds_for_matches(matches))
