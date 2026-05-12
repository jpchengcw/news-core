"""Source registry: domain → (locale, tier, name, regions).

These are *priors*, not a hard whitelist. Items from unregistered domains are
allowed but score lower. S-tier and high-conviction Tier-2 trade press are the
edge: surface them prominently even when not yet on Tier-1 wires.
"""
from __future__ import annotations

from urllib.parse import urlparse

from news_core.schema import Source, Tier

# ---------------------------------------------------------------------------
# Tier S — regulatory / company primary
# ---------------------------------------------------------------------------
_S_TIER: list[Source] = [
    # Filings & exchange disclosures
    Source(name="SEC EDGAR", domain="sec.gov", locale="en", tier=Tier.S, regions=["US"]),
    Source(name="HKEXnews", domain="hkexnews.hk", locale="en", tier=Tier.S, regions=["HK","CN"]),
    Source(name="HKEX", domain="hkex.com.hk", locale="en", tier=Tier.S, regions=["HK"]),
    Source(name="TDnet", domain="tdnet.info", locale="ja", tier=Tier.S, regions=["JP"]),
    Source(name="EDINET", domain="disclosure.edinet-fsa.go.jp", locale="ja", tier=Tier.S, regions=["JP"]),
    Source(name="JPX", domain="jpx.co.jp", locale="ja", tier=Tier.S, regions=["JP"]),
    Source(name="DART", domain="dart.fss.or.kr", locale="ko", tier=Tier.S, regions=["KR"]),
    Source(name="KIND", domain="kind.krx.co.kr", locale="ko", tier=Tier.S, regions=["KR"]),
    Source(name="CSRC", domain="csrc.gov.cn", locale="zh-CN", tier=Tier.S, regions=["CN"]),
    Source(name="SSE", domain="sse.com.cn", locale="zh-CN", tier=Tier.S, regions=["CN"]),
    Source(name="SZSE", domain="szse.cn", locale="zh-CN", tier=Tier.S, regions=["CN"]),
    Source(name="Bundesanzeiger", domain="bundesanzeiger.de", locale="de", tier=Tier.S, regions=["DE"]),
    Source(name="AMF", domain="amf-france.org", locale="fr", tier=Tier.S, regions=["FR"]),
    Source(name="MOF Japan", domain="mof.go.jp", locale="ja", tier=Tier.S, regions=["JP"]),
    Source(name="METI", domain="meti.go.jp", locale="ja", tier=Tier.S, regions=["JP"]),
]

# ---------------------------------------------------------------------------
# Tier 1 — top-tier financial press
# ---------------------------------------------------------------------------
_TIER_1: list[Source] = [
    # English global wires
    Source(name="Bloomberg", domain="bloomberg.com", locale="en", tier=Tier.ONE, regions=["global"]),
    Source(name="Reuters", domain="reuters.com", locale="en", tier=Tier.ONE, regions=["global"]),
    Source(name="Financial Times", domain="ft.com", locale="en", tier=Tier.ONE, regions=["global"]),
    Source(name="WSJ", domain="wsj.com", locale="en", tier=Tier.ONE, regions=["global"]),
    Source(name="Nikkei Asia", domain="asia.nikkei.com", locale="en", tier=Tier.ONE, regions=["AS","JP"]),
    # Japanese
    Source(name="Nikkei", domain="nikkei.com", locale="ja", tier=Tier.ONE, regions=["JP"]),
    Source(name="Toyo Keizai", domain="toyokeizai.net", locale="ja", tier=Tier.ONE, regions=["JP"]),
    Source(name="Diamond", domain="diamond.jp", locale="ja", tier=Tier.ONE, regions=["JP"]),
    Source(name="Asahi Shimbun", domain="asahi.com", locale="ja", tier=Tier.ONE, regions=["JP"]),
    Source(name="Yomiuri", domain="yomiuri.co.jp", locale="ja", tier=Tier.ONE, regions=["JP"]),
    Source(name="NHK", domain="nhk.or.jp", locale="ja", tier=Tier.ONE, regions=["JP"]),
    Source(name="Mainichi", domain="mainichi.jp", locale="ja", tier=Tier.ONE, regions=["JP"]),
    # Chinese mainland & HK
    Source(name="Caixin", domain="caixin.com", locale="zh-CN", tier=Tier.ONE, regions=["CN"]),
    Source(name="Caixin Global", domain="caixinglobal.com", locale="en", tier=Tier.ONE, regions=["CN"]),
    Source(name="Yicai", domain="yicai.com", locale="zh-CN", tier=Tier.ONE, regions=["CN"]),
    Source(name="21st Century Business Herald", domain="21jingji.com", locale="zh-CN", tier=Tier.ONE, regions=["CN"]),
    Source(name="Securities Times", domain="stcn.com", locale="zh-CN", tier=Tier.ONE, regions=["CN"]),
    Source(name="China Securities Journal", domain="cs.com.cn", locale="zh-CN", tier=Tier.ONE, regions=["CN"]),
    Source(name="SCMP", domain="scmp.com", locale="en", tier=Tier.ONE, regions=["HK","CN"]),
    Source(name="Ming Pao", domain="mingpao.com", locale="zh-HK", tier=Tier.ONE, regions=["HK"]),
    Source(name="HKET", domain="hket.com", locale="zh-HK", tier=Tier.ONE, regions=["HK"]),
    Source(name="HK01", domain="hk01.com", locale="zh-HK", tier=Tier.ONE, regions=["HK"]),
    # Korean
    Source(name="Chosun BIZ", domain="biz.chosun.com", locale="ko", tier=Tier.ONE, regions=["KR"]),
    Source(name="Maeil Business", domain="mk.co.kr", locale="ko", tier=Tier.ONE, regions=["KR"]),
    Source(name="Hankyung", domain="hankyung.com", locale="ko", tier=Tier.ONE, regions=["KR"]),
    Source(name="Yonhap Infomax", domain="news.einfomax.co.kr", locale="ko", tier=Tier.ONE, regions=["KR"]),
    Source(name="Yonhap", domain="yna.co.kr", locale="ko", tier=Tier.ONE, regions=["KR"]),
    Source(name="The Bell", domain="thebell.co.kr", locale="ko", tier=Tier.ONE, regions=["KR"]),
    # German
    Source(name="Handelsblatt", domain="handelsblatt.com", locale="de", tier=Tier.ONE, regions=["DE"]),
    Source(name="FAZ", domain="faz.net", locale="de", tier=Tier.ONE, regions=["DE"]),
    Source(name="Manager Magazin", domain="manager-magazin.de", locale="de", tier=Tier.ONE, regions=["DE"]),
    Source(name="Boersen-Zeitung", domain="boersen-zeitung.de", locale="de", tier=Tier.ONE, regions=["DE"]),
    # French
    Source(name="Les Echos", domain="lesechos.fr", locale="fr", tier=Tier.ONE, regions=["FR"]),
    Source(name="Le Figaro", domain="lefigaro.fr", locale="fr", tier=Tier.ONE, regions=["FR"]),
    Source(name="L'Agefi", domain="agefi.fr", locale="fr", tier=Tier.ONE, regions=["FR"]),
    Source(name="La Tribune", domain="latribune.fr", locale="fr", tier=Tier.ONE, regions=["FR"]),
]

# ---------------------------------------------------------------------------
# Tier 2 — industry trade press, sell-side excerpts, regulatory media
# ---------------------------------------------------------------------------
_TIER_2: list[Source] = [
    # Semis / hardware trade
    Source(name="DigiTimes", domain="digitimes.com", locale="en", tier=Tier.TWO, regions=["TW","global"]),
    Source(name="DigiTimes Asia", domain="digitimes.com.tw", locale="zh-TW", tier=Tier.TWO, regions=["TW"]),
    Source(name="TrendForce", domain="trendforce.com", locale="en", tier=Tier.TWO, regions=["TW","global"]),
    Source(name="EE Times", domain="eetimes.com", locale="en", tier=Tier.TWO, regions=["global"]),
    Source(name="EE Times China", domain="eet-china.com", locale="zh-CN", tier=Tier.TWO, regions=["CN"]),
    Source(name="Tom's Hardware", domain="tomshardware.com", locale="en", tier=Tier.TWO, regions=["global"]),
    Source(name="AnandTech", domain="anandtech.com", locale="en", tier=Tier.TWO, regions=["global"]),
    Source(name="The Register", domain="theregister.com", locale="en", tier=Tier.TWO, regions=["global"]),
    Source(name="Nikkei xTECH", domain="xtech.nikkei.com", locale="ja", tier=Tier.TWO, regions=["JP"]),
    Source(name="ITmedia", domain="itmedia.co.jp", locale="ja", tier=Tier.TWO, regions=["JP"]),
    Source(name="MONOist", domain="monoist.itmedia.co.jp", locale="ja", tier=Tier.TWO, regions=["JP"]),
    Source(name="EDN Japan", domain="ednjapan.com", locale="ja", tier=Tier.TWO, regions=["JP"]),
    Source(name="Korea IT News", domain="english.etnews.com", locale="en", tier=Tier.TWO, regions=["KR"]),
    Source(name="ETNews", domain="etnews.com", locale="ko", tier=Tier.TWO, regions=["KR"]),
    Source(name="The Elec", domain="thelec.kr", locale="ko", tier=Tier.TWO, regions=["KR"]),
    Source(name="The Elec EN", domain="thelec.net", locale="en", tier=Tier.TWO, regions=["KR"]),
    Source(name="36Kr", domain="36kr.com", locale="zh-CN", tier=Tier.TWO, regions=["CN"]),
    Source(name="LatePost", domain="latepost.com", locale="zh-CN", tier=Tier.TWO, regions=["CN"]),
    Source(name="Jiemian", domain="jiemian.com", locale="zh-CN", tier=Tier.TWO, regions=["CN"]),
    Source(name="ChinaStarMarket", domain="chinastarmarket.cn", locale="zh-CN", tier=Tier.TWO, regions=["CN"]),
    Source(name="STCN", domain="stcn.com", locale="zh-CN", tier=Tier.TWO, regions=["CN"]),
    # Auto / industrials
    Source(name="Automotive News", domain="autonews.com", locale="en", tier=Tier.TWO, regions=["global"]),
    Source(name="Automotive News China", domain="autonewschina.com", locale="en", tier=Tier.TWO, regions=["CN"]),
    Source(name="Nikkei Mobility", domain="response.jp", locale="ja", tier=Tier.TWO, regions=["JP"]),
    # Regulatory / policy
    Source(name="MLex", domain="mlex.com", locale="en", tier=Tier.TWO, regions=["global"]),
    Source(name="Global Competition Review", domain="globalcompetitionreview.com", locale="en", tier=Tier.TWO, regions=["global"]),
    # Sell-side / banks
    Source(name="Jefferies", domain="jefferies.com", locale="en", tier=Tier.TWO, regions=["global"]),
    Source(name="Bernstein", domain="bernsteinresearch.com", locale="en", tier=Tier.TWO, regions=["global"]),
]

# ---------------------------------------------------------------------------
# Tier 3 — aggregators, corporate channels, retail-but-sometimes-signal
# ---------------------------------------------------------------------------
_TIER_3: list[Source] = [
    Source(name="Xueqiu", domain="xueqiu.com", locale="zh-CN", tier=Tier.THREE, regions=["CN"]),
    Source(name="Eastmoney", domain="eastmoney.com", locale="zh-CN", tier=Tier.THREE, regions=["CN"]),
    Source(name="Sina Finance", domain="finance.sina.com.cn", locale="zh-CN", tier=Tier.THREE, regions=["CN"]),
    Source(name="Naver Finance", domain="finance.naver.com", locale="ko", tier=Tier.THREE, regions=["KR"]),
    Source(name="Kabutan", domain="kabutan.jp", locale="ja", tier=Tier.THREE, regions=["JP"]),
    Source(name="Traders Web", domain="traders.co.jp", locale="ja", tier=Tier.THREE, regions=["JP"]),
    Source(name="Seeking Alpha", domain="seekingalpha.com", locale="en", tier=Tier.THREE, regions=["global"]),
]

# ---------------------------------------------------------------------------
# Tier X — deprioritise. SEO aggregators, low-effort rehosts, ad-farm finance.
# ---------------------------------------------------------------------------
_TIER_X: list[Source] = [
    Source(name="Simply Wall St", domain="simplywall.st", locale="en", tier=Tier.X, regions=["global"]),
    Source(name="Yahoo Finance", domain="finance.yahoo.com", locale="en", tier=Tier.X, regions=["global"]),
    Source(name="Yahoo News", domain="news.yahoo.com", locale="en", tier=Tier.X, regions=["global"]),
    Source(name="MSN Money", domain="msn.com", locale="en", tier=Tier.X, regions=["global"]),
    Source(name="Investing.com", domain="investing.com", locale="en", tier=Tier.X, regions=["global"]),
    Source(name="Benzinga", domain="benzinga.com", locale="en", tier=Tier.X, regions=["global"]),
    Source(name="The Motley Fool", domain="fool.com", locale="en", tier=Tier.X, regions=["global"]),
    Source(name="ZeroHedge", domain="zerohedge.com", locale="en", tier=Tier.X, regions=["global"]),
    Source(name="GuruFocus", domain="gurufocus.com", locale="en", tier=Tier.X, regions=["global"]),
    Source(name="Insider Monkey", domain="insidermonkey.com", locale="en", tier=Tier.X, regions=["global"]),
]

ALL_SOURCES: list[Source] = _S_TIER + _TIER_1 + _TIER_2 + _TIER_3 + _TIER_X

# Domain → Source for fast lookup. Includes www.* aliases.
_BY_DOMAIN: dict[str, Source] = {}
for _src in ALL_SOURCES:
    _BY_DOMAIN[_src.domain] = _src
    _BY_DOMAIN["www." + _src.domain] = _src


def match_source(url: str) -> Source | None:
    """Match a fetched URL to its Source record, or None if unregistered.

    Matches the registered domain and any subdomain of it (so `asia.nikkei.com`
    matches the registered `asia.nikkei.com`, and `m.scmp.com` matches `scmp.com`).
    """
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return None
    if not host:
        return None
    if host in _BY_DOMAIN:
        return _BY_DOMAIN[host]
    # Check progressive parent domains (for mobile/regional subdomains).
    parts = host.split(".")
    for i in range(1, len(parts) - 1):
        candidate = ".".join(parts[i:])
        if candidate in _BY_DOMAIN:
            return _BY_DOMAIN[candidate]
    return None


def sources_for_locale(locale: str) -> list[Source]:
    """Return all registered sources for a given locale, sorted by tier."""
    return sorted(
        [s for s in ALL_SOURCES if s.locale == locale],
        key=lambda s: (s.tier.value, s.name),
    )
