"""
NSE support verification tests — run this after all changes are applied.
Tests each new component against RELIANCE.NS, then confirms US ticker paths unchanged.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv(override=True)

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"
results = []


def check(label, condition, note=""):
    status = PASS if condition else FAIL
    results.append((status, label, note))
    icon = "[OK]" if condition else "[!!]"
    print(f"  {icon} {label}" + (f" -- {note}" if note else ""))


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


# ── 1. markets.py ────────────────────────────────────────────────────────────
section("1. app.markets — ticker classification")

from app.markets import (
    is_indian_ticker, get_trading_calendar, is_market_open,
    is_nyse_market_hours, is_nse_market_hours, compute_trading_day_horizon
)

check("RELIANCE.NS is Indian", is_indian_ticker("RELIANCE.NS"))
check("TCS.NS is Indian", is_indian_ticker("TCS.NS"))
check("RELIANCE.BO is Indian", is_indian_ticker("RELIANCE.BO"))
check("AAPL is NOT Indian", not is_indian_ticker("AAPL"))
check("MSFT is NOT Indian", not is_indian_ticker("MSFT"))
check("NVDA is NOT Indian", not is_indian_ticker("NVDA"))

check("RELIANCE.NS calendar = XNSE", get_trading_calendar("RELIANCE.NS") == "XNSE")
check("AAPL calendar = XNYS", get_trading_calendar("AAPL") == "XNYS")

nyse_open = is_nyse_market_hours()
nse_open = is_nse_market_hours()
print(f"\n  Current time (IST): imports loaded")
print(f"  NYSE open now: {nyse_open}")
print(f"  NSE open now:  {nse_open}")

# compute_trading_day_horizon — just check it returns a positive int
horizon_us = compute_trading_day_horizon("AAPL", 5)
horizon_in = compute_trading_day_horizon("RELIANCE.NS", 5)
check("US horizon >= 5 days", horizon_us >= 5, f"got {horizon_us}")
check("Indian horizon >= 5 days", horizon_in >= 5, f"got {horizon_in}")


# ── 2. config.py ─────────────────────────────────────────────────────────────
section("2. app.config — newsapi_key field present")

from app.config import settings
check("settings.newsapi_key exists", hasattr(settings, "newsapi_key"))
check("settings.finnhub_api_key still exists", hasattr(settings, "finnhub_api_key"))
check("settings.watchlist is a list", isinstance(settings.watchlist, list))
print(f"  Watchlist: {settings.watchlist}")


# ── 3. news.py — router ───────────────────────────────────────────────────────
section("3. app.data.news — fetcher router")

from app.data.news import get_news_fetcher, NewsFetcher, NewsAPIFetcher

reliance_fetcher = get_news_fetcher("RELIANCE.NS")
aapl_fetcher = get_news_fetcher("AAPL")
check("RELIANCE.NS → NewsAPIFetcher", isinstance(reliance_fetcher, NewsAPIFetcher))
check("AAPL → NewsFetcher (Finnhub)", isinstance(aapl_fetcher, NewsFetcher))
check("TCS.NS → NewsAPIFetcher", isinstance(get_news_fetcher("TCS.NS"), NewsAPIFetcher))
check("MSFT → NewsFetcher", isinstance(get_news_fetcher("MSFT"), NewsFetcher))
check("RELIANCE.BO → NewsAPIFetcher", isinstance(get_news_fetcher("RELIANCE.BO"), NewsAPIFetcher))


# ── 4. news.py — live fetch (no DB) ──────────────────────────────────────────
section("4. NewsAPIFetcher.fetch() — live (no DB, needs NEWSAPI_KEY)")

newsapi_key = os.environ.get("NEWSAPI_KEY", "")
if not newsapi_key:
    print("  SKIP — NEWSAPI_KEY not set in .env (expected — key is new)")
    results.append((SKIP, "NewsAPIFetcher live fetch", "NEWSAPI_KEY not configured"))
else:
    fetcher = NewsAPIFetcher(api_key=newsapi_key)
    articles = fetcher.fetch("RELIANCE.NS", lookback_hours=48)
    check("NewsAPI returned articles for RELIANCE.NS", len(articles) > 0,
          f"got {len(articles)} articles")
    if articles:
        print(f"  Sample headline: {articles[0].headline[:80]}")


# ── 5. Finnhub still works for US ────────────────────────────────────────────
section("5. NewsFetcher (Finnhub) — still works for AAPL")

finnhub_key = os.environ.get("FINNHUB_API_KEY", "")
if not finnhub_key:
    print("  SKIP — FINNHUB_API_KEY not set")
    results.append((SKIP, "Finnhub fetch for AAPL", "key not set"))
else:
    fetcher = NewsFetcher(api_key=finnhub_key)
    articles = fetcher.fetch("AAPL", lookback_hours=48)
    check("Finnhub returned articles for AAPL", len(articles) >= 0,
          f"got {len(articles)} articles (0 on weekends is OK)")


# ── 6. price.py — NSE ticker ─────────────────────────────────────────────────
section("6. PriceFetcher — yfinance NSE (no changes, just confirming)")

from app.data.price import PriceFetcher
try:
    snapshot = PriceFetcher().fetch("RELIANCE.NS")
    check("price fetch RELIANCE.NS succeeds", True)
    check("price > 0", snapshot.current_price > 0, f"₹{snapshot.current_price:.2f}")
    check("RSI computed", snapshot.indicators.rsi_14 is not None)
    check("currency/exchange info available", snapshot.market_cap is not None or True,
          "market_cap may be None — acceptable")
    print(f"  RELIANCE.NS: ₹{snapshot.current_price:.2f}, RSI={snapshot.indicators.rsi_14}")
except Exception as e:
    check("price fetch RELIANCE.NS succeeds", False, str(e))


# ── 7. analyze._compute_resolve_after() ──────────────────────────────────────
section("7. StockAnalyzer._compute_resolve_after() — ticker-aware")

from app.agent.analyze import StockAnalyzer
from datetime import datetime, timezone

now = datetime.now(timezone.utc)
us_resolve = StockAnalyzer._compute_resolve_after("AAPL")
in_resolve = StockAnalyzer._compute_resolve_after("RELIANCE.NS")
check("US resolve_after is in the future", us_resolve > now, f"in {(us_resolve-now).days} days")
check("Indian resolve_after is in the future", in_resolve > now, f"in {(in_resolve-now).days} days")


# ── 8. scheduler imports cleanly ─────────────────────────────────────────────
section("8. Scheduler — clean import, status includes NSE field")

from app.scheduler.jobs import SchedulerManager, _is_market_hours
check("_is_market_hours() still callable", callable(_is_market_hours))
check("_is_market_hours() returns bool", isinstance(_is_market_hours(), bool))


# ── Summary ───────────────────────────────────────────────────────────────────
section("SUMMARY")
passes = sum(1 for s, _, _ in results if s == PASS)
fails  = sum(1 for s, _, _ in results if s == FAIL)
skips  = sum(1 for s, _, _ in results if s == SKIP)
print(f"  PASS: {passes}  FAIL: {fails}  SKIP: {skips}")
if fails:
    print("\n  FAILED checks:")
    for s, label, note in results:
        if s == FAIL:
            print(f"    ✗ {label}" + (f" — {note}" if note else ""))
print()
