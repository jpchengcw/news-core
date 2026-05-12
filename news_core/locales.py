"""Locale inference: ticker + business geography → ranked locale list.

Listing exchange suffix sets the *primary* locale.
business_geography hints add *secondary* locales (peer ecosystems, end-markets).
English is always appended as a fallback.
"""
from __future__ import annotations

from typing import Iterable

# Listing-exchange suffix → primary locale.
# Empty suffix (US listings) handled separately as "en".
EXCHANGE_SUFFIX_LOCALE: dict[str, str] = {
    ".T": "ja",        # Tokyo (TSE)
    ".TYO": "ja",
    ".OS": "ja",       # Osaka
    ".HK": "zh-HK",    # HKEX (mix of Cantonese/Trad Chinese coverage)
    ".SS": "zh-CN",    # Shanghai
    ".SH": "zh-CN",
    ".SZ": "zh-CN",    # Shenzhen
    ".KS": "ko",       # KRX KOSPI
    ".KQ": "ko",       # KOSDAQ
    ".KX": "ko",
    ".PA": "fr",       # Euronext Paris
    ".AS": "en",       # Amsterdam (English-dominant coverage; NL secondary if added)
    ".BR": "fr",       # Brussels
    ".DE": "de",       # XETRA
    ".F": "de",        # Frankfurt
    ".MI": "en",       # Borsa Italiana — IT not in scope yet, fallback EN
    ".MC": "en",       # Madrid
    ".L": "en",        # LSE
    ".SW": "de",       # SIX Zurich
    ".TO": "en",       # Toronto
    ".AX": "en",       # ASX
    ".SI": "en",       # SGX
    ".TW": "zh-TW",    # Taiwan (when added)
    ".TWO": "zh-TW",
}

# Business-geography tag → list of additional locales the report should pull.
# These come from universe.csv `region` / sub-sector or are passed explicitly via API.
GEOGRAPHY_LOCALE_HINTS: dict[str, list[str]] = {
    # Asia tech / hardware ecosystems
    "global_memory":     ["ja", "ko"],          # NAND/DRAM peer ecosystem
    "global_semis":      ["zh-TW", "ko", "ja"], # foundry + memory + equipment
    "global_foundry":    ["zh-TW", "ko"],
    "global_displays":   ["ko", "ja", "zh-CN"],
    # China clusters
    "china_internet":    ["zh-CN", "zh-HK"],
    "china_evs":         ["zh-CN", "ja", "ko"],
    "china_consumer":    ["zh-CN", "zh-HK"],
    "china_ai":          ["zh-CN", "zh-HK"],
    "china_semi":        ["zh-CN", "zh-TW", "ja", "ko"],
    # Japan-specific
    "japan_dom":         ["ja"],
    "japan_industrials": ["ja", "de"],
    "japan_autos":       ["ja", "de", "ko", "zh-CN"],
    # Korea
    "korea_dom":         ["ko"],
    "korea_industrials": ["ko", "ja"],
    # Europe
    "luxury_eu":         ["fr", "zh-CN"],   # Chinese consumer is the read-through market
    "europe_industrials":["de", "fr"],
    "europe_autos":      ["de", "fr", "zh-CN"],
    # US / global EN-only
    "us_megacap":        [],
    "us_dom":            [],
    "global_en":         [],
}

# Region code from universe.csv → fallback locale hints when no specific tag is given.
REGION_FALLBACK: dict[str, list[str]] = {
    "JP": ["ja"],
    "HK": ["zh-HK", "zh-CN"],
    "CN": ["zh-CN", "zh-HK"],
    "KR": ["ko"],
    "TW": ["zh-TW", "zh-CN"],
    "DE": ["de"],
    "FR": ["fr"],
    "EU": ["de", "fr"],
    "US": [],
    "UK": [],
    "GB": [],
    "GLOBAL": [],
}


def _suffix_locale(ticker: str) -> str:
    """Return primary locale from ticker suffix; 'en' if no recognised suffix (US listing)."""
    if "." not in ticker:
        return "en"
    suffix = "." + ticker.rsplit(".", 1)[1]
    return EXCHANGE_SUFFIX_LOCALE.get(suffix, "en")


def infer_locales(
    ticker: str,
    business_geography: Iterable[str] = (),
    region: str | None = None,
) -> list[str]:
    """Return ordered locale list (primary first, EN always last unless already primary).

    De-duplicates while preserving order. Caller decides how many to actually query.
    """
    ordered: list[str] = []

    primary = _suffix_locale(ticker)
    ordered.append(primary)

    if region:
        for loc in REGION_FALLBACK.get(region.upper(), []):
            if loc not in ordered:
                ordered.append(loc)

    for tag in business_geography:
        for loc in GEOGRAPHY_LOCALE_HINTS.get(tag, []):
            if loc not in ordered:
                ordered.append(loc)

    if "en" not in ordered:
        ordered.append("en")

    return ordered
