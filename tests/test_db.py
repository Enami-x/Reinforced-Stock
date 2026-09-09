"""
Tests for app/db/ — database connectivity and model integrity.

The DB tests use mocking to avoid requiring a live Postgres instance in CI.
A separate integration test marker (pytest -m integration) can be added later
to run against a real Docker Compose DB.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import inspect, text


class TestCheckDbConnection:
    """check_db_connection() should return True/False based on reachability."""

    def test_returns_true_when_db_reachable(self):
        with patch("app.db.engine.engine") as mock_engine:
            mock_conn = MagicMock()
            mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

            from app.db.engine import check_db_connection

            # Patch the actual engine inside the module
            with patch("app.db.engine.engine.connect") as mock_connect:
                mock_ctx = MagicMock()
                mock_connect.return_value.__enter__ = MagicMock(return_value=mock_ctx)
                mock_connect.return_value.__exit__ = MagicMock(return_value=False)

                result = check_db_connection()
                assert result is True

    def test_returns_false_when_db_unreachable(self):
        with patch("app.db.engine.engine.connect") as mock_connect:
            mock_connect.side_effect = Exception("Connection refused")

            from app.db.engine import check_db_connection

            result = check_db_connection()
            assert result is False


class TestModelsImport:
    """All ORM models should be importable and have expected table names."""

    def test_prediction_record_table_name(self):
        from app.db.models import PredictionRecord

        assert PredictionRecord.__tablename__ == "predictions"

    def test_news_event_table_name(self):
        from app.db.models import NewsEvent

        assert NewsEvent.__tablename__ == "news_events"

    def test_price_snapshot_table_name(self):
        from app.db.models import PriceSnapshot

        assert PriceSnapshot.__tablename__ == "price_snapshots"


class TestModelColumns:
    """Key columns should exist on each model."""

    def test_prediction_has_required_columns(self):
        from app.db.models import PredictionRecord

        columns = {c.key for c in PredictionRecord.__table__.columns}
        required = {
            "id", "ticker", "signal", "confidence", "reasoning",
            "key_factors", "data_snapshot", "embedding",
            "created_at", "resolve_after", "resolved_at",
            "outcome_pct", "correct", "memory_ids_used",
        }
        assert required.issubset(columns), f"Missing columns: {required - columns}"

    def test_news_event_has_required_columns(self):
        from app.db.models import NewsEvent

        columns = {c.key for c in NewsEvent.__table__.columns}
        required = {
            "id", "finnhub_id", "ticker", "headline",
            "published_at", "seen_at", "triggered_analysis",
        }
        assert required.issubset(columns), f"Missing columns: {required - columns}"

    def test_price_snapshot_has_required_columns(self):
        from app.db.models import PriceSnapshot

        columns = {c.key for c in PriceSnapshot.__table__.columns}
        required = {"id", "ticker", "snapshot_date", "close_price", "data", "created_at"}
        assert required.issubset(columns), f"Missing columns: {required - columns}"


class TestHealthEndpoint:
    """FastAPI /health endpoint should return 200 without a DB connection."""

    def test_health_returns_200(self):
        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data

    def test_status_when_db_down(self):
        """
        /status should return 503 when the DB is unreachable.
        We mock check_db_connection to simulate a downed DB.
        """
        from fastapi.testclient import TestClient

        from app.main import app

        with patch("app.main.check_db_connection", return_value=False):
            client = TestClient(app)
            response = client.get("/status")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "degraded"
            assert data["checks"]["database"] == "unreachable"

    def test_status_config_present(self):
        """
        /status should always return config block regardless of DB state.
        """
        from fastapi.testclient import TestClient

        from app.main import app

        with patch("app.main.check_db_connection", return_value=False):
            client = TestClient(app)
            response = client.get("/status")
            data = response.json()
            assert "config" in data
            assert "watchlist" in data["config"]
            assert isinstance(data["config"]["watchlist"], list)
