"""
Prediction resolution — grading past predictions against actual price moves.

Resolution rules
----------------
For a prediction made at price P₀, resolved after N trading days at price P₁:
  pct_move = (P₁ - P₀) / P₀ * 100

  BUY  → correct if pct_move > +threshold  (default: +2%)
  SELL → correct if pct_move < -threshold  (default: -2%)
  HOLD → correct if -threshold ≤ pct_move ≤ +threshold

The resolver runs daily (triggered by the scheduler).  For each pending
prediction whose resolve_after timestamp has passed, it:
  1. Fetches the current close price from yfinance
  2. Computes the % move from the snapshot price stored at prediction time
  3. Applies the signal-specific correctness rule
  4. Updates the DB record with outcome_pct, correct, resolved_at

The updated records are then naturally picked up by pgvector memory retrieval
(incorrect ones get the boost factor applied during future retrievals).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import yfinance as yf
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import PredictionRecord

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


class PredictionResolver:
    """
    Finds all pending predictions due for resolution and grades them.

    Usage:
        resolver = PredictionResolver()
        summary = resolver.resolve_pending(db)

    Or resolve a single prediction by ID:
        result = resolver.resolve_one(prediction_id, db)
    """

    def resolve_pending(self, db: Session) -> dict[str, Any]:
        """
        Find and grade all predictions whose resolve_after has passed and
        that have not yet been resolved.

        Returns a summary dict: {resolved: int, correct: int, incorrect: int, errors: int}
        """
        now = datetime.now(timezone.utc)

        pending = (
            db.query(PredictionRecord)
            .filter(
                PredictionRecord.resolved_at.is_(None),
                PredictionRecord.resolve_after <= now,
            )
            .all()
        )

        if not pending:
            logger.info("Resolution: no pending predictions due.")
            return {"resolved": 0, "correct": 0, "incorrect": 0, "errors": 0}

        logger.info("Resolution: found %d pending predictions to grade", len(pending))
        counts = {"resolved": 0, "correct": 0, "incorrect": 0, "errors": 0}

        for record in pending:
            try:
                outcome = self._grade(record)
                record.outcome_pct = outcome["pct_move"]
                record.correct = outcome["correct"]
                record.resolved_at = now
                db.add(record)

                verdict = "correct" if record.correct else "incorrect"
                counts["resolved"] += 1
                counts[verdict] += 1

                logger.info(
                    "Resolved %s %s → %s%+.1f%% | %s",
                    record.ticker,
                    record.signal,
                    "✓" if record.correct else "✗",
                    record.outcome_pct,
                    record.id,
                )
            except Exception as exc:
                logger.error("Resolution failed for %s: %s", record.id, exc)
                counts["errors"] += 1

        db.commit()
        logger.info("Resolution complete: %s", counts)
        return counts

    def resolve_one(self, prediction_id: str, db: Session) -> dict[str, Any]:
        """
        Force-resolve a single prediction by UUID, even if resolve_after
        hasn't passed yet. Useful for testing or manual overrides.
        """
        import uuid

        pred_uuid = uuid.UUID(prediction_id)
        record = db.query(PredictionRecord).filter(PredictionRecord.id == pred_uuid).first()

        if not record:
            raise ValueError(f"Prediction {prediction_id} not found.")
        if record.resolved_at is not None:
            raise ValueError(f"Prediction {prediction_id} is already resolved.")

        outcome = self._grade(record)
        record.outcome_pct = outcome["pct_move"]
        record.correct = outcome["correct"]
        record.resolved_at = datetime.now(timezone.utc)
        db.add(record)
        db.commit()

        return {
            "prediction_id": prediction_id,
            "signal": record.signal,
            "correct": record.correct,
            "outcome_pct": record.outcome_pct,
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _grade(self, record: PredictionRecord) -> dict[str, Any]:
        """
        Fetch the current price for the ticker and compute correctness.

        Returns:
            {"pct_move": float, "correct": bool, "current_price": float}
        """
        snapshot_price = self._extract_snapshot_price(record)
        current_price = self._fetch_current_price(record.ticker)

        pct_move = (current_price - snapshot_price) / snapshot_price * 100
        threshold = settings.correctness_threshold_pct

        correct = self._apply_rule(record.signal, pct_move, threshold)

        logger.debug(
            "%s %s: snapshot=$%.2f current=$%.2f pct=%+.2f%% threshold=±%.1f%% → %s",
            record.ticker, record.signal,
            snapshot_price, current_price, pct_move, threshold,
            "CORRECT" if correct else "INCORRECT",
        )

        return {
            "pct_move": round(pct_move, 4),
            "correct": correct,
            "current_price": current_price,
        }

    @staticmethod
    def _extract_snapshot_price(record: PredictionRecord) -> float:
        """Extract the price-at-prediction-time from the stored data_snapshot."""
        snapshot = record.data_snapshot or {}
        price = snapshot.get("current_price")
        if price is None:
            raise ValueError(
                f"No current_price in data_snapshot for prediction {record.id}"
            )
        return float(price)

    @staticmethod
    def _fetch_current_price(ticker: str) -> float:
        """Fetch the most recent closing price for a ticker via yfinance."""
        hist = yf.Ticker(ticker).history(period="5d", interval="1d", auto_adjust=True)
        if hist.empty:
            raise RuntimeError(f"Could not fetch price for {ticker} during resolution")
        return float(hist["Close"].iloc[-1])

    @staticmethod
    def _apply_rule(signal: str, pct_move: float, threshold: float) -> bool:
        """
        Apply the correctness rule for each signal type.

        BUY  → correct if pct_move > +threshold
        SELL → correct if pct_move < -threshold
        HOLD → correct if abs(pct_move) <= threshold
        """
        if signal == "BUY":
            return pct_move > threshold
        elif signal == "SELL":
            return pct_move < -threshold
        elif signal == "HOLD":
            return abs(pct_move) <= threshold
        else:
            logger.warning("Unknown signal '%s' — treating as incorrect", signal)
            return False
