"""
SQLAlchemy engine and session factory.

Usage:
    # As a FastAPI dependency:
    def endpoint(db: Session = Depends(get_db)): ...

    # As a context manager (background jobs):
    with SessionLocal() as db:
        ...
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,        # detect stale connections before use
    pool_size=5,
    max_overflow=10,
    echo=False,                # set to True for SQL debug logging
)


@event.listens_for(engine, "connect")
def _enable_pgvector(dbapi_conn, _connection_record):
    """Ensure pgvector extension is available on every new connection."""
    with dbapi_conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    dbapi_conn.commit()


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,    # objects stay usable after commit
)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------
def get_db() -> Generator[Session, None, None]:
    """
    Yield a database session and ensure it is closed after the request.
    Use as a FastAPI dependency: ``db: Session = Depends(get_db)``.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Health helper
# ---------------------------------------------------------------------------
def check_db_connection() -> bool:
    """Return True if the database is reachable, False otherwise."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
