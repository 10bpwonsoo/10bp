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
        # 2026-10-22: 장중 LIVE 는 공식 판정을 바꾸지 않는다 — intraday 의 official 은 daily 공식 판정 그대로
        assert h["intraday"]["date"] == "2026-10-21" and h["intraday"]["source"] == "LIVE" and h["intraday"]["official_label"] == h["current_label"] == "Risk-On"

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


# ── 2026-10-22: 공식 regime 판정 단일 기준 — Daily Snapshot · 같은 미국 장은 한 번 · 장중 LIVE 는 후보 신호 ──
from datetime import timedelta  # noqa: E402

from marketpulse.engines.cockpit import LABEL_TEXT, load_cockpit_config  # noqa: E402
from marketpulse.engines.regime_history import build_regime_history  # noqa: E402
from marketpulse.models.state import StateLabel  # noqa: E402
from marketpulse.models.state_history import MarketStateHistory, StateHistoryPoint  # noqa: E402


def _pt(snap: str, mkt: str, label: str, conf: float, source: str = "RECORDED") -> StateHistoryPoint:
    asof = datetime.fromisoformat(f"{snap}T07:30:00+09:00") if source != "LIVE" else datetime.fromisoformat(f"{snap}T16:00:00+09:00")
    return StateHistoryPoint(date=date.fromisoformat(snap), as_of=asof, label=StateLabel(label), confidence=conf, coverage=0.8, composite=0.0, band="neutral", band_label="중립",
                             factors={}, drivers=[], source=source, locked=source != "LIVE", market_date=date.fromisoformat(mkt), storage_date=date.fromisoformat(mkt))


def _hist(daily: list[StateHistoryPoint], live: StateHistoryPoint | None = None) -> MarketStateHistory:
    return MarketStateHistory(as_of=daily[-1].as_of, days_requested=len(daily), points=daily, history_mode="stored", date_basis="kst_snapshot", intraday=live)


def _state(daily, live=None):
    h = build_regime_history(_hist(daily, live), load_cockpit_config().get("history") or {})
    return h, h.state


BASE = [_pt("2026-10-15", "2026-10-14", "RISK_ON", 60), _pt("2026-10-16", "2026-10-15", "RISK_ON", 60)]


class TestRegimeState:
    def test_a_risk_on_then_neutral_is_pending_1_of_2(self):
        h, st = _state(BASE + [_pt("2026-10-19", "2026-10-16", "NEUTRAL", 30)])
        assert st.official_regime == "risk_on" and st.official_state == "RISK_ON" and h.current_regime == "risk_on"
        assert st.transition_status == "PENDING" and st.transition_text == "PENDING · 1 / 2" and st.candidate_regime == "neutral" and st.transition_days == 1

    def test_b_two_neutral_snapshots_on_different_market_dates_confirm(self):
        h, st = _state(BASE + [_pt("2026-10-19", "2026-10-16", "NEUTRAL", 30), _pt("2026-10-20", "2026-10-19", "NEUTRAL", 30)])
        assert st.official_regime == "neutral" and st.official_label == "Neutral / Mixed" and st.transition_status == "CONFIRMED" and st.transition_text == "CONFIRMED · 2 / 2"
        assert st.previous_regime == "risk_on" and st.confirmed_by == "persistence"

    def test_c_intraday_live_on_same_market_date_stays_pending(self):
        """10/21 Daily Snapshot(US 10/20) Neutral + 10/21 장중 LIVE(US 10/20) Neutral — 같은 미국 장이라 여전히 1/2."""
        daily = BASE + [_pt("2026-10-20", "2026-10-19", "RISK_ON", 60), _pt("2026-10-21", "2026-10-20", "NEUTRAL", 23)]
        h, st = _state(daily, _pt("2026-10-21", "2026-10-20", "NEUTRAL", 34, source="LIVE"))
        assert st.official_regime == "risk_on" and st.transition_text == "PENDING · 1 / 2" and st.transition_days == 1
        assert st.live_signal is not None and st.live_signal.state == "NEUTRAL" and st.live_signal.same_market_date
        assert len(h.days) == len(daily) and all(d.source != "LIVE" for d in h.days)  # 장중 LIVE 는 daily 칸에 없다

    def test_same_us_close_in_two_snapshots_counts_once(self):
        """동일 미국장 종가가 두 KST snapshot 에 들어가도 persistence 는 한 번 — 예전 저장 키(UTC)로 겹친 행 흉내."""
        daily = BASE + [_pt("2026-10-19", "2026-10-16", "NEUTRAL", 30), _pt("2026-10-20", "2026-10-16", "NEUTRAL", 30)]
        h, st = _state(daily)
        assert st.transition_days == 1 and st.official_regime == "risk_on" and st.transition_status == "PENDING"

    def test_strong_evidence_still_confirms_in_one_day(self):
        """강한 증거(확신 ≥ strong_evidence) 규칙은 그대로 — 10/20 Liquidity Stress → Risk-On(89%) 이 그 예."""
        h, st = _state(BASE[:1] + [_pt("2026-10-16", "2026-10-15", "LIQUIDITY_STRESS", 60), _pt("2026-10-19", "2026-10-16", "LIQUIDITY_STRESS", 60), _pt("2026-10-20", "2026-10-19", "RISK_ON", 89)])
        assert st.official_regime == "risk_on" and st.transition_status == "CONFIRMED" and st.confirmed_by == "strong_evidence"

    def test_d_archive_market_now_and_history_share_one_state(self):
        for d in ("2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21"):
            ck = _view(d)["cockpit"]
            n, h = ck["market_now"], ck["history"]
            assert n["state"] == h["state"], d
            assert n["label"] == h["state"]["official_state"] and n["transition_status"] == h["state"]["transition_status"] == h["transition_status"], d
            assert n["persistence_days"] == h["duration_days"] and n["raw_persistence_days"] == h["raw_persistence_days"], d
            assert ck["tone"]["regime_key"] == h["current_regime"], d

    def test_1021_archive_reads_official_risk_on_pending(self):
        n = _view("2026-10-21")["cockpit"]["market_now"]
        assert n["label_text"] == "RISK-ON" and n["raw_text"] == "NEUTRAL / MIXED" and n["state"]["transition_text"] == "PENDING · 1 / 2"
        assert n["state"]["live_signal"]["state"] == "NEUTRAL" and n["change_text"] == "" and n["potential_change_text"] == "RISK-ON → NEUTRAL / MIXED"

    def test_e_no_regime_string_is_gone(self):
        assert "NO REGIME" not in LABEL_TEXT.values() and LABEL_TEXT["NEUTRAL"] == "NEUTRAL / MIXED"
        for d in ("2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-19", "2026-10-20", "2026-10-21"):
            assert "NO REGIME" not in json.dumps(_view(d), ensure_ascii=False), d
