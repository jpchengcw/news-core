"""Composite scoring: recency × authority × relevance.

Deterministic, no API calls. Used by client.fetch() after dedup.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from news_core.schema import NewsItem, Tier

# Hours half-life on recency decay. 24h half-life → 72h-old item carries 12.5% weight.
RECENCY_HALF_LIFE_H: float = 24.0

# Tier authority weights. Tier S (regulatory) is the ceiling; Tier X is near-zero.
AUTHORITY_WEIGHTS: dict[Tier, float] = {
    Tier.S:    1.00,
    Tier.ONE:  0.85,
    Tier.TWO:  0.65,
    Tier.THREE: 0.40,
    Tier.X:    0.05,
}

# Default authority for unregistered domains (treated like Tier 3-).
UNREGISTERED_AUTHORITY: float = 0.30


def recency_decay(published_at: datetime, now: datetime | None = None) -> float:
    """Exponential decay on hours since publication. Returns ∈ (0, 1]."""
    now = now or datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    hours = max(0.0, (now - published_at).total_seconds() / 3600.0)
    return math.pow(0.5, hours / RECENCY_HALF_LIFE_H)


def authority_weight(tier: Tier | None) -> float:
    if tier is None:
        return UNREGISTERED_AUTHORITY
    return AUTHORITY_WEIGHTS.get(tier, UNREGISTERED_AUTHORITY)


def topic_relevance(item: NewsItem, query_entity_id: str | None = None) -> float:
    """Heuristic relevance scoring based on entity / topic tag overlap.

    1.0 — entity match confirmed (item.entity_tags includes the query entity)
    0.7 — has at least one high-signal topic tag (earnings, mna, capex, regulatory, guidance, segment)
    0.5 — has any topic tag
    0.3 — neither
    """
    high_signal = {"earnings", "mna", "capex", "regulatory", "guidance", "segment", "ownership"}
    if query_entity_id and query_entity_id in item.entity_tags:
        return 1.0
    if any(t in high_signal for t in item.topic_tags):
        return 0.7
    if item.topic_tags:
        return 0.5
    return 0.3


def composite_score(
    item: NewsItem,
    query_entity_id: str | None = None,
    now: datetime | None = None,
) -> float:
    """Composite score = recency × authority × relevance, ∈ [0, 1]."""
    return (
        recency_decay(item.published_at, now=now)
        * authority_weight(item.tier)
        * topic_relevance(item, query_entity_id=query_entity_id)
    )


def rank(
    items: list[NewsItem],
    query_entity_id: str | None = None,
    now: datetime | None = None,
) -> list[NewsItem]:
    """Score items in place and return them sorted descending by score."""
    for it in items:
        it.score = composite_score(it, query_entity_id=query_entity_id, now=now)
    return sorted(items, key=lambda x: x.score, reverse=True)


def promote_locale_native(items: list[NewsItem], top_n: int) -> list[NewsItem]:
    """Ensure ≥1 non-EN item lands in the top-N if any exists in `items`.

    The ranking pass favours recency × authority × relevance — strong English
    wires (Reuters, Bloomberg) often dominate. For breadth in foreign-name
    coverage we want at least one locale-native item to reach the digest.

    If the top-N already contains a non-EN item, returns `items` unchanged.
    Otherwise demotes the lowest-scoring EN item past `top_n` and inserts the
    highest-scoring non-EN item at position `top_n - 1`.
    """
    if top_n <= 0 or not items:
        return items
    head = items[:top_n]
    if any(it.locale != "en" for it in head):
        return items

    # Find first non-EN beyond the head.
    promote_idx = next((i for i, it in enumerate(items[top_n:], start=top_n) if it.locale != "en"), None)
    if promote_idx is None:
        return items

    promoted = items[promote_idx]
    # Drop the lowest-scoring EN from head; replace with promoted.
    en_in_head = sorted(
        [(i, it) for i, it in enumerate(head) if it.locale == "en"],
        key=lambda x: x[1].score,
    )
    if not en_in_head:
        return items
    drop_idx, _ = en_in_head[0]

    new_items = list(items)
    new_items.pop(promote_idx)
    new_items.insert(drop_idx, promoted)
    # Move the demoted EN to right after top_n so it remains accessible if caller
    # increases top_n later; not strictly needed but keeps ordering deterministic.
    return new_items
