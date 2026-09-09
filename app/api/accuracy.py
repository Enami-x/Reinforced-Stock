"""
Accuracy and resolution API endpoints.

GET  /accuracy                  Overall prediction accuracy stats
GET  /accuracy/{ticker}         Per-ticker accuracy history
POST /resolution/resolve-one/{id}  Force-resolve a single prediction
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.engine import get_db
from app.db.models import PredictionRecord
from app.resolution.resolver import PredictionResolver

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Accuracy & Resolution"])


# ---------------------------------------------------------------------------
# Accuracy endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/accuracy",
    summary="Overall prediction accuracy statistics",
    response_description="Accuracy breakdown by signal type and overall",
)
def get_accuracy(db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    Returns accuracy statistics across all resolved predictions:
    - Overall accuracy %
    - Breakdown by signal (BUY / HOLD / SELL)
    - Total counts (resolved, pending, correct, incorrect)
    """
    return _compute_accuracy_stats(db, ticker_filter=None)


@router.get(
    "/accuracy/{ticker}",
    summary="Per-ticker prediction accuracy history",
    response_description="Accuracy stats for a specific ticker",
)
def get_ticker_accuracy(
    ticker: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Returns accuracy statistics for a single ticker, including the most
    recent resolved predictions for review.
    """
    ticker = ticker.upper().strip()
    stats = _compute_accuracy_stats(db, ticker_filter=ticker)
    if stats["total_predictions"] == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No predictions found for ticker '{ticker}'.",
        )
    return stats


@router.post(
    "/resolution/resolve-one/{prediction_id}",
    summary="Force-resolve a single prediction immediately",
    response_description="Resolution outcome for the prediction",
)
def resolve_one(
    prediction_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Immediately resolve a single prediction, fetching the current price
    and applying the correctness rule. Useful for testing or manual overrides.

    Note: This bypasses the resolve_after date check.
    """
    resolver = PredictionResolver()
    try:
        return resolver.resolve_one(prediction_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Force-resolve failed for %s: %s", prediction_id, exc)
        raise HTTPException(status_code=500, detail="Resolution failed.") from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_accuracy_stats(
    db: Session,
    ticker_filter: str | None,
) -> dict[str, Any]:
    """Compute accuracy stats, optionally filtered to a single ticker."""
    base_query = db.query(PredictionRecord)
    if ticker_filter:
        base_query = base_query.filter(PredictionRecord.ticker == ticker_filter)

    total = base_query.count()
    resolved = base_query.filter(PredictionRecord.resolved_at.isnot(None)).count()
    pending = total - resolved
    correct = base_query.filter(PredictionRecord.correct == True).count()  # noqa: E712
    incorrect = base_query.filter(PredictionRecord.correct == False).count()  # noqa: E712

    overall_accuracy = round(correct / resolved * 100, 1) if resolved > 0 else None

    # Per-signal breakdown
    signal_stats: dict[str, Any] = {}
    for signal in ("BUY", "HOLD", "SELL"):
        sig_q = base_query.filter(PredictionRecord.signal == signal)
        sig_resolved = sig_q.filter(PredictionRecord.resolved_at.isnot(None)).count()
        sig_correct = sig_q.filter(PredictionRecord.correct == True).count()  # noqa: E712
        signal_stats[signal] = {
            "total": sig_q.count(),
            "resolved": sig_resolved,
            "correct": sig_correct,
            "accuracy_pct": round(sig_correct / sig_resolved * 100, 1) if sig_resolved > 0 else None,
        }

    result: dict[str, Any] = {
        "total_predictions": total,
        "resolved": resolved,
        "pending": pending,
        "correct": correct,
        "incorrect": incorrect,
        "overall_accuracy_pct": overall_accuracy,
        "by_signal": signal_stats,
    }

    if ticker_filter:
        result["ticker"] = ticker_filter

    return result
