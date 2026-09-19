"""
Centralised settings — loaded once from environment / .env file.
All other modules import `settings` from here; never read os.environ directly.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from dotenv import load_dotenv
from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Ensure .env file overrides stale environment variables in parent shell
load_dotenv(override=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql://stock_agent:stock_secret@localhost:5432/stock_insights",
        description="SQLAlchemy-compatible PostgreSQL connection string.",
    )

    # ── NVIDIA NIM ────────────────────────────────────────────────────────────
    nim_api_key: str = Field(default="", description="NVIDIA NIM API key (nvapi-...).")
    nim_base_url: str = Field(
        default="https://integrate.api.nvidia.com/v1",
        description="NIM OpenAI-compatible base URL.",
    )
    nim_llm_model: str = Field(
        default="meta/llama-3.2-11b-vision-instruct",
        description="NIM model name for prediction completions.",
    )
    nim_embedding_model: str = Field(
        default="nvidia/nemotron-3-embed-1b",
        description="NIM model name for generating vector embeddings.",
    )

    # ── Finnhub ───────────────────────────────────────────────────────────────
    finnhub_api_key: str = Field(default="", description="Finnhub API key.")

    # ── NewsAPI ───────────────────────────────────────────────────────────────
    newsapi_key: str = Field(
        default="",
        description=(
            "NewsAPI.org API key. Used as fallback news source for Indian tickers "
            "(.NS/.BO) where Finnhub free tier has no coverage."
        ),
    )

    # ── Watchlist ─────────────────────────────────────────────────────────────
    # Stored as a plain CSV string — pydantic-settings v2 would try to
    # JSON-decode a List[str] field from the env var, breaking CSV input.
    # We read it as a str and parse it in the computed_field below.
    watchlist_raw: str = Field(
        default="AAPL,MSFT,TSLA,NVDA,GOOGL",
        alias="watchlist",
        description="Comma-separated list of tickers (env var: WATCHLIST).",
    )

    @computed_field  # type: ignore[misc]
    @property
    def watchlist(self) -> List[str]:
        """Parse the raw CSV watchlist env var into an uppercased list."""
        return [t.strip().upper() for t in self.watchlist_raw.split(",") if t.strip()]

    # ── Scheduler ─────────────────────────────────────────────────────────────
    scan_interval_minutes: int = Field(
        default=240,
        ge=1,
        description="Full watchlist scan interval in minutes.",
    )
    news_poll_interval_minutes: int = Field(
        default=15,
        ge=1,
        description="News polling interval in minutes.",
    )
    resolution_hour_utc: int = Field(
        default=22,
        ge=0,
        le=23,
        description="Hour (UTC, 24h) at which the daily resolution job runs.",
    )

    # ── Agent settings ────────────────────────────────────────────────────────
    resolution_horizon_days: int = Field(
        default=5,
        ge=1,
        description="Trading days after prediction before resolution.",
    )
    correctness_threshold_pct: float = Field(
        default=2.0,
        ge=0.0,
        description="% price move required to mark a BUY/SELL prediction correct.",
    )
    memory_top_k: int = Field(
        default=5,
        ge=1,
        description="Number of similar past predictions to retrieve for context.",
    )
    news_lookback_hours: int = Field(
        default=24,
        ge=1,
        description="Hours of news history to fetch per polling cycle.",
    )

    # ── Derived helpers ───────────────────────────────────────────────────────
    @property
    def postgres_user(self) -> str:
        """Extract the user from database_url for health checks."""
        # postgresql://user:pass@host:port/db
        try:
            return self.database_url.split("://")[1].split(":")[0]
        except IndexError:
            return "unknown"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance (cached after first call)."""
    return Settings()


# Module-level convenience alias — import `settings` for easy access.
settings: Settings = get_settings()
