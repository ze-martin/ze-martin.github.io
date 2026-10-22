"""Recover verified Betano event links without repeating fixture discovery."""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import load_environment
from tools.enrich_protocol_with_betano import enrich_data, scrape_event, split_match_name


async def supplement(base: Path, target: Path, events: list[str], refresh_api: bool = False) -> None:
    from playwright.async_api import async_playwright

    data = json.loads(base.read_text(encoding="utf-8"))
    current = json.loads(target.read_text(encoding="utf-8")) if target.exists() else data
    known = {r["match"] for r in data.get("results", []) if r.get("pre_match_eligible") is not False}
    scraped = {
        r["match"]: {"url": r.get("betano_source_url"), "odds": r.get("betano_raw_odds") or {},
                     "market_count": r.get("betano_market_count", 0)}
        for r in current.get("results", [])
    }
    if refresh_api:
        from apis.football_api import FootballAPI
        from tools.generate_protocol_probabilities import build_market_rows, actionable_market
        api = FootballAPI()
        for result in data.get("results", []):
            if result.get("pre_match_eligible") is False:
                continue
            # A failed request must not retain a previously misclassified price.
            try:
                odds = api._api_fixture_odds(result["match_id"]) or {}
            except Exception as exc:
                odds = {}
                print(f"AVISO API {result['match']}: {exc}", flush=True)
            rows = result.get("all_markets") or []
            rows = build_market_rows({r["key"]: r["probability"] for r in rows}, odds,
                                     {r["key"]: r.get("source_key") for r in rows})
            result["bookmaker"] = odds.get("bookmaker", "Sin cuota")
            result["all_markets"] = result["probability_markets"] = rows
            positive = [r for r in rows if r.get("ev") is not None and r["ev"] >= .02 and actionable_market(r)]
            result["recommended_pick"] = max(positive, key=lambda r: (r.get("recommendation_score") or 0, r["probability"], r["ev"]), default=None)
        data["odds_refreshed_at"] = datetime.now(timezone.utc).isoformat()
        data["api_odds_mapping_version"] = "exact-market-and-period-v2"
        print("Cuotas API y EV recalculados con mercados exactos", flush=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        try:
            for event in events:
                match, url = event.split("=", 1)
                if match not in known or not url.startswith("https://www.betano.pe/cuotas-de-partido/"):
                    raise ValueError(f"Partido o URL no válido: {match}")
                home, away = split_match_name(match)
                page = await browser.new_page(locale="es-PE", timezone_id="America/Lima",
                                              viewport={"width": 1365, "height": 1400},
                                              user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
                page.set_default_timeout(20000)
                await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                try:
                    recovered = await scrape_event(page, url, home, away)
                    if recovered.get("odds"):
                        scraped[match] = recovered
                    print(f"Recuperación {match}: {len(recovered.get('odds') or {})} cuotas", flush=True)
                except Exception as exc:
                    print(f"AVISO recuperación {match}: {exc}", flush=True)
                finally:
                    await page.close()
        finally:
            await browser.close()
    target.write_text(json.dumps(enrich_data(data, scraped), ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    load_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--event", action="append", default=[], help="Partido=URL verificada")
    parser.add_argument("--refresh-api", action="store_true")
    args = parser.parse_args()
    asyncio.run(supplement(args.base, args.target, args.event, args.refresh_api))
