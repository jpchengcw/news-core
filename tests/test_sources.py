"""Source registry: domain matching, tier assignment, locale lookup."""
from news_core.schema import Tier
from news_core.sources import match_source, sources_for_locale


def test_nikkei_is_tier_1_japanese():
    src = match_source("https://www.nikkei.com/article/foo")
    assert src is not None
    assert src.tier == Tier.ONE
    assert src.locale == "ja"


def test_nikkei_xtech_is_tier_2():
    src = match_source("https://xtech.nikkei.com/atcl/foo")
    assert src is not None
    assert src.tier == Tier.TWO


def test_simply_wall_st_is_tier_x():
    src = match_source("https://simplywall.st/stocks/jp/tech/tse-285a/kioxia-holdings")
    assert src is not None
    assert src.tier == Tier.X


def test_tdnet_is_tier_s():
    src = match_source("https://www.tdnet.info/onbrf/9999/foo.pdf")
    assert src is not None
    assert src.tier == Tier.S


def test_edgar_is_tier_s():
    src = match_source("https://www.sec.gov/Archives/edgar/data/foo")
    assert src is not None
    assert src.tier == Tier.S


def test_36kr_is_tier_2_zh_cn():
    src = match_source("https://36kr.com/p/1234567")
    assert src is not None
    assert src.tier == Tier.TWO
    assert src.locale == "zh-CN"


def test_unregistered_domain_returns_none():
    src = match_source("https://random-blog.example.com/post/123")
    assert src is None


def test_subdomain_matching_falls_through_to_parent():
    """m.scmp.com should match the registered scmp.com."""
    src = match_source("https://m.scmp.com/foo")
    assert src is not None
    assert src.name == "SCMP"


def test_sources_for_locale_japanese():
    jp_sources = sources_for_locale("ja")
    names = {s.name for s in jp_sources}
    assert "Nikkei" in names
    assert "Toyo Keizai" in names
    assert "Nikkei xTECH" in names
    assert "TDnet" in names


def test_sources_for_locale_korean():
    kr_sources = sources_for_locale("ko")
    names = {s.name for s in kr_sources}
    assert "Chosun BIZ" in names
    assert "The Elec" in names
    assert "DART" in names


def test_sources_for_locale_sorted_by_tier():
    jp_sources = sources_for_locale("ja")
    tier_values = [s.tier.value for s in jp_sources]
    assert tier_values == sorted(tier_values)
