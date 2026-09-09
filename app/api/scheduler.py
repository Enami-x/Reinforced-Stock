"""
Scheduler API endpoints.

GET  /scheduler/status         Current scheduler state + next-run times
POST /scheduler/trigger-scan   Manually trigger a full watchlist scan
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scheduler", tags=["Scheduler"])


@router.get(
    "/status",
    summary="Scheduler status and next-run times",
    response_description="Running state, market hours flag, and per-job next runs",
)
def scheduler_status(request: Request) -> dict[str, Any]:
    """
    Returns the current state of all background scheduler jobs:
    - Whether the scheduler is running
    - Whether it's currently NYSE market hours
    - Next scheduled run time for each job (UTC ISO-8601)
    """
    manager = getattr(request.app.state, "scheduler", None)
    if manager is None:
        raise HTTPException(
            status_code=503,
            detail="Scheduler not initialised. Is the app running with lifespan?",
        )
    return manager.get_status()


@router.post(
    "/trigger-scan",
    summary="Manually trigger a full watchlist scan",
    response_description="Per-ticker signal results from the scan",
)
def trigger_scan(request: Request) -> dict[str, Any]:
    """
    Immediately run a full watchlist analysis scan, bypassing the market-hours
    gate. Useful for testing or forcing an update outside normal schedule.

    **Warning:** This calls the LLM for every ticker in the watchlist — may
    take 30–120 seconds depending on watchlist size.
    """
    manager = getattr(request.app.state, "scheduler", None)
    if manager is None:
        raise HTTPException(
            status_code=503,
            detail="Scheduler not initialised.",
        )
    try:
        results = manager.trigger_scan_now()
        return {"status": "completed", "results": results}
    except Exception as exc:
        logger.error("Manual scan failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
