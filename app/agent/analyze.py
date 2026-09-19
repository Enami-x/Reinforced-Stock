"""
Stock analysis orchestrator — the core agent pipeline.

Full pipeline per analysis run
-------------------------------
1. Fetch price data (yfinance) + technicals
2. Fetch recent news (Finnhub, with DB dedup if session provided)
3. Build snapshot text for embedding
4. Retrieve similar past predictions from pgvector memory
5. Build LLM prompt (data + memory context)
6. Call Nemotron via NIM → structured JSON prediction
7. Embed the snapshot (for future memory retrieval)
8. Store prediction + embedding in Postgres
9. Return AnalysisResult

The orchestrator is designed to be called from:
  - POST /analyze/{ticker}      (manual trigger, Stage 3)
  - Watchlist scan scheduler    (Stage 4)
  - News-triggered analysis     (Stage 4)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.data.news import NewsFetcher, NewsItem, get_news_fetcher
from app.data.price import PriceFetcher, PriceSnapshot
from app.db.models import PredictionRecord
from app.llm.client import EmbeddingClient, LLMClient
from app.llm.prompt import PredictionOutput, PredictionPromptBuilder
from app.markets import compute_trading_day_horizon
from app.memory.retrieval import MemoryRetriever, RetrievedMemory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result schema
# ---------------------------------------------------------------------------


class AnalysisResult:
    """
    The full output of a single analysis run.
    Returned by StockAnalyzer.analyze() and serialised into the API response.
    """

    def __init__(
        self,
        prediction_id: uuid.UUID,
        ticker: str,
        prediction: PredictionOutput,
        price: PriceSnapshot,
        news: list[NewsItem],
        memories_used: list[RetrievedMemory],
        resolve_after: datetime,
    ) -> None:
        self.prediction_id = prediction_id
        self.ticker = ticker
        self.prediction = prediction
        self.price = price
        self.news = news
        self.memories_used = memories_used
        self.resolve_after = resolve_after

    def to_dict(self) -> dict[str, Any]:
        return {
            "prediction_id": str(self.prediction_id),
            "ticker": self.ticker,
            "signal": self.prediction.signal,
            "confidence": self.prediction.confidence,
            "reasoning": self.prediction.reasoning,
            "key_factors": self.prediction.key_factors,
            "resolve_after": self.resolve_after.isoformat(),
            "memory_count": len(self.memories_used),
            "price_at_analysis": self.price.current_price,
            "news_count": len(self.news),
        }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class StockAnalyzer:
    """
    Orchestrates the full analysis pipeline for a single ticker.

    All dependencies are injected so they can be easily mocked in tests.

    Usage:
        analyzer = StockAnalyzer()
        result = analyzer.analyze(ticker="AAPL", db=db_session)
    """

    def __init__(
        self,
        price_fetcher: PriceFetcher | None = None,
        news_fetcher: NewsFetcher | None = None,
        llm_client: LLMClient | None = None,
        embedding_client: EmbeddingClient | None = None,
        prompt_builder: PredictionPromptBuilder | None = None,
    ) -> None:
        self._price_fetcher = price_fetcher or PriceFetcher()
        self._news_fetcher = news_fetcher or NewsFetcher()
        self._llm = llm_client or LLMClient()
        self._embedder = embedding_client or EmbeddingClient()
        self._prompt_builder = prompt_builder or PredictionPromptBuilder()

    def analyze(
        self,
        ticker: str,
        db: Session,
        store_news: bool = True,
    ) -> AnalysisResult:
        """
        Run the full analysis pipeline for a ticker.

        Args:
            ticker: Stock ticker symbol.
            db: Active SQLAlchemy session (used for memory retrieval + storage).
            store_news: If True, deduplicate and store news articles in DB.

        Returns:
            AnalysisResult containing the prediction and all intermediate data.

        Raises:
            ValueError: If price data is unavailable for the ticker.
            RuntimeError: If the LLM call fails after all retries.
        """
        ticker = ticker.upper().strip()
        logger.info("Starting analysis for %s", ticker)

        # ── Step 1: Fetch price data ──────────────────────────────────────────
        price = self._price_fetcher.fetch(ticker)
        logger.info("%s: current price $%.2f, RSI=%.1f",
                    ticker, price.current_price,
                    price.indicators.rsi_14 or 0)

        # ── Step 2: Fetch news ────────────────────────────────────────────────
        # Route to correct news source per ticker:
        #   US tickers            → Finnhub (NewsFetcher)
        #   Indian (.NS/.BO)      → NewsAPI keyword search (NewsAPIFetcher)
        news: list[NewsItem] = []
        routed_fetcher = get_news_fetcher(ticker)
        try:
            if store_news:
                news = routed_fetcher.fetch_and_store(ticker, db)
            else:
                news = routed_fetcher.fetch(ticker)
        except Exception as exc:
            logger.warning("%s: news fetch failed (non-fatal): %s", ticker, exc)

        logger.info("%s: fetched %d news articles", ticker, len(news))

        # ── Step 3: Build snapshot text for embedding ─────────────────────────
        snapshot_text = self._prompt_builder.build_snapshot_text(ticker, price, news)

        # ── Step 4: Retrieve memory ───────────────────────────────────────────
        retriever = MemoryRetriever(self._embedder)
        memories: list[RetrievedMemory] = []
        try:
            memories = retriever.retrieve(
                snapshot_text=snapshot_text,
                db=db,
                ticker=ticker,
                top_k=settings.memory_top_k,
            )
            logger.info(
                "%s: retrieved %d memories (%d boosted for incorrectness)",
                ticker, len(memories),
                sum(1 for m in memories if m.boosted_for_incorrectness),
            )
        except Exception as exc:
            logger.warning("%s: memory retrieval failed (non-fatal): %s", ticker, exc)

        # ── Step 5 & 6: Build prompt + call LLM ──────────────────────────────
        messages = self._prompt_builder.build(ticker, price, news, memories)

        logger.info("%s: calling NIM LLM (%s)", ticker, settings.nim_llm_model)
        raw_response = self._llm.complete(messages, temperature=0.2, max_tokens=1024)

        prediction = self._prompt_builder.parse_response(raw_response)
        logger.info(
            "%s: prediction = %s (conf=%.0f%%)",
            ticker, prediction.signal, prediction.confidence * 100,
        )

        # ── Step 7: Embed the snapshot ────────────────────────────────────────
        embedding: list[float] | None = None
        try:
            embedding = self._embedder.embed(snapshot_text)
        except Exception as exc:
            logger.warning("%s: embedding failed (non-fatal): %s", ticker, exc)

        # ── Step 8: Store prediction ──────────────────────────────────────────
        resolve_after = self._compute_resolve_after(ticker)
        memory_ids = [str(m.prediction_id) for m in memories]

        record = PredictionRecord(
            ticker=ticker,
            signal=prediction.signal,
            confidence=prediction.confidence,
            reasoning=prediction.reasoning,
            key_factors=prediction.key_factors,
            data_snapshot=price.to_dict(),
            embedding=embedding,
            resolve_after=resolve_after,
            memory_ids_used=memory_ids,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        logger.info(
            "%s: prediction stored (id=%s, resolve_after=%s)",
            ticker, record.id, resolve_after.date(),
        )

        return AnalysisResult(
            prediction_id=record.id,
            ticker=ticker,
            prediction=prediction,
            price=price,
            news=news,
            memories_used=memories,
            resolve_after=resolve_after,
        )

    @staticmethod
    def _compute_resolve_after(ticker: str) -> datetime:
        """
        Compute the datetime after which this prediction can be resolved.

        Uses exchange_calendars to count actual trading days for the ticker's
        own market (XNSE for Indian, XNYS for US). Falls back to a calendar-day
        approximation (horizon * 7/5) if exchange_calendars is unavailable.
        """
        calendar_days = compute_trading_day_horizon(ticker, settings.resolution_horizon_days)
        return datetime.now(timezone.utc) + timedelta(days=calendar_days)
