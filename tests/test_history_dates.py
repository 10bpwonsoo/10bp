"""
History 날짜 기준 (2026-10-21) — snapshot 날짜(KST Daily Snapshot) 와 market 날짜(미국 정규장) 분리.
저장 데이터는 바꾸지 않고 view 에서만 날짜를 붙인다. 같은 snapshot 날짜는 한 번, 장중 LIVE 는 intraday 로 따로.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from marketpulse.history.dates import load_rule, market_date, resolve, row_date
from marketpulse.history.legacy_view import store_rows_of, upgrade_sections
from marketpulse.history.manager import DailySnapshotManager
from marketpulse.history.store import JsonDirStore

ROOT = Path(__file__).resolve().parents[1] / "marketpulse" / "data"
KST = ZoneInfo("Asia/Seoul")
RULE = load_rule()


def kst(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=KST).astimezone(timezone.utc)


class TestRule:
    def test_0730_kst_uses_previous_us_close(self):
        """10/21 07:30 KST = 10/20 18:30 EDT — 미국 10/20 정규장은 이미 끝났다 → market 10/20, snapshot 10/21."""
        rd = row_date(date(2026, 10, 20), kst(2026, 10, 21, 7, 30), RULE)
        assert rd.market_date == date(2026, 10, 20) and rd.snapshot_date == date(2026, 10, 21)

    def test_intraday_kst_same_snapshot_day(self):
        """10/21 16:00 KST(장중) = 10/21 03:00 EDT → 미국 10/21 장 전 → market 10/20, snapshot 10/21 (같은 날의 장중 값)."""
        rd = row_date(date(2026, 10, 21), kst(2026, 10, 21, 16), RULE)
        assert rd.market_date == date(2026, 10, 20) and rd.snapshot_date == date(2026, 10, 21)

    def test_monday_uses_friday_close_and_weekend_never_a_snapshot(self):
        assert market_date(kst(2026, 10, 19, 7, 30), RULE) == date(2026, 10, 16)
        fri_backfill = row_date(date(2026, 10, 16), datetime(2026, 10, 16, 23, 59, 59, tzinfo=timezone.utc), RULE)
        assert fri_backfill.snapshot_date == date(2026, 10, 19)
        for h in range(0, 24):
            assert row_date(date(2026, 10, 17), kst(2026, 10, 17, h), RULE).snapshot_date.weekday() < 5

    def test_before_us_close_is_previous_session(self):
        assert market_date(datetime(2026, 10, 20, 19, 59, tzinfo=timezone.utc), RULE) == date(2026, 10, 19)  # 15:59 EDT
        assert market_date(datetime(2026, 10, 20, 20, 0, tzinfo=timezone.utc), RULE) == date(2026, 10, 20)  # 16:00 EDT


@dataclass
class Row:
    storage: date
    source: str
    asof: datetime


def _res(rows):
    return resolve(rows, storage=lambda r: r.storage, source=lambda r: r.source, asof=lambda r: r.asof, rule=RULE)


class TestResolve:
    def test_live_is_intraday_not_a_daily_cell(self):
        rows = [Row(date(2026, 10, 19), "RECORDED", kst(2026, 10, 20, 7, 30)), Row(date(2026, 10, 20), "BACKFILLED", datetime(2026, 10, 20, 23, 59, 59, tzinfo=timezone.utc)),
                Row(date(2026, 10, 21), "LIVE", kst(2026, 10, 21, 16))]
        r = _res(rows)
        assert [rd.snapshot_date for _, rd, _ in r.rows] == [date(2026, 10, 20), date(2026, 10, 21)]
        assert r.intraday is not None and r.intraday[0].source == "LIVE" and r.intraday[1].snapshot_date == date(2026, 10, 21)
        assert r.gaps == []

    def test_same_snapshot_day_keeps_recorded_and_lists_the_other(self):
        """KST 장중에 기록된 RECORDED(미국 전날 종가) 와 그 전날 키의 BACKFILLED 는 같은 snapshot 날짜다 — RECORDED 하나, 다른 행은 merged."""
        rows = [Row(date(2026, 10, 9), "BACKFILLED", datetime(2026, 10, 9, 23, 59, 59, tzinfo=timezone.utc)), Row(date(2026, 10, 12), "RECORDED", kst(2026, 10, 12, 15, 9))]
        r = _res(rows)
        assert len(r.rows) == 1
        kept, rd, merged = r.rows[0]
        assert kept.source == "RECORDED" and rd.snapshot_date == date(2026, 10, 12) and rd.market_date == date(2026, 10, 9)
        assert [(m.storage_date, m.source) for m in merged] == [(date(2026, 10, 9), "BACKFILLED")]

    def test_gap_is_reported_not_filled(self):
        rows = [Row(date(2026, 10, 13), "RECORDED", kst(2026, 10, 13, 9, 12)), Row(date(2026, 10, 14), "RECORDED", kst(2026, 10, 15, 8, 31))]
        r = _res(rows)
        assert [rd.snapshot_date for _, rd, _ in r.rows] == [date(2026, 10, 13), date(2026, 10, 15)] and r.gaps == [date(2026, 10, 14)]


def _doc(d: str) -> dict:
    return json.loads((ROOT / "archive" / d[:4] / d[5:7] / f"{d}.json").read_text(encoding="utf-8"))


def _view(d: str) -> dict:
    doc = _doc(d)
    live = datetime.fromisoformat(doc["meta"]["source_asof"].replace("Z", "+00:00"))
    return upgrade_sections(doc, live_asof=live, rows_of=store_rows_of(DailySnapshotManager(JsonDirStore(ROOT / "history"))))


class TestArchiveView:
    def test_1020_and_1021_end_on_their_own_snapshot_date(self):
        for d, tail in (("2026-10-20", ["2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20"]), ("2026-10-21", ["2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21"])):
            h = _view(d)["cockpit"]["history"]
            dates = [x["date"] for x in h["days"]]
            assert dates[-4:] == tail and len(dates) == len(set(dates)) and h["date_basis"] == "kst_snapshot"
            assert all(date.fromisoformat(x).weekday() < 5 for x in dates)

    def test_1021_daily_row_is_us_1020_close_and_live_is_separate(self):
        h = _view("2026-10-21")["cockpit"]["history"]
        last = h["days"][-1]
        assert last["date"] == "2026-10-21" and last["market_date"] == "2026-10-20" and last["source"] == "BACKFILLED" and last["locked"]
        assert h["intraday"]["date"] == "2026-10-21" and h["intraday"]["source"] == "LIVE" and h["intraday"]["official_label"] == _doc("2026-10-21")["cockpit"]["history"]["current_label"]

    def test_values_per_day_are_the_stored_ones(self):
        """날짜만 다시 붙는다 — 판정·확신·factor 는 저장본의 그 저장 행 그대로."""
        doc, h = _doc("2026-10-21"), _view("2026-10-21")
        old = {x["date"]: x for x in doc["cockpit"]["history"]["days"]}
        for x in h["cockpit"]["history"]["days"]:
            o = old[x["storage_date"]]
            assert (x["raw_state"], x["evidence_strength"], x["factors"], x["source"]) == (o["raw_state"], o["evidence_strength"], o["factors"], o["source"])
        for tab, dh in h["daily_history"].items():
            dates = [p["date"] for p in dh["points"]]
            assert len(dates) == len(set(dates)) and dh["date_basis"] == "kst_snapshot", tab
            assert all(p["source"] != "LIVE" for p in dh["points"]), tab

    def test_files_are_not_changed(self):
        before = (ROOT / "archive" / "2026" / "10" / "2026-10-21.json").read_bytes()
        _view("2026-10-21")
        assert (ROOT / "archive" / "2026" / "10" / "2026-10-21.json").read_bytes() == before


class TestArchiveApi:
    def test_default_view_is_kst_and_stored_is_untouched(self):
        from fastapi.testclient import TestClient

        from marketpulse.api.main import create_app
        from marketpulse.api.routes.archive import use_archive_service, use_history_rows
        from marketpulse.archive.service import DailyArchiveService
        from marketpulse.archive.store import ArchiveStore
        use_archive_service(DailyArchiveService(ArchiveStore(ROOT / "archive")))
        use_history_rows(store_rows_of(DailySnapshotManager(JsonDirStore(ROOT / "history"))))
        try:
            c = TestClient(create_app())
            v = c.get("/api/v1/archive/2026-10-21").json()
            raw = c.get("/api/v1/archive/2026-10-21?view=stored").json()
            assert v["cockpit"]["history"]["days"][-1]["date"] == "2026-10-21" and v["cockpit"]["history"]["intraday"]["source"] == "LIVE"
            assert raw == _doc("2026-10-21")
        finally:
            use_archive_service(None); use_history_rows(None)
