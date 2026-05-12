"""Google site-search adapter (DE/FR/HK/EN).

Pure delegation to TavilyAdapter with a per-locale `include_domains` list.
This is the adapter we use for German (Handelsblatt/FAZ), French (Les Echos/
Le Figaro), and Hong Kong (HK01/SCMP/Ming Pao) coverage — Q12(a): we route
through Tavily rather than scraping Google SERPs (which reCAPTCHA aggressively).

Each call counts against the Tavily $-budget but produces hits from Tier-1
publishers we want for those locales.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from news_core.adapters._base import BaseAdapter
from news_core.fetch import RawHit

if TYPE_CHECKING:
    from news_core.adapters.tavily import TavilyAdapter
    from news_core.budget import BudgetCenter
    from news_core.cache import NewsCache

log = logging.getLogger("news_core.adapters.google_site")


# Locale → publisher domains routed through Tavily site-search.
# Kept in lockstep with sources.py priority outlets.
DOMAINS_BY_LOCALE: dict[str, list[str]] = {
    "de":    ["handelsblatt.com", "faz.net", "manager-magazin.de", "boersen-zeitung.de"],
    "fr":    ["lesechos.fr", "lefigaro.fr", "agefi.fr", "latribune.fr", "lemonde.fr"],
    "zh-HK": ["hk01.com", "scmp.com", "mingpao.com", "hket.com"],
    "en":    [],  # broad EN doesn't need site restriction
}


class GoogleSiteAdapter(BaseAdapter):
    """Tavily-routed site-search restricted to a per-locale publisher set.

    The adapter "name" is `google_site` for telemetry/cache; the actual fetch
    rides on the shared TavilyAdapter, so spend is recorded there once per call.
    """

    name = "google_site"
    counts_against_tavily_budget = False  # the inner TavilyAdapter records spend

    def __init__(
        self,
        tavily_adapter: "TavilyAdapter",
        cache: "NewsCache | None" = None,
        budget: "BudgetCenter | None" = None,
        domains_by_locale: dict[str, list[str]] | None = None,
    ):
        super().__init__(cache=cache, budget=budget)
        self._tav = tavily_adapter
        self._domains = domains_by_locale or DOMAINS_BY_LOCALE

    def _search_impl(
        self,
        query: str,
        locale: str,
        lookback_hours: int,
        max_results: int,
        include_domains: list[str] | None,
        exclude_domains: list[str] | None,
    ) -> list[RawHit]:
        domains = self._domains.get(locale)
        if not domains:
            return []

        hits = self._tav.search(
            query=query,
            locale=locale,
            lookback_hours=lookback_hours,
            max_results=max_results,
            include_domains=domains,
        )
        # Stamp source_used to the *site-search* adapter, not Tavily —
        # downstream telemetry differentiates "google_site" from raw Tavily.
        for h in hits:
            h.source_used = self.name
        return hits
