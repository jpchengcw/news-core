"""Search + fetch backends.

Public interface: Fetcher protocol with `search()` and `fetch_content()`.
Default impl is `MultiSourceFetcher` — composes locale-native scrapers
(Baidu/Yahoo Japan/Naver), Tavily-routed publisher adapters (Bloomberg/
Reuters/GoogleSite for DE/FR/HK), and a broad Tavily fallback into a single
priority-ordered pipeline.

The legacy `TavilyFetcher` is retained for backward compatibility with
consumers that haven't migrated to MultiSourceFetcher. `StubFetcher` is the
no-op for tests.
"""
from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

log = logging.getLogger("news_core.fetch")


@dataclass
class RawHit:
    """Single search result before tier scoring / translation."""
    url: str
    title: str
    snippet: str
    locale: str
    published_at: datetime | None = None
    raw_metadata: dict = field(default_factory=dict)
    paywalled: bool = False
    source_used: str | None = None  # adapter name: "tavily","bloomberg","baidu",...

    def stable_id(self) -> str:
        return hashlib.sha1(self.url.encode()).hexdigest()[:16]


class Fetcher(Protocol):
    """Search backend interface."""

    def search(
        self,
        query: str,
        locale: str,
        lookback_hours: int,
        max_results: int = 10,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[RawHit]:
        """Locale-aware search. Caller passes a single query string.

        `include_domains` makes the search exclusive to those domains (used for
        targeted Tier-1/2 passes). `exclude_domains` filters known noise.
        """
        ...

    def fetch_content(self, url: str) -> str | None:
        """Fetch article body. Returns None on failure."""
        ...


class StubFetcher:
    """No-op fetcher. Lets the pipeline shape be tested without network calls."""

    def search(self, query, locale, lookback_hours, max_results=10,
               include_domains=None, exclude_domains=None):
        return []

    def fetch_content(self, url):
        return None


class TavilyFetcher:
    """Tavily-backed search + fetch.

    Configures locale via Tavily's `country` / `topic` parameters and prepends
    locale-targeted site operators when the locale is non-English.
    """

    def __init__(self, api_key: str | None = None):
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

    @staticmethod
    def _country_for_locale(locale: str) -> str | None:
        return {
            "ja":    "japan",
            "ko":    "south korea",
            "zh-CN": "china",
            "zh-HK": "hong kong",
            "zh-TW": "taiwan",
            "de":    "germany",
            "fr":    "france",
            "en":    None,
        }.get(locale)

    def search(
        self,
        query,
        locale,
        lookback_hours,
        max_results=10,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ):
        client = self._client_or_init()
        days = max(1, (lookback_hours + 23) // 24)
        kwargs: dict = dict(
            query=query,
            search_depth="advanced",
            max_results=max_results,
            days=days,
        )
        # Targeted domain searches use the general index (so features/analysis/
        # interviews surface, not just breaking news). Broad locale searches
        # add `topic=news` and `country` for recency + locale bias.
        if include_domains:
            kwargs["include_domains"] = include_domains
        else:
            kwargs["topic"] = "news"
            country = self._country_for_locale(locale)
            if country:
                kwargs["country"] = country
        if exclude_domains:
            kwargs["exclude_domains"] = exclude_domains
        try:
            resp = client.search(**kwargs)
        except Exception:
            return []
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
            ))
        return hits

    def fetch_content(self, url):
        client = self._client_or_init()
        try:
            resp = client.extract(urls=[url])
            results = resp.get("results", [])
            if results:
                return results[0].get("raw_content")
        except Exception:
            return None
        return None


# ---------------------------------------------------------------------------
# MultiSourceFetcher — composition of adapters in priority order.
# ---------------------------------------------------------------------------
class MultiSourceFetcher:
    """Walks a per-locale ordered adapter list until enough hits are collected.

    Priority (per spec §1.5):
      1. Locale-native scraper (Baidu / Yahoo Japan / Naver / GoogleSite-DE/FR/HK)
      2. Reuters
      3. Bloomberg
      4. Broad Tavily — only if 1–3 returned zero AND under daily $-cap.

    The instance implements the Fetcher protocol, so the existing client.py
    pipeline works unchanged. It accepts an `adapters_by_locale` map plus a
    fallback `broad_tavily` adapter.

    `search()` for a given locale fans out IN PARALLEL across the adapters in
    that locale's priority list — these are independent network calls and
    parallelism is safe (each adapter has its own rate limit + quota).
    """

    def __init__(
        self,
        adapters_by_locale: dict[str, list],
        broad_tavily=None,
        target_per_call: int = 6,
    ):
        self._adapters_by_locale = adapters_by_locale
        self._broad_tavily = broad_tavily
        self._target_per_call = target_per_call

    def _adapters_for(self, locale: str) -> list:
        """Adapters for `locale`. Falls back to the broad-EN list if unknown."""
        return self._adapters_by_locale.get(locale) or self._adapters_by_locale.get("en") or []

    def search(
        self,
        query: str,
        locale: str,
        lookback_hours: int,
        max_results: int = 10,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[RawHit]:
        # If caller already specifies include_domains (e.g. the existing
        # client.py per-domain fanout), bypass the adapter walk and route
        # straight to broad Tavily — that's the only adapter that honors
        # arbitrary include_domains. Used for backward-compat callsites.
        if include_domains and self._broad_tavily is not None:
            return self._broad_tavily.search(
                query, locale, lookback_hours, max_results,
                include_domains=include_domains, exclude_domains=exclude_domains,
            )

        adapters = self._adapters_for(locale)
        accumulated: list[RawHit] = []

        from concurrent.futures import ThreadPoolExecutor, as_completed
        if adapters:
            with ThreadPoolExecutor(max_workers=min(4, len(adapters))) as pool:
                futs = [
                    pool.submit(
                        a.search, query, locale, lookback_hours, max_results,
                        None, exclude_domains,
                    )
                    for a in adapters
                ]
                for fut in as_completed(futs):
                    try:
                        hits = fut.result()
                    except Exception as e:
                        log.debug("adapter failed in MultiSourceFetcher: %s", e)
                        continue
                    accumulated.extend(hits)

        # Broad Tavily fallback: ONLY if every primary adapter returned empty.
        if not accumulated and self._broad_tavily is not None:
            try:
                if hasattr(self._broad_tavily, "budget") and self._broad_tavily.budget is not None:
                    if not self._broad_tavily.budget.tavily.can_spend():
                        log.info("broad-tavily fallback blocked by $-cap")
                        return []
                accumulated = self._broad_tavily.search(
                    query, locale, lookback_hours, max_results,
                    include_domains=None, exclude_domains=exclude_domains,
                )
            except Exception as e:
                log.debug("broad-tavily fallback error: %s", e)

        return accumulated

    def fetch_content(self, url: str) -> str | None:
        # No-op at the composer level. Adapters that need body fetch handle it
        # internally during their search() (e.g. Bloomberg meta enrichment).
        return None
