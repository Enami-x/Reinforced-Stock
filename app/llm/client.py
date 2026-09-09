"""
Nemotron LLM and embedding client via NVIDIA NIM (OpenAI-compatible API).

Both the completion model (for predictions) and the embedding model
(for pgvector memory) use the same NIM base URL and API key.

Retry policy
------------
- Up to 3 attempts with exponential backoff (1s, 2s, 4s)
- Retries on: rate limit (429), server error (5xx), timeout
- Raises RuntimeError after all retries exhausted

Timeout
-------
- LLM completions: 60s (Nemotron-70B can be slow on first token)
- Embeddings: 30s
"""

from __future__ import annotations

import logging
import time
from typing import Any

from openai import APIStatusError, APITimeoutError, OpenAI, RateLimitError

from app.config import settings

logger = logging.getLogger(__name__)

# Retry configuration
_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0   # seconds

# Embedding dimension for nvidia/nemotron-3-embed-1b
EMBEDDING_DIM = 2048


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _should_retry(exc: Exception) -> bool:
    """Return True if the exception is transient and worth retrying."""
    if isinstance(exc, RateLimitError):
        return True
    if isinstance(exc, APITimeoutError):
        return True
    if isinstance(exc, APIStatusError) and exc.status_code >= 500:
        return True
    return False


def _with_retry(fn, *args, **kwargs) -> Any:
    """Call fn with exponential-backoff retry on transient errors."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if not _should_retry(exc):
                raise
            wait = _BACKOFF_BASE * (2 ** attempt)
            logger.warning(
                "NIM API error (attempt %d/%d): %s — retrying in %.1fs",
                attempt + 1, _MAX_RETRIES, exc, wait,
            )
            time.sleep(wait)
            last_exc = exc
    raise RuntimeError(
        f"NIM API call failed after {_MAX_RETRIES} attempts"
    ) from last_exc


# ---------------------------------------------------------------------------
# LLM Client (completions)
# ---------------------------------------------------------------------------


class LLMClient:
    """
    Thin wrapper around the NIM OpenAI-compatible completions endpoint.

    Usage:
        client = LLMClient()
        response_text = client.complete(prompt_messages)
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self._model = model or settings.nim_llm_model
        self._client = OpenAI(
            api_key=api_key or settings.nim_api_key,
            base_url=base_url or settings.nim_base_url,
            timeout=60.0,
            max_retries=0,   # we handle retries ourselves
        )

    def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        """
        Send a chat-completion request and return the response text.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            temperature: Sampling temperature (low = more deterministic).
            max_tokens: Maximum tokens in the response.

        Returns:
            The assistant's response text.

        Raises:
            RuntimeError: After all retries are exhausted.
            ValueError: If the API returns an empty response.
        """
        logger.debug("Calling NIM LLM (model=%s, messages=%d)", self._model, len(messages))

        def _call():
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response

        response = _with_retry(_call)

        content = response.choices[0].message.content
        if not content:
            raise ValueError("NIM LLM returned an empty response.")

        logger.debug(
            "NIM LLM response received (%d chars, finish_reason=%s)",
            len(content),
            response.choices[0].finish_reason,
        )
        return content


# ---------------------------------------------------------------------------
# Embedding Client
# ---------------------------------------------------------------------------


class EmbeddingClient:
    """
    Thin wrapper around the NIM OpenAI-compatible embeddings endpoint.

    Usage:
        client = EmbeddingClient()
        vector = client.embed("some text to embed")
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self._model = model or settings.nim_embedding_model
        self._client = OpenAI(
            api_key=api_key or settings.nim_api_key,
            base_url=base_url or settings.nim_base_url,
            timeout=30.0,
            max_retries=0,
        )

    def embed(self, text: str) -> list[float]:
        """
        Embed a text string and return the dense vector.

        Args:
            text: The text to embed (will be truncated to ~8192 tokens by NIM).

        Returns:
            List of floats of length EMBEDDING_DIM (1024).

        Raises:
            RuntimeError: After all retries exhausted.
            ValueError: If the returned vector has unexpected dimensions.
        """
        if not text.strip():
            logger.warning("Embedding called with empty text — returning zero vector")
            return [0.0] * EMBEDDING_DIM

        logger.debug("Embedding text (%d chars) via NIM", len(text))

        def _call():
            response = self._client.embeddings.create(
                model=self._model,
                input=text,
                encoding_format="float",
            )
            return response

        response = _with_retry(_call)

        vector = response.data[0].embedding
        if len(vector) != EMBEDDING_DIM:
            logger.warning(
                "Unexpected embedding dimension: got %d, expected %d",
                len(vector), EMBEDDING_DIM,
            )
        return vector
