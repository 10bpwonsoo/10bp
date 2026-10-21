"""Daily Full Dashboard Archive(2026-10-21) — 저장 · 덮어쓰기 금지 · 부분 실패 · 날짜 목록 · 없는 날짜."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from marketpulse.api.main import create_app
from marketpulse.api.routes.archive import use_archive_service
from marketpulse.archive import ArchiveCaptureError, ArchiveStore, DailyArchiveService

AS_OF = "2026-10-20T22:31:00Z"
NOW = datetime(2026, 10, 20, 22, 35, tzinfo=timezone.utc)  # = 2026-10-21 07:35 KST


def collectors(**override):
    base = {
        "snapshot": lambda: {"as_of": AS_OF, "mode": "DELAYED", "scenario": "baseline", "data_health": {"mode": "DELAYED", "coverage": 0.76, "available_instruments": 41, "expected_instruments": 54}},
        "cockpit": lambda: {"as_of": AS_OF, "market_now": {"label_text": "LIQUIDITY STRESS"}},
        "market_state_history": lambda: {"as_of": AS_OF, "points": []},
        "ai_regime": lambda: {"as_of": AS_OF, "regime_label": "AI-SPECIFIC DE-RISKING", "headline": "저장된 문구 그대로"},
        "rates_regime": lambda: {"as_of": AS_OF},
        "oil_regime": lambda: {"as_of": AS_OF},
        "investment": lambda: {"as_of": "2026-10-20T22:33:00Z", "stocks": {}},
        "scenario_checks": lambda: [{"name": "x"}],
        "analyst_views": lambda: {"as_of": "2026-10-20T22:34:00Z", "views": []},
        "daily_history": lambda: {"market_regime": {"tab_id": "market_regime"}},
        "news": lambda: [],
    }
    base.update(override)
    return base


@pytest.fixture
def svc(tmp_path):
    return DailyArchiveService(ArchiveStore(tmp_path / "archive"), collectors=collectors())


def test_capture_writes_full_json(svc, tmp_path):
    res = svc.capture(now=NOW)
    assert res.status == "WRITTEN" and res.snapshot_date == "2026-10-21" and res.archive_status == "COMPLETE"
    p = tmp_path / "archive" / "2026" / "10" / "2026-10-21.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert doc["schema_version"] == "1" and doc["snapshot_date"] == "2026-10-21" and doc["archive_status"] == "COMPLETE"
    assert doc["ai_regime"]["headline"] == "저장된 문구 그대로" and doc["errors"] == {}
    assert doc["meta"]["source_asof"] == AS_OF and doc["meta"]["coverage"] == 0.76 and doc["meta"]["data_mode"] == "DELAYED"
    assert doc["meta"]["consistency"]["ok"] is True
    assert not list((tmp_path / "archive").rglob("*.tmp"))
    idx = json.loads((tmp_path / "archive" / "index.json").read_text(encoding="utf-8"))
    assert idx["latest"] == "2026-10-21" and idx["dates"] == ["2026-10-21"] and idx["entries"][0]["archive_status"] == "COMPLETE"
    assert doc["cutoff"] == "2026-10-21T07:35:00+09:00" and doc["meta"]["is_weekend"] is False and doc["meta"]["archive_origin"] == "daily_archive"


def test_same_date_is_never_overwritten(svc, tmp_path):
    svc.capture(now=NOW)
    p = tmp_path / "archive" / "2026" / "10" / "2026-10-21.json"
    before = p.read_bytes()
    called = []
    later = collectors(snapshot=lambda: called.append(1) or {"as_of": "2026-10-21T05:00:00Z", "mode": "DELAYED"})
    res = svc.capture(now=NOW.replace(hour=23), collectors=later)  # 같은 KST 날짜
    assert res.status == "EXISTS" and p.read_bytes() == before and called == []  # 모으지도 않는다
    with pytest.raises(FileExistsError):
        svc.store.write_new(svc.archive_date(NOW), {"snapshot_date": "2026-10-21", "schema_version": "1"})
    assert p.read_bytes() == before


def test_partial_failure_still_saves(svc):
    def boom():
        raise RuntimeError("AI 서비스 실패")
    res = svc.capture(now=NOW, collectors=collectors(ai_regime=boom))
    doc = svc.get("2026-10-21")
    assert res.archive_status == "PARTIAL" and doc["archive_status"] == "PARTIAL"
    assert doc["ai_regime"] is None and "AI 서비스 실패" in doc["errors"]["ai_regime"]
    assert doc["meta"]["sections"]["ai_regime"] == "MISSING" and doc["cockpit"]["market_now"]["label_text"] == "LIQUIDITY STRESS"


def test_required_snapshot_failure_leaves_no_file(svc, tmp_path):
    def boom():
        raise RuntimeError("수집 실패")
    with pytest.raises(ArchiveCaptureError):
        svc.capture(now=NOW, collectors=collectors(snapshot=boom))
    assert not list((tmp_path / "archive").rglob("*.json*")) if (tmp_path / "archive").exists() else True


def test_as_of_mismatch_is_flagged(svc):
    svc.capture(now=NOW, collectors=collectors(cockpit=lambda: {"as_of": "2026-10-19T22:31:00Z"}))
    doc = svc.get("2026-10-21")
    assert doc["archive_status"] == "PARTIAL" and doc["meta"]["consistency"]["mismatched"] == ["cockpit"] and "as_of 불일치" in doc["errors"]["cockpit"]


def test_due_follows_config_time_and_weekdays(svc):
    assert not svc.due(datetime(2026, 10, 20, 22, 0, tzinfo=timezone.utc))   # 07:00 KST
    assert svc.due(datetime(2026, 10, 20, 22, 31, tzinfo=timezone.utc))      # 07:31 KST 화
    assert not svc.due(datetime(2026, 10, 24, 0, 0, tzinfo=timezone.utc))    # 토요일
    assert not svc.due(datetime(2026, 10, 25, 0, 0, tzinfo=timezone.utc))    # 일요일
    svc.capture(now=NOW)
    assert not svc.due(datetime(2026, 10, 21, 1, 0, tzinfo=timezone.utc))   # 이미 저장


def test_correction_keeps_previous_file(svc, tmp_path):
    svc.capture(now=NOW)
    old = svc.get("2026-10-21")
    fixed = dict(old, cockpit={"as_of": AS_OF, "market_now": {"label_text": "FIXED"}})
    final, keep = svc.correct(svc.archive_date(NOW), fixed, reason="수기 태깅 오류 수정", by="tester")
    assert keep.is_file() and json.loads(keep.read_text(encoding="utf-8"))["cockpit"]["market_now"]["label_text"] == "LIQUIDITY STRESS"
    doc = svc.get("2026-10-21")
    assert doc["cockpit"]["market_now"]["label_text"] == "FIXED" and doc["meta"]["corrections"][0]["reason"] == "수기 태깅 오류 수정"


class TestApi:
    @pytest.fixture
    def client(self, tmp_path):
        s = DailyArchiveService(ArchiveStore(tmp_path / "archive"), collectors=collectors())
        for day in (13, 20, 15):  # 일부러 섞어서 저장
            s.capture(now=datetime(2026, 10, day, 23, 0, tzinfo=timezone.utc))
        use_archive_service(s)
        yield TestClient(create_app())
        use_archive_service(None)

    def test_dates_sorted_latest_first(self, client):
        assert client.get("/api/v1/archive/dates").json() == ["2026-10-21", "2026-10-16", "2026-10-14"]
        idx = client.get("/api/v1/archive/index").json()
        assert [r["date"] for r in idx] == ["2026-10-21", "2026-10-16", "2026-10-14"] and idx[0]["archive_status"] == "COMPLETE"

    def test_get_and_latest(self, client):
        assert client.get("/api/v1/archive/2026-10-16").json()["snapshot_date"] == "2026-10-16"
        assert client.get("/api/v1/archive/latest").json()["snapshot_date"] == "2026-10-21"

    def test_missing_date_is_404_with_nearest(self, client):
        r = client.get("/api/v1/archive/2026-10-15")
        assert r.status_code == 404
        d = r.json()["detail"]
        assert d["message"] == "2026-10-15 저장 화면이 없습니다" and d["nearest"] == {"before": ["2026-10-14"], "after": ["2026-10-16"]}
        assert client.get("/api/v1/archive/2026-13-40").status_code == 422
        assert client.get("/api/v1/archive/not-a-date").status_code == 422

    def test_no_write_endpoint(self, client):
        assert client.post("/api/v1/archive/2026-10-22").status_code == 405
        assert client.put("/api/v1/archive/2026-10-21").status_code == 405


# ── 2026-10-21 v2: 평일만 · 누락 평일 backfill · look-ahead 금지 ─────────────────────────
from datetime import date, timedelta  # noqa: E402

from marketpulse.archive.backfill import plan  # noqa: E402
from marketpulse.archive.pit import cut_series  # noqa: E402
from marketpulse.archive.service import future_data_paths, is_snapshot_day  # noqa: E402


def kst(y, m, d, hh=7, mm=30):
    return datetime(y, m, d, hh - 9 + 24 if hh < 9 else hh - 9, mm, tzinfo=timezone.utc) - (timedelta(days=1) if hh < 9 else timedelta(0))


def test_saturday_and_sunday_are_never_created(svc, tmp_path):
    for day in (17, 18):  # 토 · 일
        res = svc.capture(now=kst(2026, 10, day))
        assert res.status == "SKIPPED_WEEKEND" and not res.path.exists()
    assert svc.store.dates() == []
    assert is_snapshot_day(date(2026, 10, 16)) and not is_snapshot_day(date(2026, 10, 17)) and not is_snapshot_day(date(2026, 10, 18))


def test_plan_lists_only_missing_weekdays_and_keeps_existing(svc, tmp_path):
    for day in (12, 13, 15):
        svc.capture(now=kst(2026, 10, day))
    # 과거에 이미 있던 주말 파일은 지우지도 바꾸지도 않는다
    weekend = svc.store.path_for(date(2026, 10, 11))
    weekend.parent.mkdir(parents=True, exist_ok=True)
    weekend.write_text(json.dumps({"schema_version": "1", "snapshot_date": "2026-10-11"}), encoding="utf-8")
    before = {d: svc.store.path_for(d).read_bytes() for d in svc.store.dates()}
    rows = {r["date"].isoformat(): r["action"] for r in plan(svc, date(2026, 10, 21))}
    assert [d for d, a in rows.items() if a == "MISSING"] == ["2026-10-14", "2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21"]
    assert rows["2026-10-17"] == rows["2026-10-18"] == "SKIPPED_WEEKEND"
    assert rows["2026-10-11"] == rows["2026-10-12"] == rows["2026-10-15"] == "EXISTING"
    # 이미 있는 날짜를 다시 저장하려 해도 그대로다
    assert svc.capture(now=kst(2026, 10, 15, 9, 0)).status == "EXISTS"
    assert {d: svc.store.path_for(d).read_bytes() for d in svc.store.dates()} == before


def test_future_data_is_kept_out_of_a_past_archive(svc):
    cutoff = kst(2026, 10, 16)
    future = "2026-10-19T13:30:00Z"
    cols = collectors(snapshot=lambda: {"as_of": "2026-10-15T22:30:00Z", "mode": "DELAYED", "data_health": {}},
                      cockpit=lambda: {"as_of": "2026-10-15T22:30:00Z", "upcoming": [{"date": "2026-10-22", "as_of": "2026-10-28T00:00:00Z"}]},  # 일정은 미래여도 된다
                      news=lambda: [{"published_at": "2026-10-15T20:00:00Z"}, {"published_at": future}],
                      ai_regime=lambda: {"as_of": "2026-10-15T22:30:00Z", "ai_vs_market": {"last_date": "2026-10-20"}})
    res = svc.capture(now=cutoff, collectors=cols, origin="historical_backfill", cutoff=cutoff, check_future=True)
    doc = svc.get(res.snapshot_date)
    assert res.snapshot_date == "2026-10-16" and doc["cutoff"] == "2026-10-16T07:30:00+09:00"
    assert doc["news"] is None and doc["meta"]["sections"]["news"] == "FUTURE_DATA_REMOVED" and "FUTURE_DATA" in doc["errors"]["news"]
    assert doc["ai_regime"] is None and doc["meta"]["sections"]["ai_regime"] == "FUTURE_DATA_REMOVED"
    assert doc["cockpit"] is not None and doc["archive_status"] == "PARTIAL" and doc["meta"]["archive_origin"] == "historical_backfill"
    assert future_data_paths({"x": {"published_at": future}}, cutoff) == [".x.published_at=" + future]
    with pytest.raises(ArchiveCaptureError):  # 필수 섹션에 미래 데이터가 있으면 아무 파일도 남기지 않는다
        svc.capture(now=kst(2026, 10, 19), collectors=collectors(snapshot=lambda: {"as_of": future, "mode": "DELAYED"}), cutoff=kst(2026, 10, 19), check_future=True)
    assert not svc.store.exists(date(2026, 10, 19))


def test_point_in_time_cut_drops_bars_not_yet_published():
    from marketpulse.models.common import DataMeta, DataMode
    from marketpulse.models.market import MarketSeries

    def s(iid, source, stamps):
        ts = [datetime.fromisoformat(t.replace("Z", "+00:00")) for t in stamps]
        return MarketSeries(instrument_id=iid, timestamps=ts, values=[1.0] * len(ts),
                            meta=DataMeta(source=source, mode=DataMode.DELAYED, retrieved_at=ts[-1], as_of=ts[-1]))
    series = {
        "SPX": s("SPX", "yahoo:^GSPC", ["2026-10-15T13:30:00Z", "2026-10-16T13:30:00Z"]),
        "KOSPI": s("KOSPI", "yahoo:^KS11", ["2026-10-15T00:00:00Z", "2026-10-16T00:00:00Z"]),
        "USDKRW": s("USDKRW", "yahoo:KRW=X", ["2026-10-14T23:00:00Z", "2026-10-15T23:00:00Z"]),
        "US10Y": s("US10Y", "fred:DGS10", ["2026-10-15T00:00:00Z", "2026-10-16T00:00:00Z"]),
        "CURVE": s("CURVE", "derived:spread(US10Y,US2Y)", ["2026-10-15T00:00:00Z", "2026-10-16T00:00:00Z"]),
    }
    # 10/19(월) 07:30 KST = 10/18 22:30Z: 금요일 미국 장·한국 장은 끝났고, 금요일 FRED 금리는 월요일 오후에야 나온다
    cut = cut_series(series, kst(2026, 10, 19))
    last = {k: v.timestamps[-1].isoformat()[:10] for k, v in cut.items()}
    assert last == {"SPX": "2026-10-16", "KOSPI": "2026-10-16", "USDKRW": "2026-10-15", "US10Y": "2026-10-15", "CURVE": "2026-10-15"}
    # 10/16(금) 07:30 KST: 10/15 미국 장까지, 10/15 FRED 금리는 아직(다음 평일 오후 공개)
    cut = cut_series(series, kst(2026, 10, 16))
    # 환율 일봉(10/14 23:00Z 시작)은 10/15 23:00Z 에 끝나 아직 공개 전 — 남는 봉이 없으면 계열을 빼고 지금 값으로 메우지 않는다
    assert {k: v.timestamps[-1].isoformat()[:10] for k, v in cut.items()} == {"SPX": "2026-10-15", "KOSPI": "2026-10-15"}


def test_history_never_records_a_weekend_day(tmp_path):
    from marketpulse.history import DailySnapshotManager, JsonDirStore
    from marketpulse.models.daily_history import DailySnapshot
    m = DailySnapshotManager(JsonDirStore(tmp_path / "h"))
    sunday = DailySnapshot(snapshot_date=date(2026, 10, 18), tab_id="market_regime", state="RISK_ON", history_source="LIVE",
                           calculated_at=datetime(2026, 10, 18, 22, 30, tzinfo=timezone.utc))
    m.record(sunday, as_of=datetime(2026, 10, 18, 22, 30, tzinfo=timezone.utc))
    assert m.get_snapshot("market_regime", date(2026, 10, 18)) is None
    made = m.backfill_missing("market_regime", [date(2026, 10, 16), date(2026, 10, 17), date(2026, 10, 18)], lambda d, prev: None)
    assert [s.snapshot_date for s in made] == [date(2026, 10, 16)]


def test_locked_history_row_is_not_overwritten(tmp_path):
    from marketpulse.history import DailySnapshotManager, JsonDirStore
    from marketpulse.models.daily_history import DailySnapshot
    m = DailySnapshotManager(JsonDirStore(tmp_path / "h"))
    at = datetime(2026, 10, 15, 22, 30, tzinfo=timezone.utc)  # 마감 시각 뒤 → RECORDED · LOCKED
    first = m.record(DailySnapshot(snapshot_date=date(2026, 10, 15), tab_id="market_regime", state="LIQUIDITY_STRESS", history_source="LIVE", calculated_at=at), as_of=at)
    assert first.is_locked
    again = m.record(DailySnapshot(snapshot_date=date(2026, 10, 15), tab_id="market_regime", state="RISK_ON", history_source="LIVE", calculated_at=at), as_of=at)
    assert again.state == "LIQUIDITY_STRESS" and m.get_snapshot("market_regime", date(2026, 10, 15)).state == "LIQUIDITY_STRESS"
