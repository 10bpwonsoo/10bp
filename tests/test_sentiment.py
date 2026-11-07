"""SentimentEngine 과 룰 추출기 테스트 (설계서 STEP 5.6)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from marketpulse.ai.rule_extractor import extract_events
from marketpulse.engines.sentiment import (
    aggregate_sentiment,
    decay_weight,
    fuse_sentiment,
    lexicon_sentiment,
    news_momentum,
    scoped_sentiment,
)
from marketpulse.models.common import DataMeta, DataMode, utcnow
from marketpulse.models.news import NewsEvent


def _event(sentiment: int, hours_ago: float, as_of, impact: int = 100) -> NewsEvent:
    return NewsEvent(
        id=f"e{hours_ago}",
        event="t",
        sentiment=sentiment,
        impact_score=impact,
        timestamp=as_of - timedelta(hours=hours_ago),
    )


class TestLexicon:
    @pytest.mark.parametrize(
        "text,sign",
        [
            ("브렌트유 급등", 1),
            ("나스닥 급락", -1),
            ("외국인 순매수 지속", 1),
            ("공급 차질 우려", -1),
            ("특별한 변화가 없었다", 0),
        ],
    )
    def test_polarity(self, text, sign):
        score, _ = lexicon_sentiment(text)
        assert (score > 0) - (score < 0) == sign

    def test_negation_flips(self):
        assert lexicon_sentiment("지수가 상승했다")[0] > 0
        assert lexicon_sentiment("지수는 상승하지 않았다")[0] < 0

    def test_opposing_terms_do_not_cancel_to_zero(self):
        """
        '중동 긴장 고조에 유가 급등' 이 중립으로 읽히면 안 된다.
        앞에 나온 표현에 더 큰 비중을 두어 정확한 상쇄를 막는다.
        """
        score, hits = lexicon_sentiment("중동 긴장 고조에 유가 급등")
        assert len(hits) >= 2
        assert score != 0

    def test_bounded(self):
        text = " ".join(["급등"] * 20)
        assert -100 <= lexicon_sentiment(text)[0] <= 100

    def test_ambiguous_terms_excluded(self):
        """
        맥락에 따라 부호가 뒤집히는 말은 사전에 없어야 한다.
        성장 둔화는 악재, 물가 둔화는 호재다.
        """
        from marketpulse.engines.sentiment import load_lexicon

        lex = load_lexicon()
        terms = set(lex["positive"]) | set(lex["negative"])
        assert "둔화" not in terms
        assert "확대" not in terms
        assert "증산" not in terms


class TestScopedSentiment:
    def test_splits_on_contrast_conjunction(self):
        body = "정유·에너지 업종이 강세를 보인 반면 항공 업종은 약세를 나타냈다."
        assert scoped_sentiment(body, ["에너지"]) > 0
        assert scoped_sentiment(body, ["항공"]) < 0

    def test_splits_on_headline_ellipsis(self):
        """한국어 헤드라인의 …는 두 절을 가르는 표지다."""
        title = "중동 긴장 고조… 브렌트유 급등"
        assert scoped_sentiment(title, ["브렌트"]) > 0
        assert scoped_sentiment(title, ["긴장"]) < 0

    def test_returns_none_when_keyword_absent(self):
        assert scoped_sentiment("금리가 올랐다", ["반도체"]) is None


class TestDecayAndAggregation:
    def test_recent_news_weighs_more(self, as_of):
        fresh = decay_weight(_event(50, 0.0, as_of), as_of)
        stale = decay_weight(_event(50, 24.0, as_of), as_of)
        assert fresh > stale * 4

    def test_half_life(self, as_of):
        full = decay_weight(_event(50, 0.0, as_of), as_of)
        half = decay_weight(_event(50, 6.0, as_of), as_of)
        assert half == pytest.approx(full / 2, rel=1e-6)

    def test_impact_scales_weight(self, as_of):
        big = decay_weight(_event(50, 1.0, as_of, impact=100), as_of)
        small = decay_weight(_event(50, 1.0, as_of, impact=20), as_of)
        assert big == pytest.approx(small * 5, rel=1e-6)

    def test_not_a_simple_mean(self, as_of):
        """
        요구 5 가 단순 평균을 금지한다. 3일 전 기사와 10분 전 기사를 같은
        무게로 취급하면 급변을 놓친다.
        """
        events = [_event(100, 0.1, as_of), _event(-100, 48.0, as_of)]
        value, weight = aggregate_sentiment(events, as_of)
        assert weight > 0
        assert value > 50, "최근 기사가 지배해야 한다"

    def test_empty_reports_zero_weight(self, as_of):
        value, weight = aggregate_sentiment([], as_of)
        assert (value, weight) == (0.0, 0.0)

    def test_momentum_needs_both_windows(self, as_of):
        only_recent = [_event(50, 0.5, as_of)]
        assert news_momentum(only_recent, as_of) is None
        both = [_event(80, 0.5, as_of), _event(-40, 10.0, as_of)]
        assert news_momentum(both, as_of) > 0


class TestFusion:
    def test_llm_ignored_when_invalid(self):
        assert fuse_sentiment(30, 90, llm_valid=False) == 30

    def test_llm_ignored_when_absent(self):
        assert fuse_sentiment(30, None, llm_valid=True) == 30

    def test_weighted_blend(self):
        assert fuse_sentiment(0, 100, llm_valid=True) == 70


class TestRuleExtractor:
    @pytest.fixture
    def events(self, news_adapter, as_of):
        return extract_events(news_adapter.fetch_news(as_of=as_of), as_of=as_of)

    def test_runs_without_llm(self, events):
        """LLM 없이도 파이프라인이 완주해야 한다 (요구 15-7)."""
        assert len(events) == 5
        assert all(e.extractor == "rule" for e in events)
        assert all(e.extractor_model is None for e in events)

    def test_provenance_is_recorded(self, events):
        assert all(e.validation.schema_ok for e in events)
        assert all(0.0 < e.confidence <= 0.6 for e in events), (
            "키워드 매칭은 LLM 만큼 정교하지 않다. confidence 가 그것을 말해야 한다."
        )

    def test_themes_tagged(self, events):
        tagged = [e for e in events if e.themes]
        assert tagged, "어느 기사도 테마에 걸리지 않았다"
        assert all(t for e in tagged for t in e.theme_sentiment)

    def test_theme_sentiment_can_differ_per_theme(self, as_of):
        """
        기사 하나가 여러 테마를 건드릴 때 같은 감성을 모든 테마에 붙이면
        틀린다. '정유주 강세, 항공주 약세' 는 갈려야 한다.
        """
        from marketpulse.models.news import RawNewsItem

        item = RawNewsItem(
            id="x",
            title="정유·에너지주 강세… 항공주는 약세",
            body="",
            published_at=as_of,
            meta=DataMeta(
                source="t", mode=DataMode.MOCK, retrieved_at=utcnow(), as_of=as_of
            ),
        )
        e = extract_events([item])[0]
        assert e.theme_sentiment.get("energy", 0) > 0

    def test_risk_theme_polarity_inverted(self, as_of):
        """지정학 리스크 테마는 악재가 테마를 키운다."""
        from marketpulse.models.news import RawNewsItem

        item = RawNewsItem(
            id="g",
            title="중동 분쟁 격화로 긴장 고조",
            body="",
            published_at=as_of,
            meta=DataMeta(
                source="t", mode=DataMode.MOCK, retrieved_at=utcnow(), as_of=as_of
            ),
        )
        e = extract_events([item])[0]
        assert e.sentiment < 0
        assert e.theme_sentiment["geopolitical_risk"] > 0

    def test_novelty_not_invented(self, events):
        """중복 제거 기반 novelty 는 P3 다. 여기서 지어내지 않는다."""
        assert all(e.novelty_score == 50 for e in events)

    def test_deterministic(self, news_adapter, as_of):
        items = news_adapter.fetch_news(as_of=as_of)
        a = extract_events(items)
        b = extract_events(items)
        assert [e.model_dump() for e in a] == [e.model_dump() for e in b]
