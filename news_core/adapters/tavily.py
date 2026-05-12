"""Tavily adapter. Budget-aware wrapper around the Tavily search API.

This is both:
  - the standalone fallback adapter (last in priority order), AND
  - the search backbone for BloombergAdapter / ReutersAdapter / GoogleSiteAdapter
    which call TavilyAdapter.search() internally with `include_domains`.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from news_core.adapters._base import AdapterError, BaseAdapter, _Transient
from news_core.fetch import RawHit

if TYPE_CHECKING:
    from news_core.budget import BudgetCenter
    from news_core.cache import NewsCache

log = logging.getLogger("news_core.adapters.tavily")


class TavilyAdapter(BaseAdapter):
    name = "tavily"
    counts_against_tavily_budget = True

    _COUNTRY_BY_LOCALE: dict[str, str | None] = {
        "ja":    "japan",
        "ko":    "south korea",
        "zh-CN": "china",
        "zh-HK": "hong kong",
        "zh-TW": "taiwan",
        "de":    "germany",
        "fr":    "france",
        "en":    None,
    }

    def __init__(
        self,
        api_key: str | None = None,
        cache: "NewsCache | None" = None,
        budget: "BudgetCenter | None" = None,
    ):
        super().__init__(cache=cache, budget=budget)
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY")
        if not self.api_key:
            raise RuntimeError("TAVILY_API_KEY not set")
        self._client = None

    def _client_or_init(self):
        if self._client is None:
            try:
                from tavily import TavilyClient  # type: ignore
            except ImportError as e:
                raise RuntimeError("tavily-python not installed") from e
            self._client = TavilyClient(api_key=self.api_key)
        return self._client

    def _search_impl(
        self,
        query: str,
        locale: str,
        lookback_hours: int,
        max_results: int,
        include_domains: list[str] | None,
        exclude_domains: list[str] | None,
    ) -> list[RawHit]:
        client = self._client_or_init()
        days = max(1, (lookback_hours + 23) // 24)
        kwargs: dict = dict(
            query=query,
            search_depth="advanced",
            max_results=max_results,
            days=days,
        )
        if include_domains:
            kwargs["include_domains"] = include_domains
        else:
            kwargs["topic"] = "news"
            country = self._COUNTRY_BY_LOCALE.get(locale)
            if country:
                kwargs["country"] = country
        if exclude_domains:
            kwargs["exclude_domains"] = exclude_domains

        try:
            resp = client.search(**kwargs)
        except Exception as e:
            # Tavily client raises various exceptions; treat 5xx / network as transient.
            msg = str(e).lower()
            if any(k in msg for k in ("timeout", "connection", "5", "rate")):
                raise _Transient(f"tavily transient: {e}") from e
            # Non-transient (e.g. 401 Unauthorized, malformed query, quota exhausted).
            # Raise so _base.search() catches and returns [] WITHOUT recording the
            # call against the Tavily $-budget. Previously this returned [] inline,
            # which let _base.search() record_call() and burn cap on failed auth.
            raise AdapterError(f"tavily non-transient: {e}") from e

        hits: list[RawHit] = []
        for r in resp.get("results", []):
            published = None
            if r.get("published_date"):
                try:
                    published = datetime.fromisoformat(r["published_date"].replace("Z", "+00:00"))
                except Exception:
                    published = None
            hits.append(RawHit(
                url=r.get("url", ""),
                title=r.get("title", ""),
                snippet=r.get("content", ""),
                locale=locale,
                published_at=published or datetime.now(timezone.utc),
                raw_metadata={"score": r.get("score")},
                source_used=self.name,
            ))
        return hits

    def fetch_content(self, url: str) -> str | None:
        client = self._client_or_init()
        try:
            resp = client.extract(urls=[url])
            results = resp.get("results", [])
            if results:
                return results[0].get("raw_content")
        except Exception as e:
            log.debug("tavily extract failed for %s: %s", url, e)
            return None
        return None
