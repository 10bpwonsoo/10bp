"""
DivergenceEngine 테스트 (설계서 STEP 5.8 / 요구 7).

요구 7 이 "이 프로젝트의 핵심 차별화 기능 중 하나" 로 지목한 부분이다.
TestRequirement7 이 요구사항의 예시 상황을 그대로 재현한다.
"""

from __future__ import annotations

import pytest

from marketpulse.config.settings import Settings
from marketpulse.engines.divergence import (
    load_divergence_rules,
    qualifies,
    severity_of,
)
from marketpulse.engines.korean import fix_particles, has_batchim
from marketpulse.engines.orchestrator import run_pipeline_detailed
from marketpulse.engines.scoring import load_scoring
from marketpulse.models.divergence import DivergenceType, SeverityBand


def _two_ticks(scenario: str):
    """괴리는 최소 두 틱이 있어야 확정된다."""
    s = Settings(scenario=scenario)
    first = run_pipeline_detailed(s)
    second = run_pipeline_detailed(
        s, history=[first.snapshot], pending_divergences=first.pending
    )
    return first, second


@pytest.fixture(scope="module")
def ai_ticks():
    return _two_ticks("ai_divergence")


@pytest.fixture(scope="module")
def shock_ticks():
    return _two_ticks("inflation_shock")


class TestQualification:
    """같은 방향으로 크기만 다른 것은 괴리가 아니다."""

    @pytest.fixture
    def trigger(self):
        return load_scoring()["divergence"]["trigger"]

    def test_opposing_signs(self, trigger):
        assert qualifies(60.0, -40.0, trigger) == "opposing"

    def test_one_side_unresponsive(self, trigger):
        assert qualifies(70.0, 3.0, trigger) == "unresponsive"

    def test_same_direction_is_not_divergence(self, trigger):
        """
        뉴스 톤 +20 과 가격 +90 은 격차가 70 이지만 둘 다 같은 방향이다.
        "내러티브가 가격으로 확인되지 않는다" 고 말하면 틀린 말이 된다.
        """
        assert qualifies(20.0, 90.0, trigger) is None

    def test_both_tiny_is_not_divergence(self, trigger):
        assert qualifies(3.0, -3.0, trigger) is None

    def test_opposing_needs_both_sides_material(self, trigger):
        assert qualifies(80.0, -5.0, trigger) == "unresponsive"
        assert qualifies(80.0, -20.0, trigger) == "opposing"


class TestSeverity:
    @pytest.fixture
    def cfg(self):
        return load_scoring()["divergence"]

    def test_grows_with_gap(self, cfg):
        assert severity_of(30, 80, 2, cfg) < severity_of(70, 80, 2, cfg)

    def test_grows_with_duration(self, cfg):
        """한 틱짜리 노이즈와 지속되는 구조적 괴리는 다르다."""
        assert severity_of(60, 80, 2, cfg) < severity_of(60, 80, 6, cfg)

    def test_persistence_is_capped(self, cfg):
        assert severity_of(60, 80, 20, cfg) == pytest.approx(
            severity_of(60, 80, 6, cfg)
        )

    def test_materiality_kills_trivial_gaps(self, cfg):
        """A=+3, B=-3 은 통계적으로 괴리지만 실무적으로 무의미하다."""
        assert severity_of(6, 3, 4, cfg) < 2.0


class TestDurationGating:
    def test_first_tick_publishes_nothing(self, ai_ticks):
        first, _ = ai_ticks
        assert first.snapshot.divergences == []
        assert first.pending, "후보는 남아야 다음 틱에서 이어붙일 수 있다"

    def test_second_tick_confirms(self, ai_ticks):
        _, second = ai_ticks
        assert second.snapshot.divergences
        assert all(d.duration_periods >= 2 for d in second.snapshot.divergences)

    def test_first_detected_at_is_preserved(self, ai_ticks):
        first, second = ai_ticks
        pending_by_id = {d.id: d for d in first.pending}
        for d in second.snapshot.divergences:
            if d.id in pending_by_id:
                assert d.first_detected_at == pending_by_id[d.id].first_detected_at

    def test_sorted_by_severity(self, ai_ticks):
        _, second = ai_ticks
        sev = [d.severity for d in second.snapshot.divergences]
        assert sev == sorted(sev, reverse=True)


class TestRequirement7:
    """
    요구 7 의 예시 상황.

        ⚠ AI Divergence
        News Sentiment: +82 / Price Momentum: +61 / Foreign Flow: -34
        "AI 관련 뉴스와 가격은 긍정적이나 외국인 수급이 동반되지 않고 있음"
    """

    def test_ai_theme_has_the_described_shape(self, ai_ticks):
        _, second = ai_ticks
        ai = next(t for t in second.snapshot.themes if t.theme_id == "ai")
        assert ai.news_sentiment > 0
        assert ai.price_momentum > 0
        assert ai.flow_momentum < 0

    def test_price_vs_flow_detected(self, ai_ticks):
        _, second = ai_ticks
        ai_div = [
            d
            for d in second.snapshot.divergences
            if d.related_theme == "ai" and d.type is DivergenceType.PRICE_VS_FLOW
        ]
        assert ai_div, "가격과 수급의 괴리를 잡지 못했다"
        assert ai_div[0].severity_band in (SeverityBand.CRITICAL, SeverityBand.HIGH)

    def test_news_vs_flow_detected(self, ai_ticks):
        _, second = ai_ticks
        assert any(
            d.related_theme == "ai" and d.type is DivergenceType.NEWS_VS_FLOW
            for d in second.snapshot.divergences
        )

    def test_explanation_generated_without_llm(self, ai_ticks):
        _, second = ai_ticks
        assert second.snapshot.data_health.llm_status == "disabled"
        for d in second.snapshot.divergences:
            assert d.explanation
            assert d.llm_commentary is None

    def test_legs_carry_the_raw_numbers(self, ai_ticks):
        """재현할 수 있어야 한다. 설명만 있고 숫자가 없으면 검증이 불가능하다."""
        _, second = ai_ticks
        for d in second.snapshot.divergences:
            assert len(d.legs) == 2
            assert d.gap == pytest.approx(abs(d.legs[0].value - d.legs[1].value))


class TestExplanations:
    def test_never_reverses_active_and_quiet(self, ai_ticks, shock_ticks):
        """
        무반응 문장이 큰 쪽과 작은 쪽을 뒤바꿔 말하면 안 된다.
        "가격은 -8로 움직였으나 수급은 +39에 그쳤다" 같은 문장은 틀렸다.
        """
        for _, second in (ai_ticks, shock_ticks):
            for d in second.snapshot.divergences:
                if "그쳤다" not in d.explanation:
                    continue
                big, small = sorted(d.legs, key=lambda l: abs(l.value), reverse=True)
                before, after = d.explanation.split("그쳤다")[0].split("움직였으나")
                assert f"{big.value:+.0f}" in before
                assert f"{small.value:+.0f}" in after

    def test_no_unresolved_particle_markers(self, ai_ticks, shock_ticks):
        """화면에 "은(는)" 이 그대로 나가면 안 된다."""
        for _, second in (ai_ticks, shock_ticks):
            for d in second.snapshot.divergences:
                assert "(는)" not in d.explanation
                assert "(가)" not in d.explanation
                assert "(로)" not in d.explanation

    def test_rules_define_both_explanation_kinds(self):
        rules = load_divergence_rules()
        specs = (
            rules["theme_pairs"]
            + rules["instrument_pairs"]
            + rules["state_vs_volatility"]
            + [rules["theme_vs_asset"]]
        )
        for spec in specs:
            assert {"opposing", "unresponsive"} <= set(spec["explanation"]), spec["id"]


class TestKoreanParticles:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("가격 모멘텀은(는)", "가격 모멘텀은"),
            ("VIX은(는)", "VIX는"),
            ("금은(는)", "금은"),
            ("+66으로(로)", "+66으로"),
            ("+65으로(로)", "+65로"),
            ("수급이(가)", "수급이"),
        ],
    )
    def test_particle_selection(self, text, expected):
        assert fix_particles(text) == expected

    def test_unknown_ending_left_alone(self):
        """틀린 조사를 쓰느니 이중 표기가 낫다."""
        assert fix_particles("※은(는)") == "※은(는)"

    def test_batchim_detection(self):
        assert has_batchim("각") is True
        assert has_batchim("가") is False
        assert has_batchim("") is None


class TestNewsSufficiency:
    def test_news_divergence_requires_enough_articles(self, shock_ticks):
        """기사 1건으로 "내러티브가 가격과 어긋난다" 고 말하지 않는다."""
        _, second = shock_ticks
        by_id = {t.theme_id: t for t in second.snapshot.themes}
        for d in second.snapshot.divergences:
            if d.type not in (
                DivergenceType.NEWS_VS_PRICE,
                DivergenceType.NEWS_VS_FLOW,
            ):
                continue
            theme = by_id[d.related_theme]
            assert len(theme.supporting_events) >= 2


class TestReproducibility:
    def test_same_inputs_same_divergences(self):
        a = _two_ticks("ai_divergence")[1].snapshot.divergences
        b = _two_ticks("ai_divergence")[1].snapshot.divergences
        assert [d.model_dump(exclude={"as_of", "first_detected_at"}) for d in a] == [
            d.model_dump(exclude={"as_of", "first_detected_at"}) for d in b
        ]
