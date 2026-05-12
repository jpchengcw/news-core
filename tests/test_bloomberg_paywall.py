"""Bloomberg paywall handling.

When the public URL returns no body content, the adapter still produces a
RawHit with the title from the Tavily snippet and `paywalled=True`. We never
fabricate body content.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from news_core.adapters.bloomberg import BloombergAdapter, _parse_bloomberg_meta
from news_core.fetch import RawHit


_FULL_META_HTML = """
<html><head>
<meta property="og:title" content="Tencent Profit Beats on Games Recovery">
<meta property="og:description" content="Earnings rose 12% as the gaming unit returned to growth.">
<meta property="article:published_time" content="2026-05-08T08:30:00Z">
</head><body>
<div class="body-content">
  <p>Tencent Holdings Ltd. posted first-quarter earnings that exceeded analyst estimates as its gaming business returned to growth amid a recovery in domestic consumer spending.</p>
  <p>More content here.</p>
</div>
</body></html>
"""

_HARD_PAYWALL_HTML = """
<html><head>
<meta property="og:title" content="Bloomberg Story That's Paywalled">
</head><body>
<div class="paywall">Subscribe to read.</div>
</body></html>
"""


def test_full_meta_parsed():
    meta = _parse_bloomberg_meta(_FULL_META_HTML)
    assert meta["title"] == "Tencent Profit Beats on Games Recovery"
    assert "Earnings rose" in meta["description"]
    assert "Tencent Holdings" in meta["first_paragraph"]
    assert meta["published_at"] is not None
    assert meta["published_at"].year == 2026


def test_hard_paywall_yields_title_no_body():
    meta = _parse_bloomberg_meta(_HARD_PAYWALL_HTML)
    assert meta["title"] == "Bloomberg Story That's Paywalled"
    assert meta["description"] is None
    # No first paragraph extractable — must be None, never fabricated.
    assert meta["first_paragraph"] is None


def test_enrich_paywalled_hit_keeps_title_marks_paywalled():
    """Adapter._enrich on a hit whose body is empty: snippet kept, paywalled=True."""
    fake_tav = MagicMock()
    adapter = BloombergAdapter.__new__(BloombergAdapter)
    adapter._tav = fake_tav
    adapter._http = MagicMock()
    adapter._http.get = MagicMock(return_value=MagicMock(status_code=200, text=_HARD_PAYWALL_HTML))
    adapter.cache = None
    adapter.budget = None

    seed = RawHit(
        url="https://www.bloomberg.com/news/articles/2026-05-08/something",
        title="Original Snippet Title",
        snippet="",  # Tavily returned empty body
        locale="en",
        published_at=datetime.now(timezone.utc),
        source_used="bloomberg",
    )
    out = adapter._enrich(seed)
    assert out.title == "Bloomberg Story That's Paywalled"
    # Empty body + empty snippet → paywalled
    assert out.paywalled is True


def test_enrich_full_article_not_paywalled():
    fake_tav = MagicMock()
    adapter = BloombergAdapter.__new__(BloombergAdapter)
    adapter._tav = fake_tav
    adapter._http = MagicMock()
    adapter._http.get = MagicMock(return_value=MagicMock(status_code=200, text=_FULL_META_HTML))
    adapter.cache = None
    adapter.budget = None

    seed = RawHit(
        url="https://www.bloomberg.com/news/articles/2026-05-08/tencent",
        title="seed title",
        snippet="",
        locale="en",
        published_at=datetime.now(timezone.utc),
        source_used="bloomberg",
    )
    out = adapter._enrich(seed)
    assert "Tencent" in out.title
    assert "Earnings rose" in out.snippet or "gaming business" in out.snippet
    assert out.paywalled is False
