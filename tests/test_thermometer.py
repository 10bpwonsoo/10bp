"""
센티멘트 온도계 (P5).

새 데이터를 쓰지 않는다는 것, 결측을 0 으로 채우지 않는다는 것, 두 바늘의
거리가 괴리로 읽힌다는 것 — 세 가지가 이 엔진의 약속이다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from marketpulse.config.settings import Settings
from marketpulse.engines.orchestrator import run_pipeline
from marketpulse.engines.scoring import load_scoring, squash
from marketpulse.engines.thermometer import (
    compute_thermometer,
    news_temperature,
    price_temperature,
)
from marketpulse.models.common import ScoreBreakdown
from marketpulse.models.news import NewsEvent
from marketpulse.models.state import FactorScore, MarketState
from marketpulse.models.theme import DataQualityBand
from marketpulse.models.thermometer import SentimentThermometer

AS_OF = datetime(2026, 9, 11, 7, 0, tzinfo=timezone.utc)


def _factor(name: str, z: float, quality: DataQualityBand = DataQualityBand.OK) -> FactorScore:
    return FactorScore(
        factor=name,
        score=z,
        breakdown=ScoreBreakdown.build(value=z, method="t", contributions=[]),
        data_quality=quality,
    )


def _state(**factors: float) -> MarketState:
    return MarketState(as_of=AS_OF, factors={k: _factor(k, v) for k, v in factors.items()})


def _event(eid: str, sentiment: int, hours_ago: float = 1.0, impact: int = 60, extractor="rule") -> NewsEvent:
    return NewsEvent(
        id=eid,
        event=f"기사 {eid}",
        sentiment=sentiment,
        impact_score=impact,
        timestamp=AS_OF - timedelta(hours=hours_ago),
        extractor=extractor,
    )


class TestPriceTemperature:
    def test_uses_existing_factors_with_signs(self):
        # RiskAppetite +, Volatility - : 둘 다 '뜨거운' 쪽으로 밀어야 한다
        state = _state(RiskAppetite=1.0, Volatility=-1.0)
        value, bd, cov = price_temperature(state)
        cfg = load_scoring()["thermometer"]
        w = {c["factor"]: c for c in cfg["price_components"]}
        expected_z = (
            w["RiskAppetite"]["weight"] * 1.0 + w["Volatility"]["weight"] * 1.0
        ) / (w["RiskAppetite"]["weight"] + w["Volatility"]["weight"])
        assert value == pytest.approx(squash(expected_z))
        assert bd.missing_inputs == ["Growth", "Credit", "KoreaFlow"]

    def test_no_factors_is_none_not_zero(self):
        value, bd, cov = price_temperature(_state())
        assert value is None
        assert cov == 0.0
        assert len(bd.missing_inputs) == 5

    def test_coverage_is_quality_weighted(self):
        # 종목 하나로 만든 factor 는 있어도 없는 것처럼 센다
        state = MarketState(
            as_of=AS_OF,
            factors={"RiskAppetite": _factor("RiskAppetite", 2.0, DataQualityBand.INSUFFICIENT)},
        )
        value, _, cov = price_temperature(state)
        assert value is not None, "값은 낸다"
        assert cov == 0.0, "신뢰는 주지 않는다"


class TestNewsTemperature:
    def test_no_events_is_none(self):
        value, bd, n = news_temperature([], AS_OF)
        assert value is None and n == 0
        assert bd.missing_inputs == ["news"]

    def test_recent_high_impact_dominates(self):
        old_negative = _event("old", -80, hours_ago=48, impact=30)
        fresh_positive = _event("new", +60, hours_ago=0.5, impact=90)
        value, bd, n = news_temperature([old_negative, fresh_positive], AS_OF)
        assert n == 2
        assert value > 0, "48시간 전 기사가 30분 전 기사를 이기면 감쇠가 없는 것이다"
        assert bd.contributions[0].key == "new", "근거는 기여도 순이다"

    def test_breakdown_weights_sum_to_one(self):
        events = [_event(f"e{i}", 10 * i) for i in range(1, 5)]
        _, bd, _ = news_temperature(events, AS_OF)
        assert sum(c.weight for c in bd.contributions) == pytest.approx(1.0)


class TestComposite:
    def test_blend_and_band(self):
        state = _state(RiskAppetite=2.0, Volatility=-2.0)
        t = compute_thermometer(state, [_event("a", 80), _event("b", 70)], AS_OF)
        assert t.price is not None and t.news is not None
        cfg = load_scoring()["thermometer"]["blend"]
        assert t.composite == pytest.approx(cfg["price"] * t.price + cfg["news"] * t.news)
        assert t.band in ("warm", "overheated")
        assert t.composite_breakdown is not None and t.composite_breakdown.missing_inputs == []

    def test_missing_news_uses_price_only(self):
        state = _state(RiskAppetite=1.0)
        t = compute_thermometer(state, [], AS_OF)
        assert t.news is None
        assert t.composite == pytest.approx(t.price), "0 으로 채워 평균내지 않는다"
        assert t.gap is None and t.gap_flag == "none"
        assert "뉴스 온도는 기사가 없어" in t.note
        assert t.confidence_breakdown is not None
        assert "news_sufficiency" in t.confidence_breakdown.missing_inputs

    def test_nothing_measured(self):
        t = compute_thermometer(_state(), [], AS_OF)
        assert t.composite is None and t.band == "unknown"
        assert t.confidence == 0.0
        assert t.composite_breakdown is None

    def test_gap_flags_narrative_direction(self):
        cold_price = _state(RiskAppetite=-2.0, Volatility=2.0)
        hot_news = [_event("a", 90), _event("b", 85)]
        t = compute_thermometer(cold_price, hot_news, AS_OF)
        assert t.gap is not None and t.gap > load_scoring()["thermometer"]["gap_threshold"]
        assert t.gap_flag == "narrative_hot"
        assert "앞서 달린다" in t.note

        hot_price = _state(RiskAppetite=2.0, Volatility=-2.0)
        cold_news = [_event("a", -90), _event("b", -85)]
        t2 = compute_thermometer(hot_price, cold_news, AS_OF)
        assert t2.gap_flag == "narrative_cold"

    def test_trend_from_previous(self):
        state = _state(RiskAppetite=1.5)
        prev = SentimentThermometer(as_of=AS_OF - timedelta(hours=1), composite=0.0)
        t = compute_thermometer(state, [], AS_OF, previous=prev)
        assert t.delta == pytest.approx(t.composite)
        assert t.trend == "up" and t.trend_arrow == "↑"

        flat_prev = SentimentThermometer(as_of=AS_OF, composite=t.composite)
        t2 = compute_thermometer(state, [], AS_OF, previous=flat_prev)
        assert t2.trend == "flat" and t2.delta == pytest.approx(0.0)

    def test_first_tick_has_no_trend(self):
        t = compute_thermometer(_state(RiskAppetite=1.0), [], AS_OF)
        assert t.delta is None and t.trend == "flat"

    def test_counts_llm_events(self):
        events = [_event("a", 10, extractor="llm"), _event("b", 10)]
        t = compute_thermometer(_state(RiskAppetite=0.5), events, AS_OF)
        assert t.news_events == 2 and t.llm_events == 1

    def test_deterministic_hash(self):
        state = _state(RiskAppetite=1.0, Growth=0.5)
        events = [_event("a", 40)]
        a = compute_thermometer(state, events, AS_OF)
        b = compute_thermometer(state, events, AS_OF)
        assert a.composite_breakdown.inputs_hash == b.composite_breakdown.inputs_hash
        assert a.price_breakdown.inputs_hash == b.price_breakdown.inputs_hash


class TestPipeline:
    @pytest.mark.parametrize("scenario", ["baseline", "inflation_shock", "ai_divergence"])
    def test_snapshot_carries_thermometer(self, scenario):
        snap = run_pipeline(Settings(scenario=scenario))
        t = snap.thermometer
        assert t is not None
        assert t.composite is not None
        assert t.price is not None and t.news is not None
        assert t.news_events == len(snap.events)
        assert "thermometer" in snap.engine_versions
        assert "thermometer" in snap.data_health.engine_timings_ms

    def test_inflation_shock_reads_cold_with_hot_narrative(self):
        # 위험회피 + 변동성 급등이면 가격 온도는 차갑다. 그 시나리오의 기사는
        # 물가 '상승' 을 말하지만 톤이 극단적으로 어둡지는 않아 뉴스가 더 뜨겁다.
        t = run_pipeline(Settings(scenario="inflation_shock")).thermometer
        assert t.price < 0
        assert t.gap_flag == "narrative_hot"
