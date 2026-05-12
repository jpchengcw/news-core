"""Baidu News adapter — HTML scrape of news.baidu.com / baidu.com news vertical.

Baidu has no public API and its HTML structure shifts. We extract what's
structurally stable: each result block has an anchor with article URL + title,
a description span, and a meta line with source + time. Anything we can't
parse cleanly we drop — the downstream entity filter + tier scoring will
re-validate via `match_source()`.

CI note: GitHub-hosted runner IPs trigger Baidu's wappass captcha challenge
on every request (302 → wappass.baidu.com), making this adapter useless from
GHA. We short-circuit when GITHUB_ACTIONS=true to avoid wasting per-engine
quota slots on guaranteed-zero calls.
"""
from __future__ import annotations

import logging
import os
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

log = logging.getLogger("news_core.adapters.baidu")

# Realistic UA — Baidu's bot detection is moderate; UA + Accept-Language
# headers are usually enough for the news vertical.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class BaiduAdapter(BaseAdapter):
    name = "baidu"

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
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
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
        if locale not in ("zh-CN", "zh-HK"):
            return []
        if os.environ.get("GITHUB_ACTIONS") == "true":
            log.info("baidu: skipping in GitHub Actions (captcha-blocked from GHA IPs)")
            return []
        url = (
            "https://www.baidu.com/s"
            f"?tn=news&rtt=1&cl=2&rsv_dl=ns_pc&word={urllib.parse.quote(query)}"
            f"&rn={min(max_results * 2, 30)}"
        )
        try:
            resp = self._http.get(url)
            if resp.status_code in (429, 503):
                raise _Transient(f"baidu {resp.status_code}")
            if resp.status_code >= 400:
                return []
            html = resp.text
        except httpx.HTTPError as e:
            raise _Transient(f"baidu http: {e}") from e

        return _parse_baidu_serp(html, locale=locale, lookback_hours=lookback_hours)


# ---------------------------------------------------------------------------
# Parser (also exported for tests)
# ---------------------------------------------------------------------------
_TIME_HOURS = re.compile(r"(\d+)\s*小时前")
_TIME_MIN = re.compile(r"(\d+)\s*分钟前")
_TIME_DAYS = re.compile(r"(\d+)\s*天前")
_TIME_DATE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")


def _parse_baidu_serp(html: str, locale: str, lookback_hours: int) -> list[RawHit]:
    soup = BeautifulSoup(html, "lxml")
    out: list[RawHit] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    # Baidu wraps each news result in <div class="result-op c-container ...">.
    # Be permissive — fall back to any block with a c-container class.
    blocks = soup.select("div.result-op, div.c-container")
    for block in blocks:
        a = block.find("a", href=True)
        if not a:
            continue
        url = a["href"].strip()
        title = a.get_text(" ", strip=True)
        if not url or not title or len(title) < 4:
            continue
        # Skip Baidu's own redirect-only links if we can't extract a real URL.
        if not (url.startswith("http://") or url.startswith("https://")):
            continue

        # Description.
        desc = ""
        desc_node = block.select_one("span.c-summary, .c-row .c-summary, .c-color-text")
        if desc_node:
            desc = desc_node.get_text(" ", strip=True)
        if not desc:
            # Fallback: any <span> with substantive text.
            for span in block.find_all("span"):
                t = span.get_text(" ", strip=True)
                if len(t) > 30 and t != title:
                    desc = t[:400]
                    break

        # Time + source line.
        meta_text = ""
        meta_node = block.select_one(".c-color-gray, .c-color-gray2, .news-source")
        if meta_node:
            meta_text = meta_node.get_text(" ", strip=True)

        published = _parse_baidu_time(meta_text)
        if published and published < cutoff:
            continue

        out.append(RawHit(
            url=url,
            title=title,
            snippet=desc,
            locale=locale,
            published_at=published,
            raw_metadata={"source_meta": meta_text, "engine": "baidu"},
            source_used="baidu",
        ))

    # Promote to WARNING when we got nothing — that's the signature of
    # selector drift OR a captcha redirect, both of which want triage.
    if not out:
        log.warning("baidu parsed 0 hits from %d blocks (selector drift or captcha?)", len(blocks))
    else:
        log.info("baidu parsed %d hits from %d blocks", len(out), len(blocks))
    return out


def _parse_baidu_time(text: str) -> datetime | None:
    if not text:
        return None
    now = datetime.now(timezone.utc)
    if m := _TIME_MIN.search(text):
        return now - timedelta(minutes=int(m.group(1)))
    if m := _TIME_HOURS.search(text):
        return now - timedelta(hours=int(m.group(1)))
    if m := _TIME_DAYS.search(text):
        return now - timedelta(days=int(m.group(1)))
    if m := _TIME_DATE.search(text):
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except ValueError:
            return None
    return None
