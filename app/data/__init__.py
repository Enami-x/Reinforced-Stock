"""
Data package — price and news fetchers.
"""

from app.data.news import NewsFetcher, NewsItem
from app.data.price import PriceFetcher, PriceSnapshot

__all__ = ["PriceFetcher", "PriceSnapshot", "NewsFetcher", "NewsItem"]
