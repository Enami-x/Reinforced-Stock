"""
pgvector memory retrieval for the stock insight agent.

How it works
------------
When the agent is about to analyse a ticker, it:
1. Embeds the current data snapshot (price + news summary) via Nemotron.
2. Runs a cosine-similarity search against all past prediction embeddings.
3. Returns the top-K most similar past predictions, with INCORRECT ones
   boosted in priority so the LLM sees where it previously went wrong.

The retrieved memories are formatted into a compact context block that is
injected into the LLM prompt before the BUY/HOLD/SELL call.

Retrieval strategy
------------------
- Primary sort: cosine similarity (pgvector <=> operator)
- Tie-break boost: if a prediction was marked correct=False, its effective
  score is multiplied by a configurable boost factor (default 1.15) so it
  ranks higher than an equally-similar correct prediction.
  This is implemented in Python post-retrieval (fetch top-K*2, re-rank, take K).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import PredictionRecord

logger = logging.getLogger(__name__)

# How many candidates to over-fetch before re-ranking for incorrect boost
_OVER_FETCH_MULTIPLIER = 2
# Score multiplier applied to incorrect predictions during re-ranking
_INCORRECT_BOOST = 1.15


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


@dataclass
class RetrievedMemory:
    """A single past prediction retrieved from pgvector memory."""

    prediction_id: UUID
    ticker: str
    signal: str          # BUY | HOLD | SELL
    confidence: float
    reasoning: str
    key_factors: list[str]
    correct: bool | None  # None = unresolved
    outcome_pct: float | None
    similarity: float    # cosine similarity to current snapshot, 0–1
    created_at: datetime
    # Was this memory retrieved primarily because it was wrong?
    boosted_for_incorrectness: bool = False

    def to_prompt_str(self) -> str:
        """
        Compact multi-line representation for LLM prompt injection.
        Emphasises incorrect predictions so the LLM learns from mistakes.
        """
        age_days = (datetime.now(timezone.utc) - self.created_at).days
        outcome_str = ""
        if self.correct is not None:
            verdict = "✗ WRONG" if not self.correct else "✓ CORRECT"
            outcome_str = f" | Outcome: {verdict}"
            if self.outcome_pct is not None:
                outcome_str += f" ({self.outcome_pct:+.1f}%)"
        elif self.outcome_pct is None:
            outcome_str = " | Outcome: pending"

        factors = "; ".join(self.key_factors[:3]) if self.key_factors else "—"
        warning = " ⚠ LEARN FROM THIS MISTAKE" if self.boosted_for_incorrectness else ""

        return (
            f"[Past call {age_days}d ago | {self.ticker} | "
            f"Signal: {self.signal} ({self.confidence:.0%} conf){outcome_str}]{warning}\n"
            f"  Reasoning: {self.reasoning[:200]}\n"
            f"  Key factors: {factors}"
        )


# ---------------------------------------------------------------------------
# Retriever
# ---------------------------------------------------------------------------


class MemoryRetriever:
    """
    Retrieves semantically similar past predictions using pgvector.

    Usage:
        memories = MemoryRetriever(embedder).retrieve(snapshot_text, db)
        context_block = MemoryRetriever.format_context(memories)
    """

    def __init__(self, embedder: "EmbeddingClient") -> None:  # noqa: F821
        self._embedder = embedder

    def retrieve(
        self,
        snapshot_text: str,
        db: Session,
        ticker: str | None = None,
        top_k: int | None = None,
    ) -> list[RetrievedMemory]:
        """
        Embed snapshot_text and retrieve the top-K most similar past predictions.

        Args:
            snapshot_text: Text representation of the current data snapshot.
            db: Active SQLAlchemy session.
            ticker: If provided, filters to same-ticker predictions PLUS
                    cross-ticker similar ones (same-ticker gets a mild boost).
            top_k: Number of memories to return (default: settings.memory_top_k).

        Returns:
            List of RetrievedMemory, ordered by effective score descending.
        """
        k = top_k or settings.memory_top_k
        over_fetch = k * _OVER_FETCH_MULTIPLIER

        # ── Embed the snapshot ────────────────────────────────────────────────
        try:
            embedding = self._embedder.embed(snapshot_text)
        except Exception as exc:
            logger.error("Embedding failed during memory retrieval: %s", exc)
            return []

        if not embedding:
            logger.warning("Embedder returned empty vector — skipping memory retrieval")
            return []

        # ── pgvector cosine similarity query ─────────────────────────────────
        # We fetch over_fetch candidates then re-rank in Python
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

        sql = text(
            """
            SELECT
                id,
                ticker,
                signal,
                confidence,
                reasoning,
                key_factors,
                correct,
                outcome_pct,
                created_at,
                1 - (embedding <=> :embedding ::vector) AS similarity
            FROM predictions
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> :embedding ::vector
            LIMIT :limit
            """
        )

        try:
            rows = db.execute(
                sql,
                {"embedding": embedding_str, "limit": over_fetch},
            ).fetchall()
        except Exception as exc:
            logger.error("pgvector similarity query failed: %s", exc)
            return []

        if not rows:
            logger.debug("No past predictions in memory yet.")
            return []

        # ── Parse rows ────────────────────────────────────────────────────────
        memories: list[RetrievedMemory] = []
        for row in rows:
            try:
                key_factors = row.key_factors if isinstance(row.key_factors, list) else []
                memories.append(
                    RetrievedMemory(
                        prediction_id=row.id,
                        ticker=row.ticker,
                        signal=row.signal,
                        confidence=float(row.confidence),
                        reasoning=row.reasoning,
                        key_factors=key_factors,
                        correct=row.correct,
                        outcome_pct=float(row.outcome_pct) if row.outcome_pct is not None else None,
                        similarity=float(row.similarity),
                        created_at=row.created_at.replace(tzinfo=timezone.utc)
                        if row.created_at.tzinfo is None
                        else row.created_at,
                    )
                )
            except Exception:
                logger.debug("Skipping malformed memory row", exc_info=True)

        # ── Re-rank: boost incorrect predictions ──────────────────────────────
        def effective_score(m: RetrievedMemory) -> float:
            score = m.similarity
            if m.correct is False:
                score *= _INCORRECT_BOOST
                m.boosted_for_incorrectness = True
            return score

        memories.sort(key=effective_score, reverse=True)
        return memories[:k]

    @staticmethod
    def format_context(memories: list[RetrievedMemory]) -> str:
        """
        Format retrieved memories into a context block for the LLM prompt.
        Returns an empty string if no memories are available.
        """
        if not memories:
            return ""

        lines = [
            "## Past Prediction Memory",
            f"({len(memories)} similar past analyses retrieved — "
            "incorrect ones are highlighted for learning)\n",
        ]
        for i, mem in enumerate(memories, 1):
            lines.append(f"{i}. {mem.to_prompt_str()}")

        return "\n".join(lines)
