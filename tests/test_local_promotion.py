"""Locale-native item promotion.

For a foreign name with both EN and local items, ranking.promote_locale_native
guarantees ≥1 local item lands in the top-N output even when EN items dominate
on raw score.
"""
from __future__ import annotations

from datetime import datetime, timezone

from news_core.ranking import promote_locale_native
from news_core.schema import NewsItem, Tier


def _item(score: float, locale: str, tag: str) -> NewsItem:
    return NewsItem(
        id=f"id-{tag}",
        url=f"https://example.com/{tag}",
        source_name="X",
        source_domain="example.com",
        locale=locale,
        tier=Tier.ONE,
        title_original=tag,
        published_at=datetime.now(timezone.utc),
        fetched_at=datetime.now(timezone.utc),
        score=score,
    )


def test_promotes_local_when_top_n_is_all_en():
    items = [
        _item(0.9, "en", "en1"),
        _item(0.8, "en", "en2"),
        _item(0.7, "en", "en3"),
        _item(0.4, "ja", "ja1"),  # would normally be cut
    ]
    out = promote_locale_native(items, top_n=3)
    head_locales = {it.locale for it in out[:3]}
    assert "ja" in head_locales


def test_no_promotion_when_local_already_in_head():
    items = [
        _item(0.9, "en", "en1"),
        _item(0.85, "ja", "ja1"),  # already in head
        _item(0.7, "en", "en2"),
        _item(0.4, "ja", "ja2"),
    ]
    out = promote_locale_native(items, top_n=3)
    assert out == items  # unchanged


def test_no_promotion_when_no_local_anywhere():
    items = [_item(0.9 - 0.1 * i, "en", f"en{i}") for i in range(5)]
    out = promote_locale_native(items, top_n=3)
    assert out == items


def test_demotes_lowest_scoring_en_first():
    items = [
        _item(0.9, "en", "high"),
        _item(0.8, "en", "mid"),
        _item(0.7, "en", "low"),  # this one should be displaced
        _item(0.5, "ko", "ko1"),
    ]
    out = promote_locale_native(items, top_n=3)
    head = out[:3]
    head_titles = [it.title_original for it in head]
    # The lowest-scoring EN ("low") should NOT be in the head anymore.
    assert "low" not in head_titles
    assert "ko1" in head_titles
    # The two highest-scoring EN should remain.
    assert "high" in head_titles
    assert "mid" in head_titles


def test_handles_empty_input():
    assert promote_locale_native([], top_n=5) == []


def test_handles_zero_top_n():
    items = [_item(0.5, "en", "en1"), _item(0.4, "ja", "ja1")]
    assert promote_locale_native(items, top_n=0) == items
