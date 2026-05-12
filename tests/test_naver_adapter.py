"""Naver adapter parser tests + Samsung regression."""
from __future__ import annotations

from news_core.adapters.naver import _parse_naver_serp, _parse_naver_time


_SAMSUNG_FIXTURE = """
<html><body>
<ul class="list_news">
<li class="bx">
  <div class="news_wrap">
    <a class="news_tit" href="https://biz.chosun.com/it-science/ict/2026/05/08/abc.html"
       title="삼성전자, 1분기 영업익 6조4000억…HBM 수요 호조">
      삼성전자, 1분기 영업익 6조4000억…HBM 수요 호조
    </a>
    <div class="news_dsc">
      <a class="api_txt_lines dsc_txt_wrap">삼성전자가 1분기 잠정 실적을 발표했다. HBM3E 양산이 본격화되며 메모리 부문 마진이 개선됐다.</a>
    </div>
    <div class="info_group"><span>조선비즈</span><span>2시간 전</span></div>
  </div>
</li>
<li class="bx">
  <div class="news_wrap">
    <a class="news_tit" href="https://www.hankyung.com/article/202605080001"
       title="SK하이닉스, HBM4 양산 일정 앞당겨">SK하이닉스, HBM4 양산 일정 앞당겨</a>
    <div class="news_dsc"><a>SK하이닉스가 차세대 HBM4 양산 시기를 6개월 앞당긴다고 발표했다.</a></div>
    <div class="info_group"><span>한국경제</span><span>30분 전</span></div>
  </div>
</li>
</ul>
</body></html>
"""


def test_samsung_regression():
    hits = _parse_naver_serp(_SAMSUNG_FIXTURE, lookback_hours=24)
    samsung = [h for h in hits if "삼성전자" in h.title]
    assert len(samsung) >= 1
    assert samsung[0].locale == "ko"
    assert "HBM" in samsung[0].snippet or "영업익" in samsung[0].snippet
    assert samsung[0].source_used == "naver"
    # URL should resolve to a registered Tier-1 KR source.
    assert "chosun.com" in samsung[0].url


def test_parses_multiple_items():
    hits = _parse_naver_serp(_SAMSUNG_FIXTURE, lookback_hours=24)
    assert len(hits) == 2


def test_relative_time_ko():
    t1 = _parse_naver_time("조선비즈 2시간 전")
    t2 = _parse_naver_time("한국경제 30분 전")
    assert t1 is not None
    assert t2 is not None
    assert t1 < t2
