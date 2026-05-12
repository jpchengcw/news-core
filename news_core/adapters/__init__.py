"""Source adapters. Each implements the Fetcher protocol.

Composed by MultiSourceFetcher in priority order:
  1. Locale-native (Baidu/Yahoo JP/Naver/GoogleSite-DE-FR-HK)
  2. Reuters
  3. Bloomberg
  4. Tavily (broad, fallback)
"""
from news_core.adapters._base import BaseAdapter, AdapterError
from news_core.adapters.tavily import TavilyAdapter
from news_core.adapters.bloomberg import BloombergAdapter
from news_core.adapters.reuters import ReutersAdapter
from news_core.adapters.baidu import BaiduAdapter
from news_core.adapters.yahoo_japan import YahooJapanAdapter
from news_core.adapters.naver import NaverAdapter
from news_core.adapters.google_site import GoogleSiteAdapter

__all__ = [
    "BaseAdapter",
    "AdapterError",
    "TavilyAdapter",
    "BloombergAdapter",
    "ReutersAdapter",
    "BaiduAdapter",
    "YahooJapanAdapter",
    "NaverAdapter",
    "GoogleSiteAdapter",
]
