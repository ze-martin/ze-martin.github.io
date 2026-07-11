from __future__ import annotations

from datetime import date

from fastapi import FastAPI, HTTPException, Query

from config import load_environment
from services.pipeline import BettingPipeline


load_environment()


app = FastAPI(title="Sistema de Apuestas", version="1.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/run")
def run_pipeline(
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    leagues: str = Query("", description="Comma-separated league names or API ids"),
) -> dict:
    try:
        league_list = [item.strip() for item in leagues.split(",") if item.strip()]
        return BettingPipeline().run(from_date, to_date, league_list)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/matches")
def list_matches(
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    leagues: str = Query("", description="Comma-separated league names or API ids"),
) -> dict:
    try:
        league_list = [item.strip() for item in leagues.split(",") if item.strip()]
        return BettingPipeline().list_matches(from_date, to_date, league_list)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/results")
def results(limit: int = Query(100, ge=1, le=500)) -> dict:
    try:
        return {"results": BettingPipeline().latest_results(limit)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
