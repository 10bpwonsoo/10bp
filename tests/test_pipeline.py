"""End-to-End 파이프라인 테스트. 네트워크 없이 돈다."""

from __future__ import annotations

import pytest

from marketpulse.adapters.base import AdapterError
from marketpulse.adapters.registry import build_market_adapter, build_news_adapter
from marketpulse.config.settings import Settings
from marketpulse.engines.normalize import build_snapshot
from marketpulse.engines.orchestrator import (
    WHATS_MOVING_MIN_Z,
    build_intelligence,
    run_pipeline,
)
from marketpulse.models.common import DataMode
from marketpulse.models.snapshot import IntelligenceSnapshot


class TestSnapshotAssembly:
    def test_full_coverage_with_mock(self, instruments, series, as_of):
        snap = build_snapshot(instruments, series, mode=DataMode.MOCK, as_of=as_of)
        assert snap.coverage == 1.0
        assert snap.missing == []
        assert len(snap.points) == len(instruments)

    def test_missing_instrument_lowers_coverage(self, instruments, series, as_of):
        partial = {k: v for k, v in series.items() if k != "SPX"}
        snap = build_snapshot(instruments, partial, mode=DataMode.MOCK, as_of=as_of)
        assert "SPX" in snap.missing
        assert snap.coverage < 1.0
        assert "SPX" not in snap.points, "결측을 0 으로 채우지 않는다"

    def test_rate_point_carries_bp(self, instruments, series, as_of):
        snap = build_snapshot(instruments, series, mode=DataMode.MOCK, as_of=as_of)
        p = snap.points["US10Y"]
        assert p.change_bp == pytest.approx(p.change * 100.0)

    def test_equity_point_has_no_bp(self, instruments, series, as_of):
        snap = build_snapshot(instruments, series, mode=DataMode.MOCK, as_of=as_of)
        assert snap.points["SPX"].change_bp is None

    def test_z_accessor(self, instruments, series, as_of):
        snap = build_snapshot(instruments, series, mode=DataMode.MOCK, as_of=as_of)
        assert snap.z("SOXX") == pytest.approx(1.25, abs=1e-6)
        assert snap.z("NOT_A_THING") is None


class TestPurity:
    def test_build_intelligence_is_deterministic(
        self, instruments, instruments_by_id, series, news_adapter, as_of
    ):
        snap = build_snapshot(instruments, series, mode=DataMode.MOCK, as_of=as_of)
        news = news_adapter.fetch_news(as_of=as_of)
        a = build_intelligence(snap, news, instruments_by_id, scenario="baseline")
        b = build_intelligence(snap, news, instruments_by_id, scenario="baseline")
        assert [m.model_dump() for m in a.whats_moving] == [
            m.model_dump() for m in b.whats_moving
        ]

    def test_no_network_needed(self, settings):
        """엔진이 순수 함수라 테스트에 외부 의존이 없다."""
        assert isinstance(run_pipeline(settings), IntelligenceSnapshot)


class TestWhatsMoving:
    def test_sorted_by_absolute_z(self, settings):
        rows = [r for r in run_pipeline(settings).whats_moving if r.kind == "instrument"]
        mags = [abs(r.z) for r in rows]
        assert mags == sorted(mags, reverse=True)

    def test_threshold_applied(self, settings):
        for r in run_pipeline(settings).whats_moving:
            if r.kind == "instrument":
                assert abs(r.z) >= WHATS_MOVING_MIN_Z

    def test_declared_shocks_lead(self, settings):
        """시나리오가 말하려는 이야기가 맨 위에 와야 한다."""
        rows = [r for r in run_pipeline(settings).whats_moving if r.kind == "instrument"]
        assert rows[0].key == "SOXX"
        assert {r.key for r in rows[:3]} == {"SOXX", "KRX_SEMI", "NDX"}

    def test_units_in_display(self, settings):
        by_key = {
            r.key: r
            for r in run_pipeline(settings).whats_moving
            if r.kind == "instrument"
        }
        if "US2Y" in by_key:
            assert by_key["US2Y"].change_display.endswith("bp")
        assert by_key["SOXX"].change_display.endswith("%")


class TestDataHealth:
    def test_reports_mode_and_coverage(self, settings):
        h = run_pipeline(settings).data_health
        assert h.mode is DataMode.MOCK
        assert h.coverage == 1.0
        assert h.available_instruments == h.expected_instruments

    def test_llm_disabled_is_visible(self, settings):
        assert run_pipeline(settings).data_health.llm_status == "disabled"

    def test_timings_recorded(self, settings):
        t = run_pipeline(settings).data_health.engine_timings_ms
        assert {"market_fetch", "news_fetch", "normalize", "orchestrator"} <= set(t)

    def test_news_counted(self, settings):
        assert run_pipeline(settings).data_health.news_items == 5


class TestUnimplementedStagesAreEmptyNotFaked:
    """
    아직 만들지 않은 단계는 비어 있어야 한다.
    그럴듯한 가짜 숫자로 채우면 데모는 좋아 보이지만 시스템은 거짓말을 한다.
    """

    def test_p3_sections_now_populated(self, settings):
        snap = run_pipeline(settings)
        assert snap.impact_maps, "Impact Map 이 비어 있다"
        assert all(len(m.nodes) >= 2 for m in snap.impact_maps)
        assert all(m.edges for m in snap.impact_maps)

    def test_p1_sections_now_populated(self, settings):
        snap = run_pipeline(settings)
        assert len(snap.themes) >= 12
        assert snap.events
        assert len(snap.market_state.factors) == 11
        assert snap.market_state.hypotheses
        assert snap.market_state.narrative_source == "template"

    def test_llm_is_not_used(self, settings):
        """P1 은 LLM 없이 완주한다. narrative 도 템플릿에서 나온다."""
        snap = run_pipeline(settings)
        assert snap.data_health.llm_status == "disabled"
        assert all(e.extractor == "rule" for e in snap.events)
        assert snap.market_state.narrative_source != "llm"


class TestHistoryEffects:
    def test_persistence_raises_confidence_on_repeat(self, settings):
        first = run_pipeline(settings)
        second = run_pipeline(settings, history=[first])
        assert second.market_state.confidence >= first.market_state.confidence

    def test_theme_change_measured_against_previous(self, settings):
        first = run_pipeline(settings)
        second = run_pipeline(settings, history=[first])
        assert all(t.last_change == pytest.approx(0.0, abs=1e-9) for t in second.themes)

    def test_theme_movers_appear_when_scores_shift(self, settings):
        first = run_pipeline(settings)
        shifted = first.model_copy(
            update={
                "themes": [
                    t.model_copy(update={"theme_score": t.theme_score - 40.0})
                    for t in first.themes
                ]
            }
        )
        second = run_pipeline(settings, history=[shifted])
        assert any(m.kind == "theme" for m in second.whats_moving)


class TestAdapterRegistry:
    def test_mock_mode_resolves(self, settings):
        assert build_market_adapter(settings).mode is DataMode.MOCK
        assert build_news_adapter(settings).mode is DataMode.MOCK

    @pytest.mark.parametrize("mode", ["LIVE", "DELAYED"])
    def test_real_modes_never_serve_mock_data(self, mode):
        """
        P4 이전에는 LIVE/DELAYED 가 예외를 던졌다. 이제 실어댑터가 있다.
        그때 지키려던 불변식은 그대로다 — **MOCK 데이터가 LIVE 라는
        이름표를 달고 나가지 않는다.**
        """
        from marketpulse.adapters.market.live import LiveMarketAdapter
        from marketpulse.adapters.news.rss import RssNewsAdapter

        s = Settings(data_mode=mode)
        market = build_market_adapter(s)
        news = build_news_adapter(s)
        assert isinstance(market, LiveMarketAdapter)
        assert isinstance(news, RssNewsAdapter)
        assert market.mode is not DataMode.MOCK
        assert news.mode is not DataMode.MOCK

    def test_live_is_labelled_delayed_not_live(self):
        """
        무료 공급자는 일봉 종가만 준다. 사용자가 LIVE 를 요구해도 그것을
        실시간이라 표시하지 않고, 왜 아닌지 경고로 남긴다.
        """
        from marketpulse.adapters.registry import mode_warnings

        s = Settings(data_mode="LIVE")
        assert build_market_adapter(s).mode is DataMode.DELAYED
        notes = mode_warnings(s)
        assert notes and "지연" in notes[0]
        assert mode_warnings(Settings(data_mode="DELAYED")) == []

    def test_unknown_mode_still_fails_loudly(self):
        from marketpulse.adapters.registry import build_market_adapter as build

        class Fake:
            data_mode = "NONSENSE"

        with pytest.raises(AdapterError):
            build(Fake())


class TestSerialization:
    def test_round_trip(self, settings):
        snap = run_pipeline(settings)
        raw = snap.model_dump(mode="json")
        assert IntelligenceSnapshot.model_validate(raw).model_dump(mode="json") == raw

    def test_freshness_exposed_to_ui(self, settings, instruments, series, as_of):
        """UI 가 신선도를 항상 표시할 수 있어야 한다 (요구 12)."""
        snap = build_snapshot(instruments, series, mode=DataMode.MOCK, as_of=as_of)
        meta = snap.points["SPX"].meta.model_dump(mode="json")
        assert "freshness_sec" in meta and "is_stale" in meta and "mode" in meta
