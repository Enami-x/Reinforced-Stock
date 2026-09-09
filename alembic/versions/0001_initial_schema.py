"""Initial schema — predictions, news_events, price_snapshots.

Revision ID: 0001
Revises:
Create Date: 2026-09-08 00:00:00.000000 UTC
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Embedding dimensionality — matches nvidia/nv-embedqa-e5-v5
EMBEDDING_DIM = 1024


def upgrade() -> None:
    # Ensure pgvector extension exists
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── predictions ─────────────────────────────────────────────────────────
    op.create_table(
        "predictions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("ticker", sa.String(10), nullable=False),
        sa.Column("signal", sa.String(4), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("key_factors", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("data_snapshot", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolve_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome_pct", sa.Float(), nullable=True),
        sa.Column("correct", sa.Boolean(), nullable=True),
        sa.Column(
            "memory_ids_used",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
    )

    # Indexes on predictions
    op.create_index("ix_predictions_ticker", "predictions", ["ticker"])
    op.create_index(
        "ix_predictions_ticker_created", "predictions", ["ticker", "created_at"]
    )
    op.create_index(
        "ix_predictions_pending_resolution",
        "predictions",
        ["resolve_after", "resolved_at"],
    )
    # HNSW vector index (cosine similarity)
    op.execute(
        """
        CREATE INDEX ix_predictions_embedding_hnsw
        ON predictions
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )

    # ── news_events ──────────────────────────────────────────────────────────
    op.create_table(
        "news_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("finnhub_id", sa.String(64), nullable=False),
        sa.Column("ticker", sa.String(10), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source", sa.String(256), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("triggered_analysis", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_unique_constraint(
        "uq_news_events_finnhub_id", "news_events", ["finnhub_id"]
    )
    op.create_index("ix_news_events_ticker", "news_events", ["ticker"])
    op.create_index(
        "ix_news_events_ticker_published", "news_events", ["ticker", "published_at"]
    )

    # ── price_snapshots ──────────────────────────────────────────────────────
    op.create_table(
        "price_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(10), nullable=False),
        sa.Column("snapshot_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("close_price", sa.Float(), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        "uq_price_snapshots_ticker_date",
        "price_snapshots",
        ["ticker", "snapshot_date"],
    )
    op.create_index("ix_price_snapshots_ticker", "price_snapshots", ["ticker"])
    op.create_index(
        "ix_price_snapshots_ticker_date",
        "price_snapshots",
        ["ticker", "snapshot_date"],
    )


def downgrade() -> None:
    op.drop_table("price_snapshots")
    op.drop_table("news_events")
    op.drop_index("ix_predictions_embedding_hnsw", table_name="predictions")
    op.drop_index("ix_predictions_pending_resolution", table_name="predictions")
    op.drop_index("ix_predictions_ticker_created", table_name="predictions")
    op.drop_index("ix_predictions_ticker", table_name="predictions")
    op.drop_table("predictions")
