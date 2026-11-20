"""
DirectionEngine 테스트 — 방향은 감성과 다른 축이다.

이 파일이 고정하는 것은 하나다. **호재냐 악재냐(감성)와 오르냐
내리냐(방향)는 독립이다.** 둘을 한 필드로 합치면 Impact Map 의 인과
연쇄 전체가 뒤집힌다.
"""

from __future__ import annotations

import pytest

from marketpulse.ai.rule_extractor import extract_events
from marketpulse.config.registry import get_themes
from marketpulse.engines.direction import lexicon_direction, scoped_direction
from marketpulse.engines.sentiment import lexicon_sentiment

INFLATION = ["물가", "인플레이션", "기대인플레이션", "CPI"]
RATES = ["금리", "국채", "연준", "FOMC"]


class TestTwoAxesAreIndependent:
    def test_good_news_can_mean_down(self):
        """
        "물가 둔화" 는 시장에 호재지만 물가 자체는 내려간다.
        감성 부호를 방향으로 쓰면 이 문장이 '물가가 오른다' 가 된다.
        """
        text = '연준 위원 "물가 둔화 흐름 확인"'
        sentiment, _ = lexicon_sentiment(text)
        heading, terms = scoped_direction(text, INFLATION)
        assert heading == "down"
        assert "둔화" in terms
        assert sentiment >= 0  # 호재로 읽힌다

    def test_bad_news_can_mean_up(self):
        """
        이 버그의 원인이 된 헤드라인이다. "부담"·"우려" 가 감성을 음수로
        만들지만 기사가 말하는 것은 물가 상승이다.
        """
        text = "원달러 환율 장중 1380원대… 수입 물가 부담 확대 우려"
        sentiment, _ = lexicon_sentiment(text)
        heading, terms = scoped_direction(text, INFLATION)
        assert heading == "up"
        assert "확대" in terms
        assert sentiment < 0  # 악재로 읽힌다

    def test_lexicon_deliberately_excludes_these_from_sentiment(self):
        """
        감성 사전은 둔화·확대를 맥락 의존이라며 일부러 뺐다. 방향으로는
        전혀 모호하지 않다 — 두 축이 독립이라는 증거다.
        """
        for word in ("둔화", "확대"):
            score, hits = lexicon_sentiment(word)
            assert score == 0 and hits == []
        assert lexicon_direction("확대")[0] == "up"
        assert lexicon_direction("둔화")[0] == "down"


class TestScoping:
    def test_nearest_term_wins_not_the_first(self):
        """
        연준 위원 "물가 둔화 흐름 확인"… 국채 금리 소폭 상승

        rates 는 '연준'(1절)과 '금리'(2절) 양쪽에 걸린다. 등장 순서로 재면
        1절의 '둔화' 가 이기지만 그 둔화는 물가를 말한 것이다. 키워드와의
        거리로 재야 '금리↔상승' 이 이긴다.
        """
        text = '연준 위원 "물가 둔화 흐름 확인"… 국채 금리 소폭 상승'
        assert scoped_direction(text, RATES)[0] == "up"
        assert scoped_direction(text, INFLATION)[0] == "down"

    def test_one_headline_two_themes_two_directions(self):
        text = "정유·에너지주 강세, 항공주는 약세… 업종 간 온도차"
        assert scoped_direction(text, ["정유", "에너지"])[0] == "up"
        assert scoped_direction(text, ["항공"])[0] == "down"

    def test_unrelated_clause_does_not_leak(self):
        """
        키워드가 없는 절의 방향어를 그 테마에 붙이지 않는다. 그것이
        이 버그의 구조적 원인이었다.
        """
        text = "외국인, 코스피 5거래일 연속 순매수… 반도체 대형주에 집중"
        assert scoped_direction(text, ["반도체"])[0] == "neutral"

    def test_no_keyword_is_neutral_not_a_guess(self):
        """기사 전체 방향으로 되돌아가지 않는다."""
        assert scoped_direction("유가 급등", ["반도체"]) == ("neutral", [])

    def test_negation_flips(self):
        assert scoped_direction("물가가 상승하지 않았다", INFLATION)[0] == "down"


class TestConservatism:
    def test_policy_verbs_are_not_direction_words(self):
        """
        "금리 인하 시점이 늦춰질 가능성" 은 인하라는 글자를 담고도 금리
        상승을 뜻한다. 부분 문자열 매칭으로 감당할 수 없으므로 사전에서
        뺐다. 지어내는 것보다 모른다고 하는 편이 낫다.
        """
        text = "채권시장은 연준의 금리 인하 시점이 늦춰질 가능성을 반영했다"
        assert scoped_direction(text, RATES)[0] != "down"

    def test_exact_cancellation_stays_neutral(self):
        assert lexicon_direction("")[0] == "neutral"


class TestRuleExtractor:
    @pytest.fixture
    def events(self, as_of):
        """세 시나리오의 mock 기사 전부."""
        from marketpulse.adapters.registry import build_news_adapter
        from marketpulse.config.settings import Settings

        out = []
        for scenario in ("baseline", "inflation_shock", "ai_divergence"):
            adapter = build_news_adapter(Settings(scenario=scenario))
            out.extend(extract_events(adapter.fetch_news(as_of=as_of)))
        return out

    def test_every_matched_theme_gets_a_direction(self, events):
        for e in events:
            assert set(e.theme_direction) == set(e.themes), e.event
            assert all(v in ("up", "down", "neutral") for v in e.theme_direction.values())

    def test_direction_is_not_the_sign_of_sentiment(self, events):
        """
        두 축이 늘 같다면 필드를 따로 둘 이유가 없다. mock 기사 중
        최소 하나는 감성과 방향의 부호가 갈려야 한다.
        """
        split = [
            (e.event, t)
            for e in events
            for t in e.themes
            if e.theme_sentiment.get(t, 0) < 0 and e.theme_direction.get(t) == "up"
        ]
        assert split, "감성과 방향이 갈리는 기사가 하나도 없다"

    def test_reason_records_the_basis(self, events):
        """어떤 표현으로 방향을 읽었는지 추적할 수 있어야 한다 (요구 15-6)."""
        assert all("방향 표현" in e.reason for e in events)
