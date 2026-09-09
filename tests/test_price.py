"""
Tests for app/data/price.py — PriceFetcher and indicator computation.

All yfinance calls are mocked — no network required.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.data.price import PriceFetcher, PriceSnapshot, TechnicalIndicators


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlcv(n: int = 252, seed: int = 42) -> pd.DataFrame:
    """Generate a synthetic OHLCV DataFrame of length n."""
    rng = np.random.default_rng(seed)
    close = 150.0 + np.cumsum(rng.normal(0, 1, n))
    close = np.clip(close, 1, None)
    high = close * (1 + rng.uniform(0.001, 0.02, n))
    low = close * (1 - rng.uniform(0.001, 0.02, n))
    open_ = close * (1 + rng.normal(0, 0.005, n))
    volume = rng.integers(1_000_000, 50_000_000, n).astype(float)

    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=pd.date_range("2024-01-01", periods=n, freq="B"),
    )
    return df


# ---------------------------------------------------------------------------
# PriceFetcher.fetch() — mocked yfinance
# ---------------------------------------------------------------------------

class TestPriceFetcherFetch:
    def test_returns_price_snapshot(self, mocker):
        hist = _make_ohlcv(252)
        mock_ticker = mocker.MagicMock()
        mock_ticker.history.return_value = hist
        mock_ticker.info = {"marketCap": 3_000_000_000_000, "trailingPE": 28.5}
        mocker.patch("app.data.price.yf.Ticker", return_value=mock_ticker)

        result = PriceFetcher().fetch("AAPL")

        assert isinstance(result, PriceSnapshot)
        assert result.ticker == "AAPL"
        assert result.current_price > 0
        assert result.volume > 0

    def test_ticker_uppercased(self, mocker):
        hist = _make_ohlcv(252)
        mock_ticker = mocker.MagicMock()
        mock_ticker.history.return_value = hist
        mock_ticker.info = {}
        mocker.patch("app.data.price.yf.Ticker", return_value=mock_ticker)

        result = PriceFetcher().fetch("aapl")
        assert result.ticker == "AAPL"

    def test_raises_on_empty_history(self, mocker):
        mock_ticker = mocker.MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker.info = {}
        mocker.patch("app.data.price.yf.Ticker", return_value=mock_ticker)

        with pytest.raises(ValueError, match="No price data"):
            PriceFetcher().fetch("INVALID")

    def test_raises_on_insufficient_history(self, mocker):
        hist = _make_ohlcv(5)  # only 5 bars
        mock_ticker = mocker.MagicMock()
        mock_ticker.history.return_value = hist
        mock_ticker.info = {}
        mocker.patch("app.data.price.yf.Ticker", return_value=mock_ticker)

        with pytest.raises(RuntimeError, match="Insufficient history"):
            PriceFetcher().fetch("TINY")

    def test_recent_closes_length(self, mocker):
        hist = _make_ohlcv(252)
        mock_ticker = mocker.MagicMock()
        mock_ticker.history.return_value = hist
        mock_ticker.info = {}
        mocker.patch("app.data.price.yf.Ticker", return_value=mock_ticker)

        result = PriceFetcher().fetch("AAPL")
        assert len(result.recent_closes) == 5

    def test_info_failure_is_graceful(self, mocker):
        """If yf.Ticker.info raises, we still get a snapshot (market_cap=None)."""
        hist = _make_ohlcv(252)
        mock_ticker = mocker.MagicMock()
        mock_ticker.history.return_value = hist
        mock_ticker.info = mocker.PropertyMock(side_effect=Exception("rate limit"))
        # Make .info access raise
        type(mock_ticker).info = mocker.PropertyMock(side_effect=Exception("rate limit"))
        mocker.patch("app.data.price.yf.Ticker", return_value=mock_ticker)

        result = PriceFetcher().fetch("AAPL")
        assert result.market_cap is None


# ---------------------------------------------------------------------------
# Technical indicators
# ---------------------------------------------------------------------------

class TestTechnicalIndicators:
    """All indicators should be computed without error on 252 bars."""

    @pytest.fixture
    def snapshot(self, mocker) -> PriceSnapshot:
        hist = _make_ohlcv(252)
        mock_ticker = mocker.MagicMock()
        mock_ticker.history.return_value = hist
        mock_ticker.info = {}
        mocker.patch("app.data.price.yf.Ticker", return_value=mock_ticker)
        return PriceFetcher().fetch("TEST")

    def test_rsi_in_range(self, snapshot):
        assert snapshot.indicators.rsi_14 is not None
        assert 0 <= snapshot.indicators.rsi_14 <= 100

    def test_macd_all_present(self, snapshot):
        assert snapshot.indicators.macd_line is not None
        assert snapshot.indicators.macd_signal is not None
        assert snapshot.indicators.macd_histogram is not None

    def test_bollinger_bands_ordered(self, snapshot):
        ind = snapshot.indicators
        assert ind.bb_lower is not None
        assert ind.bb_middle is not None
        assert ind.bb_upper is not None
        assert ind.bb_lower < ind.bb_middle < ind.bb_upper

    def test_sma50_present(self, snapshot):
        assert snapshot.indicators.sma_50 is not None
        assert snapshot.indicators.sma_50 > 0

    def test_sma200_present(self, snapshot):
        assert snapshot.indicators.sma_200 is not None

    def test_volume_ratio_positive(self, snapshot):
        assert snapshot.indicators.volume_ratio is not None
        assert snapshot.indicators.volume_ratio > 0

    def test_52w_high_ge_low(self, snapshot):
        assert snapshot.indicators.week_52_high is not None
        assert snapshot.indicators.week_52_low is not None
        assert snapshot.indicators.week_52_high >= snapshot.indicators.week_52_low

    def test_pct_from_52w_high_nonpositive(self, snapshot):
        """Current price can never be above 52w high."""
        assert snapshot.indicators.pct_from_52w_high is not None
        assert snapshot.indicators.pct_from_52w_high <= 0.01  # tiny float tolerance

    def test_atr_positive(self, snapshot):
        assert snapshot.indicators.atr_14 is not None
        assert snapshot.indicators.atr_14 > 0

    def test_short_history_degrades_gracefully(self, mocker):
        """With only 25 bars, SMA-200 should be None but others present."""
        hist = _make_ohlcv(25)
        mock_ticker = mocker.MagicMock()
        mock_ticker.history.return_value = hist
        mock_ticker.info = {}
        mocker.patch("app.data.price.yf.Ticker", return_value=mock_ticker)

        result = PriceFetcher().fetch("SHORT")
        assert result.indicators.sma_200 is None
        assert result.indicators.rsi_14 is not None  # RSI only needs 14 bars

    def test_to_dict_serialisable(self, snapshot):
        """to_dict() should return a JSON-serialisable structure."""
        import json
        d = snapshot.to_dict()
        json.dumps(d)  # should not raise
        assert "ticker" in d
        assert "indicators" in d
        assert "fetched_at" in d
