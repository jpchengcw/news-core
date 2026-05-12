"""Reuters adapter.

Discovery: Tavily with `include_domains=["reuters.com"]`. Reuters allows public
read; we GET each URL and parse the first 2-3 paragraphs for snippet enrichment
when Tavily's snippet is sparse.
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

log = logging.getLogger("news_core.adapters.reuters")

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
)
_MIN_TAVILY_SNIPPET_LEN = 120


class ReutersAdapter(BaseAdapter):
    name = "reuters"
    counts_against_tavily_budget = False  # discovery's TavilyAdapter records the spend

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
        seed = self._tav.search(
            query=query,
            locale=locale,
            lookback_hours=lookback_hours,
            max_results=max_results,
            include_domains=["reuters.com"],
        )

        out: list[RawHit] = []
        for hit in seed:
            if "reuters.com" not in hit.url:
                continue
            # Reuters is largely free — only enrich when Tavily snippet is too short.
            if len(hit.snippet or "") >= _MIN_TAVILY_SNIPPET_LEN:
                hit.source_used = self.name
                out.append(hit)
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
                    raise _Transient(f"reuters fetch {resp.status_code}")
                html = resp.text if resp.status_code < 400 else ""
            except httpx.HTTPError as e:
                log.debug("reuters fetch error %s: %s", hit.url, e)
                html = ""
            if self.cache is not None and html:
                self.cache.put_body(hit.url, html)

        meta = _parse_reuters(html) if html else {}
        title = meta.get("title") or hit.title
        snippet = meta.get("body") or hit.snippet
        published = meta.get("published_at") or hit.published_at

        return RawHit(
            url=hit.url,
            title=title,
            snippet=snippet,
            locale=hit.locale,
            published_at=published,
            raw_metadata={**hit.raw_metadata},
            source_used=self.name,
        )


def _parse_reuters(html: str) -> dict:
    if not html:
        return {}
    soup = BeautifulSoup(html, "lxml")

    def _meta(prop: str) -> str | None:
        tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
        if tag and tag.get("content"):
            return tag["content"].strip()
        return None

    title = _meta("og:title") or (soup.title.string.strip() if soup.title and soup.title.string else None)
    description = _meta("og:description") or _meta("description") or ""

    # Reuters article body: first 2-3 paragraphs. They use various class names —
    # "article-body", "Body__content", or just <article><p>...</p></article>.
    paras: list[str] = []
    for selector in [
        ('div', {'class': re.compile(r'article.*body|Body__content', re.I)}),
        ('article', {}),
    ]:
        node = soup.find(*selector)
        if node:
            for p in node.find_all("p", limit=4):
                text = p.get_text(strip=True)
                if text and len(text) > 40:
                    paras.append(text)
                if len(paras) >= 3:
                    break
            if paras:
                break

    body = " ".join([description] + paras).strip()[:1200] if paras else (description or "")

    published_at = None
    pub = _meta("article:published_time") or _meta("og:article:published_time")
    if pub:
        try:
            published_at = datetime.fromisoformat(pub.replace("Z", "+00:00"))
        except Exception:
            published_at = None

    return {"title": title, "body": body, "published_at": published_at}
