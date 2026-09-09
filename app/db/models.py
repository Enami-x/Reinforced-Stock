"""
SQLAlchemy ORM models for the stock insight agent.

Tables
------
predictions    — LLM predictions with pgvector embedding for memory retrieval
news_events    — Deduplicated log of seen Finnhub news articles
price_snapshots — Daily price + technicals snapshots (used at resolution time)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Predictions
# ---------------------------------------------------------------------------
class PredictionRecord(Base):
    """
    Stores each LLM-generated prediction along with the data snapshot it saw
    and a pgvector embedding of that snapshot for semantic memory retrieval.
    """

    __tablename__ = "predictions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    ticker: Mapped[str] = mapped_column(String(10), nullable=False, index=True)

    # ── Prediction output ────────────────────────────────────────────────────
    signal: Mapped[str] = mapped_column(
        String(4),
        nullable=False,
        comment="BUY | HOLD | SELL",
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="LLM self-reported confidence, 0.0–1.0",
    )
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    key_factors: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="List of bullet-point factors driving the signal",
    )

    # ── Input snapshot ────────────────────────────────────────────────────────
    data_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Full technicals + news at prediction time",
    )

    # ── pgvector embedding ────────────────────────────────────────────────────
    # 2048-dim to match nvidia/nemotron-3-embed-1b output
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(2048),
        nullable=True,
        comment="Embedding of the data_snapshot for similarity search",
    )

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    resolve_after: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Earliest datetime the prediction can be resolved",
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ── Resolution outcome ────────────────────────────────────────────────────
    outcome_pct: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Actual % price change over the resolution horizon",
    )
    correct: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        comment="True / False after resolution; None while pending",
    )

    # ── Memory context used ───────────────────────────────────────────────────
    memory_ids_used: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="UUIDs of past predictions retrieved as context for this call",
    )

    # ── Indexes ───────────────────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_predictions_ticker_created", "ticker", "created_at"),
        Index("ix_predictions_pending_resolution", "resolve_after", "resolved_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<PredictionRecord id={self.id} ticker={self.ticker} "
            f"signal={self.signal} correct={self.correct}>"
        )


# ---------------------------------------------------------------------------
# News Events
# ---------------------------------------------------------------------------
class NewsEvent(Base):
    """
    Deduplication log for Finnhub news articles.
    Each article is identified by its Finnhub-assigned ID.
    When the news poller sees a new article it hasn't stored here,
    it triggers an analysis of the related ticker.
    """

    __tablename__ = "news_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    finnhub_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Finnhub article ID (used for dedup)",
    )
    ticker: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(256), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    triggered_analysis: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("finnhub_id", name="uq_news_events_finnhub_id"),
        Index("ix_news_events_ticker_published", "ticker", "published_at"),
    )

    def __repr__(self) -> str:
        return f"<NewsEvent id={self.id} ticker={self.ticker} headline={self.headline[:40]!r}>"


# ---------------------------------------------------------------------------
# Price Snapshots
# ---------------------------------------------------------------------------
class PriceSnapshot(Base):
    """
    Daily closing price + technicals snapshot.
    Used at resolution time to avoid re-fetching historical data from yfinance.
    Also serves as a lightweight audit trail of what the market looked like.
    """

    __tablename__ = "price_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    snapshot_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="The trading date this snapshot represents",
    )
    close_price: Mapped[float] = mapped_column(Float, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Full technical indicator values for this date",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "ticker",
            "snapshot_date",
            name="uq_price_snapshots_ticker_date",
        ),
        Index("ix_price_snapshots_ticker_date", "ticker", "snapshot_date"),
    )

    def __repr__(self) -> str:
        return (
            f"<PriceSnapshot ticker={self.ticker} "
            f"date={self.snapshot_date} close={self.close_price}>"
        )
