"""Public API: NewsClient.fetch().

Pipeline:
  1. Infer locales from ticker + business_geography
  2. Build per-locale queries with conventional name variants
  3. Fetch raw hits via MultiSourceFetcher (locale-native → Reuters → Bloomberg → Tavily fallback)
  4. Tag tier from sources registry; drop below min_tier
  5. Persistent dedup (per-consumer SeenStore) + cross-language clustering
  6. Locale-native promotion: ensure ≥1 non-EN item survives if any was found
  7. Translate + gloss top items (above min_tier, after dedup)
  8. Score + rank
  9. Persist seen hashes
 10. Return FetchResult with per-source counts + Tavily $-spend delta
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from news_core import dedup as _dedup
from news_core import fetch as _fetch
from news_core import locales as _locales
from news_core import queries as _queries
from news_core import ranking as _ranking
from news_core import sources as _sources
from news_core import translate as _translate
from news_core.budget import BudgetCenter
from news_core.cache import NewsCache
from news_core.schema import FetchRequest, FetchResult, NewsItem, Tier

log = logging.getLogger("news_core")


class NewsClient:
    """Multilingual news ingestion client.

    Construct once per consumer-app process. Lazy-initialises fetch + translate
    backends so consumers without API keys get a degraded but non-crashing path.
    """

    def __init__(
        self,
        cache_dir: str | Path = ".cache/news_core",
        consumer: Literal["pm_pulse", "deep_dive"] = "deep_dive",
        fetcher: _fetch.Fetcher | None = None,
        translator: _translate.Translator | None = None,
        budget: BudgetCenter | None = None,
        cache: NewsCache | None = None,
        tavily_cap_usd: float = 1.00,
        adapter_daily_cap: int = 200,
        no_tavily: bool = False,
    ):
        self.cache_dir = Path(cache_dir)
        self.consumer = consumer
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.seen = _dedup.SeenStore(self.cache_dir / f"news_seen_{consumer}.sqlite")
        self.fetcher = fetcher
        self.translator = translator
        # Shared cache + budget across PM Pulse + Deep Dive when both point at
        # the same cache_dir (e.g. ~/.cache/news_core).
        self.cache = cache or NewsCache(self.cache_dir / "news_cache.sqlite")
        self.budget = budget or BudgetCenter(
            self.cache_dir / "budget.sqlite",
            tavily_cap_usd=0.0 if no_tavily else tavily_cap_usd,
            adapter_daily_cap=adapter_daily_cap,
        )
        self.no_tavily = no_tavily

    # ------------------------------------------------------------------
    # Lazy backend init
    # ------------------------------------------------------------------
    def _get_fetcher(self) -> _fetch.Fetcher:
        """Build a MultiSourceFetcher with all adapters wired up.

        Falls back to StubFetcher when TAVILY_API_KEY is absent and no custom
        fetcher was injected — allows tests / no-key environments to run.
        """
        if self.fetcher is not None:
            return self.fetcher
        if not os.environ.get("TAVILY_API_KEY"):
            log.warning("TAVILY_API_KEY missing — using StubFetcher (no network)")
            self.fetcher = _fetch.StubFetcher()
            return self.fetcher

        # Build adapters. Tavily is shared between Bloomberg/Reuters/GoogleSite
        # (they record their own spend through the shared instance).
        from news_core.adapters import (
            BaiduAdapter, BloombergAdapter, GoogleSiteAdapter, NaverAdapter,
            ReutersAdapter, TavilyAdapter, YahooJapanAdapter,
        )
        tavily = TavilyAdapter(cache=self.cache, budget=self.budget)
        bloomberg = BloombergAdapter(tavily, cache=self.cache, budget=self.budget)
        reuters = ReutersAdapter(tavily, cache=self.cache, budget=self.budget)
        google_site = GoogleSiteAdapter(tavily, cache=self.cache, budget=self.budget)
        baidu = BaiduAdapter(cache=self.cache, budget=self.budget)
        yahoo_jp = YahooJapanAdapter(cache=self.cache, budget=self.budget)
        naver = NaverAdapter(cache=self.cache, budget=self.budget)

        adapters_by_locale: dict[str, list] = {
            "ja":    [yahoo_jp, reuters, bloomberg],
            "ko":    [naver, reuters, bloomberg],
            "zh-CN": [baidu, reuters, bloomberg],
            "zh-HK": [google_site, reuters, bloomberg],
            "zh-TW": [google_site, reuters, bloomberg],
            "de":    [google_site, reuters, bloomberg],
            "fr":    [google_site, reuters, bloomberg],
            "en":    [reuters, bloomberg],
        }

        self.fetcher = _fetch.MultiSourceFetcher(
            adapters_by_locale=adapters_by_locale,
            broad_tavily=tavily,
        )
        return self.fetcher

    def _get_translator(self) -> _translate.Translator:
        if self.translator is not None:
            return self.translator
        self.translator = _translate.HybridTranslator.from_env()
        return self.translator

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def fetch(
        self,
        ticker: str,
        company_name: str,
        business_geography: list[str] | None = None,
        lookback_hours: int = 72,
        max_items: int = 20,
        min_tier: Tier | int = Tier.TWO,
        region: str | None = None,
    ) -> FetchResult:
        if isinstance(min_tier, int):
            min_tier = Tier(min_tier)
        req = FetchRequest(
            ticker=ticker,
            company_name=company_name,
            business_geography=business_geography or [],
            lookback_hours=lookback_hours,
            max_items=max_items,
            min_tier=min_tier,
            consumer=self.consumer,
        )
        return self._run(req, region=region)

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------
    def _run(self, req: FetchRequest, region: str | None = None) -> FetchResult:
        locales = _locales.infer_locales(
            ticker=req.ticker,
            business_geography=req.business_geography,
            region=region,
        )
        qs = _queries.build_queries(req.ticker, req.company_name, locales)

        # MultiSourceFetcher fans out per-adapter internally, so client.py
        # only issues one search per (query, locale).
        raw_hits: list[_fetch.RawHit] = []
        fetcher = self._get_fetcher()

        # Capture pre-spend for delta telemetry (None if no budget — e.g. stub).
        pre_spend = self.budget.tavily.spent_today() if self.budget else 0.0

        with ThreadPoolExecutor(max_workers=min(8, max(1, len(qs)))) as pool:
            futures = [
                pool.submit(
                    fetcher.search,
                    q.query, q.locale, req.lookback_hours, 10, None, None,
                )
                for q in qs
            ]
            for fut in as_completed(futures):
                try:
                    raw_hits.extend(fut.result())
                except Exception as e:
                    log.debug("search failed: %s", e)

        # Per-source counts (for telemetry / digest footer).
        source_counts: dict[str, int] = {}
        for h in raw_hits:
            key = h.source_used or "unknown"
            source_counts[key] = source_counts.get(key, 0) + 1

        log.info("locales=%s queries=%d raw_hits=%d sources=%s",
                 locales, len(qs), len(raw_hits), source_counts)

        # Build the entity-name set for relevance filtering. A hit is tagged with
        # the ticker only if a name variant actually appears in title or snippet.
        entity_variants = _all_entity_variants(req.ticker, req.company_name, locales)

        # Promote raw hits to NewsItem with tier and locale resolved from registry.
        items: list[NewsItem] = []
        seen_urls: set[str] = set()
        dropped = 0
        malformed = 0
        for hit in raw_hits:
            if not hit.url or not hit.title or hit.url in seen_urls:
                malformed += 1
                continue
            seen_urls.add(hit.url)
            src = _sources.match_source(hit.url)
            tier = src.tier if src else Tier.THREE
            if tier.value > req.min_tier.value:
                dropped += 1
                continue
            # Source-registered locale wins over query locale (Reuters → "en"
            # even when surfaced from the JP query).
            item_locale = src.locale if src else hit.locale
            domain = src.domain if src else _domain_of(hit.url)
            source_name = src.name if src else domain

            blob = (hit.title + " " + (hit.snippet or "")).lower()
            entity_match = any(v.lower() in blob for v in entity_variants)
            entity_tags = [req.ticker] if entity_match else []

            try:
                items.append(NewsItem(
                    id=hit.stable_id(),
                    url=hit.url,
                    source_name=source_name,
                    source_domain=domain,
                    locale=item_locale,
                    tier=tier,
                    title_original=hit.title,
                    published_at=hit.published_at or datetime.now(timezone.utc),
                    fetched_at=datetime.now(timezone.utc),
                    raw_excerpt=hit.snippet,
                    entity_tags=entity_tags,
                    topic_tags=_infer_topic_tags(blob),
                    paywalled=hit.paywalled,
                    source_used=hit.source_used,
                ))
            except ValidationError as e:
                log.debug("skipping malformed hit url=%s: %s", hit.url, e)
                malformed += 1
        if malformed:
            log.info("dropped %d malformed/dup hits", malformed)

        # Drop items that don't mention the entity by name. Tier-S (regulatory
        # primary disclosures filed BY the named entity) is the only exception —
        # those are by definition about the named filer.
        before = len(items)
        items = [it for it in items if it.entity_tags or it.tier == Tier.S]
        log.info("entity filter: %d → %d items", before, len(items))

        # Persistent dedup (per-consumer) before clustering.
        items = self.seen.filter_unseen(items)

        reps, n_clusters = _dedup.dedup(items)

        # Translate + gloss top candidates only (cost discipline).
        reps = _ranking.rank(reps, query_entity_id=req.ticker)

        # Locale-native promotion (spec §3): if any non-EN item exists, ensure at
        # least one survives into the top-N output, even if its raw score sits
        # below the EN cutoff. Diversity-over-pure-score for breadth coverage.
        reps = _ranking.promote_locale_native(reps, top_n=req.max_items)
        reps = reps[: req.max_items]

        translator = self._get_translator()
        for it in reps:
            if it.locale != "en":
                try:
                    it.title_translated = translator.translate(it.title_original, src=it.locale, tgt="en")
                    if _is_substantive(it.raw_excerpt):
                        capped = _translate.truncate_to_sentences(it.raw_excerpt or "")
                        it.summary_translated = translator.translate(capped, src=it.locale, tgt="en")
                except Exception as e:
                    log.debug("translate failed for %s: %s", it.url, e)
            if _is_substantive(it.summary_translated or it.raw_excerpt):
                try:
                    it.analyst_gloss = translator.gloss(
                        title=it.title_translated or it.title_original,
                        summary=it.summary_translated or (it.raw_excerpt or ""),
                        ticker=req.ticker,
                        context={"company": req.company_name},
                    )
                except Exception as e:
                    log.debug("gloss failed for %s: %s", it.url, e)

        # Persist seen state.
        for it in reps:
            self.seen.mark_seen(it, ticker=req.ticker)

        post_spend = self.budget.tavily.spent_today() if self.budget else 0.0
        cap_remaining = self.budget.tavily.remaining_today() if self.budget else 0.0

        return FetchResult(
            items=reps,
            locales_queried=locales,
            queries_issued=len(qs),
            raw_hits=len(raw_hits),
            deduped_clusters=n_clusters,
            dropped_below_tier=dropped,
            source_counts=source_counts,
            tavily_spend_usd=round(max(0.0, post_spend - pre_spend), 6),
            tavily_cap_remaining_usd=round(cap_remaining, 6),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_HIGH_SIGNAL_TOPICS: dict[str, list[str]] = {
    "earnings":   ["earnings", "results", "guidance", "EPS", "revenue", "決算", "業績", "실적"],
    "mna":        ["acquire", "merger", "buyout", "stake", "tender", "M&A", "買収", "인수"],
    "capex":      ["capex", "capacity", "fab", "expansion", "投資", "설비"],
    "regulatory": ["antitrust", "fine", "probe", "investigation", "sanction", "export control",
                   "규제", "規制", "反垄断", "反壟斷"],
    "ownership":  ["stake", "secondary", "placement", "lockup", "13F", "shareholder", "持ち株", "株主"],
    "guidance":   ["guidance", "forecast", "outlook", "通期予想", "ガイダンス"],
    "segment":    ["segment", "division", "BU", "事業部"],
}


def _infer_topic_tags(text: str) -> list[str]:
    """Lightweight tag inference from snippet text. Pattern-based, no LLM."""
    if not text:
        return []
    lower = text.lower()
    tags: list[str] = []
    for tag, keywords in _HIGH_SIGNAL_TOPICS.items():
        if any(kw.lower() in lower for kw in keywords):
            tags.append(tag)
    return tags


def _domain_of(url: str) -> str:
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _all_entity_variants(ticker: str, company_name: str, locales: list[str]) -> list[str]:
    """Union of all locale-specific name variants for entity-match validation."""
    variants: set[str] = set()
    for loc in locales:
        for v in _queries.conventional_names(ticker, loc, fallback=company_name):
            if v and len(v) >= 2:  # skip noisy 1-char tokens
                variants.add(v)
    variants.add(company_name)
    variants.add(ticker)
    return sorted(variants, key=len, reverse=True)


# Minimum chars of substance before we burn translate/gloss tokens on it.
# Tavily often returns a 30-char site footer / "All quotes delayed ..." for
# content it couldn't extract. Don't gloss those.
_MIN_SUBSTANTIVE_CHARS = 80
_BOILERPLATE_MARKERS = (
    "all quotes are at least",
    "all quotes delayed",
    "data is provided",
    "this site uses cookies",
    "subscribe to read",
    "log in to read",
)


def _is_substantive(text: str | None) -> bool:
    if not text:
        return False
    if len(text) < _MIN_SUBSTANTIVE_CHARS:
        return False
    lower = text.lower()
    return not any(m in lower for m in _BOILERPLATE_MARKERS)
