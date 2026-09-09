"""
Tests for app/config.py — Settings loading and validation.

All tests operate entirely in-process; no external services required.
"""

from __future__ import annotations

import os

import pytest

from app.config import Settings


class TestSettingsDefaults:
    """Settings should have sensible defaults even without a .env file."""

    def test_default_watchlist(self):
        s = Settings()
        assert s.watchlist == ["AAPL", "MSFT", "TSLA", "NVDA", "GOOGL"]

    def test_default_resolution_horizon(self):
        s = Settings()
        assert s.resolution_horizon_days == 5

    def test_default_correctness_threshold(self):
        s = Settings()
        assert s.correctness_threshold_pct == 2.0

    def test_default_memory_top_k(self):
        s = Settings()
        assert s.memory_top_k == 5

    def test_default_scan_interval(self):
        s = Settings()
        assert s.scan_interval_minutes == 240

    def test_default_news_poll_interval(self):
        s = Settings()
        assert s.news_poll_interval_minutes == 15


class TestWatchlistParsing:
    """Watchlist should be parsed from the WATCHLIST CSV env var."""

    def test_csv_string_parsed(self, monkeypatch):
        monkeypatch.setenv("WATCHLIST", "AAPL,TSLA,NVDA")
        s = Settings()
        assert s.watchlist == ["AAPL", "TSLA", "NVDA"]

    def test_csv_with_spaces(self, monkeypatch):
        monkeypatch.setenv("WATCHLIST", " AAPL , TSLA , NVDA ")
        s = Settings()
        assert s.watchlist == ["AAPL", "TSLA", "NVDA"]

    def test_lowercase_tickers_uppercased(self, monkeypatch):
        monkeypatch.setenv("WATCHLIST", "aapl,msft")
        s = Settings()
        assert s.watchlist == ["AAPL", "MSFT"]

    def test_single_ticker(self, monkeypatch):
        monkeypatch.setenv("WATCHLIST", "SPY")
        s = Settings()
        assert s.watchlist == ["SPY"]


class TestSettingsValidation:
    """Invalid values should be rejected by Pydantic."""

    def test_scan_interval_must_be_positive(self, monkeypatch):
        monkeypatch.setenv("SCAN_INTERVAL_MINUTES", "0")
        with pytest.raises(Exception):  # pydantic ValidationError
            Settings()

    def test_resolution_hour_must_be_valid(self, monkeypatch):
        monkeypatch.setenv("RESOLUTION_HOUR_UTC", "25")
        with pytest.raises(Exception):
            Settings()

    def test_correctness_threshold_cannot_be_negative(self, monkeypatch):
        monkeypatch.setenv("CORRECTNESS_THRESHOLD_PCT", "-1.0")
        with pytest.raises(Exception):
            Settings()


class TestPostgresUserExtraction:
    """postgres_user property should parse the user from DATABASE_URL."""

    def test_extracts_user(self):
        s = Settings(
            database_url="postgresql://myuser:mypass@localhost:5432/mydb"
        )
        assert s.postgres_user == "myuser"

    def test_default_url_user(self):
        s = Settings()
        assert s.postgres_user == "stock_agent"
