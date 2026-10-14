"""금리 탭 상단 정리(2026-10-12) — RATES REGIME 방향·driver read, CURRENT RATES ANALYSIS, POLICY & MACRO EVENTS.

상단 필드는 기존 계산값을 다시 읽을 뿐이라 같은 입력이면 기존 값이 바뀌지 않는다. 이벤트는 출처 확인된 파일 값 + 미국채 일간 종가 반응만 쓴다.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone

import pytest

from marketpulse.engines.policy_events import build_policy_events, load_events_file, rate_reaction, load_policy_events_config
from marketpulse.engines.rates_regime import build_rates_regime
from marketpulse.models.common import DataMeta, DataMode, DataQuality
from marketpulse.models.market import MarketSeries
from tests.test_rates_regime import _run

AS_OF = datetime(2026, 10, 12, 6, 0, tzinfo=timezone.utc)


def _regime(scenario: str = "inflation_shock"):
    snap, market, by_id = _run(scenario)
    return build_rates_regime(market, snap.themes, by_id)


def _series(iid: str, pts: list[tuple[str, float]]) -> MarketSeries:
    ts = [datetime.fromisoformat(d).replace(tzinfo=timezone.utc) for d, _ in pts]
    meta = DataMeta(source="test", mode=DataMode.DELAYED, retrieved_at=ts[-1], as_of=ts[-1], quality=DataQuality.OK)
    return MarketSeries(instrument_id=iid, timestamps=ts, values=[v for _, v in pts], meta=meta)


def _data() -> dict:
    return {
        "collected": "2026-10-12", "note": "test",
        "policy": [
            {"bank": "FED", "name": "FED / FOMC", "date": "2026-09-16", "decision": "HIKE", "change_bp": 25, "previous_rate": "3.50–3.75%", "current_rate": "3.75–4.00%",
             "rate_label": "Fed funds", "vote": "12–0", "guidance": "hawkish", "line": "l", "next_meeting": "2026-10-28", "sources": [{"title": "t", "url": "https://x"}]},
            {"bank": "ECB", "name": "ECB", "date": "2026-09-10", "decision": "HOLD", "previous_rate": "2.50%", "current_rate": "2.50%", "rate_label": "DFR", "line": "l", "next_meeting": "2026-10-29"},
        ],
        "releases": [
            {"key": "us_cpi", "name": "US CPI", "period": "2026-08", "date": "2026-09-11",
             "measures": [{"key": "headline_yoy", "label": "CPI YoY", "actual": 3.4, "consensus": 3.4, "prior": None}, {"key": "core_mom", "label": "Core MoM", "actual": 0.3, "consensus": 0.2, "prior": None}]},
            {"key": "us_pce", "name": "US PCE", "period": "2026-08", "date": "2026-09-30",
             "measures": [{"key": "core_yoy", "label": "Core PCE YoY", "actual": 3.0, "consensus": 3.0, "prior": 3.3}]},
            {"key": "us_nfp", "name": "Nonfarm Payrolls", "period": "2026-09", "date": "2026-10-02",
             "measures": [{"key": "payrolls", "label": "Payrolls", "unit": "k", "actual": 29, "consensus": 84, "prior": 133}, {"key": "ahe", "label": "AHE", "actual": None, "consensus": None, "prior": None}]},
            {"key": "us_cpi", "name": "US CPI future", "period": "2026-09", "date": "2026-10-14", "measures": [{"key": "headline_yoy", "label": "CPI YoY", "actual": 3.7, "consensus": 3.7}]},
        ],
        "upcoming": [{"date": "2026-10-14", "kind": "us_cpi", "name": "US CPI (9월)"}, {"date": "2026-10-12", "kind": "bok", "name": "오늘 — 제외"}, {"date_start": "2026-10-27", "date": "2026-10-28", "kind": "fomc", "name": "FOMC"}],
    }


SERIES = {
    "US2Y": _series("US2Y", [("2026-09-10", 4.56), ("2026-09-11", 4.63), ("2026-09-15", 4.67), ("2026-09-16", 4.74), ("2026-09-29", 4.89), ("2026-09-30", 4.88), ("2026-10-01", 4.78), ("2026-10-02", 4.83)]),
    "US10Y": _series("US10Y", [("2026-09-10", 4.95), ("2026-09-11", 4.96), ("2026-09-15", 5.00), ("2026-09-16", 5.01), ("2026-09-29", 5.26), ("2026-09-30", 5.29), ("2026-10-01", 5.24), ("2026-10-02", 5.28)]),
}


class TestRatesTop:
    def test_top_reads_existing_values_only(self):
        r = _regime()
        t = r.top
        assert t is not None and r.current_analysis is not None
        # 방향은 rate_move 그대로, primary 는 지배 driver 그대로 — 새 계산이 없다
        assert t.direction == r.rate_move.direction and t.primary.id == r.dominant
        assert t.primary.score == next(d.score for d in r.drivers if d.id == r.dominant)
        assert t.direction_arrow in ("↑", "↓", "→", "?") and t.driver_title.endswith("DRIVEN")
        # MARKET READ: 최대 2문장, 숫자를 다시 읽지 않는다, '확률' 없음
        sentences = [x for x in re.split(r"(?<=[다요])\.\s*", t.market_read) if x.strip()]
        assert 1 <= len(sentences) <= 2 and not re.search(r"\d", t.market_read) and "확률" not in t.market_read
        assert "(이)" not in t.market_read and "(은)" not in t.market_read and "(을)" not in t.market_read

    def test_counter_and_not_confirmed(self):
        r = _regime()
        t = r.top
        if t.counter is not None:
            c = next(d for d in r.drivers if d.id == t.counter.id)
            assert c.id != r.dominant and (c.status == "CONTRADICTED" or c.score * t.primary.score < 0) and abs(c.score) >= 25
        for d in t.not_confirmed:
            assert d.id in ("inflation_repricing", "fed_policy") and d.status != "CONFIRMED" and d.id != r.dominant
        assert set(t.driver_lines) >= {r.dominant} and all("확률" not in v for v in t.driver_lines.values())

    def test_current_analysis_tiles(self):
        r = _regime()
        ca = r.current_analysis
        assert [x.key for x in ca.tiles] == ["driver", "curve", "real_yield", "breakeven"]
        assert ca.tiles[0].value == next(d.label for d in r.drivers if d.id == r.dominant) and ca.tiles[0].sub in ("DOMINANT", "LEADING", "CONTESTED")
        for x in ca.tiles[2:]:
            assert x.move in ("up", "down", "flat", "missing")
        assert ca.sentence and "확률" not in ca.sentence

    def test_old_capture_without_top_still_validates(self):
        from marketpulse.models.rates_regime import RatesRegime
        raw = json.loads(_regime().model_dump_json())
        for k in ("top", "current_analysis", "events"):
            raw.pop(k, None)
        old = RatesRegime.model_validate(raw)
        assert old.top is None and old.events is None


class TestPolicyEvents:
    def test_surprise_reaction_and_impact(self):
        r = _regime()  # inflation_shock: 금리 ↑, 지배 driver = inflation_repricing
        ev = build_policy_events(_data(), SERIES, r, as_of=AS_OF)
        rel = {x.key: x for x in ev.releases}
        # 미래 날짜 발표(10/14)는 결과로 쓰지 않는다
        assert all(x.date <= AS_OF.date() for x in ev.releases) and len(ev.releases) == 3
        cpi, pce, nfp = rel["us_cpi"], rel["us_pce"], rel["us_nfp"]
        assert cpi.surprise == "HOT" and "Core MoM" in cpi.surprise_basis
        assert pce.surprise == "INLINE" and nfp.surprise == "WEAK"
        # 반응 = 발표일 종가 − 직전 거래일 종가(bp)
        assert cpi.reaction.us2y_bp == pytest.approx(7.0) and cpi.reaction.us10y_bp == pytest.approx(1.0)
        assert nfp.reaction.us2y_bp == pytest.approx(5.0) and nfp.reaction.us10y_bp == pytest.approx(4.0)
        # 금리 ↑ regime: HOT(↑) + 물가 경로 = 지배 driver → SUPPORTED, WEAK(↓) → CHALLENGED, INLINE → NEUTRAL
        assert r.rate_move.direction == "up" and r.dominant == "inflation_repricing"
        assert cpi.regime.impact == "SUPPORTED" and nfp.regime.impact == "CHALLENGED" and pce.regime.impact == "NEUTRAL"
        assert cpi.chain[0] == "CPI HOT" and cpi.chain[-1] == "10Y +1bp"
        # 확인 못 한 값은 None 으로 남고 missing 에 적힌다
        ahe = next(m for m in nfp.measures if m.key == "ahe")
        assert ahe.actual is None and any("AHE" in m for m in ev.missing)
        for x in ev.releases:
            assert "확률" not in x.read and "확률" not in x.regime.reason

    def test_policy_tone_and_non_us(self):
        r = _regime()
        ev = build_policy_events(_data(), SERIES, r, as_of=AS_OF)
        fed = next(p for p in ev.policy if p.bank == "FED"); ecb = next(p for p in ev.policy if p.bank == "ECB")
        assert fed.tone == "HAWKISH" and fed.decision_label == "HIKE +25bp" and fed.reaction is not None and fed.reaction.us2y_bp == pytest.approx(7.0)
        assert fed.regime.impact == "SUPPORTED" or fed.regime.impact == "NEUTRAL"  # 금리 ↑ 와 같은 방향 — 도전은 아니다
        # guidance 가 없으면 결정으로 톤을 정하고, 미국 외 중앙은행은 regime 판정을 하지 않는다
        assert ecb.tone == "NEUTRAL" and ecb.reaction is None and ecb.regime.impact is None and "ECB 표결" in ev.missing

    def test_recent_upcoming_and_link(self):
        r = _regime()
        ev = build_policy_events(_data(), SERIES, r, as_of=AS_OF)
        assert [u.name for u in ev.upcoming] == ["US CPI (9월)", "FOMC"] and ev.upcoming[0].days_ahead == 2 and ev.upcoming[1].date_start == date(2026, 10, 27)
        assert ev.recent[0].importance == "HIGH" and all(x.importance == "HIGH" for x in ev.recent[:4])
        assert ev.link is not None and ev.link.latest_key == "us_pce"  # CPI·PCE 중 최근
        assert sum(ev.link.counts.values()) == sum(1 for x in ev.recent if x.impact is not None)

    def test_reaction_missing_date_is_none(self):
        rx = rate_reaction(date(2026, 9, 12), SERIES, load_policy_events_config())
        assert rx.us2y_bp is None and rx.us10y_bp is None and rx.us2y_arrow == "–"

    def test_no_file_returns_none(self, tmp_path):
        assert load_events_file(date(2026, 10, 12), data_dir=tmp_path) is None
        assert build_policy_events(None, SERIES, _regime(), as_of=AS_OF) is None
        (tmp_path / "2026-10-01.json").write_text("{}", encoding="utf-8"); (tmp_path / "2026-10-20.json").write_text('{"x": 1}', encoding="utf-8")
        assert load_events_file(date(2026, 10, 12), data_dir=tmp_path) == {}  # as_of 이후 파일은 쓰지 않는다

    def test_curated_file_has_sources(self):
        data = load_events_file(date(2026, 10, 12))
        assert data is not None
        for p in data["policy"]:
            assert p["sources"] and all(s["url"].startswith("https://") for s in p["sources"])
        for x in data["releases"]:
            assert x["sources"]
        for u in data["upcoming"]:
            assert u["sources"]


class TestApi:
    def test_mock_has_no_real_events(self, client):
        body = client.get("/api/v1/rates-regime?scenario=inflation_shock").json()
        assert body["events"] is None and body["top"] is not None and body["current_analysis"] is not None


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from marketpulse.api.deps import get_investment_service, get_rates_regime_service, get_scenario_check_service, get_service, get_state_history_service
    from marketpulse.api.main import create_app
    for svc in (get_service(), get_state_history_service(), get_investment_service(), get_scenario_check_service(), get_rates_regime_service()):
        svc.clear()
    with TestClient(create_app()) as c:
        yield c


class TestSameDayUpcoming:
    def test_release_time_keeps_today_event_until_release(self):
        """발표 시각이 적힌 오늘 일정은 그 시각 전까지 UPCOMING 에 남는다 — 시각이 없거나 지났으면 뺀다(2026-10-14)."""
        data = _data()
        data["upcoming"] = [
            {"date": "2026-10-12", "kind": "us_cpi", "name": "오늘 밤 CPI", "release_utc": "2026-10-12T12:30:00Z"},
            {"date": "2026-10-12", "kind": "bok", "name": "오늘 — 시각 없음"},
            {"date": "2026-10-12", "kind": "fomc", "name": "오늘 — 이미 지남", "release_utc": "2026-10-12T05:00:00Z"},
        ]
        ev = build_policy_events(data, SERIES, _regime(), as_of=AS_OF)
        assert [u.name for u in ev.upcoming] == ["오늘 밤 CPI"]
        assert ev.upcoming[0].days_ahead == 0 and ev.upcoming[0].release_utc == datetime(2026, 10, 12, 12, 30, tzinfo=timezone.utc)
