"""Ranking: recency × authority × relevance composite score."""
from datetime import datetime, timedelta, timezone

from news_core.schema import NewsItem, Tier
from news_core.ranking import (
    AUTHORITY_WEIGHTS,
    authority_weight,
    composite_score,
    rank,
    recency_decay,
)


NOW = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)


def _item(*, hours_old: float = 1.0, tier: Tier = Tier.ONE, topics: list[str] | None = None,
          entities: list[str] | None = None) -> NewsItem:
    return NewsItem(
        id="x",
        url="https://example.com/x",
        source_name="X",
        source_domain="example.com",
        locale="en",
        tier=tier,
        title_original="t",
        published_at=NOW - timedelta(hours=hours_old),
        fetched_at=NOW,
        topic_tags=topics or [],
        entity_tags=entities or [],
    )


def test_recency_decay_monotonic():
    """Older items decay; same item now ≥ same item 1h ago ≥ 24h ago."""
    fresh = recency_decay(NOW, now=NOW)
    one_h = recency_decay(NOW - timedelta(hours=1), now=NOW)
    one_d = recency_decay(NOW - timedelta(hours=24), now=NOW)
    assert fresh > one_h > one_d
    # 24h half-life: a 24h-old item should be ~0.5.
    assert abs(one_d - 0.5) < 0.01


def test_authority_weights_ordered():
    assert AUTHORITY_WEIGHTS[Tier.S] > AUTHORITY_WEIGHTS[Tier.ONE]
    assert AUTHORITY_WEIGHTS[Tier.ONE] > AUTHORITY_WEIGHTS[Tier.TWO]
    assert AUTHORITY_WEIGHTS[Tier.TWO] > AUTHORITY_WEIGHTS[Tier.THREE]
    assert AUTHORITY_WEIGHTS[Tier.THREE] > AUTHORITY_WEIGHTS[Tier.X]


def test_authority_weight_unregistered():
    assert authority_weight(None) == 0.30


def test_composite_score_higher_for_higher_tier():
    s_item = _item(tier=Tier.S, entities=["AAPL"], topics=["earnings"])
    one_item = _item(tier=Tier.ONE, entities=["AAPL"], topics=["earnings"])
    assert composite_score(s_item, query_entity_id="AAPL", now=NOW) > \
           composite_score(one_item, query_entity_id="AAPL", now=NOW)


def test_composite_score_higher_for_more_recent():
    fresh = _item(hours_old=1, tier=Tier.ONE, entities=["AAPL"])
    old = _item(hours_old=72, tier=Tier.ONE, entities=["AAPL"])
    assert composite_score(fresh, query_entity_id="AAPL", now=NOW) > \
           composite_score(old, query_entity_id="AAPL", now=NOW)


def test_entity_match_beats_topic_only():
    matched = _item(tier=Tier.ONE, entities=["AAPL"], topics=["earnings"])
    topic_only = _item(tier=Tier.ONE, entities=[], topics=["earnings"])
    assert composite_score(matched, query_entity_id="AAPL", now=NOW) > \
           composite_score(topic_only, query_entity_id="AAPL", now=NOW)


def test_rank_sorts_descending():
    items = [
        _item(hours_old=72, tier=Tier.X, topics=[]),
        _item(hours_old=1, tier=Tier.S, entities=["AAPL"], topics=["earnings"]),
        _item(hours_old=12, tier=Tier.ONE, entities=["AAPL"], topics=["earnings"]),
    ]
    ranked = rank(items, query_entity_id="AAPL", now=NOW)
    assert ranked[0].tier == Tier.S
    assert ranked[-1].tier == Tier.X
    assert ranked[0].score >= ranked[1].score >= ranked[2].score
