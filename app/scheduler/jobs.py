"""
APScheduler jobs for the stock insight agent.

Three jobs run in the background inside the FastAPI process:

  1. watchlist_scan  — every SCAN_INTERVAL_MINUTES during NYSE market hours
                       (Mon–Fri 09:30–16:00 ET). Analyses all tickers in config.

  2. news_poll       — every NEWS_POLL_INTERVAL_MINUTES. Checks Finnhub news for
                       each watchlist ticker. Triggers an immediate analysis if
                       new unseen articles are found for a ticker.

  3. resolution_job  — daily at RESOLUTION_HOUR_UTC UTC. Finds all predictions
                       whose resolve_after has passed and grades them against the
                       actual price move. Implemented in Stage 5 — stub here.

Market-hours gate
-----------------
NYSE is open Mon–Fri 09:30–16:00 US/Eastern. We check UTC time and convert.
If the scan fires outside market hours it is silently skipped (no error logged).
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

logger = logging.getLogger(__name__)

_NYSE_TZ = pytz.timezone("America/New_York")
_MARKET_OPEN_HOUR = 9
_MARKET_OPEN_MIN = 30
_MARKET_CLOSE_HOUR = 16
_MARKET_CLOSE_MIN = 0


# ---------------------------------------------------------------------------
# Market-hours helper
# ---------------------------------------------------------------------------

def _is_market_hours() -> bool:
    """Return True if current time is within NYSE trading hours (Mon–Fri 09:30–16:00 ET)."""
    now_et = datetime.now(_NYSE_TZ)
    if now_et.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    market_open = now_et.replace(
        hour=_MARKET_OPEN_HOUR, minute=_MARKET_OPEN_MIN, second=0, microsecond=0
    )
    market_close = now_et.replace(
        hour=_MARKET_CLOSE_HOUR, minute=_MARKET_CLOSE_MIN, second=0, microsecond=0
    )
    return market_open <= now_et < market_close


# ---------------------------------------------------------------------------
# Job functions
# ---------------------------------------------------------------------------

def _run_watchlist_scan() -> dict[str, Any]:
    """
    Analyse every ticker in the watchlist.
    Skipped silently if outside NYSE market hours.
    Returns a summary dict for the scheduler status endpoint.
    """
    if not _is_market_hours():
        logger.debug("Watchlist scan skipped — outside market hours")
        return {"skipped": True, "reason": "outside market hours"}

    from app.agent.analyze import StockAnalyzer

    logger.info("Starting scheduled watchlist scan for %d tickers", len(settings.watchlist))
    results: dict[str, str] = {}
    analyzer = StockAnalyzer()

    for ticker in settings.watchlist:
        with SessionLocal() as db:
            try:
                result = analyzer.analyze(ticker=ticker, db=db, store_news=True)
                results[ticker] = result.prediction.signal
                logger.info("Scan: %s → %s (%.0f%%)",
                            ticker, result.prediction.signal,
                            result.prediction.confidence * 100)
            except Exception as exc:
                logger.error("Scan failed for %s: %s", ticker, exc)
                results[ticker] = "ERROR"

    logger.info("Watchlist scan complete: %s", results)
    return {"skipped": False, "results": results}


def _run_news_poll() -> dict[str, Any]:
    """
    Poll Finnhub for new articles on every watchlist ticker.
    If new unseen articles are found for a ticker, trigger an immediate analysis.
    """
    if not settings.finnhub_api_key:
        logger.debug("News poll skipped — FINNHUB_API_KEY not configured")
        return {"skipped": True, "reason": "no finnhub key"}

    from app.agent.analyze import StockAnalyzer
    from app.data.news import NewsFetcher

    logger.debug("Running news poll for %d tickers", len(settings.watchlist))
    fetcher = NewsFetcher()
    triggered: list[str] = []

    for ticker in settings.watchlist:
        with SessionLocal() as db:
            try:
                new_articles = fetcher.fetch_and_store(ticker, db)
                if new_articles:
                    logger.info(
                        "News poll: %d new articles for %s — triggering analysis",
                        len(new_articles), ticker,
                    )
                    analyzer = StockAnalyzer()
                    result = analyzer.analyze(ticker=ticker, db=db, store_news=False)
                    # Mark the articles as having triggered an analysis
                    for article in new_articles:
                        fetcher.mark_triggered(article.finnhub_id, db)
                    triggered.append(ticker)
                    logger.info(
                        "News-triggered analysis for %s: %s", ticker, result.prediction.signal
                    )
            except Exception as exc:
                logger.error("News poll failed for %s: %s", ticker, exc)

    return {"triggered_tickers": triggered}


def _run_resolution_job() -> dict[str, Any]:
    """
    Grade past predictions that are now due for resolution.
    Implemented fully in Stage 5 — this stub keeps the scheduler wired up.
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
            name="News polling (Finnhub)",
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

        return {
            "running": True,
            "market_hours_now": _is_market_hours(),
            "watchlist": settings.watchlist,
            "jobs": jobs,
        }
