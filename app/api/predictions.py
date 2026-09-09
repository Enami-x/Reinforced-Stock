"""
Prediction endpoints — trigger analysis and query past predictions.

POST /analyze/{ticker}            Trigger a full analysis run
GET  /predictions/{ticker}        List past predictions for a ticker
GET  /predictions/id/{id}         Get a single prediction by UUID
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.analyze import AnalysisResult, StockAnalyzer
from app.db.engine import get_db
from app.db.models import PredictionRecord

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Predictions"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class AnalyzeResponse(BaseModel):
    prediction_id: str
    ticker: str
    signal: str
    confidence: float
    reasoning: str
    key_factors: list[str]
    resolve_after: str
    price_at_analysis: float
    news_count: int
    memory_count: int


class PredictionSummary(BaseModel):
    prediction_id: str
    ticker: str
    signal: str
    confidence: float
    reasoning: str
    key_factors: list[str]
    correct: bool | None
    outcome_pct: float | None
    created_at: str
    resolved_at: str | None
    resolve_after: str | None


class PredictionDetail(PredictionSummary):
    data_snapshot: dict[str, Any]
    memory_ids_used: list[str]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/analyze/{ticker}",
    response_model=AnalyzeResponse,
    summary="Trigger a full analysis for a ticker",
    response_description="The generated buy/hold/sell prediction",
)
def analyze_ticker(
    ticker: str,
    db: Session = Depends(get_db),
) -> AnalyzeResponse:
    """
    Run the full analysis pipeline for a ticker:
    1. Fetch price + technicals (yfinance)
    2. Fetch recent news (Finnhub)
    3. Retrieve similar past predictions (pgvector)
    4. Generate signal via Nemotron LLM
    5. Store prediction in Postgres

    Returns the prediction immediately. Resolution happens later via the
    daily background job (Stage 5).

    **Note:** Requires NIM_API_KEY and FINNHUB_API_KEY to be configured.
    """
    ticker = ticker.upper().strip()
    logger.info("Manual analysis triggered for %s", ticker)

    analyzer = StockAnalyzer()
    try:
        result: AnalysisResult = analyzer.analyze(ticker=ticker, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Analysis failed for {ticker}: {exc}",
        ) from exc
    except Exception as exc:
        logger.error("Unexpected error during analysis of %s: %s", ticker, exc)
        raise HTTPException(
            status_code=500,
            detail=f"Internal error during analysis of {ticker}.",
        ) from exc

    return AnalyzeResponse(**result.to_dict())


@router.get(
    "/predictions/{ticker}",
    response_model=list[PredictionSummary],
    summary="List past predictions for a ticker",
)
def list_predictions(
    ticker: str,
    limit: int = Query(default=20, ge=1, le=100),
    resolved_only: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[PredictionSummary]:
    """
    Return past predictions for a ticker, newest first.

    Query params:
    - **limit**: max records to return (1–100, default 20)
    - **resolved_only**: if true, only return predictions that have been graded
    """
    ticker = ticker.upper().strip()
    query = (
        db.query(PredictionRecord)
        .filter(PredictionRecord.ticker == ticker)
        .order_by(PredictionRecord.created_at.desc())
    )
    if resolved_only:
        query = query.filter(PredictionRecord.resolved_at.isnot(None))

    records = query.limit(limit).all()

    return [_to_summary(r) for r in records]


@router.get(
    "/predictions/id/{prediction_id}",
    response_model=PredictionDetail,
    summary="Get a single prediction by ID",
)
def get_prediction(
    prediction_id: str,
    db: Session = Depends(get_db),
) -> PredictionDetail:
    """
    Return full detail for a single prediction including the data snapshot
    it saw and the memory IDs that were used as context.
    """
    try:
        pred_uuid = uuid.UUID(prediction_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format.")

    record = db.query(PredictionRecord).filter(PredictionRecord.id == pred_uuid).first()
    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"Prediction {prediction_id} not found.",
        )

    summary = _to_summary(record)
    return PredictionDetail(
        **summary.model_dump(),
        data_snapshot=record.data_snapshot or {},
        memory_ids_used=record.memory_ids_used or [],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_summary(r: PredictionRecord) -> PredictionSummary:
    return PredictionSummary(
        prediction_id=str(r.id),
        ticker=r.ticker,
        signal=r.signal,
        confidence=r.confidence,
        reasoning=r.reasoning,
        key_factors=r.key_factors or [],
        correct=r.correct,
        outcome_pct=r.outcome_pct,
        created_at=r.created_at.isoformat() if r.created_at else "",
        resolved_at=r.resolved_at.isoformat() if r.resolved_at else None,
        resolve_after=r.resolve_after.isoformat() if r.resolve_after else None,
    )
