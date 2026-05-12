"""Naver News adapter — HTML scrape of search.naver.com news vertical.

Naver is the dominant Korean news aggregator. Its SERP exposes title, snippet,
publisher, and time. Anchors point to publisher sites (Chosun BIZ, Hankyung,
Maeil, The Bell, etc.) — the very Tier-1 KR sources we already register.
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

log = logging.getLogger("news_core.adapters.naver")

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class NaverAdapter(BaseAdapter):
    name = "naver"

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
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
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
        if locale != "ko":
            return []
        url = (
            "https://search.naver.com/search.naver"
            f"?where=news&sm=tab_jum&query={urllib.parse.quote(query)}"
        )
        try:
            resp = self._http.get(url)
            if resp.status_code in (429, 503):
                raise _Transient(f"naver {resp.status_code}")
            if resp.status_code >= 400:
                return []
            html = resp.text
        except httpx.HTTPError as e:
            raise _Transient(f"naver http: {e}") from e

        return _parse_naver_serp(html, lookback_hours=lookback_hours)


_T_MIN = re.compile(r"(\d+)\s*분\s*전")
_T_HOUR = re.compile(r"(\d+)\s*시간\s*전")
_T_DAY = re.compile(r"(\d+)\s*일\s*전")
_T_DATE = re.compile(r"(\d{4})\.(\d{1,2})\.(\d{1,2})")


def _parse_naver_serp(html: str, lookback_hours: int) -> list[RawHit]:
    soup = BeautifulSoup(html, "lxml")
    out: list[RawHit] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    # Each result lives in <li class="bx"> (preferred). Fall back to
    # `.news_wrap` only when `li.bx` is absent — they're often nested, and
    # double-matching produces duplicate hits.
    blocks = soup.select("li.bx") or soup.select("div.news_wrap")
    for block in blocks:
        title_a = block.select_one("a.news_tit") or block.find("a", href=True)
        if not title_a:
            continue
        url = title_a.get("href", "").strip()
        title = title_a.get("title") or title_a.get_text(" ", strip=True)
        if not url.startswith("http") or not title:
            continue

        desc = ""
        desc_node = block.select_one(".news_dsc, .api_txt_lines.dsc_txt_wrap, p")
        if desc_node:
            desc = desc_node.get_text(" ", strip=True)[:400]

        meta_text = ""
        info = block.select_one(".info_group, .news_info")
        if info:
            meta_text = info.get_text(" ", strip=True)

        published = _parse_naver_time(meta_text)
        if published and published < cutoff:
            continue

        out.append(RawHit(
            url=url,
            title=title,
            snippet=desc,
            locale="ko",
            published_at=published,
            raw_metadata={"source_meta": meta_text, "engine": "naver"},
            source_used="naver",
        ))

    log.debug("naver parsed %d hits", len(out))
    return out


def _parse_naver_time(text: str) -> datetime | None:
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
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except ValueError:
            return None
    return None
