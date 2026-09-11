"""
MOCK 어댑터 테스트.

현재 환경은 외부 마켓데이터 API 가 전면 차단이라 MOCK 이 유일한 데이터
경로다. 따라서 MOCK 의 결정론성은 편의가 아니라 전제다.
"""

from __future__ import annotations

import numpy as np
import pytest

from marketpulse.adapters.market.mock import MockMarketAdapter, business_timestamps
from marketpulse.adapters.market.scenario import (
    RegimeSpec,
    Scenario,
    available_scenarios,
    load_scenario,
)
from marketpulse.adapters.market.synthetic import Regime, generate, solve_last_change
from marketpulse.config.settings import MOCK_DIR
from marketpulse.engines.features import change_series
from marketpulse.models.common import DataMode


class TestDeterminism:
    def test_same_seed_same_series(self, instruments, as_of):
        a = MockMarketAdapter(MOCK_DIR, "baseline").fetch_series(
            instruments, bars=180, as_of=as_of
        )
        b = MockMarketAdapter(MOCK_DIR, "baseline").fetch_series(
            instruments, bars=180, as_of=as_of
        )
        assert {k: v.values for k, v in a.items()} == {k: v.values for k, v in b.items()}

    def test_instruments_are_independent(self, instruments_by_id):
        """한 종목의 시드가 다른 종목에 영향을 주면 안 된다."""
        g1 = generate(
            instruments_by_id["SPX"], Regime(base=100, vol=0.01),
            bars=180, window=60, seed=1,
        )
        g2 = generate(
            instruments_by_id["NDX"], Regime(base=100, vol=0.01),
            bars=180, window=60, seed=2,
        )
        assert g1.values != g2.values


class TestShockReproduction:
    """시나리오에 적은 σ 가 FeatureEngine 의 z_1d 로 정확히 재현되어야 한다."""

    @pytest.mark.parametrize("target", [-2.5, -1.0, 0.5, 1.25, 3.0])
    def test_solve_last_change_hits_target(self, target):
        rng = np.random.default_rng(7)
        prior = rng.normal(0.0, 0.01, size=120)
        last = solve_last_change(prior, target, window=60)
        tail = prior[-60:]
        z = (last - tail.mean()) / tail.std(ddof=1)
        assert z == pytest.approx(target, abs=1e-9)

    def test_scenario_shocks_land_exactly(self, series, instruments_by_id):
        scenario = load_scenario(MOCK_DIR, "baseline")
        assert scenario.shocks, "테스트할 shock 이 없다"
        for iid, target in scenario.shocks.items():
            ins = instruments_by_id[iid]
            chg = change_series(np.asarray(series[iid].values, float), ins.series_kind)
            tail = chg[-61:-1]
            z = (chg[-1] - tail.mean()) / tail.std(ddof=1)
            assert z == pytest.approx(target, abs=1e-6), f"{iid} 의 shock 이 어긋났다"

    def test_solve_rejects_zero_variance(self):
        with pytest.raises(ValueError, match="표준편차"):
            solve_last_change(np.zeros(80), 1.0, window=60)


class TestQuietCompression:
    def test_unshocked_moves_are_damped(self, series, instruments_by_id):
        """선언하지 않은 움직임이 선언한 충격을 덮으면 안 된다."""
        scenario = load_scenario(MOCK_DIR, "baseline")
        assert scenario.quiet_z is not None
        for iid, s in series.items():
            if iid in scenario.shocks or instruments_by_id[iid].derived_from:
                continue
            chg = change_series(np.asarray(s.values, float), instruments_by_id[iid].series_kind)
            tail = chg[-61:-1]
            z = (chg[-1] - tail.mean()) / tail.std(ddof=1)
            assert abs(z) <= scenario.quiet_z + 1e-6, f"{iid} z={z:.2f}"

    def test_compression_is_soft_not_a_hard_cap(self, series, instruments_by_id):
        """하드 컷이면 여러 종목이 정확히 같은 z 에 뭉쳐 인공물로 보인다."""
        scenario = load_scenario(MOCK_DIR, "baseline")
        zs = []
        for iid, s in series.items():
            if iid in scenario.shocks or instruments_by_id[iid].derived_from:
                continue
            chg = change_series(np.asarray(s.values, float), instruments_by_id[iid].series_kind)
            tail = chg[-61:-1]
            zs.append(round(abs((chg[-1] - tail.mean()) / tail.std(ddof=1)), 4))
        at_cap = sum(1 for z in zs if abs(z - scenario.quiet_z) < 1e-3)
        assert at_cap <= 1, f"{at_cap}개가 상한에 정확히 뭉쳤다"


class TestDerived:
    def test_curve_is_spread_in_bp(self, series):
        """2s10s 커브는 10Y - 2Y 를 bp 로 표현한 값이다."""
        expected = [
            (a - b) * 100.0
            for a, b in zip(series["US10Y"].values, series["US2Y"].values)
        ]
        assert series["CURVE_2S10S"].values == pytest.approx(expected)

    def test_copper_gold_is_ratio(self, series):
        expected = [
            a / b for a, b in zip(series["COPPER"].values, series["GOLD"].values)
        ]
        assert series["COPPER_GOLD"].values == pytest.approx(expected)


class TestShape:
    def test_all_instruments_covered(self, series, instruments):
        assert set(series) == {i.id for i in instruments}

    def test_series_length_and_alignment(self, series):
        for s in series.values():
            assert len(s.values) == len(s.timestamps) >= 180

    def test_metadata_is_mock(self, series):
        for s in series.values():
            assert s.meta.mode is DataMode.MOCK
            assert s.meta.source == "mock:scenario_baseline"

    def test_ends_at_requested_time(self, series, as_of):
        for s in series.values():
            assert s.as_of == as_of

    def test_business_timestamps_skip_weekends(self, as_of):
        stamps = business_timestamps(as_of, 40)
        assert all(t.weekday() < 5 for t in stamps)
        assert stamps == sorted(stamps)

    def test_floor_and_cap_respected(self, series):
        assert min(series["VIX"].values) >= 9.0
        assert max(series["VIX"].values) <= 80.0
        assert 0.0 <= min(series["KOSPI_ADV_RATIO"].values)
        assert max(series["KOSPI_ADV_RATIO"].values) <= 0.98


class TestScenarioFiles:
    def test_baseline_exists_and_validates(self):
        assert "baseline" in available_scenarios(MOCK_DIR)
        sc = load_scenario(MOCK_DIR, "baseline")
        assert sc.title and sc.description

    def test_history_exceeds_zscore_window(self):
        """P0 에서 히스토리를 빼먹으면 P1 전체가 막힌다 (설계서 STEP 6.1)."""
        sc = load_scenario(MOCK_DIR, "baseline")
        assert sc.bars >= 60 + 3

    def test_unknown_scenario_lists_alternatives(self):
        with pytest.raises(FileNotFoundError, match="baseline"):
            load_scenario(MOCK_DIR, "does-not-exist")

    def test_absurd_shock_rejected(self):
        with pytest.raises(ValueError, match="비현실적"):
            Scenario(name="x", shocks={"SPX": 99.0})

    def test_regime_override_beats_class_default(self, instruments_by_id):
        sc = Scenario(
            name="x",
            class_defaults={"equity": RegimeSpec(vol=0.02)},
            regimes={"SPX": RegimeSpec(base=5000.0, vol=0.005)},
        )
        spx = sc.regime_for(instruments_by_id["SPX"])
        ndx = sc.regime_for(instruments_by_id["NDX"])
        assert (spx.base, spx.vol) == (5000.0, 0.005)
        assert ndx.vol == 0.02

    def test_too_few_bars_is_an_error(self, instruments_by_id):
        with pytest.raises(ValueError, match="부족"):
            generate(
                instruments_by_id["SPX"], Regime(), bars=30, window=60, seed=1
            )
