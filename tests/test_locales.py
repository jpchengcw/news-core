"""Locale inference must produce the right ranked locale list for representative tickers.

Acceptance: Kioxia (285A.T) + global_memory must yield ja + ko + en.
"""
from news_core.locales import infer_locales


def test_kioxia_canary():
    """The Kioxia canary: ja primary, ko secondary (memory peers), en fallback."""
    locales = infer_locales("285A.T", business_geography=["global_memory"])
    assert locales[0] == "ja"
    assert "ko" in locales
    assert "en" in locales


def test_tencent_hk_listed():
    locales = infer_locales("0700.HK", business_geography=["china_internet"])
    assert locales[0] == "zh-HK"
    assert "zh-CN" in locales
    assert "en" in locales


def test_horizon_robotics():
    locales = infer_locales("9660.HK", business_geography=["china_ai"])
    assert locales[0] == "zh-HK"
    assert "zh-CN" in locales


def test_samsung_korea_memory():
    locales = infer_locales("005930.KS", business_geography=["global_memory"])
    assert locales[0] == "ko"
    assert "ja" in locales  # memory peers


def test_sk_hynix():
    locales = infer_locales("000660.KS", business_geography=["global_memory"])
    assert locales[0] == "ko"
    assert "ja" in locales


def test_toyota_japan_autos():
    locales = infer_locales("7203.T", business_geography=["japan_autos"])
    assert locales[0] == "ja"
    assert "de" in locales
    assert "ko" in locales
    assert "zh-CN" in locales


def test_lvmh_luxury():
    locales = infer_locales("MC.PA", business_geography=["luxury_eu"])
    assert locales[0] == "fr"
    assert "zh-CN" in locales  # Chinese consumer is the read-through market


def test_us_megacap_en_only():
    locales = infer_locales("META", business_geography=["us_megacap"])
    assert locales == ["en"]


def test_unknown_us_ticker_defaults_to_en():
    locales = infer_locales("XYZ", business_geography=[])
    assert locales == ["en"]


def test_smic_dual_listing_hk():
    locales = infer_locales("0981.HK", business_geography=["china_semi"])
    assert locales[0] == "zh-HK"
    assert "zh-CN" in locales
    assert "zh-TW" in locales  # foundry peer ecosystem


def test_region_fallback_when_no_geo_tag():
    """If no business_geography passed but region is, region fallback fills locales."""
    locales = infer_locales("285A.T", region="JP")
    assert locales[0] == "ja"
    assert "en" in locales


def test_locale_order_is_deduped():
    """Same locale arriving from multiple paths should appear once."""
    locales = infer_locales("285A.T", business_geography=["japan_dom", "global_memory"])
    assert locales.count("ja") == 1
    assert locales.count("en") == 1


def test_en_always_appended_last_when_not_primary():
    locales = infer_locales("285A.T", business_geography=["global_memory"])
    assert locales[-1] == "en"
