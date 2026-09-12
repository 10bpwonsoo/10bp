"""
MarketStateEngine 테스트 (설계서 STEP 5.3 / 5.4).

이 파일의 핵심은 TestRequirement14 다. 요구 14 가 명시한 검증 케이스를
그대로 재현하고, 어떤 rule 에 의해 판정이 나왔는지까지 고정한다.
"""

from __future__ import annotations

import pytest

from marketpulse.adapters.market.mock import MockMarketAdapter
from marketpulse.config.settings import MOCK_DIR
from marketpulse.engines.factors import compute_factors, load_factor_specs
from marketpulse.engines.market_state import (
    compute_confidence,
    compute_market_state,
    evaluate_hypotheses,
    load_state_rules,
)
from marketpulse.engines.normalize import build_snapshot
from marketpulse.models.common import DataMode
from marketpulse.models.state import FACTOR_NAMES, ConfirmationResult, StateLabel
from marketpulse.models.theme import DataQualityBand


@pytest.fixture
def shock_snapshot(instruments, as_of):
    series = MockMarketAdapter(MOCK_DIR, "inflation_shock").fetch_series(
        instruments, bars=180, as_of=as_of
    )
    return build_snapshot(instruments, series, mode=DataMode.MOCK, as_of=as_of)


@pytest.fixture
def quiet_snapshot(instruments, series, as_of):
    return build_snapshot(instruments, series, mode=DataMode.MOCK, as_of=as_of)


class TestFactors:
    def test_all_designed_factors_present(self, quiet_snapshot):
        factors = compute_factors(quiet_snapshot)
        assert set(factors) == set(FACTOR_NAMES)

    def test_config_weights_sum_to_one(self):
        for name, spec in load_factor_specs().items():
            total = sum(c["weight"] for c in spec["components"])
            assert total == pytest.approx(1.0), name

    def test_sign_is_applied(self, shock_snapshot):
        """VIX 가 오르면 RiskAppetite 는 내려야 한다."""
        factors = compute_factors(shock_snapshot)
        vix = next(
            c for c in factors["RiskAppetite"].breakdown.contributions if c.key == "VIX"
        )
        assert vix.normalized > 0
        assert vix.contribution < 0

    def test_breakdown_is_traceable(self, shock_snapshot):
        f = compute_factors(shock_snapshot)["Inflation"]
        keys = {c.key for c in f.breakdown.contributions}
        assert {"BRENT", "WTI", "COPPER", "BE10Y"} <= keys
        recomputed = sum(c.contribution for c in f.breakdown.contributions)
        weights = sum(abs(c.weight) for c in f.breakdown.contributions)
        assert f.score == pytest.approx(recomputed / weights)

    def test_missing_inputs_lower_quality(self, instruments, series, as_of):
        partial = {k: v for k, v in series.items() if k not in {"BRENT", "WTI"}}
        snap = build_snapshot(instruments, partial, mode=DataMode.MOCK, as_of=as_of)
        infl = compute_factors(snap)["Inflation"]
        assert set(infl.breakdown.missing_inputs) == {"BRENT", "WTI"}
        assert infl.data_quality is not DataQualityBand.OK

    def test_reproducible(self, shock_snapshot):
        a = compute_factors(shock_snapshot)
        b = compute_factors(shock_snapshot)
        for name in a:
            assert a[name].breakdown.inputs_hash == b[name].breakdown.inputs_hash
            assert a[name].score == b[name].score


class TestRuleConfig:
    def test_support_weights_sum_to_one(self):
        for name, spec in load_state_rules().items():
            total = sum(s["weight"] for s in spec["support"])
            assert total == pytest.approx(1.0), name

    def test_every_label_except_neutral_has_rules(self):
        labels = {s.value for s in StateLabel} - {"NEUTRAL"}
        assert set(load_state_rules()) == labels

    def test_ambiguous_state_has_no_expected_table(self):
        """방향이 모호한 상태에 틀린 기대표를 두느니 비워 둔다."""
        assert load_state_rules()["POLICY_DRIVEN"]["expected_response"] == {}


class TestRequirement14:
    """
    요구 14 의 검증 케이스.

        Oil +2σ / Rates +1.5σ / VIX +1.5σ / Equity -1.2σ
        →  Inflation Shock / Risk-Off

    입력값과 출력값이 재현 가능해야 하고, 어떤 rule 에 의해 발생했는지
    확인할 수 있어야 한다.
    """

    def test_inputs_are_as_declared(self, shock_snapshot):
        assert shock_snapshot.z("BRENT") == pytest.approx(2.10, abs=1e-6)
        assert shock_snapshot.z("US10Y") == pytest.approx(1.60, abs=1e-6)
        assert shock_snapshot.z("VIX") == pytest.approx(1.50, abs=1e-6)
        assert shock_snapshot.z("SPX") == pytest.approx(-1.20, abs=1e-6)

    def test_primary_and_secondary(self, shock_snapshot, instruments_by_id):
        state = compute_market_state(shock_snapshot, instruments_by_id)
        assert state.primary_label is StateLabel.INFLATION_SHOCK
        assert state.secondary_label is StateLabel.RISK_OFF

    def test_which_rules_fired(self, shock_snapshot, instruments_by_id):
        """'어떤 rule 에 의해 발생했는지' 를 그대로 고정한다."""
        state = compute_market_state(shock_snapshot, instruments_by_id)
        top = state.hypotheses[0]
        assert top.label is StateLabel.INFLATION_SHOCK
        assert top.score == pytest.approx(1.0)
        assert [m.rule_id for m in top.matched_rules if m.passed] == [
            "inf_core",
            "inf_rates",
            "inf_risk",
            "inf_vol",
            "inf_growth",
        ]

    def test_what_separates_the_two_labels(self, shock_snapshot, instruments_by_id):
        """
        Risk-Off 가 2등인 이유는 국내 수급 조건 하나가 실패했기 때문이다.
        이 한 줄이 순위를 가른다.
        """
        state = compute_market_state(shock_snapshot, instruments_by_id)
        risk_off = next(
            h for h in state.hypotheses if h.label is StateLabel.RISK_OFF
        )
        failed = [m.rule_id for m in risk_off.matched_rules if not m.passed]
        assert failed == ["ro_flow"]
        assert risk_off.score == pytest.approx(0.875)

    def test_observed_values_recorded(self, shock_snapshot, instruments_by_id):
        state = compute_market_state(shock_snapshot, instruments_by_id)
        core = next(
            m for m in state.hypotheses[0].matched_rules if m.rule_id == "inf_core"
        )
        assert core.expression == "Inflation >= 1.0"
        assert core.observed == pytest.approx(state.factors["Inflation"].score)

    def test_reproducible(self, shock_snapshot, instruments_by_id):
        a = compute_market_state(shock_snapshot, instruments_by_id)
        b = compute_market_state(shock_snapshot, instruments_by_id)
        assert a.primary_label == b.primary_label
        assert a.confidence == b.confidence
        assert (
            a.confidence_breakdown.inputs_hash == b.confidence_breakdown.inputs_hash
        )


class TestNeutral:
    def test_quiet_market_gets_no_label(self, quiet_snapshot, instruments_by_id):
        """
        평시 시나리오에서는 어느 룰도 발동하지 않아야 한다.
        데이터가 조용한데 라벨을 붙이면 그 시스템은 아무 말이나 하는 것이다.
        """
        state = compute_market_state(quiet_snapshot, instruments_by_id)
        assert state.primary_label is StateLabel.NEUTRAL
        assert state.secondary_label is None
        assert all(h.score == 0.0 for h in state.hypotheses)

    def test_neutral_still_reports_factors(self, quiet_snapshot, instruments_by_id):
        """판정이 없어도 factor 는 보여야 한다. 요구 6 이 요구한 바다."""
        state = compute_market_state(quiet_snapshot, instruments_by_id)
        assert len(state.factors) == len(FACTOR_NAMES)

    def test_neutral_narrative_says_so(self, quiet_snapshot, instruments_by_id):
        state = compute_market_state(quiet_snapshot, instruments_by_id)
        assert state.narrative and "충족하지 않" in state.narrative
        assert state.narrative_source == "template"


class TestConfirmation:
    def test_confirms_expected_directions(self, shock_snapshot, instruments_by_id):
        state = compute_market_state(shock_snapshot, instruments_by_id)
        c = state.cross_asset_confirmation
        assert "BRENT" in c.confirmed
        assert "NDX" in c.confirmed  # 기대 -1, 실제 -1.6
        assert c.verdict == "HIGH"

    def test_note_is_generated_without_llm(self, shock_snapshot, instruments_by_id):
        """요구 6 의 문장이 템플릿에서 나온다."""
        state = compute_market_state(shock_snapshot, instruments_by_id)
        assert state.cross_asset_confirmation.note
        assert state.narrative_source == "template"

    def test_empty_expected_table_is_not_scored(
        self, shock_snapshot, instruments_by_id
    ):
        from marketpulse.engines.confirmation import evaluate_confirmation

        result = evaluate_confirmation({}, shock_snapshot, instruments_by_id)
        assert result.score == 0.0
        assert "적용하지 않" in result.note


class TestConfidence:
    def _hyps(self, top: float, second: float):
        from marketpulse.models.state import StateHypothesis

        return [
            StateHypothesis(label=StateLabel.RISK_OFF, score=top),
            StateHypothesis(label=StateLabel.RISK_ON, score=second),
        ]

    def test_tight_race_lowers_confidence(self):
        far = compute_confidence(
            self._hyps(1.0, 0.2), ConfirmationResult(), 1.0, 1.0
        )
        close = compute_confidence(
            self._hyps(1.0, 0.98), ConfirmationResult(), 1.0, 1.0
        )
        assert far.value > close.value

    def test_missing_data_lowers_confidence(self):
        full = compute_confidence(self._hyps(1.0, 0.2), ConfirmationResult(), 1.0, 1.0)
        thin = compute_confidence(self._hyps(1.0, 0.2), ConfirmationResult(), 0.3, 1.0)
        assert full.value > thin.value

    def test_no_history_renormalizes_instead_of_zero(self):
        """
        직전 스냅샷이 없다고 persistence 를 0 으로 두면 첫 틱의 신뢰도가
        부당하게 깎인다. 모르는 항은 분모에서 빼야 한다.
        """
        without = compute_confidence(
            self._hyps(1.0, 0.2), ConfirmationResult(), 1.0, None
        )
        as_zero = compute_confidence(
            self._hyps(1.0, 0.2), ConfirmationResult(), 1.0, 0.0
        )
        assert without.value > as_zero.value
        assert "persistence" in without.missing_inputs
        assert "persistence" not in as_zero.missing_inputs

    def test_breakdown_lists_components(self):
        bd = compute_confidence(self._hyps(1.0, 0.2), ConfirmationResult(), 1.0, 1.0)
        assert {c.key for c in bd.contributions} >= {
            "separation",
            "coverage",
            "persistence",
        }

    def test_persistence_rewards_same_label(self, shock_snapshot, instruments_by_id):
        fresh = compute_market_state(shock_snapshot, instruments_by_id)
        repeated = compute_market_state(
            shock_snapshot,
            instruments_by_id,
            previous_label=StateLabel.INFLATION_SHOCK,
        )
        flipped = compute_market_state(
            shock_snapshot, instruments_by_id, previous_label=StateLabel.RISK_ON
        )
        assert repeated.confidence > fresh.confidence > flipped.confidence


class TestDrivers:
    def test_sorted_and_prefers_expected_assets(
        self, shock_snapshot, instruments_by_id
    ):
        state = compute_market_state(shock_snapshot, instruments_by_id)
        expected = set(
            load_state_rules()["INFLATION_SHOCK"]["expected_response"]
        )
        assert state.main_drivers[0].instrument_id in expected
        assert state.main_drivers[0].arrow == "↑↑"

    def test_threshold_applied(self, shock_snapshot, instruments_by_id):
        state = compute_market_state(shock_snapshot, instruments_by_id)
        assert all(abs(d.z) >= 0.5 for d in state.main_drivers)


class TestUnevaluatedRivalsAreNotDefeatedRivals:
    """
    데이터가 없어 평가조차 못 한 가설을 "제친 경쟁자" 로 세면, 데이터가
    빠질수록 confidence 가 올라가는 뒤집힌 지표가 된다.
    """

    def _hypothesis(self, label, score, *, evaluable):
        from marketpulse.models.state import RuleMatch, StateHypothesis

        return StateHypothesis(
            label=label,
            score=score,
            matched_rules=[
                RuleMatch(
                    rule_id="r",
                    expression="Growth <= -1.0",
                    kind="require",
                    passed=False,
                    observed=None if not evaluable else -0.2,
                    evaluable=evaluable,
                )
            ],
        )

    def _confidence(self, hypotheses, coverage=0.14):
        from marketpulse.engines.market_state import compute_confidence
        from marketpulse.models.state import ConfirmationResult

        return compute_confidence(
            hypotheses,
            ConfirmationResult(expected={}),
            coverage,
            None,
        )

    def test_unevaluable_rival_is_excluded(self):
        from marketpulse.models.state import StateLabel

        top = self._hypothesis(StateLabel.RISK_OFF, 0.8, evaluable=True)
        ghost = self._hypothesis(StateLabel.GROWTH_SHOCK, 0.0, evaluable=False)
        breakdown = self._confidence([top, ghost])
        keys = {c.key for c in breakdown.contributions}
        # 겨룰 상대가 없었으므로 separation 은 '모름' 이고 가중치에서 빠진다
        assert "separation" not in keys
        assert "separation" in breakdown.missing_inputs

    def test_evaluated_rival_still_counts(self):
        """실제로 평가되어 탈락한 경쟁자는 정상적으로 격차를 만든다."""
        from marketpulse.models.state import StateLabel

        top = self._hypothesis(StateLabel.RISK_OFF, 0.8, evaluable=True)
        loser = self._hypothesis(StateLabel.GROWTH_SHOCK, 0.0, evaluable=True)
        breakdown = self._confidence([top, loser])
        sep = next(c for c in breakdown.contributions if c.key == "separation")
        assert sep.normalized > 0.0

    def test_thin_data_does_not_inflate_confidence(self):
        """
        똑같이 1등이어도, 경쟁자가 평가된 경우와 평가조차 못 한 경우의
        confidence 가 같으면 안 된다.
        """
        from marketpulse.models.state import StateLabel

        top = self._hypothesis(StateLabel.RISK_OFF, 0.8, evaluable=True)
        real = self._confidence([top, self._hypothesis(StateLabel.GROWTH_SHOCK, 0.0, evaluable=True)])
        ghost = self._confidence([top, self._hypothesis(StateLabel.GROWTH_SHOCK, 0.0, evaluable=False)])
        assert ghost.value < real.value

    def test_state_without_require_rules_is_always_evaluable(self):
        """require 가 없는 상태는 막는 것이 없다. 평가 불가가 아니다."""
        from marketpulse.engines.market_state import _was_evaluable
        from marketpulse.models.state import StateHypothesis, StateLabel

        bare = StateHypothesis(label=StateLabel.NEUTRAL, score=0.0, matched_rules=[])
        assert _was_evaluable(bare)
