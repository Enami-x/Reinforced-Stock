"""
Data inspection endpoints — useful for debugging what the agent sees.

GET /data/snapshot/{ticker}
    Returns the current price snapshot + recent news for a ticker.
    This is exactly the data that would be fed into the LLM at analysis time.
    Does NOT store anything — purely read-only / diagnostic.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import settings
from app.data.news import NewsFetcher, NewsItem
from app.data.price import PriceFetcher, PriceSnapshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data", tags=["Data"])


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class DataSnapshotResponse(BaseModel):
    """Combined price + news snapshot for a ticker."""

    ticker: str
    price: PriceSnapshot
    news: list[NewsItem]
    news_lookback_hours: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/snapshot/{ticker}",
    response_model=DataSnapshotResponse,
    summary="Inspect what the agent would see for a ticker right now",
    response_description="Price technicals + recent news headlines",
)
def get_snapshot(
    ticker: str,
    lookback_hours: int = Query(
        default=None,
        ge=1,
        le=168,
        description="News lookback window in hours (default: settings.news_lookback_hours)",
    ),
) -> DataSnapshotResponse:
    """
    Returns the full data snapshot the agent would use to analyse this ticker:
    - Current price, OHLCV, and all 7 technical indicators
    - Recent news headlines from Finnhub

    This endpoint does NOT trigger an LLM call or store anything — it's a
    diagnostic / debugging tool.

    **Note:** Requires a valid `FINNHUB_API_KEY` in settings.
    """
    ticker = ticker.upper().strip()
    hours = lookback_hours or settings.news_lookback_hours

    # ── Price ────────────────────────────────────────────────────────────────
    try:
        price = PriceFetcher().fetch(ticker)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Unexpected error fetching price for %s: %s", ticker, exc)
        raise HTTPException(
            status_code=502,
            detail=f"Price data fetch failed for {ticker}. Check yfinance connectivity.",
        ) from exc

    # ── News ─────────────────────────────────────────────────────────────────
    news: list[NewsItem] = []
    if settings.finnhub_api_key:
        try:
            news = NewsFetcher().fetch(ticker, lookback_hours=hours)
        except Exception as exc:
            logger.warning("News fetch failed for %s (non-fatal): %s", ticker, exc)
            # News failure is non-fatal — return price data without news
    else:
        logger.warning("FINNHUB_API_KEY not set — skipping news for %s", ticker)

    return DataSnapshotResponse(
        ticker=ticker,
        price=price,
        news=news,
        news_lookback_hours=hours,
    )
