"""Public data shapes. All consumers (PM Pulse, Deep Dive) speak this schema."""
from __future__ import annotations

from datetime import datetime
from enum import IntEnum
from typing import Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


class Tier(IntEnum):
    """Source authority tier. Lower = more authoritative.

    S=0 regulatory/primary, 1=top-tier press, 2=industry trade,
    3=aggregator/corp channel, X=99 deprioritised SEO/forum.
    """
    S = 0
    ONE = 1
    TWO = 2
    THREE = 3
    X = 99


class Source(BaseModel):
    """A registered news source with locale + tier metadata."""
    name: str
    domain: str
    locale: str  # e.g. "ja", "zh-CN", "zh-HK", "ko", "en", "de", "fr"
    tier: Tier
    regions: list[str] = Field(default_factory=list)  # e.g. ["JP","global"]


class NewsItem(BaseModel):
    """A single ranked, deduped, translated news item."""
    id: str  # stable hash of (canonical_url || title+source+date)
    url: HttpUrl
    source_name: str
    source_domain: str
    locale: str
    tier: Tier

    title_original: str
    title_translated: Optional[str] = None  # None when locale == "en"
    summary_translated: Optional[str] = None  # 2–4 most material sentences, copyright-capped
    analyst_gloss: Optional[str] = None  # one-line "Read-through: ..." / "Implication: ..."

    published_at: datetime
    fetched_at: datetime

    entity_tags: list[str] = Field(default_factory=list)  # canonical entity ids matched
    topic_tags: list[str] = Field(default_factory=list)  # e.g. "earnings","mna","capex","regulatory"

    score: float = 0.0  # composite recency × authority × relevance
    cluster_id: Optional[str] = None  # cross-language cluster membership

    raw_excerpt: Optional[str] = None  # original-language excerpt for citation

    paywalled: bool = False  # True when body inaccessible — title+dek only (e.g. Bloomberg)
    source_used: Optional[str] = None  # which adapter produced this hit (for telemetry)


class FetchRequest(BaseModel):
    """Inputs to NewsClient.fetch()."""
    ticker: str
    company_name: str
    business_geography: list[str] = Field(default_factory=list)
    lookback_hours: int = 72
    max_items: int = 20
    min_tier: Tier = Tier.TWO
    consumer: Literal["pm_pulse", "deep_dive"] = "deep_dive"


class FetchResult(BaseModel):
    """Output of NewsClient.fetch()."""
    items: list[NewsItem]
    locales_queried: list[str]
    queries_issued: int
    raw_hits: int
    deduped_clusters: int
    dropped_below_tier: int
    # Per-source fetch counts (e.g. {"tavily": 3, "bloomberg": 2, "baidu": 4}).
    source_counts: dict[str, int] = Field(default_factory=dict)
    # USD spent on Tavily for this fetch (delta).
    tavily_spend_usd: float = 0.0
    # Tavily $-cap remaining at end of fetch (for digest footer telemetry).
    tavily_cap_remaining_usd: float = 0.0
