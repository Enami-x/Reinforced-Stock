"""
Tests for Stages 4, 5, and 6:
  - app/scheduler/jobs.py  — market-hours gate, job functions (mocked)
  - app/resolution/resolver.py — correctness rules, resolve_pending, resolve_one
  - app/logging_config.py  — buffer handler, get_recent_logs
  - API endpoints: /scheduler/status, /accuracy, /logs/recent
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


# ============================================================================
# Stage 4 — Scheduler
# ============================================================================

class TestMarketHours:
    """_is_market_hours() should correctly gate NYSE trading hours."""

    def test_weekday_during_market_is_true(self, mocker):
        from app.scheduler.jobs import _is_market_hours
        import pytz

        # Monday 14:00 ET = 19:00 UTC → market open
        ny_tz = pytz.timezone("America/New_York")
        fake_now = ny_tz.localize(datetime(2026, 9, 7, 14, 0, 0))  # Monday
        mocker.patch("app.scheduler.jobs.datetime", wraps=datetime)
        with patch("app.scheduler.jobs.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            result = _is_market_hours()
        assert result is True

    def test_weekend_is_false(self, mocker):
        from app.scheduler.jobs import _is_market_hours
        import pytz

        ny_tz = pytz.timezone("America/New_York")
        fake_now = ny_tz.localize(datetime(2026, 9, 6, 12, 0, 0))  # Sunday
        with patch("app.scheduler.jobs.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            result = _is_market_hours()
        assert result is False

    def test_before_market_open_is_false(self, mocker):
        from app.scheduler.jobs import _is_market_hours
        import pytz

        ny_tz = pytz.timezone("America/New_York")
        fake_now = ny_tz.localize(datetime(2026, 9, 7, 8, 0, 0))  # Monday 8am ET
        with patch("app.scheduler.jobs.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            result = _is_market_hours()
        assert result is False

    def test_after_market_close_is_false(self, mocker):
        from app.scheduler.jobs import _is_market_hours
        import pytz

        ny_tz = pytz.timezone("America/New_York")
        fake_now = ny_tz.localize(datetime(2026, 9, 7, 17, 0, 0))  # Monday 5pm ET
        with patch("app.scheduler.jobs.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            result = _is_market_hours()
        assert result is False


class TestSchedulerManager:
    def test_start_and_stop(self):
        from app.scheduler.jobs import SchedulerManager

        manager = SchedulerManager()
        manager.start()
        assert manager._scheduler.running is True
        status = manager.get_status()
        assert status["running"] is True
        assert len(status["jobs"]) == 3
        manager.stop()
        assert manager._scheduler.running is False

    def test_get_status_job_ids(self):
        from app.scheduler.jobs import SchedulerManager

        manager = SchedulerManager()
        manager.start()
        job_ids = {j["id"] for j in manager.get_status()["jobs"]}
        assert "watchlist_scan" in job_ids
        assert "news_poll" in job_ids
        assert "resolution_job" in job_ids
        manager.stop()

    def test_watchlist_scan_skips_outside_hours(self, mocker):
        from app.scheduler.jobs import _run_watchlist_scan

        mocker.patch("app.scheduler.jobs._is_market_hours", return_value=False)
        result = _run_watchlist_scan()
        assert result["skipped"] is True

    def test_watchlist_scan_runs_during_hours(self, mocker):
        from app.scheduler.jobs import _run_watchlist_scan

        mocker.patch("app.scheduler.jobs._is_market_hours", return_value=True)
        # Can't patch computed_field directly — patch watchlist_raw on the settings singleton
        mocker.patch.object(
            __import__("app.config", fromlist=["settings"]).settings,
            "watchlist_raw",
            "AAPL",
            create=True,
        )

        mock_result = MagicMock()
        mock_result.prediction.signal = "BUY"

        with patch("app.agent.analyze.StockAnalyzer") as mock_cls:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = mock_result
            mock_cls.return_value = mock_analyzer
            with patch("app.scheduler.jobs.SessionLocal") as mock_session:
                mock_ctx = MagicMock()
                mock_ctx.__enter__ = MagicMock(return_value=MagicMock())
                mock_ctx.__exit__ = MagicMock(return_value=False)
                mock_session.return_value = mock_ctx
                result = _run_watchlist_scan()

        assert result.get("skipped") is not True

    def test_news_poll_skips_without_api_key(self, mocker):
        from app.scheduler.jobs import _run_news_poll

        mocker.patch("app.config.settings.finnhub_api_key", "")
        result = _run_news_poll()
        assert result["skipped"] is True


class TestSchedulerEndpoints:
    def test_status_endpoint_503_without_scheduler(self):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from app.api.scheduler import router

        # App without scheduler on state
        bare_app = FastAPI()
        bare_app.include_router(router)
        client = TestClient(bare_app)
        response = client.get("/scheduler/status")
        assert response.status_code == 503

    def test_trigger_scan_503_without_scheduler(self):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from app.api.scheduler import router

        bare_app = FastAPI()
        bare_app.include_router(router)
        client = TestClient(bare_app)
        response = client.post("/scheduler/trigger-scan")
        assert response.status_code == 503


# ============================================================================
# Stage 5 — Resolution
# ============================================================================

class TestCorrectnessRule:
    """PredictionResolver._apply_rule() should correctly grade each signal."""

    def setup_method(self):
        from app.resolution.resolver import PredictionResolver
        self.resolver = PredictionResolver()

    def test_buy_correct_when_price_up_above_threshold(self):
        assert self.resolver._apply_rule("BUY", 3.0, 2.0) is True

    def test_buy_incorrect_when_price_up_below_threshold(self):
        assert self.resolver._apply_rule("BUY", 1.5, 2.0) is False

    def test_buy_incorrect_when_price_down(self):
        assert self.resolver._apply_rule("BUY", -2.5, 2.0) is False

    def test_sell_correct_when_price_down_below_threshold(self):
        assert self.resolver._apply_rule("SELL", -3.0, 2.0) is True

    def test_sell_incorrect_when_price_only_slightly_down(self):
        assert self.resolver._apply_rule("SELL", -1.0, 2.0) is False

    def test_sell_incorrect_when_price_up(self):
        assert self.resolver._apply_rule("SELL", 2.5, 2.0) is False

    def test_hold_correct_within_threshold(self):
        assert self.resolver._apply_rule("HOLD", 1.5, 2.0) is True
        assert self.resolver._apply_rule("HOLD", -1.5, 2.0) is True
        assert self.resolver._apply_rule("HOLD", 0.0, 2.0) is True

    def test_hold_incorrect_outside_threshold(self):
        assert self.resolver._apply_rule("HOLD", 3.0, 2.0) is False
        assert self.resolver._apply_rule("HOLD", -3.0, 2.0) is False

    def test_at_exactly_threshold_buy_is_incorrect(self):
        # Must be strictly above threshold
        assert self.resolver._apply_rule("BUY", 2.0, 2.0) is False

    def test_unknown_signal_is_incorrect(self):
        assert self.resolver._apply_rule("STRONG_BUY", 5.0, 2.0) is False


class TestSnapshotPriceExtraction:
    def test_extracts_current_price(self):
        from app.resolution.resolver import PredictionResolver

        record = MagicMock()
        record.data_snapshot = {"current_price": 185.5}
        price = PredictionResolver._extract_snapshot_price(record)
        assert price == 185.5

    def test_raises_if_missing(self):
        from app.resolution.resolver import PredictionResolver

        record = MagicMock()
        record.data_snapshot = {}
        with pytest.raises(ValueError, match="No current_price"):
            PredictionResolver._extract_snapshot_price(record)


class TestResolvePending:
    def _make_pending_record(self, signal: str, snapshot_price: float) -> MagicMock:
        record = MagicMock(spec=["id", "ticker", "signal", "data_snapshot",
                                  "resolved_at", "resolve_after",
                                  "outcome_pct", "correct"])
        record.id = uuid.uuid4()
        record.ticker = "AAPL"
        record.signal = signal
        record.data_snapshot = {"current_price": snapshot_price}
        record.resolved_at = None
        return record

    def test_no_pending_returns_zero(self):
        from app.resolution.resolver import PredictionResolver

        db = MagicMock()
        db.query.return_value.filter.return_value.filter.return_value.all.return_value = []
        summary = PredictionResolver().resolve_pending(db)
        assert summary["resolved"] == 0

    def test_correct_prediction_graded(self, mocker):
        from app.resolution.resolver import PredictionResolver

        record = self._make_pending_record("BUY", 100.0)
        db = MagicMock()
        # Resolver uses a single .filter(cond1, cond2).all() — one chained filter call
        db.query.return_value.filter.return_value.all.return_value = [record]

        # Current price → +3% move → BUY is correct (threshold=2%)
        mocker.patch.object(PredictionResolver, "_fetch_current_price", return_value=103.0)
        mocker.patch("app.config.settings.correctness_threshold_pct", 2.0)

        summary = PredictionResolver().resolve_pending(db)
        assert summary["resolved"] == 1
        assert summary["correct"] == 1
        assert record.correct is True
        assert abs(record.outcome_pct - 3.0) < 0.01

    def test_incorrect_prediction_graded(self, mocker):
        from app.resolution.resolver import PredictionResolver

        record = self._make_pending_record("BUY", 100.0)
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [record]

        mocker.patch.object(PredictionResolver, "_fetch_current_price", return_value=101.0)
        mocker.patch("app.config.settings.correctness_threshold_pct", 2.0)

        summary = PredictionResolver().resolve_pending(db)
        assert summary["incorrect"] == 1
        assert record.correct is False

    def test_error_in_one_record_doesnt_halt_others(self, mocker):
        from app.resolution.resolver import PredictionResolver

        good = self._make_pending_record("BUY", 100.0)
        bad = self._make_pending_record("SELL", 100.0)

        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [bad, good]

        call_count = 0
        def side_effect(ticker):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("yfinance timeout")
            return 103.0

        mocker.patch.object(PredictionResolver, "_fetch_current_price", side_effect=side_effect)
        mocker.patch("app.config.settings.correctness_threshold_pct", 2.0)

        summary = PredictionResolver().resolve_pending(db)
        assert summary["errors"] == 1
        assert summary["resolved"] == 1  # the good one still resolved


class TestAccuracyEndpoints:
    def _make_db_with_records(self, records_data: list[dict]) -> MagicMock:
        """Build a mock DB that simulates query().count() and .filter().count()."""
        db = MagicMock()

        total = len(records_data)
        resolved_count = sum(1 for r in records_data if r.get("resolved"))
        correct_count = sum(1 for r in records_data if r.get("correct") is True)
        incorrect_count = sum(1 for r in records_data if r.get("correct") is False)

        # This is complex to mock properly — use a simpler approach:
        # Patch _compute_accuracy_stats directly
        return db

    def test_accuracy_returns_200(self, mocker):
        from fastapi.testclient import TestClient
        from app.main import app

        mocker.patch("app.api.accuracy.get_db", return_value=MagicMock())
        mocker.patch("app.api.accuracy._compute_accuracy_stats", return_value={
            "total_predictions": 10,
            "resolved": 8,
            "pending": 2,
            "correct": 6,
            "incorrect": 2,
            "overall_accuracy_pct": 75.0,
            "by_signal": {
                "BUY": {"total": 5, "resolved": 4, "correct": 3, "accuracy_pct": 75.0},
                "HOLD": {"total": 3, "resolved": 2, "correct": 2, "accuracy_pct": 100.0},
                "SELL": {"total": 2, "resolved": 2, "correct": 1, "accuracy_pct": 50.0},
            },
        })

        client = TestClient(app)
        response = client.get("/accuracy")
        assert response.status_code == 200
        data = response.json()
        assert data["overall_accuracy_pct"] == 75.0
        assert "by_signal" in data

    def test_ticker_accuracy_404_for_unknown(self, mocker):
        from fastapi.testclient import TestClient
        from app.main import app

        mocker.patch("app.api.accuracy.get_db", return_value=MagicMock())
        mocker.patch("app.api.accuracy._compute_accuracy_stats", return_value={
            "total_predictions": 0,
            "resolved": 0, "pending": 0, "correct": 0, "incorrect": 0,
            "overall_accuracy_pct": None, "by_signal": {},
            "ticker": "FAKE",
        })

        client = TestClient(app)
        response = client.get("/accuracy/FAKE")
        assert response.status_code == 404


# ============================================================================
# Stage 6 — Observability
# ============================================================================

class TestLoggingConfig:
    def test_setup_logging_runs_without_error(self):
        from app.logging_config import setup_logging
        setup_logging(level="INFO", json_format=False)

    def test_buffer_captures_log_records(self):
        import logging
        from app.logging_config import setup_logging, get_recent_logs, _log_buffer

        _log_buffer.clear()
        setup_logging(level="DEBUG", json_format=False)

        test_logger = logging.getLogger("test.buffer")
        test_logger.info("Test buffer message XYZ123")

        logs = get_recent_logs(10)
        messages = [l["message"] for l in logs]
        assert any("XYZ123" in m for m in messages)

    def test_get_recent_logs_newest_first(self):
        import logging
        from app.logging_config import setup_logging, get_recent_logs, _log_buffer

        _log_buffer.clear()
        setup_logging(level="DEBUG", json_format=False)

        lg = logging.getLogger("test.order")
        lg.info("FIRST_MESSAGE")
        lg.info("SECOND_MESSAGE")
        lg.info("THIRD_MESSAGE")

        logs = get_recent_logs(3)
        assert "THIRD_MESSAGE" in logs[0]["message"]

    def test_get_recent_logs_respects_n(self):
        import logging
        from app.logging_config import setup_logging, get_recent_logs, _log_buffer

        _log_buffer.clear()
        setup_logging(level="DEBUG", json_format=False)

        lg = logging.getLogger("test.limit")
        for i in range(10):
            lg.info("MSG %d", i)

        logs = get_recent_logs(3)
        assert len(logs) <= 3


class TestObservabilityEndpoint:
    def test_logs_recent_returns_list(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        response = client.get("/logs/recent")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_logs_recent_respects_n_param(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        response = client.get("/logs/recent?n=5")
        assert response.status_code == 200
        assert len(response.json()) <= 5

    def test_logs_recent_rejects_out_of_range(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        response = client.get("/logs/recent?n=500")
        assert response.status_code == 422  # Pydantic validation error
