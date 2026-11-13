"""
FeatureEngine 테스트 (설계서 STEP 5.1).

정량 레이어 전체가 이 모듈 위에 선다. z 정의가 틀리면 Market State 도
Theme Score 도 Divergence 도 전부 틀린다.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from marketpulse.engines.features import (
    MIN_OBSERVATIONS,
    TRADING_DAYS,
    Z_CLAMP,
    change_series,
    compute_feature,
    percentile_rank,
    rolling_sums,
    rolling_z,
)
from marketpulse.models.common import DataMeta, DataMode, utcnow
from marketpulse.models.market import MarketSeries


def _series(instrument_id: str, values: list[float], stamps=None) -> MarketSeries:
    now = utcnow()
    n = len(values)
    if stamps is None:
        from datetime import timedelta

        stamps = [now - timedelta(days=n - 1 - i) for i in range(n)]
    return MarketSeries(
        instrument_id=instrument_id,
        timestamps=stamps,
        values=values,
        meta=DataMeta(source="test", mode=DataMode.MOCK, retrieved_at=now, as_of=stamps[-1]),
    )


class TestChangeSeries:
    def test_price_uses_log_returns(self):
        out = change_series(np.array([100.0, 110.0]), "price")
        assert out[0] == pytest.approx(math.log(1.1))

    def test_level_uses_differences(self):
        """금리 4.20 -> 4.35 는 0.15 포인트 변화다. 로그수익률이 아니다."""
        out = change_series(np.array([4.20, 4.35]), "level")
        assert out[0] == pytest.approx(0.15)

    def test_nonpositive_price_becomes_nan(self):
        out = change_series(np.array([100.0, 0.0, 50.0]), "price")
        assert np.isnan(out).any()

    def test_level_handles_negative_values(self):
        """수급은 음수가 정상이다."""
        out = change_series(np.array([-500.0, 300.0]), "level")
        assert out[0] == pytest.approx(800.0)


class TestRollingZ:
    def test_baseline_excludes_current_observation(self):
        """
        현재 값을 기준선에 포함시키면 충격이 자기 자신을 희석한다.
        기준선은 직전 구간만이어야 한다.
        """
        data = np.array([0.0] * 40 + [1.0, -1.0] * 20 + [10.0])
        z, obs = rolling_z(data, window=60)
        baseline = data[-61:-1]
        expected = (data[-1] - baseline.mean()) / baseline.std(ddof=1)
        assert z == pytest.approx(min(expected, Z_CLAMP))
        assert obs == 60

    def test_returns_none_when_too_short(self):
        z, obs = rolling_z(np.arange(5, dtype=float), window=60)
        assert z is None, "관측치가 부족하면 0 이 아니라 None 이다"

    def test_returns_none_on_zero_variance(self):
        z, _ = rolling_z(np.ones(100), window=60)
        assert z is None

    def test_clamped(self):
        data = np.concatenate([np.random.default_rng(3).normal(0, 1, 80), [500.0]])
        z, _ = rolling_z(data, window=60)
        assert z == pytest.approx(Z_CLAMP)

    def test_min_observations_boundary(self):
        rng = np.random.default_rng(1)
        just_under = rng.normal(0, 1, MIN_OBSERVATIONS)
        just_over = rng.normal(0, 1, MIN_OBSERVATIONS + 1)
        assert rolling_z(just_under, window=60)[0] is None
        assert rolling_z(just_over, window=60)[0] is not None

    def test_ignores_nan(self):
        rng = np.random.default_rng(5)
        data = rng.normal(0, 1, 90)
        data[3] = np.nan
        z, obs = rolling_z(data, window=60)
        assert z is not None and math.isfinite(z)


class TestRollingSums:
    def test_span_sum(self):
        out = rolling_sums(np.array([1.0, 2.0, 3.0, 4.0]), 2)
        assert out.tolist() == [3.0, 5.0, 7.0]

    def test_empty_when_too_short(self):
        assert rolling_sums(np.array([1.0]), 5).size == 0


class TestPercentileRank:
    def test_max_is_top(self):
        assert percentile_rank(np.array([float(i) for i in range(50)])) > 95

    def test_min_is_bottom(self):
        vals = [float(i) for i in range(50)][::-1]
        assert percentile_rank(np.array(vals)) < 5

    def test_none_when_too_short(self):
        assert percentile_rank(np.array([1.0, 2.0])) is None


class TestComputeFeature:
    def test_rate_change_reported_in_bp(self, instruments_by_id):
        """US10Y 가 4.20 -> 4.35 면 '3.6% 상승' 이 아니라 '15bp 상승' 이다."""
        values = [4.20 + 0.001 * ((i * 7) % 11 - 5) for i in range(90)]
        values[-1] = values[-2] + 0.15
        f = compute_feature(instruments_by_id["US10Y"], _series("US10Y", values))
        assert f.ret_1d == pytest.approx(15.0, abs=1e-6)

    def test_price_change_reported_in_percent(self, instruments_by_id):
        rng = np.random.default_rng(11)
        values = list(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 90))))
        values.append(values[-1] * 1.025)
        f = compute_feature(instruments_by_id["SPX"], _series("SPX", values))
        assert f.ret_1d == pytest.approx(2.5, abs=1e-6)

    def test_realized_vol_annualized_for_price(self, instruments_by_id):
        rng = np.random.default_rng(13)
        chg = rng.normal(0, 0.01, 90)
        values = list(100 * np.exp(np.cumsum(chg)))
        f = compute_feature(instruments_by_id["SPX"], _series("SPX", values))
        expected = float(np.std(np.diff(np.log(values))[-20:], ddof=1)) * math.sqrt(TRADING_DAYS) * 100
        assert f.realized_vol_20d == pytest.approx(expected)

    def test_realized_vol_matches_ret_unit_for_rates(self, instruments_by_id):
        """level 계열은 연율화하지 않고 ret_1d 와 같은 단위(bp)를 쓴다."""
        rng = np.random.default_rng(17)
        values = list(4.2 + np.cumsum(rng.normal(0, 0.05, 90)))
        f = compute_feature(instruments_by_id["US10Y"], _series("US10Y", values))
        expected = float(np.std(np.diff(values)[-20:], ddof=1)) * 100
        assert f.realized_vol_20d == pytest.approx(expected)

    def test_short_series_yields_none_not_zero(self, instruments_by_id):
        f = compute_feature(instruments_by_id["SPX"], _series("SPX", [100.0, 101.0, 102.0]))
        assert f.z_1d is None and f.z_5d is None and f.rsi_14 is None
        assert f.ma_dist_20 is None and f.percentile_1y is None

    def test_carries_source_metadata(self, instruments_by_id):
        f = compute_feature(instruments_by_id["SPX"], _series("SPX", [100.0] * 90))
        assert f.meta.source == "test" and f.meta.mode is DataMode.MOCK

    def test_reproducible(self, instruments_by_id, series):
        a = compute_feature(instruments_by_id["SOXX"], series["SOXX"])
        b = compute_feature(instruments_by_id["SOXX"], series["SOXX"])
        assert a.model_dump() == b.model_dump()


class TestAgainstScenario:
    def test_declared_shocks_match_z_1d(self, instruments_by_id, series):
        """시나리오에 +1.25σ 라 적으면 z_1d 가 정확히 +1.25 여야 한다 (요구 14)."""
        from marketpulse.adapters.market.scenario import load_scenario
        from marketpulse.config.settings import MOCK_DIR

        for iid, target in load_scenario(MOCK_DIR, "baseline").shocks.items():
            f = compute_feature(instruments_by_id[iid], series[iid])
            assert f.z_1d == pytest.approx(target, abs=1e-6), iid
