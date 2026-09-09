"""
Observability endpoints.

GET /logs/recent   Return the last N in-memory log records
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.logging_config import get_recent_logs

router = APIRouter(tags=["Observability"])


@router.get(
    "/logs/recent",
    summary="Recent in-memory log entries",
    response_description="Last N log records (newest first)",
)
def recent_logs(
    n: int = Query(default=50, ge=1, le=200, description="Number of log records to return"),
) -> list[dict[str, Any]]:
    """
    Return the most recent log entries captured in the in-memory ring buffer.
    Useful for quick diagnostics without SSH access to log files.

    Buffer holds the last 200 records; oldest entries are evicted automatically.
    """
    return get_recent_logs(n)
