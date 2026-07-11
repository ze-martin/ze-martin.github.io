from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analysis.evaluator import expected_value
from analysis.model import PoissonModel, TeamStats
from apis.football_api import FootballAPI
from config import load_environment


LIMA_TZ = ZoneInfo("America/Lima")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate protocol results including probability-only markets.")
    parser.add_argument("--from", dest="from_date", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--leagues", required=True, help="Comma-separated API-Football league ids")
    parser.add_argument("--date-lima", dest="date_lima", help="Filter matches by Lima date YYYY-MM-DD after kickoff conversion")
    parser.add_argument("--selected-numbers", help="Comma-separated original selection numbers to keep after sorting/filtering")
    parser.add_argument("--output-dir", default="protocol/runs", help="Directory for JSON/Markdown outputs")
    parser.add_argument("--name", default="protocol_with_probabilities", help="Output filename prefix")
    return parser.parse_args()


def team_stats(team: str, stats: dict) -> TeamStats:
    return TeamStats(
        team=team,
        matches=int(stats["matches"]),
        goals_for=float(stats["goals_for"]),
        goals_against=float(stats["goals_against"]),
    )


def confidence(probability: float) -> str:
    if probability >= 0.7:
        return "Alta"
    if probability >= 0.55:
        return "Media"
    return "Baja"


def market_name(key: str) -> str:
    market, selection = key.split(":", 1)
    return f"{market} {selection.replace('_', '.')}"


def source_label(source: str | None) -> str:
    labels = {
        "current_tournament": "torneo actual",
        "recent_all_competitions": "fallback ultimos partidos",
        "premium_current_tournament": "contexto premium torneo actual",
        "premium_recent_all_competitions": "contexto premium fallback reciente",
        "premium_mixed": "contexto premium mixto",
    }
    return labels.get(source or "", source or "modelo")


def market_reason(key: str, source: str | None = None) -> str:
    if source == "recent_all_competitions":
        return "usa Poisson fallback con ultimos partidos multi-competicion"
    if key.startswith(("CORNERS_", "CARDS_", "SHOTS_", "FIRST_HALF_")):
        if source == "premium_recent_all_competitions":
            return "usa promedios recientes multi-competicion/API-Football"
        if source == "premium_mixed":
            return "usa mezcla de promedios del torneo y recientes/API-Football"
        return "usa promedios del contexto premium/API-Football"
    if key.startswith(("TOTALS", "TEAM_TOTAL", "BTTS", "1X2", "DOUBLE_CHANCE", "DRAW_NO_BET")):
        return "usa Poisson base con estadisticas de goles del torneo"
    return "usa probabilidad calculada por el modelo"


def market_risk(key: str) -> str:
    if key.startswith("FIRST_HALF_"):
        return "el primer tiempo puede tener ritmo bajo o rotaciones"
    if key.startswith(("CORNERS_", "SHOTS_")):
        return "el volumen ofensivo puede variar por planteamiento y marcador temprano"
    if key.startswith("CARDS_"):
        return "depende mucho del arbitro y del contexto competitivo"
    if key.startswith(("TOTALS", "BTTS", "TEAM_TOTAL")):
        return "un gol temprano o baja eficacia puede cambiar la lectura del mercado"
    return "riesgo propio del resultado final y variacion del modelo"


def to_lima(iso_value: str) -> tuple[str, str, str]:
    kickoff = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=timezone.utc)
    lima = kickoff.astimezone(LIMA_TZ)
    return lima.date().isoformat(), lima.strftime("%H:%M"), lima.isoformat()


def build_market_rows(probabilities: dict[str, float], odds: dict, sources: dict[str, str] | None = None) -> list[dict]:
    rows: list[dict] = []
    odds_markets = odds.get("markets", {}) if isinstance(odds, dict) else {}
    bookmaker = odds.get("bookmaker", "Sin cuota") if isinstance(odds, dict) else "Sin cuota"
    sources = sources or {}
    for key, probability in sorted(probabilities.items(), key=lambda item: item[1], reverse=True):
        offered_odds = odds_markets.get(key)
        try:
            offered_odds = float(offered_odds) if offered_odds is not None else None
        except (TypeError, ValueError):
            offered_odds = None
        if offered_odds is not None and (not math.isfinite(offered_odds) or offered_odds <= 1):
            offered_odds = None
        ev = None
        status = "Sin cuota/EV"
        if offered_odds is not None:
            ev = expected_value(probability, offered_odds)
            status = "EV positivo" if ev >= 0.02 else "EV negativo"
        source = sources.get(key)
        rows.append(
            {
                "key": key,
                "market": market_name(key),
                "probability": round(probability, 4),
                "odds": round(offered_odds, 3) if offered_odds is not None else None,
                "ev": round(ev, 4) if ev is not None else None,
                "status": status,
                "confidence": confidence(probability),
                "bookmaker": bookmaker,
                "source": source_label(source),
                "source_key": source,
                "reason": market_reason(key, source),
                "risk": market_risk(key),
            }
        )
    return rows


def premium_source(match: dict) -> str:
    data_sources = match.get("raw", {}).get("analysis_context", {}).get("data_sources", {})
    values = {data_sources.get("home_recent"), data_sources.get("away_recent")}
    if values == {"current_tournament"}:
        return "premium_current_tournament"
    if values == {"recent_all_competitions"}:
        return "premium_recent_all_competitions"
    if "recent_all_competitions" in values:
        return "premium_mixed"
    return "premium_current_tournament"


def generate(from_date: date, to_date: date, leagues: list[str], date_lima_filter: str | None = None, selected_numbers: set[int] | None = None) -> dict:
    api = FootballAPI()
    model = PoissonModel()
    raw_matches = sorted(
        api.get_matches(from_date, to_date, leagues),
        key=lambda item: (item["kickoff"], item["league"], item["home_team"], item["away_team"]),
    )
    filtered_matches: list[dict] = []
    for match in raw_matches:
        date_lima, _, _ = to_lima(match["kickoff"])
        if date_lima_filter and date_lima != date_lima_filter:
            continue
        filtered_matches.append(match)

    enumerated_matches: list[tuple[int, dict]] = []
    for index, match in enumerate(filtered_matches, start=1):
        if selected_numbers and index not in selected_numbers:
            continue
        enumerated_matches.append((index, match))

    matches = [match for _, match in enumerated_matches]
    odds_by_match = api.get_embedded_odds(matches)

    results = []
    for index, match in enumerated_matches:
        date_lima, time_lima, kickoff_lima = to_lima(match["kickoff"])
        result = {
            "selection_number": index,
            "match_id": match["id"],
            "league": match["league"],
            "match": f"{match['home_team']} vs {match['away_team']}",
            "date_lima": date_lima,
            "time_lima": time_lima,
            "kickoff_lima": kickoff_lima,
            "bookmaker": odds_by_match.get(match["id"], {}).get("bookmaker", "Sin cuota"),
            "recommended_pick": None,
            "all_markets": [],
            "probability_markets": [],
            "note": None,
        }
        probabilities: dict[str, float] = {}
        probability_sources: dict[str, str] = {}
        note_parts: list[str] = []
        stats = api.get_team_stats(match)
        try:
            base_probabilities = model.match_probabilities(
                team_stats(match["home_team"], stats.get("home", {})),
                team_stats(match["away_team"], stats.get("away", {})),
            )
            probabilities.update(base_probabilities)
            probability_sources.update({key: "current_tournament" for key in base_probabilities})
        except Exception as exc:
            note_parts.append(f"Poisson torneo actual no disponible: {exc}")
            fallback_stats = api.get_fallback_team_stats(match)
            try:
                fallback_probabilities = model.match_probabilities(
                    team_stats(match["home_team"], fallback_stats.get("home", {})),
                    team_stats(match["away_team"], fallback_stats.get("away", {})),
                )
                probabilities.update(fallback_probabilities)
                probability_sources.update({key: "recent_all_competitions" for key in fallback_probabilities})
                home_matches = int(fallback_stats.get("home", {}).get("matches") or 0)
                away_matches = int(fallback_stats.get("away", {}).get("matches") or 0)
                note_parts.append(
                    f"Poisson fallback aplicado con ultimos partidos: home={home_matches}, away={away_matches}"
                )
            except Exception as fallback_exc:
                note_parts.append(f"Poisson fallback no disponible: {fallback_exc}")

        try:
            advanced_probabilities = model.advanced_market_probabilities(match)
            probabilities.update(advanced_probabilities)
            probability_sources.update({key: premium_source(match) for key in advanced_probabilities})
        except Exception as exc:
            note_parts.append(f"mercados premium no disponibles: {exc}")

        if probabilities:
            result["probability_markets"] = build_market_rows(
                probabilities,
                odds_by_match.get(match["id"], {}),
                probability_sources,
            )
            result["all_markets"] = result["probability_markets"]
            positive = [row for row in result["probability_markets"] if row["ev"] is not None and row["ev"] >= 0.02]
            if positive:
                positive.sort(key=lambda row: (row["probability"], row["ev"]), reverse=True)
                result["recommended_pick"] = positive[0]
            if note_parts:
                result["note"] = "; ".join(note_parts)
        else:
            result["note"] = "; ".join(note_parts) if note_parts else "No se pudieron calcular probabilidades"
        results.append(result)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cache_dir": str(api.cache_dir.resolve()),
        "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(),
        "leagues": leagues,
        "date_lima_filter": date_lima_filter,
        "selected_numbers": sorted(selected_numbers) if selected_numbers else [],
        "matches": len(results),
        "results": results,
    }


def write_markdown(payload: dict, path: Path) -> None:
    lines = [
        "# Protocolo completo con probabilidades sin EV",
        "",
        f"- Generado: `{payload['generated_at']}`",
        f"- Rango: `{payload['from_date']}` a `{payload['to_date']}` horario Peru",
        f"- Cache: `{payload['cache_dir']}`",
        f"- Fecha Peru filtrada: `{payload['date_lima_filter'] or 'sin filtro'}`",
        f"- Selecciones: `{', '.join(str(item) for item in payload['selected_numbers']) or 'todas'}`",
        "",
        "## Resumen por partido",
        "",
        "| # | Partido | Liga | Fecha | Hora | Pick recomendado | Prob. | Cuota | EV | Estado |",
        "|---:|---|---|---|---|---|---:|---:|---:|---|",
    ]
    for item in payload["results"]:
        pick = item.get("recommended_pick")
        if pick:
            pick_name = pick["market"]
            prob = f"{pick['probability']:.2%}"
            odds = f"{pick['odds']:.2f}" if pick["odds"] is not None else "N/D"
            ev = f"{pick['ev']:.2%}" if pick["ev"] is not None else "N/D"
            status = pick["status"]
        else:
            best = next(iter(item.get("probability_markets", [])), None)
            pick_name = best["market"] if best else "Sin probabilidad calculada"
            prob = f"{best['probability']:.2%}" if best else "N/D"
            odds = "N/D"
            ev = "N/D"
            status = best["status"] if best else "Sin mercado"
        lines.append(
            f"| {item['selection_number']} | {item['match']} | {item['league']} | {item['date_lima']} | {item['time_lima']} | {pick_name} | {prob} | {odds} | {ev} | {status} |"
        )
    lines.append("")
    lines.append("## Detalle completo por partido")
    lines.append("")
    for item in payload["results"]:
        lines.append(f"### {item['selection_number']}. {item['match']}")
        lines.append("")
        lines.append(f"- Liga: `{item['league']}`")
        lines.append(f"- Fecha: `{item['date_lima']}`")
        lines.append(f"- Hora Peru: `{item['time_lima']}`")
        lines.append(f"- Bookmaker: `{item['bookmaker']}`")
        pick = item.get("recommended_pick")
        if pick:
            lines.append(
                f"- Pick principal: `{pick['market']}` | Prob. `{pick['probability']:.2%}` | Cuota `{pick['odds']:.2f}` | EV `{pick['ev']:.2%}`"
            )
            lines.append(f"- Fuente: {pick.get('source', 'modelo')}")
            lines.append(f"- Razon: {pick['reason']}")
            lines.append(f"- Riesgo: {pick['risk']}")
        elif item.get("note"):
            lines.append(f"- Nota: {item['note']}")
        else:
            lines.append("- Pick principal: `Sin pick con EV positivo`")
        lines.append("")
        markets = item.get("probability_markets") or item.get("all_markets") or []
        if markets:
            lines.append("| Mercado | Prob. | Cuota | EV | Estado | Confianza | Fuente | Razon | Riesgo |")
            lines.append("|---|---:|---:|---:|---|---|---|---|---|")
            for market in markets:
                odds = f"{market['odds']:.2f}" if market["odds"] is not None else "N/D"
                ev = f"{market['ev']:.2%}" if market["ev"] is not None else "N/D"
                lines.append(
                    f"| {market['market']} | {market['probability']:.2%} | {odds} | {ev} | {market['status']} | {market['confidence']} | {market.get('source', 'modelo')} | {market['reason']} | {market['risk']} |"
                )
        else:
            lines.append("No se generaron mercados para este partido.")
        lines.append("")
    lines.append("## Nota")
    lines.append("")
    lines.append("Cuando no existe cuota compatible, la probabilidad se conserva y el EV queda como `N/D`.")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    load_environment()
    from_date = date.fromisoformat(args.from_date)
    to_date = date.fromisoformat(args.to_date)
    leagues = [item.strip() for item in args.leagues.split(",") if item.strip()]
    selected_numbers = {int(item.strip()) for item in args.selected_numbers.split(",") if item.strip()} if args.selected_numbers else None
    payload = generate(from_date, to_date, leagues, args.date_lima, selected_numbers)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"{args.name}_{stamp}.json"
    md_path = output_dir / f"{args.name}_{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, md_path)
    print(json.dumps({"json": str(json_path), "markdown": str(md_path), "matches": payload["matches"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
