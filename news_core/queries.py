"""Multilingual query construction.

Per-locale queries use locale-conventional name variants (e.g. キオクシア for JP)
so the search engine ranks the right sources. Fallback: company_name + ticker.

Conventional names are looked up in CONVENTIONAL_NAMES; unknown tickers fall
back to a passed-in display name. The downstream agent (news fetch / NewsCore
caller) is responsible for keeping CONVENTIONAL_NAMES current for the universe.
"""
from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Conventional name table — minimal seed for canary names. Extend as universe grows.
# Keyed by ticker; value is a dict of locale → list[str] of search-ready name variants.
# ---------------------------------------------------------------------------
CONVENTIONAL_NAMES: dict[str, dict[str, list[str]]] = {
    # Kioxia (JPX:285A.T) — JP canary. Includes katakana + romaji + ticker.
    "285A.T": {
        "ja":    ["キオクシア", "キオクシアホールディングス", "Kioxia", "285A"],
        "ko":    ["키오시아", "Kioxia"],
        "en":    ["Kioxia", "Kioxia Holdings", "285A"],
    },
    # Tencent (HKEX:0700.HK)
    "0700.HK": {
        "zh-HK": ["騰訊", "騰訊控股", "Tencent"],
        "zh-CN": ["腾讯", "腾讯控股", "Tencent"],
        "en":    ["Tencent", "Tencent Holdings", "0700"],
    },
    # Horizon Robotics (HKEX:9660.HK)
    "9660.HK": {
        "zh-HK": ["地平線", "地平線機器人", "Horizon Robotics"],
        "zh-CN": ["地平线", "地平线机器人", "Horizon Robotics"],
        "en":    ["Horizon Robotics", "9660"],
    },
    # Samsung Electronics (KRX:005930.KS)
    "005930.KS": {
        "ko":    ["삼성전자", "Samsung Electronics"],
        "ja":    ["サムスン電子", "Samsung"],
        "en":    ["Samsung Electronics", "Samsung", "005930"],
    },
    # SK hynix
    "000660.KS": {
        "ko":    ["SK하이닉스", "하이닉스", "SK Hynix"],
        "ja":    ["SKハイニックス", "ハイニックス"],
        "en":    ["SK Hynix", "SK hynix", "000660"],
    },
    # Toyota
    "7203.T": {
        "ja":    ["トヨタ", "トヨタ自動車", "Toyota"],
        "de":    ["Toyota"],
        "en":    ["Toyota", "Toyota Motor", "7203"],
    },
    # LVMH
    "MC.PA": {
        "fr":    ["LVMH", "Louis Vuitton Moët Hennessy"],
        "zh-CN": ["LVMH", "路威酩轩"],
        "en":    ["LVMH", "MC.PA"],
    },
    # Meta
    "META": {
        "en":    ["Meta", "Meta Platforms", "Facebook"],
    },
    # NVIDIA
    "NVDA": {
        "en":    ["NVIDIA", "NVDA"],
        "zh-CN": ["英伟达", "NVIDIA"],
        "ja":    ["エヌビディア", "NVIDIA"],
        "ko":    ["엔비디아", "NVIDIA"],
    },
    # SMIC (HK + A-share dual list)
    "0981.HK": {
        "zh-HK": ["中芯國際", "SMIC"],
        "zh-CN": ["中芯国际", "SMIC"],
        "en":    ["SMIC", "Semiconductor Manufacturing", "0981"],
    },
}


@dataclass
class Query:
    """A locale-scoped search query plus the variant names it uses."""
    locale: str
    query: str
    variants: list[str]


def conventional_names(ticker: str, locale: str, fallback: str) -> list[str]:
    """Return locale-specific name variants for `ticker`, falling back to `fallback`.

    Always appends the bare ticker as a final variant (helps when local press
    cites the listing code, e.g. "(285A)").
    """
    table = CONVENTIONAL_NAMES.get(ticker, {})
    names = list(table.get(locale, []))
    if not names:
        names = [fallback]
    if ticker not in names:
        names.append(ticker)
    # Strip the listing suffix variant ("285A.T" → "285A") for cleaner local-language hits.
    bare = ticker.split(".")[0]
    if bare and bare != ticker and bare not in names:
        names.append(bare)
    # De-dup preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def build_query(locale: str, variants: list[str]) -> str:
    """Build a single search-engine query string from name variants.

    Quoted-OR construction works on Tavily, Google, Bing, Naver, Yahoo Japan,
    Baidu, and DuckDuckGo. Most locale-specific engines handle it identically.
    """
    quoted = [f'"{v}"' for v in variants if v]
    return " OR ".join(quoted)


def build_queries(
    ticker: str,
    company_name: str,
    locales: list[str],
) -> list[Query]:
    """Build one Query per locale for the given ticker."""
    queries: list[Query] = []
    for locale in locales:
        variants = conventional_names(ticker, locale, fallback=company_name)
        queries.append(Query(locale=locale, query=build_query(locale, variants), variants=variants))
    return queries
