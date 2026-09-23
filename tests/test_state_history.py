"""Market State 히스토리 재생 (2026-09-23). 같은 엔진을 날짜별로 다시 돌린 값이어야 한다."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from marketpulse.adapters.market.mock import MockMarketAdapter
from marketpulse.api.deps import get_service, get_state_history_service
from marketpulse.api.main import create_app
from marketpulse.config.registry import get_instruments
from marketpulse.config.settings import MOCK_DIR, Settings
from marketpulse.engines.calendar import event_window
from marketpulse.engines.market_state import compute_market_state
from marketpulse.engines.normalize import build_snapshot
from marketpulse.engines.orchestrator import run_pipeline_detailed
from marketpulse.engines.state_history import replay_market_state, slice_series, trading_dates
from marketpulse.models.common import DataMode


@pytest.fixture(scope="module")
def mock_series():
    as_of = datetime(2026, 9, 11, 7, 0, tzinfo=timezone.utc)
    ins = get_instruments().instruments
    return ins, MockMarketAdapter(MOCK_DIR, "inflation_shock").fetch_series(ins, bars=180, as_of=as_of), as_of


class TestSlicing:
    def test_slice_keeps_only_bars_up_to_cutoff(self, mock_series):
        ins, series, as_of = mock_series
        s = series["SPX"]
        cut = slice_series(s, as_of - timedelta(days=7))
        assert cut is not None and len(cut.values) < len(s.values)
        assert all(t <= as_of - timedelta(days=7) for t in cut.timestamps)
        assert cut.meta.as_of == cut.timestamps[-1]
        assert slice_series(s, as_of) is s  # 전부 포함되면 같은 객체
        assert slice_series(s, s.timestamps[0] - timedelta(days=1)) is None  # 봉이 없으면 None, 빈 계열이 아니다

    def test_trading_dates_need_broad_coverage(self, mock_series):
        ins, series, as_of = mock_series
        dates = trading_dates(series, as_of, 22)
        assert len(dates) == 22 and dates == sorted(dates) and dates[-1] <= as_of.date()
        # 한 계열만 가진 날은 거래일이 아니다
        lone = {"SPX": series["SPX"].model_copy(update={"timestamps": series["SPX"].timestamps + [as_of + timedelta(days=3)], "values": series["SPX"].values + [1.0]})}
        merged = dict(series); merged.update(lone)
        assert (as_of + timedelta(days=3)).date() not in trading_dates(merged, as_of + timedelta(days=4), 30)


class TestReplay:
    def test_last_point_equals_engine_at_as_of(self, mock_series):
        ins, series, as_of = mock_series
        h = replay_market_state(ins, series, as_of=as_of, days=22, mode=DataMode.MOCK)
        assert len(h.points) == 22 and h.points[-1].date == as_of.date()
        snap = build_snapshot(ins, series, mode=DataMode.MOCK, as_of=as_of, correlations=False)
        prev = h.points[-2].label
        state = compute_market_state(snap, {i.id: i for i in ins}, previous_label=prev, persistence_scale=event_window(as_of).persistence_scale)
        last = h.points[-1]
        assert last.label == state.primary_label
        assert last.confidence == pytest.approx(state.confidence, abs=1e-6)
        assert last.factors == {k: round(v.score, 3) for k, v in state.factors.items()}

    def test_segments_and_counts_are_consistent(self, mock_series):
        ins, series, as_of = mock_series
        h = replay_market_state(ins, series, as_of=as_of, days=22, mode=DataMode.MOCK)
        assert sum(s.days for s in h.segments) == len(h.points)
        assert h.changes == len(h.segments) - 1
        assert sum(h.days_by_label.values()) == len(h.points)
        assert h.current_streak == h.segments[-1].days
        assert h.summary.startswith("최근 22거래일") and "현재" in h.summary
        assert "뉴스 온도" in h.note
        for a, b in zip(h.segments, h.segments[1:]):
            assert a.label != b.label and a.end < b.start

    def test_as_of_is_always_the_final_point(self, mock_series):
        """일부 시장만 봉을 준 날도 마지막 점은 as_of 절단이다 — 화면 판정과 같은 절단."""
        ins, series, as_of = mock_series
        later = as_of + timedelta(days=1)  # 토요일 — 봉이 없는 날
        h = replay_market_state(ins, series, as_of=later, days=10, mode=DataMode.MOCK)
        assert h.points[-1].date == later.date() and len(h.points) == 10

    def test_missing_series_lower_coverage_not_zero(self, mock_series):
        ins, series, as_of = mock_series
        partial = {k: v for k, v in series.items() if k not in ("SPX", "VIX", "NDX")}
        h = replay_market_state(ins, partial, as_of=as_of, days=5, mode=DataMode.MOCK)
        assert all(p.coverage < 1.0 for p in h.points)
        assert all("SPX" not in p.drivers for p in h.points)

    def test_pipeline_result_carries_series(self):
        r = run_pipeline_detailed(Settings(data_mode="MOCK", scenario="baseline", llm_enabled=False))
        assert r.series_by_id and "SPX" in r.series_by_id
        assert not hasattr(r.snapshot, "state_history")  # 스냅샷은 그대로다


@pytest.fixture
def client() -> TestClient:
    get_service().clear()
    get_state_history_service().clear()
    return TestClient(create_app())


class TestApi:
    def test_route_and_cache(self, client):
        a = client.get("/api/v1/market-state/history?scenario=baseline")
        assert a.status_code == 200
        d = a.json()
        assert d["days_requested"] == Settings().state_history_days and len(d["points"]) == d["days_requested"]
        assert d["points"][-1]["label"] == client.get("/api/v1/market-state?scenario=baseline").json()["primary_label"]
        b = client.get("/api/v1/market-state/history?scenario=baseline")
        assert b.json()["as_of"] == d["as_of"]

    def test_days_query_and_bounds(self, client):
        assert client.get("/api/v1/market-state/history?scenario=baseline&days=5").json()["days_requested"] == 5
        assert client.get("/api/v1/market-state/history?scenario=baseline&days=1").status_code == 422
        assert client.get("/api/v1/market-state/history?scenario=nope").status_code == 404
