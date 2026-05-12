"""news-core: multilingual equity-research news ingestion."""
from news_core.client import NewsClient
from news_core.schema import NewsItem, FetchRequest, FetchResult, Source, Tier

__all__ = ["NewsClient", "NewsItem", "FetchRequest", "FetchResult", "Source", "Tier"]
__version__ = "0.1.0"
