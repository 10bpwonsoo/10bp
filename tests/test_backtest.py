"""
신호 백테스트 테스트 (설계서 STEP 6.5).

여기서 검증하는 것은 지표의 정확성보다 **말하지 않는 것을 말하지 않는가**
다. 표본 5건으로 적중률을 내거나, look-ahead 로 성적을 부풀리거나,
방향 없는 신호에 방향이 있는 척하면 이 도구는 해롭다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from marketpulse.analysis.backtest import (
    MIN_SAMPLES,
    Observation,
    Signal,
    extract_signals,
    forward_returns,
    max_drawdown,
    run_backtest,
    summarize,
)
from marketpulse.models.common import DataMeta, DataMode
from marketpulse.models.market import MarketSeries

BASE = datetime(2026, 1, 2, tzinfo=timezone.utc)


def series(values: list[float], start: datetime = BASE) -> MarketSeries:
    return MarketSeries(
        instrument_id="SPX",
        timestamps=[start + timedelta(days=i) for i in range(len(values))],
        values=values,
        meta=DataMeta(
            source="test", mode=DataMode.MOCK, retrieved_at=BASE, as_of=BASE
        ),
    )


class TestMetrics:
    def test_max_drawdown_compounds(self):
        # +10% 뒤 -50% → 고점 1.10 에서 0.55 로. -50%
        assert max_drawdown([0.10, -0.50]) == pytest.approx(-50.0)

    def test_no_drawdown_when_monotonic(self):
        assert max_drawdown([0.01, 0.02, 0.03]) == pytest.approx(0.0)

    def test_empty_is_zero_not_an_error(self):
        assert max_drawdown([]) == 0.0

    def test_hit_needs_a_direction(self):
        """방향 없는 신호는 맞았다 틀렸다를 말하지 않는다."""
        up = Signal(as_of=BASE, kind="state", label="RISK_ON", expected_sign=1)
        none = Signal(as_of=BASE, kind="divergence", label="X", expected_sign=0)
        assert Observation(signal=up, horizon_bars=5, forward_return=0.02).hit
        assert not Observation(signal=up, horizon_bars=5, forward_return=-0.02).hit
        assert not Observation(signal=none, horizon_bars=5, forward_return=0.02).hit

    def test_hit_rate_ignores_directionless_signals(self):
        up = Signal(as_of=BASE, kind="state", label="RISK_ON", expected_sign=1)
        none = Signal(as_of=BASE, kind="divergence", label="X", expected_sign=0)
        obs = [
            Observation(signal=up, horizon_bars=5, forward_return=0.02),
            Observation(signal=none, horizon_bars=5, forward_return=-0.09),
        ]
        m = summarize("t", obs, baseline=0.0)
        # 방향 신호는 1건이고 그것은 맞았다. 100% 여야 한다.
        assert m.hit_rate == pytest.approx(100.0)

    def test_small_sample_is_flagged_not_hidden(self):
        up = Signal(as_of=BASE, kind="state", label="RISK_ON", expected_sign=1)
        m = summarize("t", [Observation(signal=up, horizon_bars=5, forward_return=0.02)], baseline=0.0)
        assert not m.usable
        assert str(MIN_SAMPLES) in m.note


class TestForwardReturns:
    def test_uses_only_past_bars(self):
        """
        판정 시각 이후의 봉을 진입가로 쓰면 look-ahead 다. 시각 이하의
        마지막 봉이어야 한다.
        """
        s = series([100.0, 110.0, 121.0, 133.1])
        stamps = [BASE + timedelta(days=1, hours=5)]  # 2일차 장 마감 뒤
        out = forward_returns(s, stamps, horizon_bars=1)
        # 2일차(110) 에서 3일차(121) → +10%
        assert out[stamps[0]] == pytest.approx(0.10)

    def test_tail_has_no_answer_yet(self):
        """마지막 봉들은 아직 결과가 없다. 0 으로 채우지 않는다."""
        s = series([100.0, 101.0, 102.0])
        stamps = [s.timestamps[-1]]
        assert forward_returns(s, stamps, horizon_bars=2) == {}

    def test_series_shorter_than_horizon_is_empty(self):
        assert forward_returns(series([1.0, 2.0]), [BASE], horizon_bars=5) == {}

    def test_timestamp_before_series_is_skipped(self):
        s = series([100.0, 101.0, 102.0, 103.0])
        assert forward_returns(s, [BASE - timedelta(days=5)], horizon_bars=1) == {}


class TestSignalExtraction:
    def _snapshot(self, label: str, as_of: datetime):
        from marketpulse.config.settings import Settings
        from marketpulse.engines.orchestrator import run_pipeline

        snap = run_pipeline(Settings(scenario="baseline"))
        state = snap.market_state.model_copy(update={"primary_label": label})
        return snap.model_copy(update={"as_of": as_of, "market_state": state})

    def test_state_counted_once_per_change(self):
        """
        같은 판정이 20틱 이어지는 것을 20개의 독립 신호로 세면 표본 수가
        부풀고 지표가 거짓말을 한다.
        """
        history = [
            self._snapshot("RISK_OFF", BASE + timedelta(days=i)) for i in range(5)
        ]
        state_signals = [s for s in extract_signals(history) if s.kind == "state"]
        assert len(state_signals) == 1

    def test_state_change_makes_a_new_signal(self):
        history = [
            self._snapshot("RISK_OFF", BASE),
            self._snapshot("RISK_ON", BASE + timedelta(days=1)),
            self._snapshot("RISK_ON", BASE + timedelta(days=2)),
        ]
        state_signals = [s for s in extract_signals(history) if s.kind == "state"]
        assert [s.label for s in state_signals] == ["RISK_OFF", "RISK_ON"]

    def test_divergences_carry_no_direction(self):
        """
        괴리는 어느 쪽으로 수렴할지 말하지 않는다. 억지로 부호를 붙이면
        없는 주장을 만드는 것이다.
        """
        from marketpulse.config.settings import Settings
        from marketpulse.engines.orchestrator import run_pipeline

        first = run_pipeline(Settings(scenario="ai_divergence"))
        second = run_pipeline(Settings(scenario="ai_divergence"), history=[first])
        signals = [s for s in extract_signals([first, second]) if s.kind == "divergence"]
        assert all(s.expected_sign == 0 for s in signals)


class TestReport:
    def test_refuses_to_report_on_thin_history(self):
        report = run_backtest([], {}, horizon_bars=5)
        assert report.by_signal == {}
        assert any(str(MIN_SAMPLES) in w for w in report.warnings)

    def test_says_when_returns_are_missing(self):
        from marketpulse.config.settings import Settings
        from marketpulse.engines.orchestrator import run_pipeline

        snap = run_pipeline(Settings(scenario="baseline"))
        history = [
            snap.model_copy(update={"as_of": BASE + timedelta(days=i)})
            for i in range(MIN_SAMPLES + 2)
        ]
        report = run_backtest(history, {}, horizon_bars=5)
        assert "수익률" in " ".join(report.warnings)

    def test_end_to_end_produces_metrics(self):
        from marketpulse.config.settings import Settings
        from marketpulse.engines.orchestrator import run_pipeline

        base = run_pipeline(Settings(scenario="baseline"))
        shock = run_pipeline(Settings(scenario="inflation_shock"))
        history = []
        for i in range(14):
            src = shock if i % 3 == 0 else base
            history.append(src.model_copy(update={"as_of": BASE + timedelta(days=i)}))

        returns = {s.as_of: (0.01 if i % 2 else -0.005) for i, s in enumerate(history)}
        report = run_backtest(history, returns, horizon_bars=3)
        assert report.baseline_return is not None
        assert report.by_signal
        for metrics in report.by_signal.values():
            assert metrics.samples > 0
            assert metrics.mean_return is not None
