"""
Watchlist management API.

GET  /watchlist                  Return the user's current watchlist (from DB)
POST /watchlist/{ticker}         Add a ticker to the watchlist
DELETE /watchlist/{ticker}       Remove a ticker from the watchlist
GET  /watchlist/available        Return the full curated catalog of tickers to pick from
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.engine import get_db
from app.db.models import WatchlistEntry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/watchlist", tags=["Watchlist"])


# ---------------------------------------------------------------------------
# Curated catalog (280+ well-known, liquid tickers across US and Indian markets)
# ---------------------------------------------------------------------------

AVAILABLE_TICKERS: list[dict[str, str]] = [
    # ── Technology ──────────────────────────────────────────────────────────
    {"ticker": "AAPL", "name": "Apple", "sector": "Technology", "market": "US"},
    {"ticker": "MSFT", "name": "Microsoft", "sector": "Technology", "market": "US"},
    {"ticker": "GOOGL", "name": "Alphabet (Google)", "sector": "Technology", "market": "US"},
    {"ticker": "META", "name": "Meta Platforms", "sector": "Technology", "market": "US"},
    {"ticker": "AMZN", "name": "Amazon", "sector": "Technology", "market": "US"},
    {"ticker": "NVDA", "name": "NVIDIA", "sector": "Technology", "market": "US"},
    {"ticker": "AMD", "name": "Advanced Micro Devices", "sector": "Technology", "market": "US"},
    {"ticker": "INTC", "name": "Intel", "sector": "Technology", "market": "US"},
    {"ticker": "CRM", "name": "Salesforce", "sector": "Technology", "market": "US"},
    {"ticker": "ORCL", "name": "Oracle", "sector": "Technology", "market": "US"},
    {"ticker": "IBM", "name": "IBM", "sector": "Technology", "market": "US"},
    {"ticker": "ADBE", "name": "Adobe", "sector": "Technology", "market": "US"},
    {"ticker": "SNOW", "name": "Snowflake", "sector": "Technology", "market": "US"},
    {"ticker": "PLTR", "name": "Palantir", "sector": "Technology", "market": "US"},
    {"ticker": "CSCO", "name": "Cisco Systems", "sector": "Technology", "market": "US"},
    {"ticker": "NOW", "name": "ServiceNow", "sector": "Technology", "market": "US"},
    {"ticker": "INTU", "name": "Intuit", "sector": "Technology", "market": "US"},
    {"ticker": "PANW", "name": "Palo Alto Networks", "sector": "Technology", "market": "US"},
    {"ticker": "FTNT", "name": "Fortinet", "sector": "Technology", "market": "US"},
    {"ticker": "DELL", "name": "Dell Technologies", "sector": "Technology", "market": "US"},
    {"ticker": "HPQ", "name": "HP Inc.", "sector": "Technology", "market": "US"},
    {"ticker": "TCS.NS", "name": "Tata Consultancy Services", "sector": "Technology", "market": "NSE"},
    {"ticker": "INFY.NS", "name": "Infosys", "sector": "Technology", "market": "NSE"},
    {"ticker": "WIPRO.NS", "name": "Wipro", "sector": "Technology", "market": "NSE"},
    {"ticker": "HCLTECH.NS", "name": "HCL Technologies", "sector": "Technology", "market": "NSE"},
    {"ticker": "TECHM.NS", "name": "Tech Mahindra", "sector": "Technology", "market": "NSE"},
    {"ticker": "PERSISTENT.NS", "name": "Persistent Systems", "sector": "Technology", "market": "NSE"},
    {"ticker": "COFORGE.NS", "name": "Coforge", "sector": "Technology", "market": "NSE"},
    {"ticker": "MPHASIS.NS", "name": "Mphasis", "sector": "Technology", "market": "NSE"},
    {"ticker": "KPITTECH.NS", "name": "KPIT Technologies", "sector": "Technology", "market": "NSE"},
    {"ticker": "TATAELXSI.NS", "name": "Tata Elxsi", "sector": "Technology", "market": "NSE"},
    {"ticker": "NAUKRI.NS", "name": "Info Edge (Naukri)", "sector": "Technology", "market": "NSE"},
    {"ticker": "PAYTM.NS", "name": "One97 Communications (Paytm)", "sector": "Technology", "market": "NSE"},
    {"ticker": "POLICYBZR.NS", "name": "PB Fintech (Policybazaar)", "sector": "Technology", "market": "NSE"},
    {"ticker": "TCS.BO", "name": "Tata Consultancy Services (BSE)", "sector": "Technology", "market": "BSE"},
    {"ticker": "WIPRO.BO", "name": "Wipro (BSE)", "sector": "Technology", "market": "BSE"},
    {"ticker": "HCLTECH.BO", "name": "HCL Technologies (BSE)", "sector": "Technology", "market": "BSE"},
    # ── Semiconductors ──────────────────────────────────────────────────────
    {"ticker": "QCOM", "name": "Qualcomm", "sector": "Semiconductors", "market": "US"},
    {"ticker": "AVGO", "name": "Broadcom", "sector": "Semiconductors", "market": "US"},
    {"ticker": "MU", "name": "Micron Technology", "sector": "Semiconductors", "market": "US"},
    {"ticker": "ASML", "name": "ASML Holding", "sector": "Semiconductors", "market": "US"},
    {"ticker": "AMAT", "name": "Applied Materials", "sector": "Semiconductors", "market": "US"},
    {"ticker": "LRCX", "name": "Lam Research", "sector": "Semiconductors", "market": "US"},
    {"ticker": "KLAC", "name": "KLA Corp", "sector": "Semiconductors", "market": "US"},
    {"ticker": "MRVL", "name": "Marvell Technology", "sector": "Semiconductors", "market": "US"},
    {"ticker": "ARM", "name": "ARM Holdings", "sector": "Semiconductors", "market": "US"},
    {"ticker": "TXN", "name": "Texas Instruments", "sector": "Semiconductors", "market": "US"},
    {"ticker": "TSM", "name": "Taiwan Semiconductor Manufacturing (TSMC)", "sector": "Semiconductors", "market": "US"},
    # ── Cloud ───────────────────────────────────────────────────────────────
    {"ticker": "NET", "name": "Cloudflare", "sector": "Cloud", "market": "US"},
    {"ticker": "DDOG", "name": "Datadog", "sector": "Cloud", "market": "US"},
    {"ticker": "ZS", "name": "Zscaler", "sector": "Cloud", "market": "US"},
    {"ticker": "MDB", "name": "MongoDB", "sector": "Cloud", "market": "US"},
    {"ticker": "SHOP", "name": "Shopify", "sector": "Cloud", "market": "US"},
    # ── Automotive ──────────────────────────────────────────────────────────
    {"ticker": "TSLA", "name": "Tesla", "sector": "Automotive", "market": "US"},
    {"ticker": "RIVN", "name": "Rivian", "sector": "Automotive", "market": "US"},
    {"ticker": "LCID", "name": "Lucid Group", "sector": "Automotive", "market": "US"},
    {"ticker": "F", "name": "Ford", "sector": "Automotive", "market": "US"},
    {"ticker": "GM", "name": "General Motors", "sector": "Automotive", "market": "US"},
    {"ticker": "TM", "name": "Toyota", "sector": "Automotive", "market": "US"},
    {"ticker": "HMC", "name": "Honda Motor", "sector": "Automotive", "market": "US"},
    {"ticker": "STLA", "name": "Stellantis", "sector": "Automotive", "market": "US"},
    {"ticker": "UBER", "name": "Uber Technologies", "sector": "Automotive", "market": "US"},
    {"ticker": "LYFT", "name": "Lyft", "sector": "Automotive", "market": "US"},
    {"ticker": "MARUTI.NS", "name": "Maruti Suzuki", "sector": "Automotive", "market": "NSE"},
    {"ticker": "M&M.NS", "name": "Mahindra & Mahindra", "sector": "Automotive", "market": "NSE"},
    {"ticker": "BAJAJ-AUTO.NS", "name": "Bajaj Auto", "sector": "Automotive", "market": "NSE"},
    {"ticker": "HEROMOTOCO.NS", "name": "Hero MotoCorp", "sector": "Automotive", "market": "NSE"},
    {"ticker": "EICHERMOT.NS", "name": "Eicher Motors", "sector": "Automotive", "market": "NSE"},
    {"ticker": "TVSMOTOR.NS", "name": "TVS Motor Company", "sector": "Automotive", "market": "NSE"},
    {"ticker": "BHARATFORG.NS", "name": "Bharat Forge", "sector": "Automotive", "market": "NSE"},
    {"ticker": "MOTHERSON.NS", "name": "Samvardhana Motherson", "sector": "Automotive", "market": "NSE"},
    {"ticker": "MRF.NS", "name": "MRF Tyres", "sector": "Automotive", "market": "NSE"},
    {"ticker": "APOLLOTYRE.NS", "name": "Apollo Tyres", "sector": "Automotive", "market": "NSE"},
    {"ticker": "BALKRISIND.NS", "name": "Balkrishna Industries", "sector": "Automotive", "market": "NSE"},
    {"ticker": "MARUTI.BO", "name": "Maruti Suzuki (BSE)", "sector": "Automotive", "market": "BSE"},
    {"ticker": "BAJAJ-AUTO.BO", "name": "Bajaj Auto (BSE)", "sector": "Automotive", "market": "BSE"},
    {"ticker": "EICHERMOT.BO", "name": "Eicher Motors (BSE)", "sector": "Automotive", "market": "BSE"},
    {"ticker": "TVSMOTOR.BO", "name": "TVS Motor (BSE)", "sector": "Automotive", "market": "BSE"},
    # ── Finance ─────────────────────────────────────────────────────────────
    {"ticker": "JPM", "name": "JPMorgan Chase", "sector": "Finance", "market": "US"},
    {"ticker": "GS", "name": "Goldman Sachs", "sector": "Finance", "market": "US"},
    {"ticker": "MS", "name": "Morgan Stanley", "sector": "Finance", "market": "US"},
    {"ticker": "BAC", "name": "Bank of America", "sector": "Finance", "market": "US"},
    {"ticker": "C", "name": "Citigroup", "sector": "Finance", "market": "US"},
    {"ticker": "WFC", "name": "Wells Fargo", "sector": "Finance", "market": "US"},
    {"ticker": "V", "name": "Visa", "sector": "Finance", "market": "US"},
    {"ticker": "MA", "name": "Mastercard", "sector": "Finance", "market": "US"},
    {"ticker": "AXP", "name": "American Express", "sector": "Finance", "market": "US"},
    {"ticker": "PYPL", "name": "PayPal", "sector": "Finance", "market": "US"},
    {"ticker": "COIN", "name": "Coinbase", "sector": "Finance", "market": "US"},
    {"ticker": "HOOD", "name": "Robinhood", "sector": "Finance", "market": "US"},
    {"ticker": "BRK-B", "name": "Berkshire Hathaway", "sector": "Finance", "market": "US"},
    {"ticker": "BLK", "name": "BlackRock", "sector": "Finance", "market": "US"},
    {"ticker": "SCHW", "name": "Charles Schwab", "sector": "Finance", "market": "US"},
    {"ticker": "HDFCBANK.NS", "name": "HDFC Bank", "sector": "Finance", "market": "NSE"},
    {"ticker": "ICICIBANK.NS", "name": "ICICI Bank", "sector": "Finance", "market": "NSE"},
    {"ticker": "SBIN.NS", "name": "State Bank of India", "sector": "Finance", "market": "NSE"},
    {"ticker": "KOTAKBANK.NS", "name": "Kotak Mahindra Bank", "sector": "Finance", "market": "NSE"},
    {"ticker": "AXISBANK.NS", "name": "Axis Bank", "sector": "Finance", "market": "NSE"},
    {"ticker": "BAJFINANCE.NS", "name": "Bajaj Finance", "sector": "Finance", "market": "NSE"},
    {"ticker": "BAJAJFINSV.NS", "name": "Bajaj Finserv", "sector": "Finance", "market": "NSE"},
    {"ticker": "INDUSINDBK.NS", "name": "IndusInd Bank", "sector": "Finance", "market": "NSE"},
    {"ticker": "BANKBARODA.NS", "name": "Bank of Baroda", "sector": "Finance", "market": "NSE"},
    {"ticker": "PNB.NS", "name": "Punjab National Bank", "sector": "Finance", "market": "NSE"},
    {"ticker": "CANBK.NS", "name": "Canara Bank", "sector": "Finance", "market": "NSE"},
    {"ticker": "IDFCFIRSTB.NS", "name": "IDFC First Bank", "sector": "Finance", "market": "NSE"},
    {"ticker": "SHRIRAMFIN.NS", "name": "Shriram Finance", "sector": "Finance", "market": "NSE"},
    {"ticker": "CHOLAFIN.NS", "name": "Cholamandalam Investment", "sector": "Finance", "market": "NSE"},
    {"ticker": "MUTHOOTFIN.NS", "name": "Muthoot Finance", "sector": "Finance", "market": "NSE"},
    {"ticker": "JIOFIN.NS", "name": "Jio Financial Services", "sector": "Finance", "market": "NSE"},
    {"ticker": "SBICARD.NS", "name": "SBI Cards", "sector": "Finance", "market": "NSE"},
    {"ticker": "HDFCLIFE.NS", "name": "HDFC Life Insurance", "sector": "Finance", "market": "NSE"},
    {"ticker": "SBILIFE.NS", "name": "SBI Life Insurance", "sector": "Finance", "market": "NSE"},
    {"ticker": "ICICIPRULI.NS", "name": "ICICI Prudential Life", "sector": "Finance", "market": "NSE"},
    {"ticker": "BSE.NS", "name": "BSE Limited", "sector": "Finance", "market": "NSE"},
    {"ticker": "MCX.NS", "name": "Multi Commodity Exchange", "sector": "Finance", "market": "NSE"},
    {"ticker": "CDSL.NS", "name": "Central Depository Services", "sector": "Finance", "market": "NSE"},
    {"ticker": "IRFC.NS", "name": "Indian Railway Finance Corp", "sector": "Finance", "market": "NSE"},
    {"ticker": "AXISBANK.BO", "name": "Axis Bank (BSE)", "sector": "Finance", "market": "BSE"},
    {"ticker": "BAJAJFINSV.BO", "name": "Bajaj Finserv (BSE)", "sector": "Finance", "market": "BSE"},
    {"ticker": "MCX.BO", "name": "Multi Commodity Exchange (BSE)", "sector": "Finance", "market": "BSE"},
    # ── Healthcare ──────────────────────────────────────────────────────────
    {"ticker": "JNJ", "name": "Johnson & Johnson", "sector": "Healthcare", "market": "US"},
    {"ticker": "PFE", "name": "Pfizer", "sector": "Healthcare", "market": "US"},
    {"ticker": "MRNA", "name": "Moderna", "sector": "Healthcare", "market": "US"},
    {"ticker": "LLY", "name": "Eli Lilly", "sector": "Healthcare", "market": "US"},
    {"ticker": "ABBV", "name": "AbbVie", "sector": "Healthcare", "market": "US"},
    {"ticker": "UNH", "name": "UnitedHealth Group", "sector": "Healthcare", "market": "US"},
    {"ticker": "MRK", "name": "Merck & Co", "sector": "Healthcare", "market": "US"},
    {"ticker": "TMO", "name": "Thermo Fisher Scientific", "sector": "Healthcare", "market": "US"},
    {"ticker": "DHR", "name": "Danaher", "sector": "Healthcare", "market": "US"},
    {"ticker": "ABT", "name": "Abbott Laboratories", "sector": "Healthcare", "market": "US"},
    {"ticker": "BMY", "name": "Bristol-Myers Squibb", "sector": "Healthcare", "market": "US"},
    {"ticker": "AMGN", "name": "Amgen", "sector": "Healthcare", "market": "US"},
    {"ticker": "GILD", "name": "Gilead Sciences", "sector": "Healthcare", "market": "US"},
    {"ticker": "ISRG", "name": "Intuitive Surgical", "sector": "Healthcare", "market": "US"},
    {"ticker": "VRTX", "name": "Vertex Pharmaceuticals", "sector": "Healthcare", "market": "US"},
    {"ticker": "SUNPHARMA.NS", "name": "Sun Pharma", "sector": "Healthcare", "market": "NSE"},
    {"ticker": "CIPLA.NS", "name": "Cipla", "sector": "Healthcare", "market": "NSE"},
    {"ticker": "DRREDDY.NS", "name": "Dr. Reddy's Laboratories", "sector": "Healthcare", "market": "NSE"},
    {"ticker": "DIVISLAB.NS", "name": "Divi's Laboratories", "sector": "Healthcare", "market": "NSE"},
    {"ticker": "APOLLOHOSP.NS", "name": "Apollo Hospitals", "sector": "Healthcare", "market": "NSE"},
    {"ticker": "MAXHEALTH.NS", "name": "Max Healthcare", "sector": "Healthcare", "market": "NSE"},
    {"ticker": "LUPIN.NS", "name": "Lupin", "sector": "Healthcare", "market": "NSE"},
    {"ticker": "AUROPHARMA.NS", "name": "Aurobindo Pharma", "sector": "Healthcare", "market": "NSE"},
    {"ticker": "TORNTPHARM.NS", "name": "Torrent Pharmaceuticals", "sector": "Healthcare", "market": "NSE"},
    {"ticker": "MANKIND.NS", "name": "Mankind Pharma", "sector": "Healthcare", "market": "NSE"},
    {"ticker": "BIOCON.NS", "name": "Biocon", "sector": "Healthcare", "market": "NSE"},
    {"ticker": "ZYDUSLIFE.NS", "name": "Zydus Lifesciences", "sector": "Healthcare", "market": "NSE"},
    {"ticker": "ALKEM.NS", "name": "Alkem Laboratories", "sector": "Healthcare", "market": "NSE"},
    {"ticker": "FORTIS.NS", "name": "Fortis Healthcare", "sector": "Healthcare", "market": "NSE"},
    # ── Energy ──────────────────────────────────────────────────────────────
    {"ticker": "XOM", "name": "ExxonMobil", "sector": "Energy", "market": "US"},
    {"ticker": "CVX", "name": "Chevron", "sector": "Energy", "market": "US"},
    {"ticker": "COP", "name": "ConocoPhillips", "sector": "Energy", "market": "US"},
    {"ticker": "SLB", "name": "SLB (Schlumberger)", "sector": "Energy", "market": "US"},
    {"ticker": "EOG", "name": "EOG Resources", "sector": "Energy", "market": "US"},
    {"ticker": "ENPH", "name": "Enphase Energy", "sector": "Energy", "market": "US"},
    {"ticker": "FSLR", "name": "First Solar", "sector": "Energy", "market": "US"},
    {"ticker": "NEE", "name": "NextEra Energy", "sector": "Energy", "market": "US"},
    {"ticker": "DUK", "name": "Duke Energy", "sector": "Energy", "market": "US"},
    {"ticker": "SO", "name": "Southern Company", "sector": "Energy", "market": "US"},
    {"ticker": "RELIANCE.NS", "name": "Reliance Industries", "sector": "Energy", "market": "NSE"},
    {"ticker": "ONGC.NS", "name": "Oil & Natural Gas Corp", "sector": "Energy", "market": "NSE"},
    {"ticker": "NTPC.NS", "name": "NTPC", "sector": "Energy", "market": "NSE"},
    {"ticker": "POWERGRID.NS", "name": "Power Grid Corp of India", "sector": "Energy", "market": "NSE"},
    {"ticker": "COALINDIA.NS", "name": "Coal India", "sector": "Energy", "market": "NSE"},
    {"ticker": "BPCL.NS", "name": "Bharat Petroleum", "sector": "Energy", "market": "NSE"},
    {"ticker": "IOC.NS", "name": "Indian Oil Corporation", "sector": "Energy", "market": "NSE"},
    {"ticker": "GAIL.NS", "name": "GAIL India", "sector": "Energy", "market": "NSE"},
    {"ticker": "TATAPOWER.NS", "name": "Tata Power", "sector": "Energy", "market": "NSE"},
    {"ticker": "JSWENERGY.NS", "name": "JSW Energy", "sector": "Energy", "market": "NSE"},
    {"ticker": "ADANIENT.NS", "name": "Adani Enterprises", "sector": "Energy", "market": "NSE"},
    {"ticker": "ADANIPORTS.NS", "name": "Adani Ports & SEZ", "sector": "Energy", "market": "NSE"},
    {"ticker": "ADANIGREEN.NS", "name": "Adani Green Energy", "sector": "Energy", "market": "NSE"},
    {"ticker": "ADANIPOWER.NS", "name": "Adani Power", "sector": "Energy", "market": "NSE"},
    {"ticker": "ATGL.NS", "name": "Adani Total Gas", "sector": "Energy", "market": "NSE"},
    {"ticker": "IREDA.NS", "name": "IREDA", "sector": "Energy", "market": "NSE"},
    {"ticker": "NHPC.NS", "name": "NHPC", "sector": "Energy", "market": "NSE"},
    {"ticker": "SUZLON.NS", "name": "Suzlon Energy", "sector": "Energy", "market": "NSE"},
    {"ticker": "PETRONET.NS", "name": "Petronet LNG", "sector": "Energy", "market": "NSE"},
    {"ticker": "NTPC.BO", "name": "NTPC (BSE)", "sector": "Energy", "market": "BSE"},
    {"ticker": "POWERGRID.BO", "name": "Power Grid (BSE)", "sector": "Energy", "market": "BSE"},
    {"ticker": "IOC.BO", "name": "Indian Oil Corp (BSE)", "sector": "Energy", "market": "BSE"},
    {"ticker": "GAIL.BO", "name": "GAIL India (BSE)", "sector": "Energy", "market": "BSE"},
    {"ticker": "COALINDIA.BO", "name": "Coal India (BSE)", "sector": "Energy", "market": "BSE"},
    {"ticker": "ADANIENT.BO", "name": "Adani Enterprises (BSE)", "sector": "Energy", "market": "BSE"},
    # ── Consumer ────────────────────────────────────────────────────────────
    {"ticker": "WMT", "name": "Walmart", "sector": "Consumer", "market": "US"},
    {"ticker": "COST", "name": "Costco", "sector": "Consumer", "market": "US"},
    {"ticker": "TGT", "name": "Target", "sector": "Consumer", "market": "US"},
    {"ticker": "HD", "name": "Home Depot", "sector": "Consumer", "market": "US"},
    {"ticker": "LOW", "name": "Lowe's", "sector": "Consumer", "market": "US"},
    {"ticker": "NKE", "name": "Nike", "sector": "Consumer", "market": "US"},
    {"ticker": "LULU", "name": "Lululemon", "sector": "Consumer", "market": "US"},
    {"ticker": "MCD", "name": "McDonald's", "sector": "Consumer", "market": "US"},
    {"ticker": "SBUX", "name": "Starbucks", "sector": "Consumer", "market": "US"},
    {"ticker": "CMG", "name": "Chipotle Mexican Grill", "sector": "Consumer", "market": "US"},
    {"ticker": "DIS", "name": "Walt Disney", "sector": "Consumer", "market": "US"},
    {"ticker": "NFLX", "name": "Netflix", "sector": "Consumer", "market": "US"},
    {"ticker": "KO", "name": "Coca-Cola", "sector": "Consumer", "market": "US"},
    {"ticker": "PEP", "name": "PepsiCo", "sector": "Consumer", "market": "US"},
    {"ticker": "PG", "name": "Procter & Gamble", "sector": "Consumer", "market": "US"},
    {"ticker": "HINDUNILVR.NS", "name": "Hindustan Unilever", "sector": "Consumer", "market": "NSE"},
    {"ticker": "ITC.NS", "name": "ITC Limited", "sector": "Consumer", "market": "NSE"},
    {"ticker": "NESTLEIND.NS", "name": "Nestle India", "sector": "Consumer", "market": "NSE"},
    {"ticker": "BRITANNIA.NS", "name": "Britannia Industries", "sector": "Consumer", "market": "NSE"},
    {"ticker": "TATACONSUM.NS", "name": "Tata Consumer Products", "sector": "Consumer", "market": "NSE"},
    {"ticker": "DABUR.NS", "name": "Dabur India", "sector": "Consumer", "market": "NSE"},
    {"ticker": "MARICO.NS", "name": "Marico", "sector": "Consumer", "market": "NSE"},
    {"ticker": "GODREJCP.NS", "name": "Godrej Consumer Products", "sector": "Consumer", "market": "NSE"},
    {"ticker": "COLPAL.NS", "name": "Colgate-Palmolive India", "sector": "Consumer", "market": "NSE"},
    {"ticker": "TITAN.NS", "name": "Titan Company", "sector": "Consumer", "market": "NSE"},
    {"ticker": "ASIANPAINT.NS", "name": "Asian Paints", "sector": "Consumer", "market": "NSE"},
    {"ticker": "BERGEPAINT.NS", "name": "Berger Paints", "sector": "Consumer", "market": "NSE"},
    {"ticker": "PIDILITIND.NS", "name": "Pidilite Industries", "sector": "Consumer", "market": "NSE"},
    {"ticker": "DMART.NS", "name": "Avenue Supermarts (DMart)", "sector": "Consumer", "market": "NSE"},
    {"ticker": "TRENT.NS", "name": "Trent (Westside/Zudio)", "sector": "Consumer", "market": "NSE"},
    {"ticker": "VBL.NS", "name": "Varun Beverages", "sector": "Consumer", "market": "NSE"},
    {"ticker": "JUBLFOOD.NS", "name": "Jubilant FoodWorks", "sector": "Consumer", "market": "NSE"},
    {"ticker": "DEVYANI.NS", "name": "Devyani International", "sector": "Consumer", "market": "NSE"},
    {"ticker": "NYKAA.NS", "name": "Nykaa (FSN E-Commerce)", "sector": "Consumer", "market": "NSE"},
    {"ticker": "PAGEIND.NS", "name": "Page Industries", "sector": "Consumer", "market": "NSE"},
    # ── Industrials ─────────────────────────────────────────────────────────
    {"ticker": "CAT", "name": "Caterpillar", "sector": "Industrials", "market": "US"},
    {"ticker": "DE", "name": "Deere & Company", "sector": "Industrials", "market": "US"},
    {"ticker": "BA", "name": "Boeing", "sector": "Industrials", "market": "US"},
    {"ticker": "LMT", "name": "Lockheed Martin", "sector": "Industrials", "market": "US"},
    {"ticker": "RTX", "name": "RTX Corporation", "sector": "Industrials", "market": "US"},
    {"ticker": "HON", "name": "Honeywell", "sector": "Industrials", "market": "US"},
    {"ticker": "GE", "name": "GE Aerospace", "sector": "Industrials", "market": "US"},
    {"ticker": "UNP", "name": "Union Pacific", "sector": "Industrials", "market": "US"},
    {"ticker": "UPS", "name": "United Parcel Service", "sector": "Industrials", "market": "US"},
    {"ticker": "TATASTEEL.NS", "name": "Tata Steel", "sector": "Industrials", "market": "NSE"},
    {"ticker": "JSWSTEEL.NS", "name": "JSW Steel", "sector": "Industrials", "market": "NSE"},
    {"ticker": "HINDALCO.NS", "name": "Hindalco Industries", "sector": "Industrials", "market": "NSE"},
    {"ticker": "VEDL.NS", "name": "Vedanta", "sector": "Industrials", "market": "NSE"},
    {"ticker": "JINDALSTEL.NS", "name": "Jindal Steel & Power", "sector": "Industrials", "market": "NSE"},
    {"ticker": "NMDC.NS", "name": "NMDC", "sector": "Industrials", "market": "NSE"},
    {"ticker": "SAIL.NS", "name": "Steel Authority of India", "sector": "Industrials", "market": "NSE"},
    {"ticker": "LT.NS", "name": "Larsen & Toubro", "sector": "Industrials", "market": "NSE"},
    {"ticker": "HAL.NS", "name": "Hindustan Aeronautics", "sector": "Industrials", "market": "NSE"},
    {"ticker": "BEL.NS", "name": "Bharat Electronics", "sector": "Industrials", "market": "NSE"},
    {"ticker": "BHEL.NS", "name": "Bharat Heavy Electricals", "sector": "Industrials", "market": "NSE"},
    {"ticker": "SIEMENS.NS", "name": "Siemens India", "sector": "Industrials", "market": "NSE"},
    {"ticker": "ABB.NS", "name": "ABB India", "sector": "Industrials", "market": "NSE"},
    {"ticker": "CUMMINSIND.NS", "name": "Cummins India", "sector": "Industrials", "market": "NSE"},
    {"ticker": "ULTRACEMCO.NS", "name": "UltraTech Cement", "sector": "Industrials", "market": "NSE"},
    {"ticker": "GRASIM.NS", "name": "Grasim Industries", "sector": "Industrials", "market": "NSE"},
    {"ticker": "AMBUJACEM.NS", "name": "Ambuja Cements", "sector": "Industrials", "market": "NSE"},
    {"ticker": "SHREECEM.NS", "name": "Shree Cement", "sector": "Industrials", "market": "NSE"},
    {"ticker": "POLYCAB.NS", "name": "Polycab India", "sector": "Industrials", "market": "NSE"},
    {"ticker": "HAVELLS.NS", "name": "Havells India", "sector": "Industrials", "market": "NSE"},
    {"ticker": "ASTRAL.NS", "name": "Astral", "sector": "Industrials", "market": "NSE"},
    {"ticker": "IRCTC.NS", "name": "IRCTC", "sector": "Industrials", "market": "NSE"},
    {"ticker": "RVNL.NS", "name": "Rail Vikas Nigam", "sector": "Industrials", "market": "NSE"},
    {"ticker": "ULTRACEMCO.BO", "name": "UltraTech Cement (BSE)", "sector": "Industrials", "market": "BSE"},
    {"ticker": "JSWSTEEL.BO", "name": "JSW Steel (BSE)", "sector": "Industrials", "market": "BSE"},
    {"ticker": "GMRAIRPORT.NS", "name": "GMR Airports Infrastructure", "sector": "Industrials", "market": "NSE"},
    {"ticker": "VEDL.BO", "name": "Vedanta (BSE)", "sector": "Industrials", "market": "BSE"},
    {"ticker": "ADANIPORTS.BO", "name": "Adani Ports (BSE)", "sector": "Industrials", "market": "BSE"},
    {"ticker": "POLYCAB.BO", "name": "Polycab India (BSE)", "sector": "Industrials", "market": "BSE"},
    {"ticker": "SIEMENS.BO", "name": "Siemens India (BSE)", "sector": "Industrials", "market": "BSE"},
    {"ticker": "HAL.BO", "name": "Hindustan Aeronautics (BSE)", "sector": "Industrials", "market": "BSE"},
    {"ticker": "BHEL.BO", "name": "Bharat Heavy Electricals (BSE)", "sector": "Industrials", "market": "BSE"},
    # ── Telecom ─────────────────────────────────────────────────────────────
    {"ticker": "BHARTIARTL.NS", "name": "Bharti Airtel", "sector": "Telecom", "market": "NSE"},
    {"ticker": "IDEA.NS", "name": "Vodafone Idea", "sector": "Telecom", "market": "NSE"},
    {"ticker": "BHARTIARTL.BO", "name": "Bharti Airtel (BSE)", "sector": "Telecom", "market": "BSE"},
    # ── ETF ─────────────────────────────────────────────────────────────────
    {"ticker": "SPY", "name": "S&P 500 ETF (SPDR)", "sector": "ETF", "market": "US"},
    {"ticker": "QQQ", "name": "NASDAQ-100 ETF (Invesco)", "sector": "ETF", "market": "US"},
    {"ticker": "DIA", "name": "Dow Jones ETF (SPDR)", "sector": "ETF", "market": "US"},
    {"ticker": "IWM", "name": "Russell 2000 ETF", "sector": "ETF", "market": "US"},
    {"ticker": "VOO", "name": "Vanguard S&P 500 ETF", "sector": "ETF", "market": "US"},
    {"ticker": "VTI", "name": "Vanguard Total Stock Market", "sector": "ETF", "market": "US"},
    {"ticker": "GLD", "name": "Gold Trust (SPDR)", "sector": "ETF", "market": "US"},
    {"ticker": "SLV", "name": "Silver Trust (iShares)", "sector": "ETF", "market": "US"},
    {"ticker": "USO", "name": "United States Oil Fund", "sector": "ETF", "market": "US"},
    {"ticker": "TLT", "name": "20+ Year Treasury Bond ETF", "sector": "ETF", "market": "US"},
    {"ticker": "SMH", "name": "VanEck Semiconductor ETF", "sector": "ETF", "market": "US"},
    {"ticker": "XLF", "name": "Financial Select Sector SPDR", "sector": "ETF", "market": "US"},
    {"ticker": "XLK", "name": "Technology Select Sector SPDR", "sector": "ETF", "market": "US"},
    {"ticker": "XLE", "name": "Energy Select Sector SPDR", "sector": "ETF", "market": "US"},
    {"ticker": "NIFTYBEES.NS", "name": "Nippon India Nifty 50 BeES ETF", "sector": "ETF", "market": "NSE"},
    {"ticker": "BANKBEES.NS", "name": "Nippon India Bank BeES ETF", "sector": "ETF", "market": "NSE"},
    {"ticker": "GOLDBEES.NS", "name": "Nippon India Gold BeES ETF", "sector": "ETF", "market": "NSE"},
    {"ticker": "ITBEES.NS", "name": "Nippon India IT BeES ETF", "sector": "ETF", "market": "NSE"},
    {"ticker": "SILVERBEES.NS", "name": "Nippon India Silver BeES ETF", "sector": "ETF", "market": "NSE"},
    {"ticker": "JUNIORBEES.NS", "name": "Nippon India Nifty Next 50 ETF", "sector": "ETF", "market": "NSE"},
]

# Quick lookup dict for validation
_TICKER_SET = {t["ticker"] for t in AVAILABLE_TICKERS}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/available",
    summary="Get the full catalog of available tickers",
    response_description="Curated list of tickers grouped by sector",
)
def get_available_tickers() -> dict[str, Any]:
    """
    Returns the full curated catalog of tickers a user can add to their watchlist.
    Grouped by sector for easy browsing.
    """
    sectors: dict[str, list[dict]] = {}
    for entry in AVAILABLE_TICKERS:
        sectors.setdefault(entry["sector"], []).append(
            {
                "ticker": entry["ticker"],
                "name": entry["name"],
                "market": entry.get(
                    "market",
                    "NSE" if entry["ticker"].endswith(".NS") else "BSE" if entry["ticker"].endswith(".BO") else "US",
                ),
            }
        )
    return {"sectors": sectors, "total": len(AVAILABLE_TICKERS)}


@router.get(
    "",
    summary="Get the user's current watchlist",
    response_description="List of tickers in the watchlist",
)
def get_watchlist(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Returns all tickers in the user's persisted watchlist."""
    entries = db.query(WatchlistEntry).order_by(WatchlistEntry.added_at).all()
    tickers = [e.ticker for e in entries]
    # Enrich with catalog metadata where available
    catalog_map = {t["ticker"]: t for t in AVAILABLE_TICKERS}
    enriched = []
    for e in entries:
        meta = catalog_map.get(e.ticker, {})
        enriched.append({
            "ticker": e.ticker,
            "name": meta.get("name", e.ticker),
            "sector": meta.get("sector", "Custom"),
            "market": meta.get(
                "market",
                "NSE" if e.ticker.endswith(".NS") else "BSE" if e.ticker.endswith(".BO") else "US",
            ),
            "added_at": e.added_at.isoformat() if e.added_at else None,
        })
    return {"watchlist": enriched, "tickers": tickers, "count": len(tickers)}


@router.post(
    "/{ticker}",
    summary="Add a ticker to the watchlist",
    status_code=201,
)
def add_to_watchlist(ticker: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    Add a ticker to the watchlist. The ticker must be from the curated catalog
    OR be a valid-looking uppercase ticker (for power users who know what they want).
    """
    ticker = ticker.upper().strip()
    if not ticker or len(ticker) > 30:
        raise HTTPException(status_code=422, detail="Invalid ticker symbol.")

    existing = db.query(WatchlistEntry).filter(WatchlistEntry.ticker == ticker).first()
    if existing:
        raise HTTPException(
            status_code=409, detail=f"{ticker} is already in the watchlist."
        )

    entry = WatchlistEntry(ticker=ticker, added_at=datetime.now(timezone.utc))
    db.add(entry)
    db.commit()
    logger.info("Watchlist: added %s", ticker)

    catalog_map = {t["ticker"]: t for t in AVAILABLE_TICKERS}
    meta = catalog_map.get(ticker, {})
    return {
        "ticker": ticker,
        "name": meta.get("name", ticker),
        "sector": meta.get("sector", "Custom"),
        "market": meta.get(
            "market",
            "NSE" if ticker.endswith(".NS") else "BSE" if ticker.endswith(".BO") else "US",
        ),
        "added": True,
    }


@router.delete(
    "/{ticker}",
    summary="Remove a ticker from the watchlist",
)
def remove_from_watchlist(ticker: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Remove a ticker from the watchlist. Returns 404 if not present."""
    ticker = ticker.upper().strip()
    entry = db.query(WatchlistEntry).filter(WatchlistEntry.ticker == ticker).first()
    if not entry:
        raise HTTPException(
            status_code=404, detail=f"{ticker} is not in the watchlist."
        )
    db.delete(entry)
    db.commit()
    logger.info("Watchlist: removed %s", ticker)
    return {"ticker": ticker, "removed": True}
