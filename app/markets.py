"""
Market routing utilities — centralised helpers for multi-market support.

Provides:
  - is_indian_ticker(ticker)      → True for .NS / .BO suffix tickers
  - is_nyse_market_hours()        → True during NYSE trading hours (ET)
  - is_nse_market_hours()         → True during NSE trading hours (IST)
  - is_market_open(ticker)        → routes to the correct calendar per ticker
  - get_trading_calendar(ticker)  → returns exchange_calendars calendar name

US tickers (no suffix) → NYSE: Mon–Fri 09:30–16:00 US/Eastern
Indian tickers (.NS/.BO) → NSE: Mon–Fri 09:15–15:30 Asia/Kolkata

NSE public holidays are respected via exchange_calendars (XNSE schedule).
NYSE public holidays are respected via exchange_calendars (XNYS schedule).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytz

logger = logging.getLogger(__name__)

# ── Timezone constants ────────────────────────────────────────────────────────

_NYSE_TZ = pytz.timezone("America/New_York")
_NSE_TZ = pytz.timezone("Asia/Kolkata")

# ── NYSE hours ────────────────────────────────────────────────────────────────

_NYSE_OPEN_HOUR, _NYSE_OPEN_MIN = 9, 30
_NYSE_CLOSE_HOUR, _NYSE_CLOSE_MIN = 16, 0

# ── NSE hours ─────────────────────────────────────────────────────────────────

_NSE_OPEN_HOUR, _NSE_OPEN_MIN = 9, 15
_NSE_CLOSE_HOUR, _NSE_CLOSE_MIN = 15, 30


# ---------------------------------------------------------------------------
# Ticker classification
# ---------------------------------------------------------------------------


def is_indian_ticker(ticker: str) -> bool:
    """Return True if *ticker* is an NSE (.NS) or BSE (.BO) listed stock."""
    return ticker.upper().endswith((".NS", ".BO"))


def get_trading_calendar(ticker: str) -> str:
    """
    Return the exchange_calendars calendar identifier for a given ticker.

    - Indian tickers (.NS/.BO) → "XNSE" (National Stock Exchange of India)
    - Everything else           → "XNYS" (New York Stock Exchange)
    """
    return "XNSE" if is_indian_ticker(ticker) else "XNYS"


# ---------------------------------------------------------------------------
# Market-hours checks
# ---------------------------------------------------------------------------


def is_nyse_market_hours() -> bool:
    """Return True if current UTC time is within NYSE trading hours (Mon–Fri 09:30–16:00 ET)."""
    now_et = datetime.now(_NYSE_TZ)
    if now_et.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    market_open = now_et.replace(
        hour=_NYSE_OPEN_HOUR, minute=_NYSE_OPEN_MIN, second=0, microsecond=0
    )
    market_close = now_et.replace(
        hour=_NYSE_CLOSE_HOUR, minute=_NYSE_CLOSE_MIN, second=0, microsecond=0
    )
    if not (market_open <= now_et < market_close):
        return False

    # Optional: respect NYSE public holidays via exchange_calendars
    try:
        import exchange_calendars as xcals  # type: ignore[import-untyped]
        cal = xcals.get_calendar("XNYS")
        date_str = now_et.strftime("%Y-%m-%d")
        return cal.is_session(date_str)
    except Exception:
        # Graceful degradation — fall back to weekday-only check (already passed)
        return True


def is_nse_market_hours() -> bool:
    """Return True if current UTC time is within NSE trading hours (Mon–Fri 09:15–15:30 IST)."""
    now_ist = datetime.now(_NSE_TZ)
    if now_ist.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    market_open = now_ist.replace(
        hour=_NSE_OPEN_HOUR, minute=_NSE_OPEN_MIN, second=0, microsecond=0
    )
    market_close = now_ist.replace(
        hour=_NSE_CLOSE_HOUR, minute=_NSE_CLOSE_MIN, second=0, microsecond=0
    )
    if not (market_open <= now_ist < market_close):
        return False

    # Optional: respect NSE public holidays via exchange_calendars
    try:
        import exchange_calendars as xcals  # type: ignore[import-untyped]
        cal = xcals.get_calendar("XNSE")
        date_str = now_ist.strftime("%Y-%m-%d")
        return cal.is_session(date_str)
    except Exception:
        # Graceful degradation — fall back to weekday-only check
        return True


def is_market_open(ticker: str) -> bool:
    """
    Route to the correct market-hours check based on ticker suffix.

    Indian tickers (.NS/.BO) → NSE hours (9:15–15:30 IST)
    Everything else           → NYSE hours (9:30–16:00 ET)
    """
    if is_indian_ticker(ticker):
        return is_nse_market_hours()
    return is_nyse_market_hours()


# ---------------------------------------------------------------------------
# Trading-day horizon calculator
# ---------------------------------------------------------------------------


def compute_trading_day_horizon(ticker: str, horizon_days: int) -> int:
    """
    Convert *horizon_days* trading days into calendar days for a given ticker's exchange.

    Uses exchange_calendars if available for accuracy; falls back to the
    approximation (trading_days * 7 / 5) if the library is unavailable.

    Returns calendar days to add to datetime.now() to get resolve_after.
    """
    cal_name = get_trading_calendar(ticker)
    try:
        import exchange_calendars as xcals  # type: ignore[import-untyped]
        import pandas as pd

        cal = xcals.get_calendar(cal_name)
        today = pd.Timestamp.now(tz="UTC").normalize()
        # Get the next N trading sessions after today
        sessions = cal.sessions_in_range(
            today + pd.Timedelta(days=1),
            today + pd.Timedelta(days=horizon_days * 3),  # wide window to be safe
        )
        if len(sessions) >= horizon_days:
            target_session = sessions[horizon_days - 1]
            delta = target_session - today
            return int(delta.days) + 1  # +1 to be after market close on that day
        # Fallback if calendar range is too narrow
        logger.warning(
            "exchange_calendars: insufficient sessions for %s horizon=%d — using approximation",
            cal_name,
            horizon_days,
        )
    except Exception as exc:
        logger.debug(
            "exchange_calendars unavailable for %s (%s) — using approximation", cal_name, exc
        )

    # Approximation: 5 trading days ≈ 7 calendar days
    return int(horizon_days * 7 / 5)
