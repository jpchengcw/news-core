"""24h URL cache shared by all adapters.

Cache key is (adapter, query, locale, include_domains_signature) → list[RawHit] JSON.
Same query never costs twice in 24h, across PM Pulse + Deep Dive (shared cache_dir).

Also exposes a per-URL fetch cache (`fetch_cache`) for HTML body fetches —
Bloomberg/Reuters article bodies are large and rarely change once published.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from news_core.fetch import RawHit


_DEFAULT_TTL_SECONDS = 24 * 3600


class NewsCache:
    """Sqlite-backed cache for adapter search results and fetched bodies.

    Single connection guarded by a lock — sqlite is fine for our concurrency
    (≤16 threads, mostly read-after-write). Daily TTL purges happen lazily on
    read.
    """

    def __init__(self, path: str | Path, ttl_seconds: int = _DEFAULT_TTL_SECONDS):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl_seconds
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS search_cache (
                key TEXT PRIMARY KEY,
                adapter TEXT NOT NULL,
                stored_at INTEGER NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fetch_cache (
                url TEXT PRIMARY KEY,
                stored_at INTEGER NOT NULL,
                body TEXT
            )
            """
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_search_stored ON search_cache(stored_at)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_fetch_stored ON fetch_cache(stored_at)")

    @contextmanager
    def _locked(self):
        with self._lock:
            yield self._conn

    @staticmethod
    def _key(adapter: str, query: str, locale: str, include_domains: list[str] | None) -> str:
        sig = "|".join(sorted(include_domains or []))
        raw = f"{adapter}::{locale}::{query}::{sig}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _now(self) -> int:
        return int(datetime.now(timezone.utc).timestamp())

    # ------------------------------------------------------------------
    # Search-result cache
    # ------------------------------------------------------------------
    def get_search(
        self,
        adapter: str,
        query: str,
        locale: str,
        include_domains: list[str] | None = None,
    ) -> list[RawHit] | None:
        key = self._key(adapter, query, locale, include_domains)
        cutoff = self._now() - self.ttl
        with self._locked() as c:
            row = c.execute(
                "SELECT stored_at, payload FROM search_cache WHERE key = ?", (key,)
            ).fetchone()
        if not row or row[0] < cutoff:
            return None
        return [_hit_from_dict(d) for d in json.loads(row[1])]

    def put_search(
        self,
        adapter: str,
        query: str,
        locale: str,
        hits: list[RawHit],
        include_domains: list[str] | None = None,
    ) -> None:
        key = self._key(adapter, query, locale, include_domains)
        payload = json.dumps([_hit_to_dict(h) for h in hits], ensure_ascii=False)
        with self._locked() as c:
            c.execute(
                "INSERT OR REPLACE INTO search_cache (key, adapter, stored_at, payload) VALUES (?,?,?,?)",
                (key, adapter, self._now(), payload),
            )

    # ------------------------------------------------------------------
    # Fetched-body cache (URL → HTML body)
    # ------------------------------------------------------------------
    def get_body(self, url: str) -> str | None:
        cutoff = self._now() - self.ttl
        with self._locked() as c:
            row = c.execute(
                "SELECT stored_at, body FROM fetch_cache WHERE url = ?", (url,)
            ).fetchone()
        if not row or row[0] < cutoff:
            return None
        return row[1]

    def put_body(self, url: str, body: str | None) -> None:
        with self._locked() as c:
            c.execute(
                "INSERT OR REPLACE INTO fetch_cache (url, stored_at, body) VALUES (?,?,?)",
                (url, self._now(), body),
            )

    def purge_expired(self) -> int:
        cutoff = self._now() - self.ttl
        with self._locked() as c:
            c1 = c.execute("DELETE FROM search_cache WHERE stored_at < ?", (cutoff,)).rowcount
            c2 = c.execute("DELETE FROM fetch_cache WHERE stored_at < ?", (cutoff,)).rowcount
        return c1 + c2


def _hit_to_dict(h: RawHit) -> dict[str, Any]:
    d = asdict(h)
    if d.get("published_at"):
        d["published_at"] = h.published_at.isoformat() if h.published_at else None
    return d


def _hit_from_dict(d: dict[str, Any]) -> RawHit:
    pub = d.get("published_at")
    if isinstance(pub, str):
        try:
            pub = datetime.fromisoformat(pub)
        except ValueError:
            pub = None
    return RawHit(
        url=d.get("url", ""),
        title=d.get("title", ""),
        snippet=d.get("snippet", ""),
        locale=d.get("locale", "en"),
        published_at=pub,
        raw_metadata=d.get("raw_metadata") or {},
        paywalled=bool(d.get("paywalled", False)),
        source_used=d.get("source_used"),
    )
