"""Cross-language clustering and dedup.

Cluster by (entity, topic, 24h window). Within a cluster, keep the highest-tier
source PLUS any S-tier primary disclosure (regulatory beats press even if
press is more recent — primary is non-negotiable in equity research).

Persistent seen-hash store lives in state/news_seen.sqlite per consumer
(PM Pulse and Deep Dive each maintain their own seen-set).
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from news_core.schema import NewsItem, Tier


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------
def _bucket_24h(dt: datetime) -> str:
    """Round to UTC date — items within the same UTC day share a bucket."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _cluster_key(item: NewsItem) -> tuple[str, frozenset[str], frozenset[str]]:
    """Cluster key: (date_bucket, entities, topics).

    Items missing entities or topics fall into a less-aggressive cluster keyed
    on a normalised title prefix to avoid lumping unrelated stories together.
    """
    entities = frozenset(item.entity_tags)
    topics = frozenset(item.topic_tags)
    if not entities:
        # Title-prefix fallback. Lowercase, ASCII-only first 40 chars.
        prefix = re.sub(r"[^a-z0-9 ]", "", item.title_original.lower())[:40]
        entities = frozenset([f"_title:{prefix}"])
    return (_bucket_24h(item.published_at), entities, topics)


def cluster(items: Iterable[NewsItem]) -> dict[str, list[NewsItem]]:
    """Group items into clusters. Returns {cluster_id: [items]}."""
    buckets: dict[tuple, list[NewsItem]] = {}
    for it in items:
        key = _cluster_key(it)
        buckets.setdefault(key, []).append(it)

    out: dict[str, list[NewsItem]] = {}
    for key, members in buckets.items():
        # Stable cluster id = sha1 of key.
        h = hashlib.sha1(repr(key).encode()).hexdigest()[:12]
        for m in members:
            m.cluster_id = h
        out[h] = members
    return out


def collapse_cluster(members: list[NewsItem]) -> list[NewsItem]:
    """Pick representatives from a cluster.

    Always keep all S-tier items (primary disclosures). For non-S, keep the
    single highest-authority + most-recent item — the rest are duplicates of
    the same story across wires/languages.
    """
    s_tier = [m for m in members if m.tier == Tier.S]
    others = [m for m in members if m.tier != Tier.S]
    kept = list(s_tier)
    if others:
        # Highest authority first, then most recent.
        others.sort(key=lambda m: (m.tier.value, -m.published_at.timestamp()))
        kept.append(others[0])
    return kept


def dedup(items: list[NewsItem]) -> tuple[list[NewsItem], int]:
    """Cluster + collapse. Returns (representatives, num_clusters)."""
    clusters = cluster(items)
    reps: list[NewsItem] = []
    for members in clusters.values():
        reps.extend(collapse_cluster(members))
    return reps, len(clusters)


# ---------------------------------------------------------------------------
# Persistent seen-hash store (per consumer)
# ---------------------------------------------------------------------------
class SeenStore:
    """SQLite-backed seen-hash store. One DB file per consumer."""

    def __init__(self, db_path: Path | str):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen (
                hash TEXT PRIMARY KEY,
                first_seen TEXT NOT NULL,
                ticker TEXT,
                source_domain TEXT
            )
            """
        )
        self._conn.commit()

    @staticmethod
    def hash_item(item: NewsItem) -> str:
        """Stable hash for cross-run identity. Uses canonical URL when present."""
        key = f"{item.url}|{item.source_domain}|{item.published_at.isoformat()}"
        return hashlib.sha1(key.encode()).hexdigest()

    def is_seen(self, item: NewsItem) -> bool:
        h = self.hash_item(item)
        cur = self._conn.execute("SELECT 1 FROM seen WHERE hash = ?", (h,))
        return cur.fetchone() is not None

    def mark_seen(self, item: NewsItem, ticker: str | None = None) -> None:
        h = self.hash_item(item)
        self._conn.execute(
            "INSERT OR IGNORE INTO seen(hash, first_seen, ticker, source_domain) VALUES (?,?,?,?)",
            (h, datetime.now(timezone.utc).isoformat(), ticker, item.source_domain),
        )
        self._conn.commit()

    def filter_unseen(self, items: list[NewsItem]) -> list[NewsItem]:
        return [it for it in items if not self.is_seen(it)]

    def prune_older_than(self, days: int = 60) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cur = self._conn.execute("DELETE FROM seen WHERE first_seen < ?", (cutoff,))
        self._conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self._conn.close()
