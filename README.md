# Stock Insight Agent

An autonomous LLM-powered stock analysis agent that generates **BUY / HOLD / SELL** signals with structured reasoning, then closes the loop by tracking whether its past calls were right or wrong — feeding that history back into future predictions via **pgvector semantic memory**.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     FastAPI App                         │
│                                                         │
│  POST /analyze/{ticker}  ──►  StockAnalyzer             │
│                                    │                    │
│  GET /scheduler/status             ▼                    │
│  POST /scheduler/trigger-scan  ┌───────────┐            │
│                                │ 1. Price  │ yfinance   │
│  GET /accuracy                 │    Data   │            │
│  GET /accuracy/{ticker}        └─────┬─────┘            │
│                                      │                  │
│  GET /logs/recent              ┌─────▼─────┐            │
│                                │ 2. News   │ Finnhub    │
│  APScheduler (background)      └─────┬─────┘            │
│  ├─ Watchlist scan (4h, NYSE)        │                  │
│  ├─ News poll (15min)          ┌─────▼─────┐            │
│  └─ Resolution (daily 22 UTC)  │ 3. Memory │ pgvector   │
│                                │ Retrieval │            │
│                                └─────┬─────┘            │
│                                      │                  │
│                                ┌─────▼─────┐            │
│                                │ 4. LLM    │ Nemotron   │
│                                │ Prediction│ (NIM)      │
│                                └─────┬─────┘            │
│                                      │                  │
│                                ┌─────▼─────┐            │
│                                │ 5. Store  │ Postgres   │
│                                │ + Embed   │ +pgvector  │
│                                └───────────┘            │
└─────────────────────────────────────────────────────────┘
```

---

## Quick Start

### 1. Prerequisites

- Docker Desktop running
- Python 3.12+
- NVIDIA NIM API key → [build.nvidia.com](https://build.nvidia.com)
- Finnhub API key (free) → [finnhub.io](https://finnhub.io)

### 2. Start the database

```bash
docker run --name stock-db \
  -e POSTGRES_USER=stock_agent \
  -e POSTGRES_PASSWORD=stock_secret \
  -e POSTGRES_DB=stock_insights \
  -p 5432:5432 -d pgvector/pgvector:pg16
```

### 3. Configure environment

```bash
copy .env.example .env
# Edit .env — fill in NIM_API_KEY and FINNHUB_API_KEY
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Apply database migrations

```bash
python -m alembic upgrade head
```

### 6. Start the server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Visit **http://localhost:8000/docs** for the interactive API docs.

---

## API Reference

### Predictions

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/analyze/{ticker}` | Run full analysis pipeline → BUY/HOLD/SELL |
| `GET` | `/predictions/{ticker}` | List past predictions for a ticker |
| `GET` | `/predictions/id/{id}` | Full detail for a single prediction |

**Example:**
```bash
curl -X POST http://localhost:8000/analyze/AAPL | python -m json.tool
```

```json
{
  "prediction_id": "3f8e2a1c-...",
  "ticker": "AAPL",
  "signal": "BUY",
  "confidence": 0.73,
  "reasoning": "RSI at 52 shows room to run. MACD just crossed bullish...",
  "key_factors": ["Bullish MACD crossover", "Volume 1.4x average", "Positive earnings news"],
  "resolve_after": "2026-09-16T...",
  "price_at_analysis": 185.0,
  "news_count": 4,
  "memory_count": 3
}
```

### Data Inspection

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/data/snapshot/{ticker}` | Price + news snapshot (no LLM call) |

### Accuracy & Resolution

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/accuracy` | Overall accuracy stats across all predictions |
| `GET` | `/accuracy/{ticker}` | Per-ticker accuracy breakdown |
| `POST` | `/resolution/resolve-one/{id}` | Force-resolve a prediction immediately |

**Example:**
```bash
curl http://localhost:8000/accuracy | python -m json.tool
```

```json
{
  "total_predictions": 42,
  "resolved": 35,
  "correct": 26,
  "overall_accuracy_pct": 74.3,
  "by_signal": {
    "BUY":  {"resolved": 18, "correct": 14, "accuracy_pct": 77.8},
    "HOLD": {"resolved": 10, "correct": 8,  "accuracy_pct": 80.0},
    "SELL": {"resolved": 7,  "correct": 4,  "accuracy_pct": 57.1}
  }
}
```

### Scheduler

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/scheduler/status` | Job list + next-run times + market hours flag |
| `POST` | `/scheduler/trigger-scan` | Manually trigger a full watchlist scan |

### Observability

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Liveness probe |
| `GET` | `/status` | Readiness probe (DB + API keys check) |
| `GET` | `/logs/recent?n=50` | Last N in-memory log entries |

---

## How the Self-Improvement Loop Works

```
Prediction stored ──► resolve_after (7 calendar days)
                            │
                    Daily resolution job
                            │
                    Fetch current price
                            │
                    Apply correctness rule:
                      BUY  → price > +2% = ✓
                      SELL → price < -2% = ✓
                      HOLD → |price| ≤ 2% = ✓
                            │
                    Mark correct/incorrect in DB
                            │
          Next analysis for same ticker
                            │
                    pgvector retrieves top-K
                    similar past predictions,
                    INCORRECT ones boosted 1.15x
                            │
                    LLM sees: "⚠ LEARN FROM THIS MISTAKE"
                    context before making new call
```

---

## Scheduler Behaviour

| Job | Trigger | Market Hours Gate |
|-----|---------|-------------------|
| Watchlist scan | Every 4h | Yes — skips outside NYSE hours |
| News poll | Every 15min | No — runs 24/7 |
| Resolution | Daily 22:00 UTC | No |

Configure intervals in `.env`:
```bash
SCAN_INTERVAL_MINUTES=240
NEWS_POLL_INTERVAL_MINUTES=15
RESOLUTION_HOUR_UTC=22
```

---

## Technical Indicators Computed

| Indicator | Window |
|-----------|--------|
| RSI | 14-day |
| MACD | 12/26/9 |
| Bollinger Bands | 20-day, 2σ |
| SMA | 50-day, 200-day |
| Volume ratio | vs 20-day avg |
| 52-week high/low distance | — |
| ATR | 14-day |

---

## Project Structure

```
app/
├── main.py              # FastAPI entry point, lifespan, router registration
├── config.py            # Pydantic-settings config (all from .env)
├── logging_config.py    # Structured logging + in-memory ring buffer
├── api/
│   ├── data.py          # GET /data/snapshot/{ticker}
│   ├── predictions.py   # POST /analyze, GET /predictions/...
│   ├── scheduler.py     # GET /scheduler/status, POST /scheduler/trigger-scan
│   ├── accuracy.py      # GET /accuracy, POST /resolution/resolve-one
│   └── observability.py # GET /logs/recent
├── agent/
│   └── analyze.py       # 8-step analysis orchestrator
├── data/
│   ├── price.py         # yfinance + technical indicators
│   └── news.py          # Finnhub news with DB dedup
├── llm/
│   ├── client.py        # NIM LLMClient + EmbeddingClient (with retry)
│   └── prompt.py        # Prompt builder + PredictionOutput schema
├── memory/
│   └── retrieval.py     # pgvector cosine search + incorrect-boost re-rank
├── resolution/
│   └── resolver.py      # Prediction grading + correctness rules
├── scheduler/
│   └── jobs.py          # APScheduler: watchlist scan, news poll, resolution
└── db/
    ├── engine.py         # SQLAlchemy engine + session factory
    └── models.py         # ORM: predictions, news_events, price_snapshots

tests/
├── test_db.py           # DB connection + model tests (Stage 1)
├── test_price.py        # Price fetcher + indicators (Stage 2)
├── test_news.py         # News fetcher + dedup (Stage 2)
├── test_stage3.py       # LLM, memory, analyzer, prediction API (Stage 3)
└── test_stages456.py    # Scheduler, resolver, accuracy, observability (Stages 4-6)
```

---

## Running Tests

```bash
python -m pytest tests/ -v
# 129 tests, all offline (mocked LLM/yfinance/Finnhub)
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://...` | Postgres connection string |
| `NIM_API_KEY` | *(required)* | NVIDIA NIM API key |
| `NIM_BASE_URL` | `https://integrate.api.nvidia.com/v1` | NIM endpoint |
| `NIM_LLM_MODEL` | `meta/llama-3.2-11b-vision-instruct` | LLM model |
| `NIM_EMBEDDING_MODEL` | `nvidia/nemotron-3-embed-1b` | Embedding model (2048-dim) |
| `FINNHUB_API_KEY` | *(required)* | Finnhub API key |
| `WATCHLIST` | `AAPL,MSFT,TSLA,NVDA,GOOGL` | Comma-separated tickers |
| `SCAN_INTERVAL_MINUTES` | `240` | Watchlist scan frequency |
| `NEWS_POLL_INTERVAL_MINUTES` | `15` | News poll frequency |
| `RESOLUTION_HORIZON_DAYS` | `5` | Trading days before resolution |
| `CORRECTNESS_THRESHOLD_PCT` | `2.0` | % move to count as correct |
| `MEMORY_TOP_K` | `5` | Past predictions to retrieve |
| `NEWS_LOOKBACK_HOURS` | `24` | Finnhub news window |
| `RESOLUTION_HOUR_UTC` | `22` | Daily resolution job hour |
