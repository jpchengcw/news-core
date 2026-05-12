"""Tavily $-budget tracker + per-adapter request quotas.

Two concerns share this module because they share state (a sqlite db) and a
daily UTC reset:

  - TavilyBudget: tracks $-spend with a daily cap (default $1/day). Tavily is
    a fallback discoverer, so this enforces "use it sparingly."
  - AdapterQuota: per-engine daily request count cap (default 200/req-per-day),
    used by Baidu/Yahoo Japan/Naver/Google-site adapters as a safety net so we
    don't get IP-banned.
  - RateLimiter: 1-req-per-second throttle per adapter, in-process only
    (no sqlite). Politeness for HTML scraping.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


_DEFAULT_TAVILY_CAP_USD = 1.00
# Tavily "advanced" search: ~$0.008/call at standard tier as of 2026-Q1.
# Conservative estimate; adapter-level pricing override possible.
_DEFAULT_TAVILY_COST_PER_CALL_USD = 0.008
_DEFAULT_ADAPTER_DAILY_CAP = 200


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class _SpendDB:
    """Shared sqlite store for budget + quota counters."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tavily_spend (
                day TEXT PRIMARY KEY,
                spent_usd REAL NOT NULL DEFAULT 0,
                calls INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS adapter_quota (
                day TEXT NOT NULL,
                adapter TEXT NOT NULL,
                calls INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (day, adapter)
            )
            """
        )

    def lock(self):
        return self._lock

    def conn(self):
        return self._conn


class TavilyBudget:
    """Daily $-spend tracker for Tavily calls."""

    def __init__(
        self,
        db: _SpendDB,
        cap_usd: float = _DEFAULT_TAVILY_CAP_USD,
        cost_per_call_usd: float = _DEFAULT_TAVILY_COST_PER_CALL_USD,
    ):
        self._db = db
        self.cap_usd = float(cap_usd)
        self.cost_per_call_usd = float(cost_per_call_usd)

    def _row(self, day: str) -> tuple[float, int]:
        c = self._db.conn()
        row = c.execute(
            "SELECT spent_usd, calls FROM tavily_spend WHERE day = ?", (day,)
        ).fetchone()
        return (float(row[0]), int(row[1])) if row else (0.0, 0)

    def spent_today(self) -> float:
        with self._db.lock():
            spent, _ = self._row(_utc_today())
            return spent

    def remaining_today(self) -> float:
        return max(0.0, self.cap_usd - self.spent_today())

    def can_spend(self, cost_usd: float | None = None) -> bool:
        cost = self.cost_per_call_usd if cost_usd is None else float(cost_usd)
        return self.remaining_today() >= cost

    def record_call(self, cost_usd: float | None = None) -> tuple[float, float]:
        """Record a call, return (new_spent, remaining)."""
        cost = self.cost_per_call_usd if cost_usd is None else float(cost_usd)
        day = _utc_today()
        with self._db.lock():
            c = self._db.conn()
            spent, calls = self._row(day)
            new_spent = round(spent + cost, 6)
            c.execute(
                "INSERT OR REPLACE INTO tavily_spend (day, spent_usd, calls) VALUES (?,?,?)",
                (day, new_spent, calls + 1),
            )
            return new_spent, max(0.0, self.cap_usd - new_spent)

    def call_count_today(self) -> int:
        with self._db.lock():
            _, calls = self._row(_utc_today())
            return calls


class AdapterQuota:
    """Per-adapter daily request count cap (shared across processes via sqlite)."""

    def __init__(self, db: _SpendDB, daily_cap: int = _DEFAULT_ADAPTER_DAILY_CAP):
        self._db = db
        self.daily_cap = int(daily_cap)

    def _calls(self, adapter: str, day: str) -> int:
        c = self._db.conn()
        row = c.execute(
            "SELECT calls FROM adapter_quota WHERE day = ? AND adapter = ?", (day, adapter)
        ).fetchone()
        return int(row[0]) if row else 0

    def can_call(self, adapter: str) -> bool:
        with self._db.lock():
            return self._calls(adapter, _utc_today()) < self.daily_cap

    def record_call(self, adapter: str) -> int:
        day = _utc_today()
        with self._db.lock():
            c = self._db.conn()
            calls = self._calls(adapter, day) + 1
            c.execute(
                "INSERT OR REPLACE INTO adapter_quota (day, adapter, calls) VALUES (?,?,?)",
                (day, adapter, calls),
            )
            return calls

    def calls_today(self, adapter: str) -> int:
        with self._db.lock():
            return self._calls(adapter, _utc_today())


class RateLimiter:
    """In-process per-adapter rate limiter — politeness, not security.

    Default: 1 req/sec per adapter. Threadsafe; blocks the calling thread.
    """

    def __init__(self, requests_per_second: float = 1.0):
        self.min_interval = 1.0 / max(0.001, requests_per_second)
        self._last_call: dict[str, float] = {}
        self._lock = threading.Lock()

    def acquire(self, adapter: str) -> None:
        with self._lock:
            now = time.monotonic()
            last = self._last_call.get(adapter, 0.0)
            wait = self.min_interval - (now - last)
            if wait > 0:
                time.sleep(wait)
                self._last_call[adapter] = time.monotonic()
            else:
                self._last_call[adapter] = now


# ---------------------------------------------------------------------------
# Convenience: a process-level holder so adapters can share state without
# threading it through every constructor. The MultiSourceFetcher creates one
# `BudgetCenter` and hands it to each adapter.
# ---------------------------------------------------------------------------
class BudgetCenter:
    """Bundle of (TavilyBudget, AdapterQuota, RateLimiter) sharing one db."""

    def __init__(
        self,
        db_path: str | Path,
        tavily_cap_usd: float = _DEFAULT_TAVILY_CAP_USD,
        tavily_cost_per_call_usd: float = _DEFAULT_TAVILY_COST_PER_CALL_USD,
        adapter_daily_cap: int = _DEFAULT_ADAPTER_DAILY_CAP,
        requests_per_second: float = 1.0,
    ):
        self.db = _SpendDB(db_path)
        self.tavily = TavilyBudget(
            self.db,
            cap_usd=tavily_cap_usd,
            cost_per_call_usd=tavily_cost_per_call_usd,
        )
        self.quota = AdapterQuota(self.db, daily_cap=adapter_daily_cap)
        self.rate = RateLimiter(requests_per_second=requests_per_second)
