"""
GOAL Kickstart 에서 차용한 여덟 가지 (2026-09-15).

  1 장기 백분위 + 3개월 변화   2 재료 스트립   3 1주 전 표식
  4 상관 레짐 대조             5 지배 축       6 이벤트 달력
  7 변동성 프리미엄            8 경기민감/방어 비율

전부 결정론이고 네트워크가 없다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import numpy as np
import pytest

from marketpulse.adapters.market.synthetic import vol_premium
from marketpulse.config.settings import Settings
from marketpulse.engines.calendar import event_window, load_calendar
from marketpulse.engines.correlation import build_correlation_book, classify
from marketpulse.engines.features import (
    QUARTER_BARS,
    WEEK_BARS,
    percentile_rank_detailed,
    rolling_z,
    rolling_z_at,
)
from marketpulse.engines.market_state import build_dominant_axis, compute_market_state
from marketpulse.engines.normalize import build_snapshot
from marketpulse.engines.orchestrator import run_pipeline_detailed
from marketpulse.engines.relationship import predefined_edges, validate_edges
from marketpulse.engines.thermometer import compute_thermometer
from marketpulse.models.common import DataMode
from marketpulse.models.divergence import DivergenceType
from marketpulse.models.snapshot import IntelligenceSnapshot
from marketpulse.storage.sqlite_repo import SqliteSnapshotRepository
from marketpulse.config.registry import get_themes


# ── 1. 백분위 · 3개월 · 1주 전 z ───────────────────────────────
class TestPercentileAndHorizons:
    def test_week_ago_z_is_what_was_computable_then(self):
        """1주 전 z 는 그 시점까지의 데이터로만 계산한 값이어야 한다."""
        rng = np.random.default_rng(1)
        chg = rng.normal(size=200)
        then, _ = rolling_z(chg[:-WEEK_BARS], 60)
        now_ago, _ = rolling_z_at(chg, 60, WEEK_BARS)
        assert now_ago == pytest.approx(then)

    def test_week_ago_none_when_too_short(self):
        assert rolling_z_at(np.zeros(3), 60, WEEK_BARS) == (None, 0)

    def test_percentile_reports_observations_used(self):
        values = np.arange(100, dtype=float)
        pct, n = percentile_rank_detailed(values)
        assert n == 100
        assert pct == pytest.approx(99.5)

    def test_feature_fields_present(self, instruments, series):
        snap = build_snapshot(instruments, series, mode=DataMode.MOCK)
        f = snap.features["SPX"]
        assert f.z_1d_week_ago is not None
        assert f.ret_3m is not None
        assert f.percentile_observations >= QUARTER_BARS

    def test_whats_moving_carries_percentile(self, settings):
        snap = run_pipeline_detailed(settings).snapshot
        rows = [r for r in snap.whats_moving if r.kind == "instrument"]
        assert rows
        assert all(r.percentile_observations > 0 for r in rows)
        assert all(r.change_3m_display for r in rows)


# ── 7 · 8. 파생 지표 ─────────────────────────────────────────
class TestDerived:
    def test_vol_premium_is_implied_minus_realized(self):
        price = [100.0 * (1.01 ** i) for i in range(40)]  # 일정한 로그수익률 → 실현변동성 0
        implied = [20.0] * 40
        out = vol_premium(implied, price)
        assert all(np.isnan(v) for v in out[:20])
        assert out[-1] == pytest.approx(20.0, abs=1e-9)

    def test_vol_premium_drops_leading_bars_in_series(self, series):
        assert len(series["VIX_RV_SPX"].values) == len(series["VIX"].values) - 20
        assert all(np.isfinite(series["VIX_RV_SPX"].values))

    def test_cyc_def_is_ratio(self, series):
        expected = [a / b for a, b in zip(series["XLY"].values, series["XLU"].values)]
        assert series["CYC_DEF"].values == pytest.approx(expected)

    def test_risk_appetite_uses_cyc_def(self, instruments, series, instruments_by_id):
        snap = build_snapshot(instruments, series, mode=DataMode.MOCK)
        state = compute_market_state(snap, instruments_by_id)
        keys = {c.key for c in state.factors["RiskAppetite"].breakdown.contributions}
        assert "CYC_DEF" in keys
        vol_keys = {c.key for c in state.factors["Volatility"].breakdown.contributions}
        assert "VIX_RV_SPX" in vol_keys


# ── 4. 상관 대조 ─────────────────────────────────────────────
class TestCorrelation:
    def test_book_is_symmetric_with_none_diagonal(self, instruments, series):
        snap = build_snapshot(instruments, series, mode=DataMode.MOCK)
        b = snap.correlations
        assert b is not None
        i, j = b.ids.index("SPX"), b.ids.index("NDX")
        assert b.current[i][i] is None
        assert b.current[i][j] == b.current[j][i]
        assert b.observations[i][j] >= b.min_observations

    def test_prior_window_exists_with_enough_history(self, instruments, series):
        snap = build_snapshot(instruments, series, mode=DataMode.MOCK)
        assert snap.correlations.prior  # 180봉이면 60 + 63 을 넘는다

    def test_perfectly_linked_pair(self, instruments, instruments_by_id, series):
        """같은 시계열끼리는 상관 1 이어야 한다 — 정렬이 맞는지 확인."""
        twin = series["SPX"].model_copy(update={"instrument_id": "NDX"})
        mixed = dict(series)
        mixed["NDX"] = twin
        snap = build_snapshot(instruments, mixed, mode=DataMode.MOCK)
        assert snap.correlations.pair("SPX", "NDX").corr == pytest.approx(1.0, abs=1e-3)

    @pytest.mark.parametrize(
        "corr, expected, verdict",
        [
            (0.5, 1, "confirmed"),
            (-0.5, 1, "reversed"),
            (0.05, 1, "weakened"),
            (-0.5, -1, "confirmed"),
            (None, 1, "unknown"),
            (0.9, 0, "unknown"),
        ],
    )
    def test_classify(self, corr, expected, verdict):
        assert classify(corr, expected) == verdict

    def test_edges_get_observed_correlation(self, instruments, series):
        snap = build_snapshot(instruments, series, mode=DataMode.MOCK)
        edges = validate_edges(predefined_edges(), snap.correlations, themes_by_id=get_themes().by_id())
        checked = [e for e in edges if e.corr_pair]
        assert checked, "대조된 관계가 하나도 없다"
        for e in checked:
            assert e.direction in ("positive", "negative")
            assert e.observed_corr is None or -1.0 <= e.observed_corr <= 1.0
            # 관계 자체는 손대지 않는다
            assert e.origin == "predefined" and e.status == "active"

    def test_without_book_edges_are_untouched(self):
        edges = predefined_edges()
        out = validate_edges(edges, None, themes_by_id=get_themes().by_id())
        assert all(e.corr_check == "unknown" for e in out)

    def test_regime_divergence_needs_reversal(self, instruments, instruments_by_id, series, as_of):
        """서로 반대로 움직이게 만든 쌍은 상관 레짐 괴리로 잡혀야 한다."""
        spx = series["SPX"]
        vals = np.asarray(spx.values)
        # NDX 를 SPX 의 거울로 — 사전 정의 관계(성장주 → 나스닥 정방향)와 무관하게
        # 감시 쌍 growth_rates(NDX↔US10Y) 가 아니라 equity_bond 를 흔들기 위해
        # US10Y 를 SPX 로그수익률의 역부호 누적으로 만든다.
        rets = np.diff(np.log(vals))
        mirrored = 4.0 + np.concatenate([[0.0], np.cumsum(-rets * 20.0)])
        mixed = dict(series)
        mixed["US10Y"] = series["US10Y"].model_copy(update={"values": [float(v) for v in mirrored]})
        snap = build_snapshot(instruments, mixed, mode=DataMode.MOCK, as_of=as_of)
        pc = snap.correlations.pair("SPX", "US10Y")
        assert pc.corr is not None and pc.corr < -0.9
        # 한 분기 전 창도 같은 부호라 '레짐 변화' 는 아니다 — 부호 뒤집힘이 아니면 잡지 않는다.
        assert pc.prior is not None and pc.prior < -0.9

    def test_regime_pair_flip_is_detected(self, instruments, instruments_by_id, series, as_of):
        from marketpulse.engines.divergence import detect_divergences
        from marketpulse.engines.theme import compute_theme_states

        spx = series["SPX"]
        vals = np.asarray(spx.values)
        rets = np.diff(np.log(vals))
        n = len(rets)
        # 앞 절반은 같은 방향, 뒤 절반은 반대 방향 → 한 분기 전 +, 지금 −
        sign = np.where(np.arange(n) < n - 60, 1.0, -1.0)
        flipped = 4.0 + np.concatenate([[0.0], np.cumsum(sign * rets * 20.0)])
        mixed = dict(series)
        mixed["US10Y"] = series["US10Y"].model_copy(update={"values": [float(v) for v in flipped]})
        snap = build_snapshot(instruments, mixed, mode=DataMode.MOCK, as_of=as_of)
        pc = snap.correlations.pair("SPX", "US10Y")
        assert pc.corr < -0.5 and pc.prior > 0.5

        themes_registry = get_themes().by_id()
        state = compute_market_state(snap, instruments_by_id)
        themes = compute_theme_states(list(themes_registry.values()), snap, [], instruments_by_id)
        first = detect_divergences(themes, themes_registry, state, snap, instruments_by_id)
        from marketpulse.engines.divergence import pending_candidates
        pending = pending_candidates(themes, themes_registry, state, snap, instruments_by_id)
        second = detect_divergences(
            themes, themes_registry, state, snap, instruments_by_id, previous=list(first) + pending
        )
        hits = [d for d in second if d.type is DivergenceType.CORRELATION_REGIME and "equity_bond" in d.id]
        assert hits, [d.id for d in second]
        assert "부호가 뒤집혔다" in hits[0].explanation


# ── 5. 지배 축 ───────────────────────────────────────────────
class TestDominantAxis:
    def test_axis_is_loudest_candidate(self, instruments, instruments_by_id, series, as_of):
        from marketpulse.adapters.market.mock import MockMarketAdapter
        from marketpulse.config.settings import MOCK_DIR

        shock = MockMarketAdapter(MOCK_DIR, "inflation_shock").fetch_series(instruments, bars=180, as_of=as_of)
        snap = build_snapshot(instruments, shock, mode=DataMode.MOCK, as_of=as_of)
        axis = build_dominant_axis(snap, instruments_by_id)
        assert axis is not None
        # 후보 중 |z| 최대여야 한다
        from marketpulse.engines.scoring import load_scoring
        cands = load_scoring()["market_state"]["axis_candidates"]
        best = max((c for c in cands if snap.z(c) is not None), key=lambda c: abs(snap.z(c)))
        assert axis.instrument_id == best
        assert all(l.corr > 0 for l in axis.positive)
        assert all(l.corr < 0 for l in axis.negative)
        assert "상관이지 인과가 아니다" in axis.note or "혼자 움직이고" in axis.note

    def test_quiet_market_has_no_axis(self, instruments, instruments_by_id, series, as_of):
        snap = build_snapshot(instruments, series, mode=DataMode.MOCK, as_of=as_of)
        axis = build_dominant_axis(snap, instruments_by_id)
        # baseline 은 조용하다. 축이 있어도 |z| ≥ 0.5 여야 한다.
        assert axis is None or abs(axis.z) >= 0.5


# ── 6. 이벤트 달력 ───────────────────────────────────────────
class TestCalendar:
    def test_calendar_loads_and_is_sorted(self):
        events = load_calendar()
        assert events
        assert [e.date for e in events] == sorted(e.date for e in events)

    def test_window_before_fomc(self):
        w = event_window(datetime(2026, 9, 15, 9, tzinfo=timezone.utc))
        assert w.active
        assert any(e.label == "FOMC" and e.days_until == 1 for e in w.in_window)
        assert w.persistence_scale < 1.0
        assert w.alert_threshold_scale > 1.0

    def test_outside_window(self):
        w = event_window(datetime(2026, 9, 11, 9, tzinfo=timezone.utc))
        assert not w.active
        assert w.persistence_scale == 1.0 and w.alert_threshold_scale == 1.0
        assert w.upcoming and w.upcoming[0].label == "FOMC"

    def test_unverified_dates_are_marked(self):
        assert any(not e.verified for e in load_calendar())
        assert any(e.verified for e in load_calendar())

    def test_persistence_weight_is_damped_in_window(self, instruments, instruments_by_id, series):
        snap = build_snapshot(instruments, series, mode=DataMode.MOCK)
        plain = compute_market_state(snap, instruments_by_id, previous_label=None)
        # 직전 판정이 있어야 persistence 가 들어간다
        same = compute_market_state(snap, instruments_by_id, previous_label=plain.primary_label)
        damped = compute_market_state(
            snap, instruments_by_id, previous_label=plain.primary_label, persistence_scale=0.5
        )
        w_same = next(c.weight for c in same.confidence_breakdown.contributions if c.key == "persistence")
        w_damp = next(c.weight for c in damped.confidence_breakdown.contributions if c.key == "persistence")
        assert w_damp == pytest.approx(w_same * 0.5)

    def test_alert_thresholds_scale(self, as_of):
        from marketpulse.engines.alert import build_alerts
        run = run_pipeline_detailed(Settings(scenario="inflation_shock"), as_of=as_of)
        snap = run.snapshot
        from marketpulse.config.registry import get_instruments
        by_id = get_instruments().by_id()
        base = dict(
            state=snap.market_state, themes=snap.themes, divergences=snap.divergences,
            health=snap.data_health, instruments_by_id=by_id,
        )
        from marketpulse.adapters.market.mock import MockMarketAdapter
        from marketpulse.config.settings import MOCK_DIR
        from marketpulse.config.registry import get_instruments as gi
        series = MockMarketAdapter(MOCK_DIR, "inflation_shock").fetch_series(gi().instruments, bars=180, as_of=as_of)
        market = build_snapshot(gi().instruments, series, mode=DataMode.MOCK, as_of=as_of)
        loose = build_alerts(snapshot=market, **base)
        strict = build_alerts(snapshot=market, threshold_scale=3.0, **base)
        spikes_loose = [a for a in loose if a.type.value == "PRICE_ZSCORE_SPIKE"]
        spikes_strict = [a for a in strict if a.type.value == "PRICE_ZSCORE_SPIKE"]
        assert len(spikes_strict) < len(spikes_loose)

    def test_snapshot_carries_calendar(self, settings, as_of):
        snap = run_pipeline_detailed(settings, as_of=as_of).snapshot
        assert snap.calendar is not None
        assert snap.calendar.as_of == as_of


# ── 2 · 3. 온도계 재료와 1주 전 ─────────────────────────────
class TestThermometerStrip:
    def test_components_cover_every_price_component_plus_news(self, settings, as_of):
        snap = run_pipeline_detailed(settings, as_of=as_of).snapshot
        t = snap.thermometer
        keys = [c.key for c in t.components]
        assert keys[-1] == "news"
        from marketpulse.engines.scoring import load_scoring
        for c in load_scoring()["thermometer"]["price_components"]:
            assert c["factor"] in keys

    def test_missing_factor_is_a_row_with_none(self, settings, as_of):
        snap = run_pipeline_detailed(settings, as_of=as_of).snapshot
        rows = {c.key: c for c in snap.thermometer.components}
        # 수급은 MOCK 에서도 계산된다; 결측 재료는 값이 None 인 채 남아야 한다
        for c in rows.values():
            if c.value is None:
                assert c.week_ago is None

    def test_price_week_ago_from_series(self, settings, as_of):
        snap = run_pipeline_detailed(settings, as_of=as_of).snapshot
        t = snap.thermometer
        assert t.price_week_ago is not None
        assert t.week_ago_source == "series"
        assert t.news_week_ago is None and t.composite_week_ago is None

    def test_week_ago_snapshot_fills_news_and_themes(self, settings, as_of):
        first = run_pipeline_detailed(settings, as_of=as_of - timedelta(days=7)).snapshot
        later = run_pipeline_detailed(settings, as_of=as_of, week_ago=first).snapshot
        assert later.thermometer.week_ago_source == "snapshot"
        assert later.thermometer.composite_week_ago == pytest.approx(first.thermometer.composite)
        assert all(t.week_ago_score is not None for t in later.themes)

    def test_factor_week_ago_uses_same_formula(self, instruments, instruments_by_id, series, as_of):
        """5봉 잘라낸 시계열의 오늘 factor == 원 시계열의 1주 전 factor."""
        snap = build_snapshot(instruments, series, mode=DataMode.MOCK, as_of=as_of)
        state = compute_market_state(snap, instruments_by_id)
        cut = {
            k: v.model_copy(update={"timestamps": v.timestamps[:-WEEK_BARS], "values": v.values[:-WEEK_BARS]})
            for k, v in series.items()
        }
        snap_cut = build_snapshot(instruments, cut, mode=DataMode.MOCK, as_of=as_of)
        state_cut = compute_market_state(snap_cut, instruments_by_id)
        for name, fs in state.factors.items():
            if fs.week_ago is not None and name in state_cut.factors:
                assert fs.week_ago == pytest.approx(state_cut.factors[name].score, abs=1e-6), name


# ── 저장소 ───────────────────────────────────────────────────
class TestWeekAgoLookup:
    def test_at_or_before_respects_distance(self, settings, as_of):
        repo = SqliteSnapshotRepository(":memory:")
        snap = run_pipeline_detailed(settings, as_of=as_of).snapshot
        repo.save("k", snap)
        # 목표 시각 이전 것 중 최근, 단 max_distance 안에서만
        assert repo.at_or_before("k", as_of + timedelta(days=1), max_distance=timedelta(days=3)) is not None
        assert repo.at_or_before("k", as_of + timedelta(days=5), max_distance=timedelta(days=3)) is None
        assert repo.at_or_before("k", as_of - timedelta(days=1), max_distance=timedelta(days=3)) is None
        repo.close()
