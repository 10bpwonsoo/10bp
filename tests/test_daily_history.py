"""
Daily snapshot history (2026-10-07) — History 는 날짜별 판단을 한 번 저장한 뒤 고정한 기록이다.
요구서의 Regression Test 1~7 을 그대로 옮겼다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from marketpulse.adapters.market.mock import MockMarketAdapter
from marketpulse.config.registry import get_instruments
from marketpulse.config.settings import MOCK_DIR, Settings
from marketpulse.engines.orchestrator import run_pipeline_detailed
from marketpulse.history import DailySnapshotManager, JsonDirStore, LockedSnapshotError, SqliteDailyStore
from marketpulse.history.calculators import MarketInputs, market_calculator, market_snapshot_from_intelligence
from marketpulse.history.integrate import past_dates, sync_market
from marketpulse.models.common import DataMode
from marketpulse.models.daily_history import DailySnapshot

AS_OF = datetime(2026, 9, 11, 7, 0, tzinfo=timezone.utc)  # 16:00 KST — finalize_time(16:10) 전 → LIVE
AFTER_CLOSE = datetime(2026, 9, 11, 8, 0, tzinfo=timezone.utc)  # 17:00 KST → RECORDED


def _snap(tab: str, d: date, state: str, score: float | None = 0.0, **kw) -> DailySnapshot:
    base = dict(snapshot_date=d, tab_id=tab, state=state, state_label=state, state_score=score, confidence=50.0, history_source="LIVE",
                calculated_at=datetime(2026, 10, 7, tzinfo=timezone.utc), model_version="m_v4", logic_version="rules_v6")
    base.update(kw)
    return DailySnapshot(**base)


@pytest.fixture
def manager(tmp_path):
    return DailySnapshotManager(JsonDirStore(tmp_path / "hist"), clock=lambda: datetime(2026, 10, 7, 4, 0, tzinfo=timezone.utc))


@pytest.fixture(scope="module")
def mock_series():
    ins = get_instruments().instruments
    return ins, MockMarketAdapter(MOCK_DIR, "inflation_shock").fetch_series(ins, bars=180, as_of=AS_OF)


class TestLifecycle:
    def test_live_then_recorded_then_locked(self, manager):
        """오늘: LIVE → 장중 교체 가능 → finalize 이후 RECORDED → LOCKED. 다음날 과거 snapshot 은 읽기 전용."""
        d = date(2026, 10, 7)
        s1 = manager.record(_snap("market_regime", d, "RISK_ON", 42), as_of=datetime(2026, 10, 7, 1, 0, tzinfo=timezone.utc))
        assert s1.history_source == "LIVE" and not s1.is_locked
        s2 = manager.record(_snap("market_regime", d, "NEUTRAL", 10), as_of=datetime(2026, 10, 7, 5, 0, tzinfo=timezone.utc))
        assert s2.history_source == "LIVE" and s2.state == "NEUTRAL"  # 장중 재계산은 LIVE 를 바꾼다
        s3 = manager.record(_snap("market_regime", d, "NEUTRAL", 12), as_of=datetime(2026, 10, 7, 7, 30, tzinfo=timezone.utc))  # 16:30 KST
        assert s3.history_source == "RECORDED" and s3.is_locked and s3.finalization == "daily_close"
        s4 = manager.record(_snap("market_regime", d, "RISK_ON", 99), as_of=datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc))
        assert s4.state == "NEUTRAL" and s4.state_score == 12  # 잠긴 뒤의 재계산은 무시된다
        with pytest.raises(LockedSnapshotError):
            manager.save_snapshot(_snap("market_regime", d, "RISK_ON", 99))

    def test_stale_live_is_promoted_not_recomputed(self, manager):
        """날이 바뀌었는데 LIVE 로 남은 어제 → 그날 마지막 관측이 RECORDED(last_observation) 로 승격·잠긴다."""
        d = date(2026, 10, 6)
        manager.record(_snap("market_regime", d, "RISK_ON", 29), as_of=datetime(2026, 10, 6, 2, 0, tzinfo=timezone.utc))
        out = manager.promote_stale_live("market_regime", today=date(2026, 10, 7))
        assert len(out) == 1 and out[0].history_source == "RECORDED" and out[0].is_locked and out[0].finalization == "last_observation"

    def test_regression_1_yesterday_kept_when_today_updates(self, manager):
        """RT1: 10/06 Risk-On 저장 → 10/07 update → 10/06 Risk-On 유지, 10/07 만 새로 계산."""
        manager.record(_snap("market_regime", date(2026, 10, 6), "RISK_ON", 29), as_of=datetime(2026, 10, 6, 8, 0, tzinfo=timezone.utc))
        manager.backfill_missing("market_regime", [date(2026, 10, 6)], lambda d, prev: _snap("market_regime", d, "NEUTRAL", 0))  # 있으면 계산하지 않는다
        manager.record(_snap("market_regime", date(2026, 10, 7), "NEUTRAL", 8), as_of=datetime(2026, 10, 7, 4, 0, tzinfo=timezone.utc))
        seq = {s.snapshot_date: s for s in manager.get_history("market_regime")}
        assert seq[date(2026, 10, 6)].state == "RISK_ON" and seq[date(2026, 10, 6)].state_score == 29
        assert seq[date(2026, 10, 7)].state == "NEUTRAL"

    def test_regression_2_sentiment_fixed_when_distribution_changes(self, manager):
        """RT2: 10/06 AI Sentiment 76 GREED → 10/07 rolling distribution 변경 → 10/06 그대로."""
        manager.record(_snap("ai_sentiment", date(2026, 10, 6), "GREED", 76), as_of=datetime(2026, 10, 6, 8, 0, tzinfo=timezone.utc))
        calls = []
        manager.backfill_missing("ai_sentiment", [date(2026, 10, 6), date(2026, 10, 7)], lambda d, prev: calls.append(d) or _snap("ai_sentiment", d, "NEUTRAL", 50))
        assert calls == [date(2026, 10, 7)]
        assert manager.get_snapshot("ai_sentiment", date(2026, 10, 6)).state_score == 76

    def test_regression_3_and_4_backfill_once_then_locked(self, manager):
        """RT3·4: 09/18 snapshot 없음 → 1회 계산 → BACKFILLED·LOCK → 다시 요청해도, 데이터가 바뀌어도 재계산하지 않는다."""
        calls = []

        def calc(d, prev):
            calls.append(d)
            return _snap("market_regime", d, "POLICY_DRIVEN", 18)
        out = manager.backfill_missing("market_regime", [date(2026, 9, 18)], calc)
        assert out[0].history_source == "BACKFILLED" and out[0].is_locked and out[0].is_backfilled and out[0].state_score == 18
        manager.backfill_missing("market_regime", [date(2026, 9, 18)], lambda d, prev: _snap("market_regime", d, "RISK_ON", 99))
        s = manager.get_snapshot("market_regime", date(2026, 9, 18))
        assert s.state == "POLICY_DRIVEN" and s.state_score == 18 and calls == [date(2026, 9, 18)]

    def test_regression_5_model_change_keeps_past(self, manager):
        """RT5: model_v4 로 저장된 과거는 model_v5 가 와도 그대로. 새 날짜만 v5."""
        manager.backfill_missing("market_regime", [date(2026, 9, 15)], lambda d, prev: _snap("market_regime", d, "RISK_ON", 30))
        manager.record(_snap("market_regime", date(2026, 10, 7), "NEUTRAL", 8, model_version="m_v5", logic_version="rules_v7"), as_of=datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc))
        seq = {s.snapshot_date: s for s in manager.get_history("market_regime")}
        assert seq[date(2026, 9, 15)].model_version == "m_v4" and seq[date(2026, 9, 15)].state == "RISK_ON"
        assert seq[date(2026, 10, 7)].model_version == "m_v5"

    def test_insufficient_data_is_stored_not_invented(self, manager):
        out = manager.backfill_missing("rates_regime", [date(2026, 9, 1)], lambda d, prev: None)
        assert out[0].state == "INSUFFICIENT_DATA" and out[0].is_locked and out[0].state_score is None

    def test_correction_leaves_audit_trail(self, manager):
        manager.backfill_missing("oil_regime", [date(2026, 9, 21)], lambda d, prev: _snap("oil_regime", d, "supply", 10))
        with pytest.raises(ValueError):
            manager.correct("oil_regime", date(2026, 9, 21), _snap("oil_regime", date(2026, 9, 21), "demand", -5), reason="  ", by="admin")
        s = manager.correct("oil_regime", date(2026, 9, 21), _snap("oil_regime", date(2026, 9, 21), "demand", -5), reason="잘못된 봉(월물 교체)", by="admin")
        assert s.state == "demand" and s.is_locked and len(s.corrections) == 1
        c = s.corrections[0]
        assert c.original_value["state"] == "supply" and c.corrected_value["state"] == "demand" and c.correction_reason and c.corrected_by == "admin"

    def test_sqlite_store_same_rules(self, tmp_path):
        m = DailySnapshotManager(SqliteDailyStore(tmp_path / "h.db"))
        m.backfill_missing("market_regime", [date(2026, 9, 18)], lambda d, prev: _snap("market_regime", d, "POLICY_DRIVEN", 18))
        with pytest.raises(LockedSnapshotError):
            m.save_snapshot(_snap("market_regime", date(2026, 9, 18), "RISK_ON", 1))
        assert m.get_history("market_regime")[0].state == "POLICY_DRIVEN"
        m2 = DailySnapshotManager(SqliteDailyStore(tmp_path / "h.db"), namespace="mock-baseline-")
        assert m2.get_history("market_regime") == []  # namespace 가 다르면 다른 기록


class TestMarketSequence:
    def test_regression_6_and_7_derived_from_stored_sequence(self, mock_series, tmp_path):
        """RT6·7: Duration · Previous · Transition · Share 와 색 블록·composite 선이 같은 저장 sequence 에서 나온다. backfill 은 날짜별 독립 계산(오늘 값 복사 아님)."""
        ins, series = mock_series
        settings = Settings(data_mode="MOCK", scenario="inflation_shock", llm_enabled=False)
        r = run_pipeline_detailed(settings, as_of=AS_OF)
        m = DailySnapshotManager(JsonDirStore(tmp_path / "h"), clock=lambda: AS_OF)
        inputs = MarketInputs(instruments=ins, series_by_id=r.series_by_id, events=r.snapshot.events, mode=DataMode.MOCK, zscore_window=settings.zscore_window)
        h = sync_market(m, inputs=inputs, snapshot=r.snapshot, as_of=AS_OF, days=10)
        assert h.history_mode == "stored" and h.footnote and h.live_today and h.backfilled_days >= 8
        # 2026-10-21: 장중 LIVE 는 daily 띠에 넣지 않고 intraday 로 — daily 점은 전부 고정된 snapshot
        assert h.date_basis == "kst_snapshot" and h.intraday is not None and h.intraday.source == "LIVE"
        assert all(p.source == "BACKFILLED" and p.locked for p in h.points)
        assert len({p.date for p in h.points}) == len(h.points)  # 같은 snapshot 날짜는 한 번
        assert len({p.label for p in h.points}) >= 2 or len({round(p.composite or 0) for p in h.points}) > 2  # 오늘 값을 과거에 복사하지 않았다
        stored = {s.snapshot_date: s for s in m.get_history("market_regime")}
        for p in h.points + [h.intraday]:  # 색(label)·선(composite)·확신 모두 같은 snapshot (저장 키로 찾는다)
            s = stored[p.storage_date]
            assert s.state == p.label.value and s.state_score == p.composite and s.confidence == p.confidence
            assert p.market_date is not None and p.date > p.market_date  # KST snapshot 날짜는 그 미국 장 다음 평일
        # 파생값은 sequence 에서
        labels = [p.label for p in h.points]
        streak = 1
        for a, b in zip(reversed(labels[:-1]), reversed(labels[1:])):
            if a == b:
                streak += 1
            else:
                break
        assert h.current_streak == streak and h.changes == sum(1 for a, b in zip(labels, labels[1:]) if a != b)
        assert h.intraday.label == r.snapshot.market_state.primary_label and h.intraday.confidence == pytest.approx(r.snapshot.market_state.confidence)
        # 둘째 호출: 아무것도 다시 계산하지 않고 같은 값
        h2 = sync_market(m, inputs=inputs, snapshot=r.snapshot, as_of=AS_OF, days=10)
        assert [(p.date, p.label, p.composite, p.source) for p in h2.points] == [(p.date, p.label, p.composite, p.source) for p in h.points]

    def test_backfill_uses_only_data_up_to_that_date(self, mock_series):
        """look-ahead 금지: 날짜 D 의 snapshot 은 D 이하 봉만 쓴다 — 미래 봉을 잘라도 같은 값."""
        ins, series = mock_series
        inputs = MarketInputs(instruments=ins, series_by_id=series, mode=DataMode.MOCK)
        d = (AS_OF - timedelta(days=7)).date()
        full = market_calculator(inputs, as_of=AS_OF)(d, None)
        from marketpulse.engines.state_history import slice_series
        cut = {k: v for k, v in ((k, slice_series(v, datetime.combine(d, datetime.max.time(), tzinfo=timezone.utc))) for k, v in series.items()) if v is not None}
        trimmed = market_calculator(MarketInputs(instruments=ins, series_by_id=cut, mode=DataMode.MOCK), as_of=AS_OF)(d, None)
        assert full is not None and trimmed is not None
        assert full.state == trimmed.state and full.state_score == trimmed.state_score and full.data_asof.date() <= d

    def test_recorded_from_pipeline_snapshot_matches_screen(self, mock_series):
        ins, series = mock_series
        settings = Settings(data_mode="MOCK", scenario="inflation_shock", llm_enabled=False)
        r = run_pipeline_detailed(settings, as_of=AFTER_CLOSE)
        s = market_snapshot_from_intelligence(r.snapshot)
        assert s.state == r.snapshot.market_state.primary_label.value and s.confidence == r.snapshot.market_state.confidence
        assert s.state_score == r.snapshot.thermometer.composite and s.payload["label"] == s.state and s.model_version.startswith("market_regime_v")
        m = DailySnapshotManager(SqliteDailyStore(":memory:"), clock=lambda: AFTER_CLOSE)
        assert m.record(s, as_of=AFTER_CLOSE).history_source == "RECORDED"

    def test_past_dates_exclude_today(self, mock_series):
        ins, series = mock_series
        ds = past_dates(series, AS_OF, 10)
        assert len(ds) == 10 and all(d < AS_OF.date() for d in ds)


class TestApi:
    def test_history_endpoints_and_stored_mode(self, tmp_path):
        from fastapi.testclient import TestClient
        from marketpulse.api.deps import get_history_service, get_service, get_state_history_service
        from marketpulse.api.main import create_app
        get_service().clear(); get_state_history_service().clear(); get_history_service().clear()
        get_history_service().use(DailySnapshotManager(SqliteDailyStore(":memory:"), namespace="test-"))
        with TestClient(create_app()) as c:
            body = c.get("/api/v1/market-state/history").json()
            assert body["history_mode"] == "stored" and body["footnote"] and body["points"][-1]["source"] in ("LIVE", "RECORDED")
            assert all(p["source"] == "BACKFILLED" and p["locked"] for p in body["points"][:-1])
            again = c.get("/api/v1/market-state/history").json()
            assert [p["label"] for p in again["points"]] == [p["label"] for p in body["points"]]
            rec = c.get("/api/v1/market-state/history?mode=recomputed").json()
            assert rec["history_mode"] == "recomputed" and all(p["source"] == "RECOMPUTED" for p in rec["points"])
            h = c.get("/api/v1/history/market_regime").json()
            assert h["tab_id"] == "market_regime" and h["footnote"] and len(h["points"]) == len(body["points"])
            assert [p["state"] for p in h["points"]] == [p["label"] for p in body["points"]]  # 같은 sequence
            assert h["current_streak"] == body["current_streak"] and h["changes"] == body["changes"]
            assert c.get("/api/v1/history/nope").status_code == 404
            ck = c.get("/api/v1/cockpit").json()
            assert ck["history"]["history_mode"] == "stored" and ck["history"]["footnote"] and all(d["source"] in ("BACKFILLED", "LIVE", "RECORDED") for d in ck["history"]["days"])
            assert [d["raw_state"] for d in ck["history"]["days"]] == [p["label"] for p in body["points"]]
            ai = c.get("/api/v1/ai-regime").json()
            sh = ai["sentiment"]["history"]
            assert sh["history_mode"] == "stored" and sh["footnote"] and all(p["source"] in ("BACKFILLED", "LIVE", "RECORDED") for p in sh["points"])
            for tab in ("ai_sentiment", "ai_regime", "rates_regime", "oil_regime", "memory_cycle"):
                hh = c.get(f"/api/v1/history/{tab}").json()
                assert hh["tab_id"] == tab and hh["footnote"] and hh["points"] and hh["points"][-1]["source"] in ("LIVE", "RECORDED")
        get_history_service().clear(); get_service().clear(); get_state_history_service().clear()
