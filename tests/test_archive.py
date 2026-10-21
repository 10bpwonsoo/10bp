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
    assert idx["dates"][0]["date"] == "2026-10-21" and idx["dates"][0]["archive_status"] == "COMPLETE"


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
