"""
Alembic migration environment.

Reads DATABASE_URL from app settings so migrations use the same connection
string as the application — no duplicate config.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import models so Alembic can detect schema changes automatically.
from app.config import settings
from app.db.models import Base  # noqa: F401 — registers all models with metadata

# ── Alembic Config object ──────────────────────────────────────────────────
config = context.config

# Inject DATABASE_URL from app settings (overrides alembic.ini sqlalchemy.url)
config.set_main_option("sqlalchemy.url", settings.database_url)

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata for 'autogenerate' support
target_metadata = Base.metadata


# ── Offline mode ───────────────────────────────────────────────────────────
def run_migrations_offline() -> None:
    """
    Run migrations without a live DB connection — useful for generating SQL.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online mode ────────────────────────────────────────────────────────────
def run_migrations_online() -> None:
    """
    Run migrations against a live database connection.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
