"""Base adapter: shared retry/backoff, cache, rate limit, quota plumbing.

Each adapter implements `_search_impl()` (the engine-specific logic) and the
base class wraps it with:
  - 24h cache lookup (skip network on hit)
  - rate limiter (1 req/sec per adapter, configurable)
  - daily quota check (skip if engine quota exhausted)
  - retry with exponential backoff (3 attempts)
  - structured error logging that never raises out of search()
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from news_core.fetch import RawHit

if TYPE_CHECKING:
    from news_core.budget import BudgetCenter
    from news_core.cache import NewsCache

log = logging.getLogger("news_core.adapters")


class AdapterError(Exception):
    """Recoverable adapter failure — caught by base.search() and logged."""


class _Transient(AdapterError):
    """Worth retrying."""


class BaseAdapter(ABC):
    """All adapters subclass this. Public entry point is `search()`."""

    name: str = "base"
    # Per-adapter override; budget center default is 1 req/sec across all adapters.
    requests_per_second: float | None = None
    # Whether this adapter consumes Tavily $-budget. Bloomberg/Reuters/GoogleSite do.
    counts_against_tavily_budget: bool = False

    def __init__(
        self,
        cache: "NewsCache | None" = None,
        budget: "BudgetCenter | None" = None,
    ):
        self.cache = cache
        self.budget = budget

    # ------------------------------------------------------------------
    # Public API (consistent with Fetcher protocol)
    # ------------------------------------------------------------------
    def search(
        self,
        query: str,
        locale: str,
        lookback_hours: int,
        max_results: int = 10,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[RawHit]:
        """Cache-aware, quota-aware, retried search."""
        if self.cache is not None:
            cached = self.cache.get_search(self.name, query, locale, include_domains)
            if cached is not None:
                log.debug("%s cache hit (q=%s, locale=%s, n=%d)", self.name, query[:60], locale, len(cached))
                return cached[:max_results]

        if self.budget is not None:
            if not self.budget.quota.can_call(self.name):
                log.info("%s daily quota exhausted; skipping", self.name)
                return []
            if self.counts_against_tavily_budget and not self.budget.tavily.can_spend():
                log.info("%s Tavily $-cap reached; skipping (spent=$%.2f cap=$%.2f)",
                         self.name, self.budget.tavily.spent_today(), self.budget.tavily.cap_usd)
                return []
            self.budget.rate.acquire(self.name)

        try:
            hits = self._search_with_retry(
                query=query, locale=locale, lookback_hours=lookback_hours,
                max_results=max_results, include_domains=include_domains,
                exclude_domains=exclude_domains,
            )
        except Exception as e:
            log.warning("%s search failed (q=%s): %s", self.name, query[:60], e)
            return []

        # Stamp source_used so downstream telemetry knows which adapter produced each hit.
        for h in hits:
            if h.source_used is None:
                h.source_used = self.name

        if self.budget is not None:
            self.budget.quota.record_call(self.name)
            if self.counts_against_tavily_budget:
                self.budget.tavily.record_call()

        if self.cache is not None and hits:
            self.cache.put_search(self.name, query, locale, hits, include_domains)

        return hits[:max_results]

    def fetch_content(self, url: str) -> str | None:
        """Default: no-op. Adapters that need body text override this."""
        return None

    # ------------------------------------------------------------------
    # Subclasses implement
    # ------------------------------------------------------------------
    @abstractmethod
    def _search_impl(
        self,
        query: str,
        locale: str,
        lookback_hours: int,
        max_results: int,
        include_domains: list[str] | None,
        exclude_domains: list[str] | None,
    ) -> list[RawHit]:
        ...

    # ------------------------------------------------------------------
    # Internal: retry wrapper
    # ------------------------------------------------------------------
    def _search_with_retry(self, **kwargs) -> list[RawHit]:
        @retry(
            retry=retry_if_exception_type(_Transient),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=4),
            reraise=True,
        )
        def _go():
            return self._search_impl(**kwargs)

        return _go()
