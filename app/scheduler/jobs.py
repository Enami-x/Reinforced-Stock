"""
APScheduler jobs for the stock insight agent.

Three jobs run in the background inside the FastAPI process:

  1. watchlist_scan  — every SCAN_INTERVAL_MINUTES. Analyses each ticker in the
                       watchlist only if that ticker's own market is currently
                       open (NYSE for US tickers, NSE for .NS/.BO tickers).
                       Mixed watchlists are supported — each ticker is checked
                       against its own calendar independently.

  2. news_poll       — every NEWS_POLL_INTERVAL_MINUTES. Checks news for each
                       watchlist ticker using the correct source (Finnhub for
                       US, NewsAPI for Indian). Triggers an immediate analysis
                       if new unseen articles are found for a ticker.

  3. resolution_job  — daily at RESOLUTION_HOUR_UTC UTC. Finds all predictions
                       whose resolve_after has passed and grades them against
                       the actual price move.

Market-hours gate
-----------------
Each ticker is routed to its own market calendar:
  - US tickers (no suffix)  → NYSE: Mon–Fri 09:30–16:00 US/Eastern
  - Indian tickers (.NS/.BO) → NSE: Mon–Fri 09:15–15:30 Asia/Kolkata

Tickers whose market is closed are silently skipped; the job still runs for
any tickers whose market is open. The job only returns skipped=True when NO
ticker in the watchlist has an open market.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.db.engine import SessionLocal
from app.markets import is_market_open, is_nyse_market_hours, is_nse_market_hours

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Backwards-compat alias — _is_market_hours() is preserved so that any
# existing callers of this private function continue to work.
# ---------------------------------------------------------------------------

_NYSE_TZ = pytz.timezone("America/New_York")


def _is_market_hours() -> bool:
    """
    Return True if current time is within NYSE trading hours (Mon–Fri 09:30–16:00 ET).

    Kept for backwards compatibility. New code should use is_market_open(ticker)
    from app.markets which routes to the correct calendar per ticker.
    """
    return is_nyse_market_hours()


# ---------------------------------------------------------------------------
# Job functions
# ---------------------------------------------------------------------------

def _run_watchlist_scan() -> dict[str, Any]:
    """
    Analyse every ticker in the watchlist whose market is currently open.

    Each ticker is independently checked against its own market calendar:
      - US tickers  → NYSE hours
      - .NS/.BO     → NSE hours

    If no ticker has an open market, the job returns skipped=True.
    Returns a summary dict for the scheduler status endpoint.
    """
    tickers_to_scan = [t for t in settings.watchlist if is_market_open(t)]

    if not tickers_to_scan:
        logger.debug(
            "Watchlist scan skipped — all markets closed (%d tickers checked)",
            len(settings.watchlist),
        )
        return {"skipped": True, "reason": "all markets closed"}

    from app.agent.analyze import StockAnalyzer

    logger.info(
        "Starting scheduled watchlist scan for %d/%d tickers (markets open: %s)",
        len(tickers_to_scan),
        len(settings.watchlist),
        tickers_to_scan,
    )
    results: dict[str, str] = {}
    analyzer = StockAnalyzer()

    for ticker in tickers_to_scan:
        with SessionLocal() as db:
            try:
                result = analyzer.analyze(ticker=ticker, db=db, store_news=True)
                results[ticker] = result.prediction.signal
                logger.info(
                    "Scan: %s → %s (%.0f%%)",
                    ticker,
                    result.prediction.signal,
                    result.prediction.confidence * 100,
                )
            except Exception as exc:
                logger.error("Scan failed for %s: %s", ticker, exc)
                results[ticker] = "ERROR"

    logger.info("Watchlist scan complete: %s", results)
    return {"skipped": False, "results": results}


def _run_news_poll() -> dict[str, Any]:
    """
    Poll news for every watchlist ticker using the correct source per ticker.

    Routing:
      - US tickers (.NS/.BO absent) → Finnhub (NewsFetcher)
      - Indian tickers (.NS/.BO)    → NewsAPI (NewsAPIFetcher)

    If new unseen articles are found for a ticker, triggers an immediate
    analysis of that ticker regardless of market hours.
    """
    from app.agent.analyze import StockAnalyzer
    from app.data.news import get_news_fetcher

    logger.debug("Running news poll for %d tickers", len(settings.watchlist))
    triggered: list[str] = []

    for ticker in settings.watchlist:
        fetcher = get_news_fetcher(ticker)

        # Skip Finnhub polling if key is absent (US tickers only)
        from app.data.news import NewsFetcher, NewsAPIFetcher
        if isinstance(fetcher, NewsFetcher) and not settings.finnhub_api_key:
            logger.debug("News poll skipped for %s — FINNHUB_API_KEY not configured", ticker)
            continue
        if isinstance(fetcher, NewsAPIFetcher) and not settings.newsapi_key:
            logger.debug("News poll skipped for %s — NEWSAPI_KEY not configured", ticker)
            continue

        with SessionLocal() as db:
            try:
                new_articles = fetcher.fetch_and_store(ticker, db)
                if new_articles:
                    logger.info(
                        "News poll: %d new articles for %s — triggering analysis",
                        len(new_articles),
                        ticker,
                    )
                    analyzer = StockAnalyzer()
                    result = analyzer.analyze(ticker=ticker, db=db, store_news=False)
                    # Mark the articles as having triggered an analysis
                    for article in new_articles:
                        fetcher.mark_triggered(article.finnhub_id, db)
                    triggered.append(ticker)
                    logger.info(
                        "News-triggered analysis for %s: %s",
                        ticker,
                        result.prediction.signal,
                    )
            except Exception as exc:
                logger.error("News poll failed for %s: %s", ticker, exc)

    return {"triggered_tickers": triggered}


def _run_resolution_job() -> dict[str, Any]:
    """
    Grade past predictions that are now due for resolution.
    """
    from app.resolution.resolver import PredictionResolver

    logger.info("Running daily resolution job")
    with SessionLocal() as db:
        try:
            resolver = PredictionResolver()
            summary = resolver.resolve_pending(db)
            logger.info("Resolution complete: %s", summary)
            return summary
        except Exception as exc:
            logger.error("Resolution job failed: %s", exc)
            return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Scheduler manager
# ---------------------------------------------------------------------------

class SchedulerManager:
    """
    Wraps APScheduler and exposes start/stop + status info.
    One instance is created at FastAPI startup and stored on app.state.
    """

    def __init__(self) -> None:
        self._scheduler = BackgroundScheduler(timezone="UTC")
        self._job_history: dict[str, Any] = {}

    def start(self) -> None:
        """Register all jobs and start the scheduler."""
        # ── Watchlist scan ────────────────────────────────────────────────────
        self._scheduler.add_job(
            _run_watchlist_scan,
            trigger=IntervalTrigger(minutes=settings.scan_interval_minutes),
            id="watchlist_scan",
            name="Watchlist full scan",
            replace_existing=True,
            misfire_grace_time=300,  # allow up to 5min late start
        )

        # ── News poll ─────────────────────────────────────────────────────────
        self._scheduler.add_job(
            _run_news_poll,
            trigger=IntervalTrigger(minutes=settings.news_poll_interval_minutes),
            id="news_poll",
            name="News polling (Finnhub/NewsAPI)",
            replace_existing=True,
            misfire_grace_time=120,
        )

        # ── Daily resolution ──────────────────────────────────────────────────
        self._scheduler.add_job(
            _run_resolution_job,
            trigger=CronTrigger(hour=settings.resolution_hour_utc, minute=0, timezone="UTC"),
            id="resolution_job",
            name="Daily prediction resolution",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        self._scheduler.start()
        logger.info(
            "Scheduler started — scan every %dmin, news poll every %dmin, "
            "resolution daily at %d:00 UTC",
            settings.scan_interval_minutes,
            settings.news_poll_interval_minutes,
            settings.resolution_hour_utc,
        )

    def stop(self) -> None:
        """Gracefully shut down the scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped.")

    def trigger_scan_now(self) -> dict[str, Any]:
        """Manually trigger a full watchlist scan immediately."""
        logger.info("Manual watchlist scan triggered via API")
        return _run_watchlist_scan()

    def get_status(self) -> dict[str, Any]:
        """Return scheduler status and next-run times for all jobs."""
        if not self._scheduler.running:
            return {"running": False, "jobs": []}

        jobs = []
        for job in self._scheduler.get_jobs():
            next_run = job.next_run_time
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_utc": next_run.isoformat() if next_run else None,
            })

        # Show both market statuses — useful when watchlist has mixed tickers
        return {
            "running": True,
            "market_hours_now": is_nyse_market_hours(),   # NYSE (US tickers)
            "nse_market_hours_now": is_nse_market_hours(),  # NSE (Indian tickers)
            "watchlist": settings.watchlist,
            "jobs": jobs,
        }
