"""Live integration test — Kioxia regression.

Hard-fails when ANY of the live API keys (TAVILY, ANTHROPIC) are present and
the canary query does not surface ≥3 distinct JP-Tier-1 sources in a 7-day
window. This is the regression gate referenced in the v2 build plan.

Skipped automatically when keys are absent so CI on a clean checkout doesn't
fail spuriously. Tag with `pytest -m live` to run only this suite.
"""
from __future__ import annotations

import os
from collections import Counter

import pytest

from news_core import NewsClient
from news_core.schema import Tier

pytestmark = pytest.mark.live


def _have_keys() -> bool:
    return bool(os.environ.get("TAVILY_API_KEY") and os.environ.get("ANTHROPIC_API_KEY"))


@pytest.fixture(scope="module")
def kioxia_result(tmp_path_factory):
    if not _have_keys():
        pytest.skip("TAVILY_API_KEY and ANTHROPIC_API_KEY required for live regression")
    cache_dir = tmp_path_factory.mktemp("news_core_live")
    client = NewsClient(cache_dir=str(cache_dir), consumer="deep_dive")
    return client.fetch(
        ticker="285A.T",
        company_name="Kioxia Holdings",
        business_geography=["JP", "global_memory"],
        lookback_hours=24 * 7,  # 7-day window per spec
        max_items=30,
        min_tier=2,
        region="JP",
    )


def test_returns_items(kioxia_result):
    assert len(kioxia_result.items) > 0, "no items surfaced for Kioxia"


def test_locales_include_japanese(kioxia_result):
    assert "ja" in kioxia_result.locales_queried
    assert "ko" in kioxia_result.locales_queried
    assert "en" in kioxia_result.locales_queried


def test_at_least_three_distinct_jp_tier1_sources(kioxia_result):
    """The canary regression: ≥3 distinct JP Tier-1 (or S) sources.

    Acceptance criterion stated in the v2 plan: "Kioxia query must surface
    ≥3 distinct JP-tier-1 sources in any 7-day window".
    """
    jp_high_tier = [
        it for it in kioxia_result.items
        if it.locale == "ja" and it.tier in {Tier.S, Tier.ONE}
    ]
    distinct_domains = {it.source_domain for it in jp_high_tier}
    assert len(distinct_domains) >= 3, (
        f"only {len(distinct_domains)} distinct JP-Tier-1 sources surfaced: "
        f"{sorted(distinct_domains)}. Items by source: "
        f"{Counter(it.source_name for it in kioxia_result.items).most_common()}"
    )


def test_translation_populated_for_japanese_items(kioxia_result):
    """At least one JP item should have a translated title (Claude or DeepL active)."""
    jp_items = [it for it in kioxia_result.items if it.locale == "ja"]
    if not jp_items:
        pytest.fail("no JP items surfaced")
    translated = [it for it in jp_items if it.title_translated]
    assert len(translated) >= 1, "no JP item translated; HybridTranslator misconfigured?"


def test_simply_wall_st_not_in_top_results(kioxia_result):
    """Sanity: the v1 failure mode (Tier-X SEO aggregator) must be excluded by min_tier=2."""
    domains = {it.source_domain for it in kioxia_result.items}
    assert "simplywall.st" not in domains
