"""
Tests for Stage 3:
  - app/llm/prompt.py  — PredictionPromptBuilder, PredictionOutput, parse_response
  - app/llm/client.py  — LLMClient, EmbeddingClient (mocked OpenAI)
  - app/memory/retrieval.py — MemoryRetriever (mocked pgvector)
  - app/agent/analyze.py — StockAnalyzer (fully mocked pipeline)
  - Prediction API endpoints (POST /analyze, GET /predictions/...)

All external calls (NIM, yfinance, Finnhub, DB) are mocked.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.data.news import NewsItem
from app.data.price import PriceSnapshot, TechnicalIndicators
from app.llm.prompt import PredictionOutput, PredictionPromptBuilder


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_price_snapshot(ticker: str = "AAPL") -> PriceSnapshot:
    return PriceSnapshot(
        ticker=ticker,
        fetched_at=datetime.now(timezone.utc),
        current_price=185.0,
        open_price=183.0,
        high_price=187.0,
        low_price=182.0,
        volume=45_000_000,
        indicators=TechnicalIndicators(
            rsi_14=58.3,
            macd_line=1.5,
            macd_signal=1.1,
            macd_histogram=0.4,
            bb_upper=192.0,
            bb_middle=183.0,
            bb_lower=174.0,
            bb_pct_b=0.6,
            sma_50=178.0,
            sma_200=162.0,
            volume_ratio=1.3,
            week_52_high=199.0,
            week_52_low=142.0,
            pct_from_52w_high=-7.0,
            pct_from_52w_low=30.3,
            atr_14=3.1,
        ),
        recent_closes=[180.0, 181.5, 183.0, 184.0, 185.0],
    )


def _make_news_item(headline: str = "Apple reports record revenue") -> NewsItem:
    return NewsItem(
        finnhub_id="test-1",
        ticker="AAPL",
        headline=headline,
        source="Reuters",
        published_at=datetime.now(timezone.utc),
    )


VALID_LLM_JSON = json.dumps({
    "signal": "BUY",
    "confidence": 0.75,
    "reasoning": "RSI is moderate and MACD shows bullish crossover. News sentiment is positive.",
    "key_factors": ["Bullish MACD crossover", "RSI not overbought", "Positive earnings news"],
})


# ---------------------------------------------------------------------------
# PredictionOutput validation
# ---------------------------------------------------------------------------

class TestPredictionOutput:
    def test_valid_buy_signal(self):
        out = PredictionOutput(
            signal="BUY",
            confidence=0.8,
            reasoning="Strong momentum signals.",
            key_factors=["RSI not overbought", "MACD bullish"],
        )
        assert out.signal == "BUY"
        assert out.confidence == 0.8

    def test_signal_uppercased(self):
        out = PredictionOutput(
            signal="buy", confidence=0.5,
            reasoning="Test reasoning here.", key_factors=["factor1"]
        )
        assert out.signal == "BUY"

    def test_invalid_signal_raises(self):
        with pytest.raises(Exception):
            PredictionOutput(signal="STRONG_BUY", confidence=0.9,
                             reasoning="x" * 10, key_factors=["f"])

    def test_confidence_out_of_range_raises(self):
        with pytest.raises(Exception):
            PredictionOutput(signal="HOLD", confidence=1.5,
                             reasoning="x" * 10, key_factors=["f"])

    def test_empty_reasoning_raises(self):
        with pytest.raises(Exception):
            PredictionOutput(signal="SELL", confidence=0.6,
                             reasoning="", key_factors=["f"])

    def test_string_key_factors_coerced_to_list(self):
        out = PredictionOutput(
            signal="HOLD", confidence=0.5,
            reasoning="Single factor scenario.", key_factors="just one factor"
        )
        assert isinstance(out.key_factors, list)


# ---------------------------------------------------------------------------
# parse_response
# ---------------------------------------------------------------------------

class TestParseResponse:
    def test_parses_clean_json(self):
        result = PredictionPromptBuilder.parse_response(VALID_LLM_JSON)
        assert result.signal == "BUY"
        assert result.confidence == 0.75
        assert len(result.key_factors) == 3

    def test_strips_markdown_code_block(self):
        wrapped = f"```json\n{VALID_LLM_JSON}\n```"
        result = PredictionPromptBuilder.parse_response(wrapped)
        assert result.signal == "BUY"

    def test_strips_prose_before_json(self):
        with_prose = f"Sure! Here is my analysis:\n{VALID_LLM_JSON}"
        result = PredictionPromptBuilder.parse_response(with_prose)
        assert result.signal == "BUY"

    def test_handles_trailing_comma(self):
        bad_json = '{"signal": "SELL", "confidence": 0.6, "reasoning": "Bearish trend.", "key_factors": ["factor1",]}'
        result = PredictionPromptBuilder.parse_response(bad_json)
        assert result.signal == "SELL"

    def test_raises_on_no_json(self):
        with pytest.raises(ValueError, match="No JSON object"):
            PredictionPromptBuilder.parse_response("I cannot provide a recommendation.")

    def test_raises_on_invalid_json(self):
        with pytest.raises(ValueError):
            PredictionPromptBuilder.parse_response("{signal: BUY}")

    def test_raises_on_invalid_schema(self):
        bad_schema = json.dumps({"action": "BUY", "conf": 0.9})  # wrong keys
        with pytest.raises(ValueError):
            PredictionPromptBuilder.parse_response(bad_schema)


# ---------------------------------------------------------------------------
# PredictionPromptBuilder.build()
# ---------------------------------------------------------------------------

class TestPromptBuilder:
    def test_build_returns_two_messages(self):
        builder = PredictionPromptBuilder()
        price = _make_price_snapshot()
        msgs = builder.build("AAPL", price, [], [])
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"

    def test_human_message_contains_ticker(self):
        builder = PredictionPromptBuilder()
        price = _make_price_snapshot()
        msgs = builder.build("AAPL", price, [], [])
        assert "AAPL" in msgs[1]["content"]

    def test_human_message_contains_price(self):
        builder = PredictionPromptBuilder()
        price = _make_price_snapshot()
        msgs = builder.build("AAPL", price, [], [])
        assert "185.00" in msgs[1]["content"]

    def test_news_included_in_prompt(self):
        builder = PredictionPromptBuilder()
        price = _make_price_snapshot()
        news = [_make_news_item("Apple beats Q3 estimates")]
        msgs = builder.build("AAPL", price, news, [])
        assert "Apple beats Q3 estimates" in msgs[1]["content"]

    def test_snapshot_text_for_embedding(self):
        builder = PredictionPromptBuilder()
        price = _make_price_snapshot()
        text = builder.build_snapshot_text("AAPL", price, [])
        assert "AAPL" in text
        assert "185" in text


# ---------------------------------------------------------------------------
# LLMClient (mocked OpenAI)
# ---------------------------------------------------------------------------

class TestLLMClient:
    def test_returns_response_text(self, mocker):
        from app.llm.client import LLMClient

        mock_response = MagicMock()
        mock_response.choices[0].message.content = VALID_LLM_JSON
        mock_response.choices[0].finish_reason = "stop"

        mocker.patch("app.llm.client.OpenAI")
        client = LLMClient(api_key="test", base_url="https://test.api", model="test-model")
        client._client.chat.completions.create.return_value = mock_response

        result = client.complete([{"role": "user", "content": "hello"}])
        assert result == VALID_LLM_JSON

    def test_retries_on_rate_limit(self, mocker):
        from openai import RateLimitError
        from app.llm.client import LLMClient

        mocker.patch("app.llm.client.time.sleep")  # don't actually sleep
        mocker.patch("app.llm.client.OpenAI")

        client = LLMClient(api_key="test", base_url="https://test", model="m")
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "ok"
        mock_response.choices[0].finish_reason = "stop"

        # Fail twice, succeed on 3rd
        client._client.chat.completions.create.side_effect = [
            RateLimitError("rate limit", response=MagicMock(), body={}),
            RateLimitError("rate limit", response=MagicMock(), body={}),
            mock_response,
        ]

        result = client.complete([{"role": "user", "content": "test"}])
        assert result == "ok"
        assert client._client.chat.completions.create.call_count == 3

    def test_raises_after_max_retries(self, mocker):
        from openai import RateLimitError
        from app.llm.client import LLMClient

        mocker.patch("app.llm.client.time.sleep")
        mocker.patch("app.llm.client.OpenAI")

        client = LLMClient(api_key="test", base_url="https://test", model="m")
        client._client.chat.completions.create.side_effect = RateLimitError(
            "rate limit", response=MagicMock(), body={}
        )

        with pytest.raises(RuntimeError, match="failed after"):
            client.complete([{"role": "user", "content": "test"}])


# ---------------------------------------------------------------------------
# EmbeddingClient (mocked)
# ---------------------------------------------------------------------------

class TestEmbeddingClient:
    def test_returns_vector(self, mocker):
        from app.llm.client import EmbeddingClient, EMBEDDING_DIM

        mocker.patch("app.llm.client.OpenAI")
        client = EmbeddingClient(api_key="test", base_url="https://test", model="m")

        mock_response = MagicMock()
        mock_response.data[0].embedding = [0.1] * EMBEDDING_DIM
        client._client.embeddings.create.return_value = mock_response

        vector = client.embed("test text")
        assert len(vector) == EMBEDDING_DIM
        assert vector[0] == 0.1

    def test_empty_text_returns_zero_vector(self, mocker):
        from app.llm.client import EmbeddingClient, EMBEDDING_DIM

        mocker.patch("app.llm.client.OpenAI")
        client = EmbeddingClient(api_key="test", base_url="https://test", model="m")
        vector = client.embed("   ")
        assert len(vector) == EMBEDDING_DIM
        assert all(v == 0.0 for v in vector)


# ---------------------------------------------------------------------------
# StockAnalyzer (fully mocked pipeline)
# ---------------------------------------------------------------------------

class TestStockAnalyzer:
    def _make_analyzer(self, mocker) -> tuple:
        """Return (analyzer, mocked dependencies) with happy-path defaults."""
        from app.agent.analyze import StockAnalyzer
        from app.llm.client import EMBEDDING_DIM

        price = _make_price_snapshot("AAPL")
        mock_price_fetcher = MagicMock()
        mock_price_fetcher.fetch.return_value = price

        mock_news_fetcher = MagicMock()
        mock_news_fetcher.fetch_and_store.return_value = [_make_news_item()]

        mock_llm = MagicMock()
        mock_llm.complete.return_value = VALID_LLM_JSON

        mock_embedder = MagicMock()
        mock_embedder.embed.return_value = [0.1] * EMBEDDING_DIM

        mock_db = MagicMock()
        # Simulate db.query for memory retrieval returning no rows
        mock_query = MagicMock()
        mock_query.filter.return_value = MagicMock(all=MagicMock(return_value=[]))
        mock_db.query.return_value = mock_query
        # Simulate execute for pgvector query returning no rows
        mock_db.execute.return_value = MagicMock(fetchall=MagicMock(return_value=[]))

        analyzer = StockAnalyzer(
            price_fetcher=mock_price_fetcher,
            news_fetcher=mock_news_fetcher,
            llm_client=mock_llm,
            embedding_client=mock_embedder,
        )
        return analyzer, mock_db, price, mock_llm

    def test_analyze_returns_result(self, mocker):
        from app.agent.analyze import AnalysisResult

        mocker.patch("app.config.settings.finnhub_api_key", "test-key")
        analyzer, mock_db, price, _ = self._make_analyzer(mocker)

        result = analyzer.analyze("AAPL", mock_db)

        assert isinstance(result, AnalysisResult)
        assert result.ticker == "AAPL"
        assert result.prediction.signal == "BUY"
        assert result.prediction.confidence == 0.75

    def test_prediction_stored_in_db(self, mocker):
        mocker.patch("app.config.settings.finnhub_api_key", "test-key")
        analyzer, mock_db, _, _ = self._make_analyzer(mocker)

        analyzer.analyze("AAPL", mock_db)

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called()

    def test_news_failure_is_nonfatal(self, mocker):
        from app.agent.analyze import StockAnalyzer, AnalysisResult
        from app.llm.client import EMBEDDING_DIM

        mocker.patch("app.config.settings.finnhub_api_key", "test-key")

        mock_news_fetcher = MagicMock()
        mock_news_fetcher.fetch_and_store.side_effect = Exception("Finnhub down")

        mock_llm = MagicMock()
        mock_llm.complete.return_value = VALID_LLM_JSON

        mock_embedder = MagicMock()
        mock_embedder.embed.return_value = [0.1] * EMBEDDING_DIM

        mock_price_fetcher = MagicMock()
        mock_price_fetcher.fetch.return_value = _make_price_snapshot()

        mock_db = MagicMock()
        mock_db.execute.return_value = MagicMock(fetchall=MagicMock(return_value=[]))

        analyzer = StockAnalyzer(
            price_fetcher=mock_price_fetcher,
            news_fetcher=mock_news_fetcher,
            llm_client=mock_llm,
            embedding_client=mock_embedder,
        )
        result = analyzer.analyze("AAPL", mock_db)
        # Should still produce a prediction
        assert result.prediction.signal == "BUY"
        assert result.news == []

    def test_llm_parse_failure_raises(self, mocker):
        from app.agent.analyze import StockAnalyzer

        mocker.patch("app.config.settings.finnhub_api_key", "")

        mock_price_fetcher = MagicMock()
        mock_price_fetcher.fetch.return_value = _make_price_snapshot()

        mock_news_fetcher = MagicMock()
        mock_news_fetcher.fetch.return_value = []

        mock_llm = MagicMock()
        mock_llm.complete.return_value = "I cannot recommend anything."  # invalid JSON

        mock_embedder = MagicMock()
        mock_embedder.embed.return_value = [0.0] * 1024

        mock_db = MagicMock()
        mock_db.execute.return_value = MagicMock(fetchall=MagicMock(return_value=[]))

        analyzer = StockAnalyzer(
            price_fetcher=mock_price_fetcher,
            news_fetcher=mock_news_fetcher,
            llm_client=mock_llm,
            embedding_client=mock_embedder,
        )
        with pytest.raises(ValueError, match="No JSON object"):
            analyzer.analyze("AAPL", mock_db)


# ---------------------------------------------------------------------------
# Prediction API endpoints
# ---------------------------------------------------------------------------

class TestPredictionEndpoints:
    def _mock_analyzer_result(self, mocker, signal: str = "BUY"):
        """Patch StockAnalyzer.analyze to return a canned AnalysisResult."""
        from app.agent.analyze import AnalysisResult
        from app.llm.client import EMBEDDING_DIM

        price = _make_price_snapshot("AAPL")
        prediction = PredictionOutput(
            signal=signal, confidence=0.75,
            reasoning="Strong technicals support this call.",
            key_factors=["RSI moderate", "MACD bullish", "Volume surge"],
        )
        result = AnalysisResult(
            prediction_id=uuid.uuid4(),
            ticker="AAPL",
            prediction=prediction,
            price=price,
            news=[],
            memories_used=[],
            resolve_after=datetime.now(timezone.utc),
        )
        mocker.patch("app.api.predictions.StockAnalyzer.analyze", return_value=result)
        return result

    def test_analyze_endpoint_returns_200(self, mocker):
        from fastapi.testclient import TestClient
        from app.main import app

        self._mock_analyzer_result(mocker)
        mocker.patch("app.api.predictions.get_db", return_value=MagicMock())

        client = TestClient(app)
        response = client.post("/analyze/AAPL")
        assert response.status_code == 200
        data = response.json()
        assert data["signal"] == "BUY"
        assert data["ticker"] == "AAPL"
        assert 0 <= data["confidence"] <= 1

    def test_analyze_returns_502_on_runtime_error(self, mocker):
        from fastapi.testclient import TestClient
        from app.main import app

        mocker.patch(
            "app.api.predictions.StockAnalyzer.analyze",
            side_effect=RuntimeError("NIM API down"),
        )
        mocker.patch("app.api.predictions.get_db", return_value=MagicMock())

        client = TestClient(app)
        response = client.post("/analyze/AAPL")
        assert response.status_code == 502

    def test_list_predictions_returns_list(self, mocker):
        from fastapi.testclient import TestClient
        from app.main import app

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = []
        mock_db.query.return_value = mock_query
        mocker.patch("app.api.predictions.get_db", return_value=mock_db)

        client = TestClient(app)
        response = client.get("/predictions/AAPL")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_prediction_by_invalid_uuid(self, mocker):
        from fastapi.testclient import TestClient
        from app.main import app

        mocker.patch("app.api.predictions.get_db", return_value=MagicMock())

        client = TestClient(app)
        response = client.get("/predictions/id/not-a-uuid")
        assert response.status_code == 400

    def test_get_prediction_not_found(self, mocker):
        from fastapi.testclient import TestClient
        from app.main import app

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mocker.patch("app.api.predictions.get_db", return_value=mock_db)

        client = TestClient(app)
        pred_id = str(uuid.uuid4())
        response = client.get(f"/predictions/id/{pred_id}")
        assert response.status_code == 404
