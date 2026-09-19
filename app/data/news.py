"""
News fetcher with dual-source support:
  - Finnhub (company-news endpoint): used for US tickers
  - NewsAPI.org (keyword search):    used for Indian tickers (.NS/.BO)
    where Finnhub free tier returns 403.

Flow per poll cycle (per ticker):
  1. Router selects the correct fetcher based on ticker suffix.
  2. Fetch articles from the appropriate source.
  3. For each article, check if the article ID already exists in news_events.
  4. Insert new articles; the scheduler marks triggered_analysis=True.
  5. Return only the NEW articles (unseen since last poll).

Finnhub limits: ~60 API calls/minute — well within budget for 5 US tickers.
NewsAPI limits:  100 requests/day on free tier — sufficient for ≤7 Indian tickers
                 polled every 15 minutes (≤ 96 calls/day).
"""

from __future__ import annotations

import hashlib
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
    """A single news article, normalised for LLM consumption."""

    finnhub_id: str
    """
    Unique article identifier. For Finnhub articles this is the numeric Finnhub ID.
    For NewsAPI articles this is a deterministic hash of the URL so dedup works
    across restarts without requiring a separate ID field.
    """
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
# Shared dedup helper
# ---------------------------------------------------------------------------


def _dedup_and_store(
    ticker: str,
    articles: list[NewsItem],
    db: Session,
) -> list[NewsItem]:
    """
    Given a list of fetched NewsItems, store the ones not already in news_events
    and return only the truly new ones. Used by both fetcher implementations.
    """
    if not articles:
        return []

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
        logger.debug("No new articles for %s", ticker)

    return new_articles


# ---------------------------------------------------------------------------
# Finnhub fetcher (US tickers)
# ---------------------------------------------------------------------------


class NewsFetcher:
    """
    Fetches and deduplicates Finnhub company news for a given ticker.

    Used for US tickers. Indian tickers (.NS/.BO) should use NewsAPIFetcher
    instead — call get_news_fetcher(ticker) to get the correct instance.

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
        """
        ticker = ticker.upper().strip()
        hours = lookback_hours or settings.news_lookback_hours
        raw = self._call_finnhub(ticker, hours)
        articles = self._parse_articles(ticker, raw)
        return _dedup_and_store(ticker, articles, db)

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


# ---------------------------------------------------------------------------
# NewsAPI fetcher (Indian tickers — .NS / .BO)
# ---------------------------------------------------------------------------


class NewsAPIFetcher:
    """
    Fetches news for Indian tickers using NewsAPI.org keyword search.

    Finnhub free tier returns 403 for NSE/BSE tickers. This fetcher uses
    the company's long name (from yfinance .info) as the search query on
    NewsAPI's /everything endpoint.

    The article ID is a deterministic SHA-256 hash of the URL so dedup
    works correctly across restarts (NewsAPI has no numeric article IDs).

    Usage:
        fetcher = NewsAPIFetcher()
        items = fetcher.fetch(ticker="RELIANCE.NS")
        new_items = fetcher.fetch_and_store(ticker="RELIANCE.NS", db=db)
    """

    _MAX_ARTICLES = 20

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.newsapi_key

    # ── Public API ────────────────────────────────────────────────────────────

    def fetch(
        self,
        ticker: str,
        lookback_hours: int | None = None,
    ) -> list[NewsItem]:
        """
        Fetch recent news for an Indian ticker from NewsAPI.org.
        Does NOT interact with the database — no dedup.
        """
        if not self._api_key:
            logger.debug("NewsAPI key not configured — skipping Indian news for %s", ticker)
            return []

        ticker = ticker.upper().strip()
        hours = lookback_hours or settings.news_lookback_hours
        company_name = self._get_company_name(ticker)
        if not company_name:
            logger.warning("Could not resolve company name for %s — skipping NewsAPI", ticker)
            return []

        raw = self._call_newsapi(company_name, hours)
        return self._parse_articles(ticker, raw)

    def fetch_and_store(
        self,
        ticker: str,
        db: Session,
        lookback_hours: int | None = None,
    ) -> list[NewsItem]:
        """
        Fetch news for an Indian ticker, store new articles in news_events,
        and return only articles that were NOT previously seen.
        """
        articles = self.fetch(ticker, lookback_hours)
        return _dedup_and_store(ticker.upper().strip(), articles, db)

    def mark_triggered(self, finnhub_id: str, db: Session) -> None:
        """Mark a news_event row as having triggered an analysis run."""
        db.query(NewsEvent).filter(NewsEvent.finnhub_id == finnhub_id).update(
            {"triggered_analysis": True}
        )
        db.commit()

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _get_company_name(ticker: str) -> str | None:
        """Resolve company long name via yfinance .info for the NewsAPI query."""
        try:
            import yfinance as yf
            info = yf.Ticker(ticker).info or {}
            name = info.get("longName") or info.get("shortName")
            if name:
                logger.debug("Resolved company name for %s: %s", ticker, name)
            return name
        except Exception as exc:
            logger.warning("Could not resolve company name for %s: %s", ticker, exc)
            return None

    def _call_newsapi(
        self,
        company_name: str,
        lookback_hours: int,
    ) -> list[dict[str, Any]]:
        """Call NewsAPI /everything endpoint and return raw article list."""
        try:
            from newsapi import NewsApiClient  # type: ignore[import-untyped]
        except ImportError:
            logger.error("newsapi-python not installed — cannot fetch Indian news")
            return []

        now = datetime.now(timezone.utc)
        from_dt = now - timedelta(hours=lookback_hours)
        from_str = from_dt.strftime("%Y-%m-%dT%H:%M:%S")

        logger.debug(
            "Fetching NewsAPI news for '%s' from %s", company_name, from_str
        )

        try:
            client = NewsApiClient(api_key=self._api_key)
            response = client.get_everything(
                q=company_name,
                from_param=from_str,
                language="en",
                sort_by="publishedAt",
                page_size=self._MAX_ARTICLES,
            )
            return response.get("articles") or []
        except Exception as exc:
            logger.error("NewsAPI error for '%s': %s", company_name, exc)
            return []

    def _parse_articles(
        self,
        ticker: str,
        raw: list[dict[str, Any]],
    ) -> list[NewsItem]:
        """Parse raw NewsAPI article dicts into NewsItem objects."""
        items: list[NewsItem] = []
        for article in raw[: self._MAX_ARTICLES]:
            try:
                url = article.get("url") or ""
                # Deterministic ID: hash of URL so dedup survives restarts
                article_id = "newsapi-" + hashlib.sha256(url.encode()).hexdigest()[:16]

                pub_str = article.get("publishedAt")
                published_at: datetime | None = None
                if pub_str:
                    try:
                        published_at = datetime.fromisoformat(
                            pub_str.replace("Z", "+00:00")
                        )
                    except ValueError:
                        pass

                source_obj = article.get("source") or {}
                source_name = (
                    source_obj.get("name")
                    if isinstance(source_obj, dict)
                    else str(source_obj)
                )

                items.append(
                    NewsItem(
                        finnhub_id=article_id,
                        ticker=ticker,
                        headline=article.get("title") or "",
                        summary=article.get("description") or None,
                        source=source_name or None,
                        url=url or None,
                        published_at=published_at,
                        is_new=True,
                    )
                )
            except Exception:
                logger.debug("Skipping malformed NewsAPI article", exc_info=True)

        # Sort newest first
        items.sort(
            key=lambda x: x.published_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return items


# ---------------------------------------------------------------------------
# Router — call this instead of instantiating fetchers directly
# ---------------------------------------------------------------------------


def get_news_fetcher(ticker: str) -> NewsFetcher | NewsAPIFetcher:
    """
    Return the correct news fetcher for *ticker*.

    Indian tickers (.NS/.BO) → NewsAPIFetcher
    Everything else           → NewsFetcher (Finnhub)

    Both implement the same .fetch() and .fetch_and_store() interface.
    """
    from app.markets import is_indian_ticker  # avoid circular import at module level

    if is_indian_ticker(ticker):
        logger.debug("Routing %s → NewsAPIFetcher (Indian ticker)", ticker)
        return NewsAPIFetcher()
    logger.debug("Routing %s → NewsFetcher (Finnhub)", ticker)
    return NewsFetcher()
