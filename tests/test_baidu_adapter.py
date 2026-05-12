"""Baidu adapter parser tests with canned SERP HTML."""
from __future__ import annotations

from datetime import datetime, timezone

from news_core.adapters.baidu import _parse_baidu_serp, _parse_baidu_time


_BAIDU_FIXTURE = """
<html><body>
<div class="result-op c-container">
  <h3><a href="https://www.caixin.com/article/2026-05-08/article-001.html">腾讯Q1业绩超预期，游戏业务回暖</a></h3>
  <span class="c-summary">腾讯控股发布2026年第一季度财报，营收同比增长12%，游戏业务在国内市场恢复明显。分析师预期上调。</span>
  <span class="c-color-gray">财新网&nbsp;&nbsp;2小时前</span>
</div>
<div class="c-container">
  <h3><a href="https://www.yicai.com/news/123.html">第一财经：腾讯回购计划继续推进</a></h3>
  <span class="c-summary">公司发布回购公告，计划在未来12个月内回购股份用于股权激励和注销。</span>
  <span class="c-color-gray">第一财经&nbsp;&nbsp;30分钟前</span>
</div>
<div class="c-container">
  <h3><a href="https://www.example-old.com/very-old">陈旧消息</a></h3>
  <span class="c-summary">past news from far away</span>
  <span class="c-color-gray">3天前</span>
</div>
</body></html>
"""


def test_parses_title_url_snippet():
    hits = _parse_baidu_serp(_BAIDU_FIXTURE, locale="zh-CN", lookback_hours=24)
    assert len(hits) >= 2  # the 3-day-old one falls outside lookback
    # First hit: caixin
    cx = next(h for h in hits if "caixin.com" in h.url)
    assert "腾讯" in cx.title
    assert cx.locale == "zh-CN"
    assert cx.snippet
    assert cx.source_used == "baidu"
    # Second hit: yicai
    yc = next(h for h in hits if "yicai.com" in h.url)
    assert "回购" in yc.title


def test_lookback_filters_old_items():
    hits = _parse_baidu_serp(_BAIDU_FIXTURE, locale="zh-CN", lookback_hours=12)
    urls = {h.url for h in hits}
    assert not any("very-old" in u for u in urls)


def test_relative_time_parsing():
    now = datetime.now(timezone.utc)
    t1 = _parse_baidu_time("财新网 2小时前")
    t2 = _parse_baidu_time("第一财经 30分钟前")
    t3 = _parse_baidu_time("3天前")
    assert t1 is not None and (now - t1).total_seconds() <= 7200 + 60
    assert t2 is not None and (now - t2).total_seconds() <= 1800 + 60
    # 3 days ago, allowing for sub-second arithmetic drift in the test.
    assert t3 is not None and 2.9 < (now - t3).total_seconds() / 86400 < 3.1


def test_returns_empty_for_non_chinese_locale():
    """Adapter is locale-gated to zh-CN/zh-HK."""
    from news_core.adapters.baidu import BaiduAdapter
    a = BaiduAdapter()
    assert a._search_impl(query="test", locale="ja", lookback_hours=24,
                          max_results=10, include_domains=None, exclude_domains=None) == []
