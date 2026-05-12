"""Query builder must produce conventional-form names per locale."""
from news_core.queries import build_queries, conventional_names


def test_kioxia_jp_uses_katakana():
    """Kioxia's JP query must include キオクシア — that's how Nikkei refers to it."""
    names = conventional_names("285A.T", "ja", fallback="Kioxia Holdings")
    assert "キオクシア" in names
    assert any("Kioxia" in n for n in names)


def test_kioxia_jp_includes_bare_ticker():
    """Local press cites the listing code without exchange suffix, e.g. (285A)."""
    names = conventional_names("285A.T", "ja", fallback="Kioxia Holdings")
    assert "285A" in names


def test_tencent_zh_cn_uses_simplified():
    names = conventional_names("0700.HK", "zh-CN", fallback="Tencent")
    assert "腾讯" in names


def test_tencent_zh_hk_uses_traditional():
    names = conventional_names("0700.HK", "zh-HK", fallback="Tencent")
    assert "騰訊" in names


def test_samsung_korean():
    names = conventional_names("005930.KS", "ko", fallback="Samsung Electronics")
    assert "삼성전자" in names


def test_toyota_japanese():
    names = conventional_names("7203.T", "ja", fallback="Toyota")
    assert "トヨタ" in names


def test_unknown_ticker_falls_back_to_company_name():
    names = conventional_names("XYZ.T", "ja", fallback="Acme Corp")
    assert "Acme Corp" in names
    assert "XYZ.T" in names  # ticker also included
    assert "XYZ" in names    # bare ticker also included


def test_query_string_format_is_quoted_or():
    """All search engines we target accept quoted-OR; assert format."""
    qs = build_queries("285A.T", "Kioxia Holdings", ["ja"])
    assert len(qs) == 1
    q = qs[0]
    assert q.locale == "ja"
    assert '"キオクシア"' in q.query
    assert " OR " in q.query


def test_build_queries_one_per_locale():
    qs = build_queries("285A.T", "Kioxia Holdings", ["ja", "ko", "en"])
    assert len(qs) == 3
    assert {q.locale for q in qs} == {"ja", "ko", "en"}


def test_no_duplicate_variants():
    """If a ticker would otherwise appear twice (e.g. ticker == bare), de-dup."""
    names = conventional_names("META", "en", fallback="Meta")
    # ensure list has no duplicates
    assert len(names) == len(set(names))
