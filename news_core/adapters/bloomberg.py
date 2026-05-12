"""Bloomberg adapter.

Discovery: Tavily with `include_domains=["bloomberg.com"]` — Bloomberg's on-site
search is JS-heavy and unreliable; Google site-search via SERP gets reCAPTCHA-
blocked. Tavily indexes Bloomberg directly, returning article URLs.

Enrichment: each URL is GET-ed via httpx and parsed for OpenGraph / Schema.org
meta tags. Bloomberg's hard paywall blocks the body but headline, dek, publish
date, and (often) the first 150 words are exposed in page metadata.

Hard paywall: when meta returns nothing usable, we keep the Tavily snippet and
mark `paywalled=True`. Still useful as a digest signal — the headline alone is
high-tier news.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING

import httpx
from bs4 import BeautifulSoup

from news_core.adapters._base import BaseAdapter, _Transient
from news_core.fetch import RawHit

if TYPE_CHECKING:
    from news_core.adapters.tavily import TavilyAdapter
    from news_core.budget import BudgetCenter
    from news_core.cache import NewsCache

log = logging.getLogger("news_core.adapters.bloomberg")

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
)


class BloombergAdapter(BaseAdapter):
    name = "bloomberg"
    # Discovery rides on Tavily, so this adapter does NOT itself spend Tavily $;
    # the inner TavilyAdapter call records that. We still respect the daily quota.
    counts_against_tavily_budget = False

    def __init__(
        self,
        tavily_adapter: "TavilyAdapter",
        cache: "NewsCache | None" = None,
        budget: "BudgetCenter | None" = None,
        http_timeout: float = 8.0,
    ):
        super().__init__(cache=cache, budget=budget)
        self._tav = tavily_adapter
        self._http = httpx.Client(
            timeout=http_timeout,
            headers={"User-Agent": _USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
            follow_redirects=True,
        )

    def _search_impl(
        self,
        query: str,
        locale: str,
        lookback_hours: int,
        max_results: int,
        include_domains: list[str] | None,
        exclude_domains: list[str] | None,
    ) -> list[RawHit]:
        # Discovery via Tavily restricted to bloomberg.com
        # (any caller-provided include_domains is ignored — Bloomberg adapter is
        # already domain-scoped.)
        seed = self._tav.search(
            query=query,
            locale=locale,
            lookback_hours=lookback_hours,
            max_results=max_results,
            include_domains=["bloomberg.com"],
        )

        out: list[RawHit] = []
        for hit in seed:
            if "bloomberg.com" not in hit.url:
                continue
            enriched = self._enrich(hit)
            out.append(enriched)
        return out

    def _enrich(self, hit: RawHit) -> RawHit:
        body_cache = self.cache.get_body(hit.url) if self.cache else None
        if body_cache is not None:
            html = body_cache
        else:
            try:
                resp = self._http.get(hit.url)
                if resp.status_code in (429, 503):
                    raise _Transient(f"bloomberg fetch {resp.status_code}")
                if resp.status_code >= 400:
                    log.debug("bloomberg fetch %s -> %s", hit.url, resp.status_code)
                    html = ""
                else:
                    html = resp.text
            except httpx.HTTPError as e:
                log.debug("bloomberg fetch error %s: %s", hit.url, e)
                html = ""
            if self.cache is not None and html:
                self.cache.put_body(hit.url, html)

        meta = _parse_bloomberg_meta(html) if html else {}
        title = meta.get("title") or hit.title
        dek = meta.get("description") or ""
        first_para = meta.get("first_paragraph") or ""
        published = meta.get("published_at") or hit.published_at

        body_text = " ".join([s for s in (dek, first_para) if s]).strip()
        snippet = body_text or hit.snippet
        # If we got nothing past metadata title, mark paywalled.
        paywalled = not body_text and not _has_substantive(hit.snippet)

        return RawHit(
            url=hit.url,
            title=title,
            snippet=snippet,
            locale=hit.locale,
            published_at=published,
            raw_metadata={**hit.raw_metadata, "bloomberg_meta": meta},
            paywalled=paywalled,
            source_used=self.name,
        )


# ---------------------------------------------------------------------------
# Meta extraction
# ---------------------------------------------------------------------------
def _parse_bloomberg_meta(html: str) -> dict:
    """Extract OpenGraph + Schema.org + first-paragraph from Bloomberg HTML."""
    if not html:
        return {}
    soup = BeautifulSoup(html, "lxml")

    def _meta(prop: str) -> str | None:
        tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
        if tag and tag.get("content"):
            return tag["content"].strip()
        return None

    title = _meta("og:title") or (soup.title.string.strip() if soup.title and soup.title.string else None)
    description = _meta("og:description") or _meta("description")

    # First paragraph: above-the-fold body. Bloomberg uses class="body-content"
    # or article paragraph blocks. Be generous about matching.
    first_paragraph = None
    for selector in [
        ('div', {'class': re.compile(r'body-content', re.I)}),
        ('div', {'class': re.compile(r'article.*body', re.I)}),
        ('article', {}),
    ]:
        node = soup.find(*selector)
        if node:
            p = node.find("p")
            if p and p.get_text(strip=True):
                first_paragraph = p.get_text(strip=True)[:600]
                break

    published_at = None
    pub = _meta("article:published_time") or _meta("og:article:published_time")
    if pub:
        try:
            published_at = datetime.fromisoformat(pub.replace("Z", "+00:00"))
        except Exception:
            published_at = None

    return {
        "title": title,
        "description": description,
        "first_paragraph": first_paragraph,
        "published_at": published_at,
    }


def _has_substantive(text: str | None) -> bool:
    return bool(text) and len(text.strip()) >= 60
