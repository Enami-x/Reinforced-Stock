"""
LangChain-based prompt builder for the stock insight agent.

The prompt is structured as a two-message conversation:
  - system: persona + output format instructions
  - human:  ticker data + memory context + instruction to predict

The LLM is asked to respond with a JSON object ONLY, no prose wrapper.
We parse and validate this JSON into a PredictionOutput Pydantic model.

Output schema (what the LLM must return):
    {
        "signal":      "BUY" | "HOLD" | "SELL",
        "confidence":  0.0 – 1.0,
        "reasoning":   "...",        // 2-4 sentence explanation
        "key_factors": ["...", ...]  // 3-5 bullet-point drivers
    }
"""

from __future__ import annotations

import json
import logging
import re
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field, field_validator

from app.data.news import NewsItem
from app.data.price import PriceSnapshot
from app.memory.retrieval import RetrievedMemory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output schema (parsed from LLM JSON response)
# ---------------------------------------------------------------------------


class PredictionOutput(BaseModel):
    """Validated prediction output from the LLM."""

    signal: Literal["BUY", "HOLD", "SELL"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(min_length=10)
    key_factors: list[str] = Field(min_length=1)

    @field_validator("signal", mode="before")
    @classmethod
    def normalise_signal(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("key_factors", mode="before")
    @classmethod
    def ensure_list(cls, v) -> list:
        if isinstance(v, str):
            return [v]
        return list(v)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert quantitative stock analyst. Your role is to analyse technical \
and news data for a given stock and produce a structured investment signal.

IMPORTANT RULES:
1. You NEVER recommend actual trades. Your output is for informational purposes only.
2. You must respond with a single JSON object — no explanation before or after.
3. Be intellectually honest about uncertainty. Use low confidence when signals conflict.
4. Learn from past incorrect predictions shown in memory. Do NOT repeat the same mistakes.
5. HOLD is a valid and often correct signal — do not force BUY/SELL.

OUTPUT FORMAT (strict JSON, no markdown code block):
{
    "signal":      "BUY" | "HOLD" | "SELL",
    "confidence":  <float 0.0–1.0>,
    "reasoning":   "<2–4 sentence explanation of the signal>",
    "key_factors": ["<factor 1>", "<factor 2>", "<factor 3>"]
}

Confidence guide:
  0.8–1.0: Very strong, multiple confirming signals
  0.6–0.8: Moderate confidence
  0.4–0.6: Weak, mixed signals
  0.0–0.4: Very uncertain, mostly noise
"""

# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


class PredictionPromptBuilder:
    """
    Builds the two-message chat prompt for a prediction call.

    Usage:
        builder = PredictionPromptBuilder()
        messages = builder.build(ticker, price_snapshot, news_items, memories)
        raw_json = llm_client.complete(messages)
        prediction = PredictionPromptBuilder.parse_response(raw_json)
    """

    def build(
        self,
        ticker: str,
        price: PriceSnapshot,
        news: list[NewsItem],
        memories: list[RetrievedMemory],
    ) -> list[dict[str, str]]:
        """
        Build the messages list ready for LLMClient.complete().

        Returns:
            [{"role": "system", "content": ...}, {"role": "user", "content": ...}]
        """
        human_content = self._build_human_message(ticker, price, news, memories)
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": human_content},
        ]

    def build_snapshot_text(
        self,
        ticker: str,
        price: PriceSnapshot,
        news: list[NewsItem],
    ) -> str:
        """
        Build a text-only representation of the snapshot for embedding.
        This is what gets embedded and stored as the prediction's vector.
        """
        return self._format_price_section(ticker, price) + "\n" + self._format_news_section(news)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_human_message(
        self,
        ticker: str,
        price: PriceSnapshot,
        news: list[NewsItem],
        memories: list[RetrievedMemory],
    ) -> str:
        sections = [
            f"## Stock Analysis Request: {ticker}",
            "",
            self._format_price_section(ticker, price),
            "",
            self._format_news_section(news),
        ]

        if memories:
            from app.memory.retrieval import MemoryRetriever
            memory_block = MemoryRetriever.format_context(memories)
            sections += ["", memory_block]

        sections += [
            "",
            "---",
            f"Based on the above data and memory context, provide your investment signal "
            f"for {ticker}. Remember: respond with the JSON object ONLY.",
        ]

        return "\n".join(sections)

    @staticmethod
    def _format_price_section(ticker: str, price: PriceSnapshot) -> str:
        ind = price.indicators
        lines = [
            f"### Price Data — {ticker}",
            f"Current price:  ${price.current_price:,.2f}",
            f"Today OHLV:     O=${price.open_price:.2f}  H=${price.high_price:.2f}  "
            f"L=${price.low_price:.2f}  Vol={price.volume:,}",
            f"Recent closes (5d): {' → '.join(f'${c:.2f}' for c in price.recent_closes)}",
            "",
            "#### Technical Indicators",
            f"RSI(14):          {ind.rsi_14 or 'N/A'}",
            f"MACD line:        {ind.macd_line or 'N/A'}",
            f"MACD signal:      {ind.macd_signal or 'N/A'}",
            f"MACD histogram:   {ind.macd_histogram or 'N/A'}",
            f"BB upper:         {ind.bb_upper or 'N/A'}",
            f"BB middle:        {ind.bb_middle or 'N/A'}",
            f"BB lower:         {ind.bb_lower or 'N/A'}",
            f"BB %B:            {ind.bb_pct_b or 'N/A'}",
            f"SMA 50:           {ind.sma_50 or 'N/A'}",
            f"SMA 200:          {ind.sma_200 or 'N/A'}",
            f"Volume ratio:     {ind.volume_ratio or 'N/A'}x (vs 20-day avg)",
            f"52w High:         ${ind.week_52_high or 'N/A'}  "
            f"({ind.pct_from_52w_high or 'N/A'}% from high)",
            f"52w Low:          ${ind.week_52_low or 'N/A'}  "
            f"({ind.pct_from_52w_low or 'N/A'}% from low)",
            f"ATR(14):          {ind.atr_14 or 'N/A'}",
        ]
        if price.pe_ratio:
            lines.append(f"P/E ratio:        {price.pe_ratio:.1f}")
        if price.market_cap:
            lines.append(f"Market cap:       ${price.market_cap / 1e9:.1f}B")
        return "\n".join(lines)

    @staticmethod
    def _format_news_section(news: list[NewsItem]) -> str:
        if not news:
            return "### Recent News\nNo recent news available."

        lines = [f"### Recent News ({len(news)} articles)"]
        for item in news[:10]:  # cap at 10 to stay within token budget
            lines.append(item.to_prompt_str())
        return "\n".join(lines)

    @staticmethod
    def parse_response(raw: str) -> PredictionOutput:
        """
        Parse and validate the LLM's JSON response into a PredictionOutput.

        Handles common LLM quirks:
        - JSON wrapped in markdown code blocks
        - Trailing commas (via regex pre-clean)
        - Extra prose before/after the JSON object

        Raises:
            ValueError: If the response cannot be parsed into a valid prediction.
        """
        # Strip markdown code block if present
        cleaned = re.sub(r"```(?:json)?\s*", "", raw, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()

        # Extract the JSON object (first { ... } block)
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON object found in LLM response: {raw[:200]!r}")

        json_str = match.group(0)

        # Remove trailing commas before } or ] (common LLM mistake)
        json_str = re.sub(r",\s*([}\]])", r"\1", json_str)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Failed to parse LLM JSON response: {exc}\nRaw: {json_str[:300]!r}"
            ) from exc

        try:
            return PredictionOutput(**data)
        except Exception as exc:
            raise ValueError(
                f"LLM response failed validation: {exc}\nData: {data}"
            ) from exc
