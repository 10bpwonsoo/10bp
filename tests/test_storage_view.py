"""
History 는 저장 당시 그대로 (2026-10-22) — 저장 키(UTC 날짜) 기준. 잠깐 KST view 로 저장된 10/22 저장본만 읽을 때 같은 기준으로 다시 조립한다.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from marketpulse.history.manager import DailySnapshotManager
from marketpulse.history.storage_view import doc_as_of, needs_view, storage_view
from marketpulse.history.store import JsonDirStore

ROOT = Path(__file__).resolve().parents[1] / "marketpulse" / "data"


def _doc(d: str) -> dict:
    return json.loads((ROOT / "archive" / d[:4] / d[5:7] / f"{d}.json").read_text(encoding="utf-8"))


def _mgr() -> DailySnapshotManager:
    return DailySnapshotManager(JsonDirStore(ROOT / "history"))


def _view(d: str) -> dict:
    doc = _doc(d)
    return storage_view(doc, as_of=doc_as_of(doc), manager=_mgr())


def test_saved_archives_are_shown_as_saved():
    """10/12~10/21 저장본(10/15 = 발표 자료의 화면)은 손대지 않는다."""
    for d in ("2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21"):
        doc = _doc(d)
        assert not needs_view(doc) and _view(d) == doc, d
    h = _doc("2026-10-15")["cockpit"]["history"]
    assert h["current_label"] == "Liquidity Stress / Risk-Off" and h["transitions_1m"] == 6


def test_1022_uses_the_same_storage_dates_as_other_days():
    v = _view("2026-10-22")["cockpit"]["history"]
    assert v.get("date_basis", "storage_utc") != "kst_snapshot" and len(v["days"]) == 22
    assert [d["date"] for d in v["days"]][-3:] == ["2026-10-19", "2026-10-20", "2026-10-21"]
    # 같은 날짜는 다른 날짜 화면(10/21 저장본)과 같은 원본 판정
    old = {d["date"]: d for d in _doc("2026-10-21")["cockpit"]["history"]["days"] if d["source"] != "LIVE"}
    for d in v["days"]:
        if d["date"] in old:
            assert d["raw_state"] == old[d["date"]]["raw_state"] and d["evidence_strength"] == old[d["date"]]["evidence_strength"]
    # MARKET NOW(저장본)와 History 의 공식 판정이 같다
    doc = _view("2026-10-22")
    assert doc["cockpit"]["market_now"]["label"] == "NEUTRAL" and v["official_state_label"] == "NEUTRAL"
    # MARKET NOW 의 Official regime 띠도 History 와 같은 sequence — 10/21 화면과 같은 날짜는 같은 판정
    spark = doc["cockpit"]["market_now"]["spark"]
    assert [p["date"] for p in spark] == [d["date"] for d in v["days"]]
    s21 = {p["date"]: p["label"] for p in _doc("2026-10-21")["cockpit"]["market_now"]["spark"]}
    assert all(s21[p["date"]] == p["label"] for p in spark if p["date"] in s21)
    for tab, h in doc["daily_history"].items():
        assert h.get("date_basis", "storage_utc") != "kst_snapshot" and h["points"][-1]["date"] == "2026-10-21", tab


def test_view_reads_only():
    before = {p: hashlib.sha1(p.read_bytes()).hexdigest() for p in (ROOT / "history").glob("*.json")}
    arch = hashlib.sha1((ROOT / "archive" / "2026" / "10" / "2026-10-22.json").read_bytes()).hexdigest()
    _view("2026-10-22")
    assert {p: hashlib.sha1(p.read_bytes()).hexdigest() for p in (ROOT / "history").glob("*.json")} == before
    assert hashlib.sha1((ROOT / "archive" / "2026" / "10" / "2026-10-22.json").read_bytes()).hexdigest() == arch


def test_api_serves_view_and_stored():
    from fastapi.testclient import TestClient

    from marketpulse.api.main import create_app
    from marketpulse.api.routes.archive import use_archive_service, use_history_manager
    from marketpulse.archive.service import DailyArchiveService
    from marketpulse.archive.store import ArchiveStore
    use_archive_service(DailyArchiveService(ArchiveStore(ROOT / "archive"))); use_history_manager(_mgr())
    try:
        c = TestClient(create_app())
        assert c.get("/api/v1/archive/2026-10-22").json()["cockpit"]["history"]["days"][-1]["date"] == "2026-10-21"
        assert c.get("/api/v1/archive/2026-10-22?view=stored").json() == _doc("2026-10-22")
        assert c.get("/api/v1/archive/2026-10-15").json() == _doc("2026-10-15")
    finally:
        use_archive_service(None); use_history_manager(None)
