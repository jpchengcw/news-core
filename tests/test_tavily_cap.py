"""Tavily $-budget enforcement test.

Once the daily cap is hit, no further Tavily calls fire — even when other
sources returned zero. The adapter `search()` returns [] without making the
network request.
"""
from __future__ import annotations

import os
import tempfile

import pytest

from news_core.budget import BudgetCenter
from news_core.cache import NewsCache


@pytest.fixture
def tmp_budget():
    with tempfile.TemporaryDirectory() as d:
        bc = BudgetCenter(
            db_path=f"{d}/budget.sqlite",
            tavily_cap_usd=0.05,
            tavily_cost_per_call_usd=0.01,
        )
        yield bc, d


def test_under_cap_allows_call(tmp_budget):
    bc, _ = tmp_budget
    assert bc.tavily.can_spend()
    assert bc.tavily.remaining_today() == pytest.approx(0.05)


def test_records_spend_and_blocks_at_cap(tmp_budget):
    bc, _ = tmp_budget
    # Burn through the cap with 5 calls of $0.01.
    for _ in range(5):
        assert bc.tavily.can_spend()
        bc.tavily.record_call()
    # Now at $0.05 spent; can_spend should be False.
    assert not bc.tavily.can_spend()
    assert bc.tavily.remaining_today() == pytest.approx(0.0)


def test_tavily_adapter_returns_empty_when_capped(monkeypatch, tmp_budget):
    """TavilyAdapter.search() short-circuits to [] when over cap, NOT calling network."""
    if not os.environ.get("TAVILY_API_KEY"):
        # Inject a dummy key so adapter init succeeds.
        monkeypatch.setenv("TAVILY_API_KEY", "test-stub-key")

    from news_core.adapters.tavily import TavilyAdapter
    bc, d = tmp_budget
    cache = NewsCache(f"{d}/cache.sqlite")
    adapter = TavilyAdapter(cache=cache, budget=bc)

    # Burn cap.
    for _ in range(5):
        bc.tavily.record_call()
    assert not bc.tavily.can_spend()

    # Should NOT touch the Tavily client — patch _client_or_init to crash if reached.
    def _explode():
        raise AssertionError("Tavily client should not be initialised when cap reached")
    adapter._client_or_init = _explode  # type: ignore[assignment]

    out = adapter.search(query="test", locale="en", lookback_hours=24, max_results=5)
    assert out == []


def test_no_tavily_flag_zeroes_cap():
    """no_tavily=True → cap is $0 → can_spend() returns False from start."""
    with tempfile.TemporaryDirectory() as d:
        bc = BudgetCenter(db_path=f"{d}/b.sqlite", tavily_cap_usd=0.0)
        assert not bc.tavily.can_spend()
