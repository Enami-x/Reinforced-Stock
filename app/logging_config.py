"""
Structured JSON logging configuration for the stock insight agent.

Sets up:
  - JSON-formatted logs via python-json-logger (machine-readable)
  - Human-readable console formatter in development
  - An in-memory ring buffer of the last N log records (for /logs/recent)
  - A unique trace_id per analysis run (injected via logging.LoggerAdapter)

Usage:
    from app.logging_config import setup_logging, get_recent_logs
    setup_logging()   # call once at startup
    logs = get_recent_logs(50)
"""

from __future__ import annotations

import collections
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from pythonjsonlogger import jsonlogger


# ---------------------------------------------------------------------------
# In-memory ring buffer for /logs/recent
# ---------------------------------------------------------------------------

_LOG_BUFFER_SIZE = 200
_log_buffer: collections.deque[dict[str, Any]] = collections.deque(maxlen=_LOG_BUFFER_SIZE)


class _BufferHandler(logging.Handler):
    """Captures log records into the in-memory ring buffer."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            _log_buffer.append({
                "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            })
        except Exception:
            pass  # never crash on logging


def get_recent_logs(n: int = 50) -> list[dict[str, Any]]:
    """Return the last n log records, newest first."""
    records = list(_log_buffer)
    return list(reversed(records))[:n]


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def setup_logging(level: str = "INFO", json_format: bool = False) -> None:
    """
    Configure root logger with:
      - JSON format (if json_format=True, e.g. in production)
      - Human-readable format (default, good for development)
      - In-memory buffer handler for /logs/recent

    Call once at application startup (before any logging calls).
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove default handlers
    root_logger.handlers.clear()

    # ── Console handler ───────────────────────────────────────────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    if json_format:
        formatter = jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%SZ",
            rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
        )
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s  %(levelname)-8s  %(name)-30s  %(message)s",
            datefmt="%H:%M:%S",
        )
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # ── In-memory buffer ──────────────────────────────────────────────────────
    root_logger.addHandler(_BufferHandler())

    # Quieten noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
