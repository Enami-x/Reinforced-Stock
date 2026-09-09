"""
Finnhub news fetcher with deduplication against the news_events DB table.

Flow per poll cycle (per ticker):
  1. Call Finnhub /company-news for the ticker over the lookback window.
  2. For each article, check if finnhub_id already exists in news_events.
  3. Insert new articles; mark triggered_analysis=True on articles that
     caused an on-demand analysis run (the scheduler does this).
  4. Return only the NEW articles (unseen since last poll).

The Finnhub free tier allows ~60 API calls/minute. With 5 tickers polled
every 15 minutes, we use at most 5 calls per cycle — well within limits.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import finnhub
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import NewsEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


class NewsItem(BaseModel):
    """A single news article from Finnhub, normalised for LLM consumption."""

    finnhub_id: str
    ticker: str
    headline: str
    summary: str | None = None
    source: str | None = None
    url: str | None = None
    published_at: datetime | None = None
    is_new: bool = Field(
        default=True,
        description="True if this article was not previously seen in the DB.",
    )

    @property
    def age_hours(self) -> float | None:
        """Hours since publication, useful for recency weighting in prompts."""
        if self.published_at is None:
            return None
        delta = datetime.now(timezone.utc) - self.published_at
        return round(delta.total_seconds() / 3600, 1)

    def to_prompt_str(self) -> str:
        """Compact single-line representation for LLM prompt injection."""
        age = f" ({self.age_hours}h ago)" if self.age_hours is not None else ""
        src = f" [{self.source}]" if self.source else ""
        summary = f" — {self.summary}" if self.summary else ""
        return f"• {self.headline}{src}{age}{summary}"


# ---------------------------------------------------------------------------
# Fetcher
# ---------------------------------------------------------------------------


class NewsFetcher:
    """
    Fetches and deduplicates Finnhub company news for a given ticker.

    Usage (without DB dedup — e.g. for one-off snapshot endpoint):
        items = NewsFetcher().fetch(ticker="AAPL")

    Usage (with DB dedup — for the scheduler's news-poll job):
        new_items = NewsFetcher().fetch_and_store(ticker="AAPL", db=db_session)
    """

    _MAX_ARTICLES = 20  # cap per ticker per fetch to keep prompts manageable

    def __init__(self, api_key: str | None = None) -> None:
        self._client = finnhub.Client(api_key=api_key or settings.finnhub_api_key)

    # ── Public API ────────────────────────────────────────────────────────────

    def fetch(
        self,
        ticker: str,
        lookback_hours: int | None = None,
    ) -> list[NewsItem]:
        """
        Fetch recent news for a ticker from Finnhub.
        Does NOT interact with the database — no dedup.

        Args:
            ticker: Stock ticker symbol (e.g. "AAPL").
            lookback_hours: Hours of history to fetch. Defaults to settings value.

        Returns:
            List of NewsItem, newest first.
        """
        ticker = ticker.upper().strip()
        hours = lookback_hours or settings.news_lookback_hours
        raw = self._call_finnhub(ticker, hours)
        return self._parse_articles(ticker, raw)

    def fetch_and_store(
        self,
        ticker: str,
        db: Session,
        lookback_hours: int | None = None,
    ) -> list[NewsItem]:
        """
        Fetch news for a ticker, store new articles in news_events, and return
        only articles that were NOT previously seen (truly new).

        This is the method called by the news-poll scheduler job.

        Args:
            ticker: Stock ticker symbol.
            db: Active SQLAlchemy session.
            lookback_hours: Hours of history to fetch.

        Returns:
            List of NEW (previously unseen) NewsItem objects.
        """
        ticker = ticker.upper().strip()
        hours = lookback_hours or settings.news_lookback_hours
        raw = self._call_finnhub(ticker, hours)
        articles = self._parse_articles(ticker, raw)

        if not articles:
            return []

        # Batch-check which finnhub_ids already exist
        incoming_ids = [a.finnhub_id for a in articles]
        existing_ids: set[str] = set(
            row[0]
            for row in db.query(NewsEvent.finnhub_id)
            .filter(NewsEvent.finnhub_id.in_(incoming_ids))
            .all()
        )

        new_articles: list[NewsItem] = []
        for article in articles:
            if article.finnhub_id in existing_ids:
                article.is_new = False
                continue

            # Insert into DB
            event = NewsEvent(
                finnhub_id=article.finnhub_id,
                ticker=ticker,
                headline=article.headline,
                summary=article.summary,
                source=article.source,
                url=article.url,
                published_at=article.published_at,
                triggered_analysis=False,
            )
            db.add(event)
            new_articles.append(article)

        if new_articles:
            db.commit()
            logger.info(
                "Stored %d new news articles for %s (seen %d duplicates)",
                len(new_articles),
                ticker,
                len(articles) - len(new_articles),
            )
        else:
            logger.debug("No new articles for %s in the last %dh", ticker, hours)

        return new_articles

    def mark_triggered(self, finnhub_id: str, db: Session) -> None:
        """Mark a news_event row as having triggered an analysis run."""
        db.query(NewsEvent).filter(NewsEvent.finnhub_id == finnhub_id).update(
            {"triggered_analysis": True}
        )
        db.commit()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _call_finnhub(self, ticker: str, lookback_hours: int) -> list[dict[str, Any]]:
        """Call Finnhub company-news endpoint and return raw article dicts."""
        now = datetime.now(timezone.utc)
        from_dt = now - timedelta(hours=lookback_hours)

        from_str = from_dt.strftime("%Y-%m-%d")
        to_str = now.strftime("%Y-%m-%d")

        logger.debug("Fetching Finnhub news for %s from %s to %s", ticker, from_str, to_str)

        try:
            articles = self._client.company_news(ticker, _from=from_str, to=to_str)
            return articles or []
        except Exception as exc:
            logger.error("Finnhub API error for %s: %s", ticker, exc)
            return []

    def _parse_articles(
        self,
        ticker: str,
        raw: list[dict[str, Any]],
    ) -> list[NewsItem]:
        """Parse raw Finnhub article dicts into NewsItem objects."""
        items: list[NewsItem] = []
        for article in raw[: self._MAX_ARTICLES]:
            try:
                pub_ts = article.get("datetime")
                published_at = (
                    datetime.fromtimestamp(pub_ts, tz=timezone.utc) if pub_ts else None
                )
                items.append(
                    NewsItem(
                        finnhub_id=str(article.get("id", f"unknown-{time.time()}")),
                        ticker=ticker,
                        headline=article.get("headline", ""),
                        summary=article.get("summary") or None,
                        source=article.get("source") or None,
                        url=article.get("url") or None,
                        published_at=published_at,
                        is_new=True,
                    )
                )
            except Exception:
                logger.debug("Skipping malformed article: %s", article, exc_info=True)

        # Sort newest first
        items.sort(
            key=lambda x: x.published_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return items
