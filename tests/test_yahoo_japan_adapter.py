"""Yahoo Japan adapter parser tests + Kioxia regression."""
from __future__ import annotations

from news_core.adapters.yahoo_japan import _parse_yahoo_jp_serp, _parse_yahoo_jp_time


_KIOXIA_FIXTURE = """
<html><body>
<ul class="newsFeed">
  <li class="newsFeed_item">
    <a href="https://news.yahoo.co.jp/articles/abc123">
      <div class="newsFeed_item_title">キオクシア、NAND価格上昇で第3四半期業績見通しを上方修正</div>
      <p class="newsFeed_item_detail">キオクシアホールディングスは8日、NAND型フラッシュメモリーの価格上昇を背景に、業績見通しを引き上げると発表した。</p>
      <div class="newsFeed_item_sub">日本経済新聞 2時間前</div>
    </a>
  </li>
  <li class="newsFeed_item">
    <a href="https://news.yahoo.co.jp/articles/def456">
      <div class="newsFeed_item_title">SKハイニックスとサムスン電子、HBM4量産加速</div>
      <p class="newsFeed_item_detail">韓国メモリ大手2社が次世代HBMの量産時期を前倒し。エヌビディア向けが主力。</p>
      <div class="newsFeed_item_sub">東洋経済オンライン 30分前</div>
    </a>
  </li>
</ul>
</body></html>
"""


def test_kioxia_regression():
    """Kioxia canary: at least one tier-1 JP source surfaces in result set."""
    hits = _parse_yahoo_jp_serp(_KIOXIA_FIXTURE, lookback_hours=24)
    kioxia = [h for h in hits if "キオクシア" in h.title]
    assert len(kioxia) >= 1
    assert kioxia[0].locale == "ja"
    assert "NAND" in kioxia[0].snippet or "業績" in kioxia[0].snippet
    assert kioxia[0].source_used == "yahoo_japan"


def test_parses_multiple_items():
    hits = _parse_yahoo_jp_serp(_KIOXIA_FIXTURE, lookback_hours=24)
    assert len(hits) == 2


def test_relative_time_jp():
    t1 = _parse_yahoo_jp_time("2時間前")
    t2 = _parse_yahoo_jp_time("30分前")
    assert t1 is not None
    assert t2 is not None
    assert t1 < t2  # 2h ago is earlier than 30min ago
