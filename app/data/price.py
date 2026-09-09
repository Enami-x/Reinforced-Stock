"""
Price data fetcher — yfinance + technical indicators.

Computes the following indicators from raw OHLCV data:
  - RSI (14-period)
  - MACD (12/26/9)
  - Bollinger Bands (20-period, 2σ)
  - SMA 50 and SMA 200
  - Volume ratio (current vs 20-day avg)
  - 52-week high/low and distance from each
  - ATR (14-period Average True Range)

All values are rounded to 4 decimal places for clean JSON storage.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import yfinance as yf
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator
from ta.volatility import AverageTrueRange, BollingerBands

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


class TechnicalIndicators(BaseModel):
    """Computed technical indicator values for a single snapshot."""

    rsi_14: float | None = Field(None, description="RSI (14-period), 0–100")
    macd_line: float | None = Field(None, description="MACD line (12-26)")
    macd_signal: float | None = Field(None, description="MACD signal line (9-period EMA)")
    macd_histogram: float | None = Field(None, description="MACD histogram")
    bb_upper: float | None = Field(None, description="Bollinger Band upper (20, 2σ)")
    bb_middle: float | None = Field(None, description="Bollinger Band middle (SMA 20)")
    bb_lower: float | None = Field(None, description="Bollinger Band lower (20, 2σ)")
    bb_pct_b: float | None = Field(None, description="%B — position within Bollinger Bands")
    sma_50: float | None = Field(None, description="50-day Simple Moving Average")
    sma_200: float | None = Field(None, description="200-day Simple Moving Average")
    volume_ratio: float | None = Field(
        None, description="Current volume / 20-day avg volume"
    )
    week_52_high: float | None = Field(None, description="52-week highest close")
    week_52_low: float | None = Field(None, description="52-week lowest close")
    pct_from_52w_high: float | None = Field(
        None, description="% below 52-week high (negative = below)"
    )
    pct_from_52w_low: float | None = Field(
        None, description="% above 52-week low (positive = above)"
    )
    atr_14: float | None = Field(None, description="ATR (14-period)")


class PriceSnapshot(BaseModel):
    """Full price + technicals snapshot for a ticker at a point in time."""

    ticker: str
    fetched_at: datetime
    current_price: float
    open_price: float
    high_price: float
    low_price: float
    volume: int
    market_cap: float | None = None
    pe_ratio: float | None = None
    indicators: TechnicalIndicators
    # Raw OHLCV tail — last 5 bars for LLM context
    recent_closes: list[float] = Field(
        default_factory=list,
        description="Last 5 daily closing prices (oldest → newest)",
    )

    def to_dict(self) -> dict[str, Any]:
        """Flatten to a JSON-serialisable dict for DB storage and LLM prompts."""
        d = self.model_dump()
        d["fetched_at"] = self.fetched_at.isoformat()
        d["indicators"] = self.indicators.model_dump()
        return d


# ---------------------------------------------------------------------------
# Fetcher
# ---------------------------------------------------------------------------


class PriceFetcher:
    """
    Fetches OHLCV data from yfinance and computes all technical indicators.

    Usage:
        snapshot = PriceFetcher().fetch("AAPL")
    """

    # Minimum bars needed for SMA-200
    _MIN_BARS = 220

    def fetch(self, ticker: str) -> PriceSnapshot:
        """
        Download ~1 year of daily OHLCV data, compute indicators,
        and return a PriceSnapshot.

        Raises:
            ValueError: If the ticker is invalid or data is unavailable.
            RuntimeError: If yfinance returns insufficient history.
        """
        ticker = ticker.upper().strip()
        logger.info("Fetching price data for %s", ticker)

        yf_ticker = yf.Ticker(ticker)

        # ── Fetch history ────────────────────────────────────────────────────
        hist: pd.DataFrame = yf_ticker.history(period="1y", interval="1d", auto_adjust=True)

        if hist.empty:
            raise ValueError(f"No price data returned for ticker '{ticker}'. "
                             "Check that the symbol is valid and markets are open.")

        if len(hist) < 20:
            raise RuntimeError(
                f"Insufficient history for '{ticker}': got {len(hist)} bars, need ≥ 20."
            )

        # Rename to lowercase for consistency
        hist.columns = [c.lower() for c in hist.columns]

        close: pd.Series = hist["close"]
        high: pd.Series = hist["high"]
        low: pd.Series = hist["low"]
        volume: pd.Series = hist["volume"]

        # ── Fetch info (market cap, P/E) — graceful degradation ──────────────
        info: dict = {}
        try:
            info = yf_ticker.info or {}
        except Exception:
            logger.warning("Could not fetch .info for %s — skipping", ticker)

        # ── Compute indicators ───────────────────────────────────────────────
        indicators = self._compute_indicators(close, high, low, volume)

        # ── Build snapshot ───────────────────────────────────────────────────
        latest = hist.iloc[-1]
        recent_closes = [round(float(p), 4) for p in close.tail(5).tolist()]

        return PriceSnapshot(
            ticker=ticker,
            fetched_at=datetime.now(timezone.utc),
            current_price=round(float(latest["close"]), 4),
            open_price=round(float(latest["open"]), 4),
            high_price=round(float(latest["high"]), 4),
            low_price=round(float(latest["low"]), 4),
            volume=int(latest["volume"]),
            market_cap=info.get("marketCap"),
            pe_ratio=info.get("trailingPE"),
            indicators=indicators,
            recent_closes=recent_closes,
        )

    # ── Private helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _round(value: float | None) -> float | None:
        return round(value, 4) if value is not None and not pd.isna(value) else None

    def _compute_indicators(
        self,
        close: pd.Series,
        high: pd.Series,
        low: pd.Series,
        volume: pd.Series,
    ) -> TechnicalIndicators:
        r = self._round  # shorthand

        # RSI
        rsi_val = None
        try:
            rsi_series = RSIIndicator(close=close, window=14).rsi()
            rsi_val = r(float(rsi_series.iloc[-1]))
        except Exception:
            logger.debug("RSI computation failed", exc_info=True)

        # MACD
        macd_line_val = macd_sig_val = macd_hist_val = None
        try:
            macd_obj = MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
            macd_line_val = r(float(macd_obj.macd().iloc[-1]))
            macd_sig_val = r(float(macd_obj.macd_signal().iloc[-1]))
            macd_hist_val = r(float(macd_obj.macd_diff().iloc[-1]))
        except Exception:
            logger.debug("MACD computation failed", exc_info=True)

        # Bollinger Bands
        bb_upper_val = bb_mid_val = bb_lower_val = bb_pctb_val = None
        try:
            bb = BollingerBands(close=close, window=20, window_dev=2)
            bb_upper_val = r(float(bb.bollinger_hband().iloc[-1]))
            bb_mid_val = r(float(bb.bollinger_mavg().iloc[-1]))
            bb_lower_val = r(float(bb.bollinger_lband().iloc[-1]))
            bb_pctb_val = r(float(bb.bollinger_pband().iloc[-1]))
        except Exception:
            logger.debug("Bollinger Bands computation failed", exc_info=True)

        # SMA 50 / 200
        sma50_val = sma200_val = None
        try:
            sma50_val = r(float(SMAIndicator(close=close, window=50).sma_indicator().iloc[-1]))
        except Exception:
            logger.debug("SMA-50 computation failed", exc_info=True)
        try:
            if len(close) >= 200:
                sma200_val = r(
                    float(SMAIndicator(close=close, window=200).sma_indicator().iloc[-1])
                )
        except Exception:
            logger.debug("SMA-200 computation failed", exc_info=True)

        # Volume ratio (current / 20-day avg)
        vol_ratio_val = None
        try:
            avg_vol_20 = float(volume.tail(20).mean())
            curr_vol = float(volume.iloc[-1])
            vol_ratio_val = r(curr_vol / avg_vol_20) if avg_vol_20 > 0 else None
        except Exception:
            logger.debug("Volume ratio computation failed", exc_info=True)

        # 52-week high / low (use last 252 trading days ≈ 1 year)
        w52_high_val = w52_low_val = pct_from_high = pct_from_low = None
        try:
            window_252 = close.tail(252)
            w52_high_val = r(float(window_252.max()))
            w52_low_val = r(float(window_252.min()))
            current = float(close.iloc[-1])
            if w52_high_val and w52_high_val > 0:
                pct_from_high = r((current - w52_high_val) / w52_high_val * 100)
            if w52_low_val and w52_low_val > 0:
                pct_from_low = r((current - w52_low_val) / w52_low_val * 100)
        except Exception:
            logger.debug("52w high/low computation failed", exc_info=True)

        # ATR (14-period)
        atr_val = None
        try:
            atr_val = r(
                float(AverageTrueRange(high=high, low=low, close=close, window=14).average_true_range().iloc[-1])
            )
        except Exception:
            logger.debug("ATR computation failed", exc_info=True)

        return TechnicalIndicators(
            rsi_14=rsi_val,
            macd_line=macd_line_val,
            macd_signal=macd_sig_val,
            macd_histogram=macd_hist_val,
            bb_upper=bb_upper_val,
            bb_middle=bb_mid_val,
            bb_lower=bb_lower_val,
            bb_pct_b=bb_pctb_val,
            sma_50=sma50_val,
            sma_200=sma200_val,
            volume_ratio=vol_ratio_val,
            week_52_high=w52_high_val,
            week_52_low=w52_low_val,
            pct_from_52w_high=pct_from_high,
            pct_from_52w_low=pct_from_low,
            atr_14=atr_val,
        )
