"""Yahoo Japan News adapter — HTML scrape of news.yahoo.co.jp/search.

Yahoo Japan aggregates Japanese-language press from Nikkei, Toyo Keizai, NHK,
Kyodo, etc. — exactly the publishers we want for JP names. The search SERP
exposes title, source, snippet, and a relative time string.
"""
from __future__ import annotations

import logging
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import httpx
from bs4 import BeautifulSoup

from news_core.adapters._base import BaseAdapter, _Transient
from news_core.fetch import RawHit

if TYPE_CHECKING:
    from news_core.budget import BudgetCenter
    from news_core.cache import NewsCache

log = logging.getLogger("news_core.adapters.yahoo_japan")

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
)


class YahooJapanAdapter(BaseAdapter):
    name = "yahoo_japan"

    def __init__(
        self,
        cache: "NewsCache | None" = None,
        budget: "BudgetCenter | None" = None,
        http_timeout: float = 8.0,
    ):
        super().__init__(cache=cache, budget=budget)
        self._http = httpx.Client(
            timeout=http_timeout,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml",
            },
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
        if locale != "ja":
            return []
        url = (
            "https://news.yahoo.co.jp/search"
            f"?p={urllib.parse.quote(query)}&ei=UTF-8"
        )
        try:
            resp = self._http.get(url)
            if resp.status_code in (429, 503):
                raise _Transient(f"yahoo_jp {resp.status_code}")
            if resp.status_code >= 400:
                return []
            html = resp.text
        except httpx.HTTPError as e:
            raise _Transient(f"yahoo_jp http: {e}") from e

        return _parse_yahoo_jp_serp(html, lookback_hours=lookback_hours)


# Relative-time formats: "1時間前", "30分前", "2日前", "3/15(金) 14:30"
_T_HOUR = re.compile(r"(\d+)\s*時間前")
_T_MIN = re.compile(r"(\d+)\s*分前")
_T_DAY = re.compile(r"(\d+)\s*日前")
_T_DATE = re.compile(r"(\d{1,2})/(\d{1,2})")  # MM/DD


def _parse_yahoo_jp_serp(html: str, lookback_hours: int) -> list[RawHit]:
    soup = BeautifulSoup(html, "lxml")
    out: list[RawHit] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    # Each result is in <li class="newsFeed_item"> or <a class="newsFeed_item_link">
    # but layout has shifted; match generously.
    items = soup.select("li.newsFeed_item, div.sw-CardBase, article")
    for item in items:
        a = item.find("a", href=True)
        if not a:
            continue
        href = a["href"]
        if not href.startswith("http"):
            continue
        # Skip Yahoo Japan internal pages that aren't articles
        if "/search" in href:
            continue

        title_node = item.select_one(".newsFeed_item_title, h3, .sw-Card_title")
        title = title_node.get_text(" ", strip=True) if title_node else a.get_text(" ", strip=True)
        if not title or len(title) < 4:
            continue

        snippet = ""
        sn = item.select_one(".newsFeed_item_detail, .sw-Card_summary, p")
        if sn:
            snippet = sn.get_text(" ", strip=True)[:400]

        meta_text = ""
        meta_node = item.select_one(".newsFeed_item_sub, .sw-Card_sub, .sub")
        if meta_node:
            meta_text = meta_node.get_text(" ", strip=True)

        published = _parse_yahoo_jp_time(meta_text or item.get_text(" ", strip=True))
        if published and published < cutoff:
            continue

        out.append(RawHit(
            url=href,
            title=title,
            snippet=snippet,
            locale="ja",
            published_at=published,
            raw_metadata={"source_meta": meta_text, "engine": "yahoo_japan"},
            source_used="yahoo_japan",
        ))

    if not out:
        log.warning("yahoo_japan parsed 0 hits (selector drift or 403?)")
    else:
        log.info("yahoo_japan parsed %d hits", len(out))
    return out


def _parse_yahoo_jp_time(text: str) -> datetime | None:
    if not text:
        return None
    now = datetime.now(timezone.utc)
    if m := _T_MIN.search(text):
        return now - timedelta(minutes=int(m.group(1)))
    if m := _T_HOUR.search(text):
        return now - timedelta(hours=int(m.group(1)))
    if m := _T_DAY.search(text):
        return now - timedelta(days=int(m.group(1)))
    if m := _T_DATE.search(text):
        try:
            return datetime(now.year, int(m.group(1)), int(m.group(2)), tzinfo=timezone.utc)
        except ValueError:
            return None
    return None
