"""
Watchlist management API.

GET  /watchlist                  Return the user's current watchlist (from DB)
POST /watchlist/{ticker}         Add a ticker to the watchlist
DELETE /watchlist/{ticker}       Remove a ticker from the watchlist
GET  /watchlist/available        Return the full curated catalog of tickers to pick from
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.engine import get_db
from app.db.models import WatchlistEntry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/watchlist", tags=["Watchlist"])


# ---------------------------------------------------------------------------
# Curated catalog  (60 well-known, liquid tickers across sectors)
# ---------------------------------------------------------------------------

AVAILABLE_TICKERS: list[dict[str, str]] = [
    # ── Technology ────────────────────────────────────────────────────────
    {"ticker": "AAPL",  "name": "Apple",                   "sector": "Technology"},
    {"ticker": "MSFT",  "name": "Microsoft",               "sector": "Technology"},
    {"ticker": "GOOGL", "name": "Alphabet (Google)",       "sector": "Technology"},
    {"ticker": "META",  "name": "Meta Platforms",          "sector": "Technology"},
    {"ticker": "AMZN",  "name": "Amazon",                  "sector": "Technology"},
    {"ticker": "NVDA",  "name": "NVIDIA",                  "sector": "Technology"},
    {"ticker": "AMD",   "name": "Advanced Micro Devices",  "sector": "Technology"},
    {"ticker": "INTC",  "name": "Intel",                   "sector": "Technology"},
    {"ticker": "TSMC",  "name": "TSMC",                    "sector": "Technology"},
    {"ticker": "CRM",   "name": "Salesforce",              "sector": "Technology"},
    {"ticker": "ORCL",  "name": "Oracle",                  "sector": "Technology"},
    {"ticker": "IBM",   "name": "IBM",                     "sector": "Technology"},
    {"ticker": "ADBE",  "name": "Adobe",                   "sector": "Technology"},
    {"ticker": "SNOW",  "name": "Snowflake",               "sector": "Technology"},
    {"ticker": "PLTR",  "name": "Palantir",                "sector": "Technology"},
    # ── Electric Vehicles / Auto ──────────────────────────────────────────
    {"ticker": "TSLA",  "name": "Tesla",                   "sector": "Automotive"},
    {"ticker": "RIVN",  "name": "Rivian",                  "sector": "Automotive"},
    {"ticker": "F",     "name": "Ford",                    "sector": "Automotive"},
    {"ticker": "GM",    "name": "General Motors",          "sector": "Automotive"},
    {"ticker": "TM",    "name": "Toyota",                  "sector": "Automotive"},
    # ── Finance ───────────────────────────────────────────────────────────
    {"ticker": "JPM",   "name": "JPMorgan Chase",          "sector": "Finance"},
    {"ticker": "GS",    "name": "Goldman Sachs",           "sector": "Finance"},
    {"ticker": "MS",    "name": "Morgan Stanley",          "sector": "Finance"},
    {"ticker": "BAC",   "name": "Bank of America",         "sector": "Finance"},
    {"ticker": "V",     "name": "Visa",                    "sector": "Finance"},
    {"ticker": "MA",    "name": "Mastercard",              "sector": "Finance"},
    {"ticker": "BRK-B", "name": "Berkshire Hathaway",     "sector": "Finance"},
    {"ticker": "COIN",  "name": "Coinbase",                "sector": "Finance"},
    # ── Healthcare ────────────────────────────────────────────────────────
    {"ticker": "JNJ",   "name": "Johnson & Johnson",       "sector": "Healthcare"},
    {"ticker": "PFE",   "name": "Pfizer",                  "sector": "Healthcare"},
    {"ticker": "MRNA",  "name": "Moderna",                 "sector": "Healthcare"},
    {"ticker": "LLY",   "name": "Eli Lilly",               "sector": "Healthcare"},
    {"ticker": "ABBV",  "name": "AbbVie",                  "sector": "Healthcare"},
    {"ticker": "UNH",   "name": "UnitedHealth Group",      "sector": "Healthcare"},
    # ── Energy ────────────────────────────────────────────────────────────
    {"ticker": "XOM",   "name": "ExxonMobil",              "sector": "Energy"},
    {"ticker": "CVX",   "name": "Chevron",                 "sector": "Energy"},
    {"ticker": "ENPH",  "name": "Enphase Energy",          "sector": "Energy"},
    {"ticker": "NEE",   "name": "NextEra Energy",          "sector": "Energy"},
    # ── Consumer ──────────────────────────────────────────────────────────
    {"ticker": "WMT",   "name": "Walmart",                 "sector": "Consumer"},
    {"ticker": "COST",  "name": "Costco",                  "sector": "Consumer"},
    {"ticker": "NKE",   "name": "Nike",                    "sector": "Consumer"},
    {"ticker": "MCD",   "name": "McDonald's",              "sector": "Consumer"},
    {"ticker": "SBUX",  "name": "Starbucks",               "sector": "Consumer"},
    {"ticker": "DIS",   "name": "Walt Disney",             "sector": "Consumer"},
    {"ticker": "NFLX",  "name": "Netflix",                 "sector": "Consumer"},
    # ── ETFs ──────────────────────────────────────────────────────────────
    {"ticker": "SPY",   "name": "S&P 500 ETF (SPDR)",     "sector": "ETF"},
    {"ticker": "QQQ",   "name": "NASDAQ-100 ETF",          "sector": "ETF"},
    {"ticker": "IWM",   "name": "Russell 2000 ETF",        "sector": "ETF"},
    {"ticker": "GLD",   "name": "Gold ETF (SPDR)",         "sector": "ETF"},
    # ── Semiconductors ────────────────────────────────────────────────────
    {"ticker": "QCOM",  "name": "Qualcomm",                "sector": "Semiconductors"},
    {"ticker": "AVGO",  "name": "Broadcom",                "sector": "Semiconductors"},
    {"ticker": "MU",    "name": "Micron Technology",       "sector": "Semiconductors"},
    {"ticker": "ASML",  "name": "ASML Holding",            "sector": "Semiconductors"},
    {"ticker": "AMAT",  "name": "Applied Materials",       "sector": "Semiconductors"},
    # ── Cloud / SaaS ─────────────────────────────────────────────────────
    {"ticker": "NET",   "name": "Cloudflare",              "sector": "Cloud"},
    {"ticker": "DDOG",  "name": "Datadog",                 "sector": "Cloud"},
    {"ticker": "ZS",    "name": "Zscaler",                 "sector": "Cloud"},
    {"ticker": "MDB",   "name": "MongoDB",                 "sector": "Cloud"},
    {"ticker": "SHOP",  "name": "Shopify",                 "sector": "Cloud"},
    {"ticker": "UBER",  "name": "Uber",                    "sector": "Cloud"},
]

# Quick lookup dict for validation
_TICKER_SET = {t["ticker"] for t in AVAILABLE_TICKERS}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/available",
    summary="Get the full catalog of available tickers",
    response_description="Curated list of tickers grouped by sector",
)
def get_available_tickers() -> dict[str, Any]:
    """
    Returns the full curated catalog of tickers a user can add to their watchlist.
    Grouped by sector for easy browsing.
    """
    sectors: dict[str, list[dict]] = {}
    for entry in AVAILABLE_TICKERS:
        sectors.setdefault(entry["sector"], []).append(
            {"ticker": entry["ticker"], "name": entry["name"]}
        )
    return {"sectors": sectors, "total": len(AVAILABLE_TICKERS)}


@router.get(
    "",
    summary="Get the user's current watchlist",
    response_description="List of tickers in the watchlist",
)
def get_watchlist(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Returns all tickers in the user's persisted watchlist."""
    entries = db.query(WatchlistEntry).order_by(WatchlistEntry.added_at).all()
    tickers = [e.ticker for e in entries]
    # Enrich with catalog metadata where available
    catalog_map = {t["ticker"]: t for t in AVAILABLE_TICKERS}
    enriched = []
    for e in entries:
        meta = catalog_map.get(e.ticker, {})
        enriched.append({
            "ticker": e.ticker,
            "name": meta.get("name", e.ticker),
            "sector": meta.get("sector", "Custom"),
            "added_at": e.added_at.isoformat() if e.added_at else None,
        })
    return {"watchlist": enriched, "tickers": tickers, "count": len(tickers)}


@router.post(
    "/{ticker}",
    summary="Add a ticker to the watchlist",
    status_code=201,
)
def add_to_watchlist(ticker: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    Add a ticker to the watchlist.  The ticker must be from the curated catalog
    OR be a valid-looking uppercase ticker (for power users who know what they want).
    """
    ticker = ticker.upper().strip()
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=422, detail="Invalid ticker symbol.")

    existing = db.query(WatchlistEntry).filter(WatchlistEntry.ticker == ticker).first()
    if existing:
        raise HTTPException(
            status_code=409, detail=f"{ticker} is already in the watchlist."
        )

    entry = WatchlistEntry(ticker=ticker, added_at=datetime.now(timezone.utc))
    db.add(entry)
    db.commit()
    logger.info("Watchlist: added %s", ticker)

    catalog_map = {t["ticker"]: t for t in AVAILABLE_TICKERS}
    meta = catalog_map.get(ticker, {})
    return {
        "ticker": ticker,
        "name": meta.get("name", ticker),
        "sector": meta.get("sector", "Custom"),
        "added": True,
    }


@router.delete(
    "/{ticker}",
    summary="Remove a ticker from the watchlist",
)
def remove_from_watchlist(ticker: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Remove a ticker from the watchlist. Returns 404 if not present."""
    ticker = ticker.upper().strip()
    entry = db.query(WatchlistEntry).filter(WatchlistEntry.ticker == ticker).first()
    if not entry:
        raise HTTPException(
            status_code=404, detail=f"{ticker} is not in the watchlist."
        )
    db.delete(entry)
    db.commit()
    logger.info("Watchlist: removed %s", ticker)
    return {"ticker": ticker, "removed": True}
