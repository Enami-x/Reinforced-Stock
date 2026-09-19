"""
Stock Insight Agent — FastAPI entry point.

Start with:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
Updated config and models.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.accuracy import router as accuracy_router
from app.api.data import router as data_router
from app.api.observability import router as observability_router
from app.api.predictions import router as predictions_router
from app.api.scheduler import router as scheduler_router
from app.api.watchlist import router as watchlist_router
from app.config import settings
from app.db.engine import check_db_connection, SessionLocal
from app.db.models import Base, WatchlistEntry
from app.db.engine import engine
from app.logging_config import setup_logging
from app.scheduler.jobs import SchedulerManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: configure logging, create any new tables, seed watchlist from
    settings if the DB watchlist is empty, then start APScheduler.
    Shutdown: gracefully stop the scheduler.
    """
    setup_logging(level="INFO", json_format=False)
    logger.info("Stock Insight Agent starting up…")

    # Ensure the watchlist table (and any other new tables) exist
    Base.metadata.create_all(bind=engine)

    # Seed the DB watchlist from settings.watchlist if the table is empty
    with SessionLocal() as db:
        existing_count = db.query(WatchlistEntry).count()
        if existing_count == 0:
            for ticker in settings.watchlist:
                db.add(WatchlistEntry(ticker=ticker))
            db.commit()
            logger.info("Watchlist seeded from settings: %s", settings.watchlist)
        else:
            tickers = [e.ticker for e in db.query(WatchlistEntry).all()]
            logger.info("Watchlist loaded from DB: %s", tickers)

    # Start background scheduler
    manager = SchedulerManager()
    manager.start()
    app.state.scheduler = manager

    yield

    manager.stop()
    logger.info("Stock Insight Agent shutting down.")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Stock Insight Agent",
    description=(
        "LLM-powered stock analysis with buy/hold/sell signals, "
        "pgvector memory retrieval, and a self-improving feedback loop."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Allow the Vite dev server (and any other local origin) to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):(517\d|3000)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────
app.include_router(data_router)         # GET /data/snapshot/{ticker}
app.include_router(predictions_router)  # POST /analyze/{ticker}, GET /predictions/...
app.include_router(scheduler_router)    # GET /scheduler/status, POST /scheduler/trigger-scan
app.include_router(accuracy_router)     # GET /accuracy, GET /accuracy/{ticker}
app.include_router(observability_router)  # GET /logs/recent
app.include_router(watchlist_router)    # GET/POST/DELETE /watchlist, GET /watchlist/available


# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def root():
    """Redirect root to interactive API docs."""
    return RedirectResponse(url="/docs")


# ---------------------------------------------------------------------------
# Health & Status endpoints
# ---------------------------------------------------------------------------
@app.get(
    "/health",
    tags=["Meta"],
    summary="Liveness probe — confirms the service is running",
    response_description="{'status': 'ok'} when healthy",
)
def health_check() -> dict:
    """
    Lightweight liveness probe.
    Returns 200 immediately if the process is alive.
    Does **not** check external dependencies (use /status for that).
    """
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get(
    "/status",
    tags=["Meta"],
    summary="Readiness probe — checks all external dependencies",
    response_description="Detailed status of DB, config, and watchlist",
)
def status_check() -> JSONResponse:
    """
    Readiness probe that checks:
    - Database connectivity (Postgres + pgvector)
    - Whether required API keys are configured (non-empty)
    - Watchlist contents (read from DB, live) and agent settings

    Returns HTTP 200 when all systems are ready, 503 otherwise.
    """
    db_ok = check_db_connection()
    nim_configured = bool(settings.nim_api_key)
    finnhub_configured = bool(settings.finnhub_api_key)

    all_ok = db_ok and nim_configured and finnhub_configured

    # Read watchlist from DB (live) so it reflects user changes
    watchlist: list[str] = []
    if db_ok:
        try:
            with SessionLocal() as db:
                watchlist = [e.ticker for e in db.query(WatchlistEntry).order_by(WatchlistEntry.added_at).all()]
        except Exception:
            watchlist = settings.watchlist  # fallback to env var on error

    payload = {
        "status": "ready" if all_ok else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {
            "database": "ok" if db_ok else "unreachable",
            "nim_api_key": "configured" if nim_configured else "missing",
            "finnhub_api_key": "configured" if finnhub_configured else "missing",
        },
        "config": {
            "watchlist": watchlist,
            "scan_interval_minutes": settings.scan_interval_minutes,
            "news_poll_interval_minutes": settings.news_poll_interval_minutes,
            "resolution_horizon_days": settings.resolution_horizon_days,
            "correctness_threshold_pct": settings.correctness_threshold_pct,
            "memory_top_k": settings.memory_top_k,
        },
    }

    status_code = 200 if all_ok else 503
    return JSONResponse(content=payload, status_code=status_code)
