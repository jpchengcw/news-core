"""Cross-language clustering + collapse + persistent SeenStore."""
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from news_core.schema import NewsItem, Tier
from news_core.dedup import SeenStore, cluster, collapse_cluster, dedup


NOW = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)


def _item(*, source_name: str, domain: str, locale: str, tier: Tier,
          title: str = "Kioxia announces FY26 capex plan",
          hours_old: float = 1.0, entities: list[str] | None = None,
          topics: list[str] | None = None) -> NewsItem:
    return NewsItem(
        id=f"{source_name}-{hours_old}",
        url=f"https://{domain}/article",
        source_name=source_name,
        source_domain=domain,
        locale=locale,
        tier=tier,
        title_original=title,
        published_at=NOW - timedelta(hours=hours_old),
        fetched_at=NOW,
        entity_tags=entities or ["285A.T"],
        topic_tags=topics or ["capex"],
    )


def test_cross_language_cluster_merges():
    """Same entity + topic + 24h window across ja and en → one cluster."""
    items = [
        _item(source_name="Nikkei",   domain="nikkei.com",     locale="ja", tier=Tier.ONE),
        _item(source_name="Reuters",  domain="reuters.com",    locale="en", tier=Tier.ONE),
        _item(source_name="Bloomberg",domain="bloomberg.com",  locale="en", tier=Tier.ONE),
    ]
    clusters = cluster(items)
    assert len(clusters) == 1


def test_different_topics_dont_cluster():
    items = [
        _item(source_name="Nikkei", domain="nikkei.com", locale="ja", tier=Tier.ONE, topics=["capex"]),
        _item(source_name="Reuters", domain="reuters.com", locale="en", tier=Tier.ONE, topics=["mna"]),
    ]
    clusters = cluster(items)
    assert len(clusters) == 2


def test_s_tier_always_kept_in_collapse():
    """A TDnet (Tier S) item must survive collapse alongside the highest non-S."""
    members = [
        _item(source_name="Nikkei", domain="nikkei.com", locale="ja", tier=Tier.ONE),
        _item(source_name="TDnet",  domain="tdnet.info", locale="ja", tier=Tier.S),
        _item(source_name="Yahoo",  domain="finance.yahoo.com", locale="en", tier=Tier.X),
    ]
    kept = collapse_cluster(members)
    kept_names = {k.source_name for k in kept}
    assert "TDnet" in kept_names
    assert "Nikkei" in kept_names  # highest non-S
    assert "Yahoo" not in kept_names


def test_dedup_returns_n_clusters():
    items = [
        _item(source_name="Nikkei", domain="nikkei.com", locale="ja", tier=Tier.ONE, topics=["capex"]),
        _item(source_name="Reuters", domain="reuters.com", locale="en", tier=Tier.ONE, topics=["capex"]),
        _item(source_name="Caixin", domain="caixin.com", locale="zh-CN", tier=Tier.ONE, topics=["mna"]),
    ]
    reps, n_clusters = dedup(items)
    assert n_clusters == 2
    assert len(reps) == 2  # one rep per cluster, both non-S


def test_seen_store_persists_across_instances():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "seen.sqlite"
        store1 = SeenStore(path)
        item = _item(source_name="Nikkei", domain="nikkei.com", locale="ja", tier=Tier.ONE)
        assert not store1.is_seen(item)
        store1.mark_seen(item, ticker="285A.T")
        assert store1.is_seen(item)
        store1.close()

        # Reopen and confirm persistence.
        store2 = SeenStore(path)
        assert store2.is_seen(item)
        store2.close()


def test_seen_store_filter_unseen():
    with tempfile.TemporaryDirectory() as tmp:
        store = SeenStore(Path(tmp) / "seen.sqlite")
        items = [
            _item(source_name="Nikkei", domain="nikkei.com", locale="ja", tier=Tier.ONE, hours_old=1),
            _item(source_name="Reuters", domain="reuters.com", locale="en", tier=Tier.ONE, hours_old=2),
        ]
        store.mark_seen(items[0], ticker="285A.T")
        unseen = store.filter_unseen(items)
        assert len(unseen) == 1
        assert unseen[0].source_name == "Reuters"
        store.close()
