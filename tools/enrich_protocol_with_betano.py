from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import unicodedata
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BETANO_HOME = "https://www.betano.pe/"
BETANO_DISCOVERY_URLS = [
    BETANO_HOME,
    "https://www.betano.pe/sport/futbol/",
]

TEAM_ALIASES = {
    "argentina": ["argentina"],
    "egypt": ["egypt", "egipto"],
    "switzerland": ["switzerland", "suiza"],
    "colombia": ["colombia"],
    "portugal": ["portugal"],
    "uzbekistan": ["uzbekistan", "uzbekistán"],
    "curacao": ["curacao", "curazao", "curaçao"],
    "cote d'ivoire": ["cote d ivoire", "costa de marfil"],
    "ivory coast": ["ivory coast", "costa de marfil"],
    "ecuador": ["ecuador"],
    "germany": ["germany", "alemania"],
    "japan": ["japan", "japón"],
    "sweden": ["sweden", "suecia"],
    "tunisia": ["tunisia", "túnez", "tunez"],
    "netherlands": ["netherlands", "países bajos", "paises bajos", "holanda"],
    "brazil": ["brazil", "brasil"],
    "france": ["france", "francia"],
    "morocco": ["morocco", "marruecos"],
    "spain": ["spain", "españa", "espana"],
    "england": ["england", "inglaterra"],
    "usa": ["usa", "estados unidos"],
    "united states": ["united states", "estados unidos", "usa"],
    "mexico": ["mexico", "méxico"],
    "canada": ["canada", "canadá"],
    "uruguay": ["uruguay"],
    "chile": ["chile"],
    "peru": ["peru", "perú"],
    "belgium": ["belgium", "bélgica", "belgica"],
    "norway": ["norway", "noruega"],
    "athletico-pr": ["athletico pr", "athletico paranaense", "atlético paranaense", "athletico"],
    "atletico-mg": ["atletico mg", "atlético mg", "atletico mineiro", "atlético mineiro"],
    "atletico goianiense": ["atletico goianiense", "atlético goianiense", "atletico go"],
    "bahia": ["bahia", "ec bahia"],
    "botafogo": ["botafogo", "botafogo rj"],
    "corinthians": ["corinthians", "sc corinthians"],
    "coritiba": ["coritiba", "coritiba fc"],
    "cruzeiro": ["cruzeiro", "cruzeiro ec"],
    "flamengo": ["flamengo", "cr flamengo"],
    "fluminense": ["fluminense", "fluminense rj"],
    "fortaleza ec": ["fortaleza ec", "fortaleza"],
    "gremio": ["gremio", "grêmio", "gremio fbpa", "grêmio fbpa"],
    "internacional": ["internacional", "sc internacional", "inter porto alegre"],
    "juventude": ["juventude", "ec juventude"],
    "mirassol": ["mirassol", "mirassol fc"],
    "palmeiras": ["palmeiras", "se palmeiras"],
    "red bull bragantino": ["red bull bragantino", "rb bragantino", "bragantino"],
    "santos": ["santos", "santos fc"],
    "sao paulo": ["sao paulo", "são paulo", "sao paulo fc", "são paulo fc"],
    "sport recife": ["sport recife", "sport club recife", "sport"],
    "vasco da gama": ["vasco da gama", "vasco"],
    "vitoria": ["vitoria", "vitória", "ec vitoria", "ec vitória"],
    "river plate": ["river plate"],
    "boca juniors": ["boca juniors", "boca"],
    "racing club": ["racing club", "racing"],
    "independiente": ["independiente"],
    "san lorenzo": ["san lorenzo"],
    "estudiantes l.p.": ["estudiantes lp", "estudiantes de la plata", "estudiantes"],
    "estudiantes de la plata": ["estudiantes de la plata", "estudiantes lp", "estudiantes"],
    "gimnasia l.p.": ["gimnasia lp", "gimnasia la plata", "gimnasia y esgrima"],
    "gimnasia la plata": ["gimnasia la plata", "gimnasia lp", "gimnasia y esgrima"],
    "argentinos jrs": ["argentinos jrs", "argentinos juniors"],
    "newells old boys": ["newells old boys", "newell s old boys", "newell's old boys"],
    "lanus": ["lanus", "lanús"],
    "huracan": ["huracan", "huracán"],
    "velez sarsfield": ["velez sarsfield", "vélez sarsfield", "velez"],
    "talleres cordoba": ["talleres cordoba", "talleres córdoba", "talleres"],
    "rosario central": ["rosario central"],
    "union santa fe": ["union santa fe", "unión santa fe", "union", "unión"],
    "defensa y justicia": ["defensa y justicia"],
    "banfield": ["banfield"],
    "belgrano cordoba": ["belgrano cordoba", "belgrano córdoba", "belgrano"],
    "instituto cordoba": ["instituto cordoba", "instituto córdoba", "instituto"],
    "platense": ["platense"],
    "sarmiento junin": ["sarmiento junin", "sarmiento junín", "sarmiento"],
    "tigre": ["tigre"],
    "godoy cruz": ["godoy cruz"],
    "deportivo riestra": ["deportivo riestra", "riestra"],
    "central cordoba de santiago": ["central cordoba", "central córdoba", "central cordoba de santiago"],
    "aldosivi": ["aldosivi"],
    "barracas central": ["barracas central", "barracas"],
}

MARKET_ORDER = [
    "Resultado del partido",
    "Goles totales Más/Menos",
    "Total de goles Más/Menos",
    "Total de Goles Más/Menos",
    "Total de goles",
    "Doble oportunidad",
    "Ambos equipos anotan",
    "Ambos equipos marcan",
    "Más/Menos Córners",
    "Total de Córners Más/Menos",
    "Total de córners Más/Menos",
    "Tarjetas Totales Más/Menos",
    "Total de Tarjetas Más/Menos",
    "Total de tarjetas Más/Menos",
    "Resultado Primer Tiempo",
    "Más/Menos Goles en Primer Tiempo",
    "Goles totales Más/Menos Primer Tiempo",
    "Total de goles Más/Menos Primer Tiempo",
    "Córners en Primer Tiempo Más/Menos",
    "Total de Tarjetas (Más/Menos) Primer Tiempo",
    "{home} - Goles totales Más/Menos",
    "{away} - Goles totales Más/Menos",
    "{home} Goles totales Más/Menos",
    "{away} Goles totales Más/Menos",
    "{home} Total de goles Más/Menos",
    "{away} Total de goles Más/Menos",
    "Total de goles de {home} Más/Menos",
    "Total de goles de {away} Más/Menos",
    "{home} Más/Menos Córners",
    "{away} Más/Menos Córners",
    "{home} - Más/Menos Córners",
    "{away} - Más/Menos Córners",
    "Total de córners de {home} Más/Menos",
    "Total de córners de {away} Más/Menos",
    "Apuesta sin Empate",
]


def norm(value: str | None) -> str:
    text = unicodedata.normalize("NFD", value or "")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def as_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip().replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return None
    if 1.01 <= number <= 100:
        return number
    return None


def split_match_name(match: str) -> tuple[str, str]:
    if " vs " not in match:
        raise ValueError(f"No puedo separar el partido: {match}")
    home, away = match.split(" vs ", 1)
    return home.strip(), away.strip()


def aliases(team: str) -> list[str]:
    key = norm(team)
    values = [norm(item) for item in TEAM_ALIASES.get(key, [team])]
    if key not in values:
        values.insert(0, key)
    return [item for item in values if item]


def unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        item = item.strip()
        if not item:
            continue
        key = norm(item)
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def market_labels(home: str, away: str) -> list[str]:
    return unique([item.format(home=home, away=away) for item in MARKET_ORDER])


def find_line(lines: list[str], label: str, start: int = 0) -> int | None:
    wanted = norm(label)
    for idx in range(start, len(lines)):
        if norm(lines[idx]) == wanted:
            return idx
    return None


def chunk_after(lines: list[str], label: str, home: str, away: str) -> list[str]:
    start = find_line(lines, label)
    if start is None:
        return []
    labels = market_labels(home, away)
    next_indexes = [
        idx
        for other in labels
        if norm(other) != norm(label)
        for idx in [find_line(lines, other, start + 1)]
        if idx is not None
    ]
    end = min(next_indexes) if next_indexes else min(len(lines), start + 80)
    return [line.strip() for line in lines[start:end] if line.strip()]


def parse_three_way(chunk: list[str], key_prefix: str, home_key: str = "HOME", draw_key: str = "DRAW", away_key: str = "AWAY") -> dict[str, float]:
    odds: dict[str, float] = {}
    labels = {"1": f"{key_prefix}:{home_key}", "x": f"{key_prefix}:{draw_key}", "2": f"{key_prefix}:{away_key}"}
    for idx, line in enumerate(chunk[:-1]):
        target = labels.get(norm(line))
        if not target:
            continue
        value = as_float(chunk[idx + 1])
        if value is not None:
            odds[target] = value
    return odds


def parse_named_pair(chunk: list[str], key_prefix: str, home: str, away: str) -> dict[str, float]:
    odds: dict[str, float] = {}
    for idx, line in enumerate(chunk[:-1]):
        value = as_float(chunk[idx + 1])
        if value is None:
            continue
        line_n = norm(line)
        if line_n in {norm(home), "1", norm(f"{home} en tiempo normal")}:
            odds[f"{key_prefix}:HOME"] = value
        elif line_n in {norm(away), "2", norm(f"{away} en tiempo normal")}:
            odds[f"{key_prefix}:AWAY"] = value
    return odds


def parse_btts(chunk: list[str]) -> dict[str, float]:
    odds: dict[str, float] = {}
    for idx, line in enumerate(chunk[:-1]):
        value = as_float(chunk[idx + 1])
        if value is None:
            continue
        line_n = norm(line)
        if line_n in {"si", "sí"}:
            odds["BTTS:YES"] = value
        elif line_n == "no":
            odds["BTTS:NO"] = value
    return odds


def parse_double_chance(chunk: list[str]) -> dict[str, float]:
    odds: dict[str, float] = {}
    labels = {
        "1x": "DOUBLE_CHANCE:1X",
        "12": "DOUBLE_CHANCE:12",
        "x2": "DOUBLE_CHANCE:X2",
    }
    for idx, line in enumerate(chunk[:-1]):
        value = as_float(chunk[idx + 1])
        if value is None:
            continue
        target = labels.get(norm(line).replace(" ", ""))
        if target:
            odds[target] = value
    return odds


def parse_over_under(chunk: list[str], key_prefix: str) -> dict[str, float]:
    odds: dict[str, float] = {}
    for idx, line in enumerate(chunk[:-1]):
        side = norm(line)
        number: float | None = None
        price: float | None = None
        if side in {"mas de", "mas", "menos", "menos de"} and idx + 2 < len(chunk):
            line_value = chunk[idx + 1].replace(",", ".")
            price = as_float(chunk[idx + 2])
            try:
                number = float(line_value)
            except ValueError:
                number = None
        else:
            match = re.search(r"\b(M[aá]s de|Menos de|Menos)\s+(\d+(?:[,.]\d+)?)\b", line, flags=re.I)
            if match:
                side = norm(match.group(1))
                try:
                    number = float(match.group(2).replace(",", "."))
                except ValueError:
                    number = None
                price = as_float(chunk[idx + 1])
        if number is None or price is None:
            continue
        side_key = "OVER" if side in {"mas", "mas de"} else "UNDER"
        line_key = str(number).replace(".", "_")
        odds[f"{key_prefix}:{side_key}_{line_key}"] = price
    return odds


def parse_text_markets(text: str, home: str, away: str) -> dict[str, float]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    odds: dict[str, float] = {}

    odds.update(parse_three_way(chunk_after(lines, "Resultado del partido", home, away), "1X2"))
    odds.update(parse_named_pair(chunk_after(lines, "Apuesta sin Empate", home, away), "DRAW_NO_BET", home, away))
    odds.update(parse_btts(chunk_after(lines, "Ambos equipos anotan", home, away)))
    odds.update(parse_btts(chunk_after(lines, "Ambos equipos marcan", home, away)))
    odds.update(parse_double_chance(chunk_after(lines, "Doble oportunidad", home, away)))
    odds.update(parse_over_under(chunk_after(lines, "Goles totales Más/Menos", home, away), "TOTALS"))
    odds.update(parse_over_under(chunk_after(lines, "Total de goles Más/Menos", home, away), "TOTALS"))
    odds.update(parse_over_under(chunk_after(lines, "Total de Goles Más/Menos", home, away), "TOTALS"))
    odds.update(parse_over_under(chunk_after(lines, "Más/Menos Goles en Primer Tiempo", home, away), "FIRST_HALF_TOTALS"))
    odds.update(parse_over_under(chunk_after(lines, "Goles totales Más/Menos Primer Tiempo", home, away), "FIRST_HALF_TOTALS"))
    odds.update(parse_over_under(chunk_after(lines, "Total de goles Más/Menos Primer Tiempo", home, away), "FIRST_HALF_TOTALS"))
    odds.update(parse_over_under(chunk_after(lines, "Más/Menos Córners", home, away), "CORNERS_TOTALS"))
    odds.update(parse_over_under(chunk_after(lines, "Total de Córners Más/Menos", home, away), "CORNERS_TOTALS"))
    odds.update(parse_over_under(chunk_after(lines, "Total de córners Más/Menos", home, away), "CORNERS_TOTALS"))
    odds.update(parse_over_under(chunk_after(lines, "Tarjetas Totales Más/Menos", home, away), "CARDS_TOTALS"))
    odds.update(parse_over_under(chunk_after(lines, "Total de Tarjetas Más/Menos", home, away), "CARDS_TOTALS"))
    odds.update(parse_over_under(chunk_after(lines, "Total de tarjetas Más/Menos", home, away), "CARDS_TOTALS"))
    odds.update(parse_over_under(chunk_after(lines, f"{home} Más/Menos Córners", home, away), "CORNERS_HOME"))
    odds.update(parse_over_under(chunk_after(lines, f"{away} Más/Menos Córners", home, away), "CORNERS_AWAY"))
    odds.update(parse_over_under(chunk_after(lines, f"{home} - Más/Menos Córners", home, away), "CORNERS_HOME"))
    odds.update(parse_over_under(chunk_after(lines, f"{away} - Más/Menos Córners", home, away), "CORNERS_AWAY"))
    odds.update(parse_over_under(chunk_after(lines, f"Total de córners de {home} Más/Menos", home, away), "CORNERS_HOME"))
    odds.update(parse_over_under(chunk_after(lines, f"Total de córners de {away} Más/Menos", home, away), "CORNERS_AWAY"))
    odds.update(parse_over_under(chunk_after(lines, f"{home} - Goles totales Más/Menos", home, away), "TEAM_TOTAL_HOME"))
    odds.update(parse_over_under(chunk_after(lines, f"{away} - Goles totales Más/Menos", home, away), "TEAM_TOTAL_AWAY"))
    odds.update(parse_over_under(chunk_after(lines, f"{home} Goles totales Más/Menos", home, away), "TEAM_TOTAL_HOME"))
    odds.update(parse_over_under(chunk_after(lines, f"{away} Goles totales Más/Menos", home, away), "TEAM_TOTAL_AWAY"))
    odds.update(parse_over_under(chunk_after(lines, f"{home} Total de goles Más/Menos", home, away), "TEAM_TOTAL_HOME"))
    odds.update(parse_over_under(chunk_after(lines, f"{away} Total de goles Más/Menos", home, away), "TEAM_TOTAL_AWAY"))
    odds.update(parse_over_under(chunk_after(lines, f"Total de goles de {home} Más/Menos", home, away), "TEAM_TOTAL_HOME"))
    odds.update(parse_over_under(chunk_after(lines, f"Total de goles de {away} Más/Menos", home, away), "TEAM_TOTAL_AWAY"))
    return odds


async def close_overlays(page) -> None:
    await page.evaluate(
        """() => {
          for (const sel of ['[data-testid="landing-modal-close-button"]', '.ot-close-icon', 'button[aria-label="Cerrar"]']) {
            const el = document.querySelector(sel);
            if (el) el.click();
          }
          for (const button of [...document.querySelectorAll('button')]) {
            const text = (button.innerText || '').trim();
            if (['SÍ, ACEPTO', 'SI, ACEPTO', 'NO, GRACIAS'].includes(text)) button.click();
          }
        }"""
    )
    await page.wait_for_timeout(700)


async def click_normalized(page, target: str, prefer_market: bool = False) -> bool:
    result = await page.evaluate(
        """({target, preferMarket}) => {
          const norm = s => (s || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
          const wanted = norm(target);
          const elements = [...document.querySelectorAll('div,span,button,a')].filter(el => norm(el.innerText || el.textContent) === wanted);
          let selected = null;
          if (preferMarket) {
            selected = elements.find(el => {
              const clickable = el.closest('[data-qa^="market-type-id-"]');
              return Boolean(clickable);
            });
          }
          selected = selected || elements.find(el => el.closest('button,a,[role="button"],[role="tab"],[data-qa^="market-type-id-"]')) || elements[0];
          if (!selected) return false;
          const clickable = selected.closest('[data-qa^="market-type-id-"],button,a,[role="button"],[role="tab"]') || selected;
          clickable.scrollIntoView({block: 'center'});
          clickable.click();
          return true;
        }""",
        {"target": target, "preferMarket": prefer_market},
    )
    return bool(result)


async def collect_event_links_from_page(page, *, max_scrolls: int = 9) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for _ in range(max_scrolls):
        await close_overlays(page)
        page_links = await page.locator("a[href*='/cuotas-de-partido/']").evaluate_all(
            """els => els.map(a => ({text: a.innerText || '', href: a.href || ''}))"""
        )
        for item in page_links:
            href = item.get("href") or ""
            if href and href not in seen:
                seen.add(href)
                links.append(item)
        await page.mouse.wheel(0, random.randint(700, 1200))
        await page.wait_for_timeout(random.randint(800, 1400))
    return links


async def discover_event_links(page, matches: list[dict[str, str]]) -> dict[str, str]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for url in BETANO_DISCOVERY_URLS:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=18000)
            await page.wait_for_timeout(random.randint(4500, 6500))
            for item in await collect_event_links_from_page(page, max_scrolls=8):
                href = item.get("href") or ""
                if href and href not in seen:
                    seen.add(href)
                    links.append(item)
        except Exception:
            continue
    found: dict[str, str] = {}
    for match in matches:
        home_aliases = aliases(match["home"])
        away_aliases = aliases(match["away"])
        for item in links:
            haystack = norm(f"{item.get('text', '')} {item.get('href', '')}")
            if any(alias in haystack for alias in home_aliases) and any(alias in haystack for alias in away_aliases):
                found[match["match"]] = item["href"]
                break
    return found


async def expand_visible_market_blocks(page, *, rounds: int = 4) -> None:
    expanders = [
        "Mostrar más",
        "Ver más",
        "Más mercados",
    ]
    for _ in range(rounds):
        clicked = False
        for label in expanders:
            try:
                if await click_normalized(page, label):
                    clicked = True
                    await page.wait_for_timeout(random.randint(900, 1700))
            except Exception:
                pass
        if not clicked:
            break


async def collect_body_snapshots(page, *, scrolls: int = 8) -> list[str]:
    snapshots: list[str] = []
    try:
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(random.randint(700, 1200))
    except Exception:
        pass
    for _ in range(scrolls):
        try:
            await expand_visible_market_blocks(page, rounds=2)
            snapshots.append(await page.locator("body").inner_text(timeout=15000))
            await page.mouse.wheel(0, random.randint(650, 1100))
            await page.wait_for_timeout(random.randint(900, 1700))
        except Exception:
            pass
    return snapshots


async def scrape_event(page, url: str, home: str, away: str) -> dict[str, Any]:
    await page.goto(url, wait_until="load", timeout=60000)
    await page.wait_for_timeout(random.randint(6000, 9000))
    await close_overlays(page)

    betano_home = aliases(home)[-1].title()
    betano_away = aliases(away)[-1].title()
    text_snapshots = await collect_body_snapshots(page, scrolls=3)

    # Try tabs first; some market families only hydrate inside their category.
    for tab in [
        "Todo",
        "Populares",
        "Principales",
        "Goles",
        "Más/Menos",
        "Córners",
        "Tarjetas",
        "Primer Tiempo",
        "1ª Mitad",
        "Especiales",
        "Bet Builder",
    ]:
        try:
            if await click_normalized(page, tab):
                await page.wait_for_timeout(random.randint(1800, 3400))
                text_snapshots.extend(await collect_body_snapshots(page, scrolls=3))
        except Exception:
            pass

    # Then expand the relevant accordions. Not every event exposes every family.
    labels = [
        "Resultado del partido",
        "Goles totales Más/Menos",
        "Doble oportunidad",
        "Ambos equipos anotan",
        "Ambos equipos marcan",
        "Más/Menos Córners",
        "Total de Córners Más/Menos",
        "Total de córners Más/Menos",
        "Tarjetas Totales Más/Menos",
        "Total de Tarjetas Más/Menos",
        "Total de tarjetas Más/Menos",
        "Resultado Primer Tiempo",
        "Más/Menos Goles en Primer Tiempo",
        "Goles totales Más/Menos Primer Tiempo",
        "Total de goles Más/Menos Primer Tiempo",
        "Córners en Primer Tiempo Más/Menos",
        "Total de Tarjetas (Más/Menos) Primer Tiempo",
        f"{betano_home} Más/Menos Córners",
        f"{betano_away} Más/Menos Córners",
        f"{betano_home} - Más/Menos Córners",
        f"{betano_away} - Más/Menos Córners",
        f"Total de córners de {betano_home} Más/Menos",
        f"Total de córners de {betano_away} Más/Menos",
        f"{betano_home} - Goles totales Más/Menos",
        f"{betano_away} - Goles totales Más/Menos",
        f"{betano_home} Goles totales Más/Menos",
        f"{betano_away} Goles totales Más/Menos",
        f"{betano_home} Total de goles Más/Menos",
        f"{betano_away} Total de goles Más/Menos",
        f"Total de goles de {betano_home} Más/Menos",
        f"Total de goles de {betano_away} Más/Menos",
        "Apuesta sin Empate",
    ]
    for label in labels:
        try:
            if await click_normalized(page, label, prefer_market=True):
                await page.wait_for_timeout(random.randint(1200, 2400))
                text_snapshots.extend(await collect_body_snapshots(page, scrolls=1))
        except Exception:
            pass

    odds: dict[str, float] = {}
    for text in text_snapshots:
        odds.update(parse_text_markets(text, betano_home, betano_away))
        odds.update(parse_text_markets(text, home, away))

    return {
        "url": page.url,
        "odds": odds,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "market_count": len(odds),
    }


def enrich_data(data: dict[str, Any], betano: dict[str, dict[str, Any]]) -> dict[str, Any]:
    enriched = deepcopy(data)
    enriched["betano_enrichment"] = {
        "bookmaker": "Betano",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "matches_found": len([v for v in betano.values() if v.get("odds")]),
    }
    for result in enriched.get("results", []):
        scraped = betano.get(result.get("match", ""), {})
        odds_map = scraped.get("odds", {}) or {}
        api_bookmaker = result.get("bookmaker") or None
        if api_bookmaker == "Sin cuota":
            api_bookmaker = None
        result["bookmakers"] = {
            "api_primary": api_bookmaker,
            "betano": "Betano" if odds_map else None,
        }
        result["betano_source_url"] = scraped.get("url")
        result["betano_market_count"] = scraped.get("market_count", 0)
        for market in result.get("all_markets", []):
            market["odds_api"] = market.get("odds")
            market["ev_api"] = market.get("ev")
            market["bookmaker_api"] = (market.get("bookmaker") or api_bookmaker or "API-Football") if market["odds_api"] is not None else None
            market["bookmaker_betano"] = "Betano" if odds_map else None
            betano_odds = odds_map.get(market.get("key"))
            market["odds_betano"] = betano_odds
            market["betano_source_url"] = scraped.get("url")
            market["ev_betano"] = round((market.get("probability") or 0) * betano_odds - 1, 4) if betano_odds else None
            if betano_odds is None:
                market["status_betano"] = "No encontrado en Betano"
            elif market["ev_betano"] > 0:
                market["status_betano"] = "EV positivo Betano"
            else:
                market["status_betano"] = "EV negativo Betano"
        rec = result.get("recommended_pick") or {}
        if rec:
            rec["odds_api"] = rec.get("odds")
            rec["ev_api"] = rec.get("ev")
            rec["bookmaker_api"] = (rec.get("bookmaker") or api_bookmaker or "API-Football") if rec["odds_api"] is not None else None
            rec["bookmaker_betano"] = "Betano" if odds_map else None
            betano_odds = odds_map.get(rec.get("key"))
            rec["odds_betano"] = betano_odds
            rec["ev_betano"] = round((rec.get("probability") or 0) * betano_odds - 1, 4) if betano_odds else None
            rec["status_betano"] = (
                "No encontrado en Betano"
                if betano_odds is None
                else ("EV positivo Betano" if rec["ev_betano"] > 0 else "EV negativo Betano")
            )
            rec["betano_source_url"] = scraped.get("url")
    return enriched


async def run(source: Path, output: Path) -> Path:
    data = json.loads(source.read_text(encoding="utf-8"))
    matches: list[dict[str, str]] = []
    for result in data.get("results", []):
        home, away = split_match_name(result["match"])
        matches.append({"match": result["match"], "home": home, "away": away})

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise SystemExit("Playwright no está instalado. Ejecuta: python -m pip install playwright && python -m playwright install chromium") from exc

    scraped: dict[str, dict[str, Any]] = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        page = await browser.new_page(
            locale="es-PE",
            timezone_id="America/Lima",
            viewport={"width": 1365, "height": 1400},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page.set_default_timeout(20000)
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        links = await discover_event_links(page, matches)
        await page.close()
        for match in matches:
            url = links.get(match["match"])
            if not url:
                scraped[match["match"]] = {"url": None, "odds": {}, "market_count": 0, "error": "No se encontró enlace en Betano"}
                print(f"Betano: sin enlace para {match['match']}", flush=True)
                continue
            print(f"Betano: scrapeando {match['match']} -> {url}", flush=True)
            event_page = await browser.new_page(
                locale="es-PE",
                timezone_id="America/Lima",
                viewport={"width": 1365, "height": 1400},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            event_page.set_default_timeout(20000)
            await event_page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            try:
                scraped[match["match"]] = await scrape_event(event_page, url, match["home"], match["away"])
            except Exception as exc:
                scraped[match["match"]] = {"url": url, "odds": {}, "market_count": 0, "error": str(exc)}
            finally:
                await event_page.close()
            print(
                f"Betano: {match['match']} mercados={scraped[match['match']].get('market_count', 0)}",
                flush=True,
            )
            await asyncio.sleep(random.uniform(1.2, 2.5))
        await browser.close()

    enriched = enrich_data(data, scraped)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output.resolve())
    for match, item in scraped.items():
        print(match, item.get("market_count", 0), item.get("url"), item.get("error", ""))
        for key, value in sorted((item.get("odds") or {}).items()):
            print(" ", key, value)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Enriquece un protocolo existente con cuotas scrapeadas de Betano Perú.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    asyncio.run(run(Path(args.source), Path(args.output)))


if __name__ == "__main__":
    main()
