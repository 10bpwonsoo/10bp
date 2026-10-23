"""메모리 가격 과거 DB(2026-10-23) — 원문 파서 · RAW vs Daily State 분리 · 계약가 PIT · 1Y z/percentile · coverage · 아카이브 look-ahead."""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from marketpulse.adapters.alternative.memory_history import parse_daily_express, parse_trendforce_weekly
from marketpulse.engines.memory_history import (Anchor, Raw, anchor_state, daily_state, load_contract_raw, load_spot_raw, state_change, weekdays,
                                                window_coverage, zstats)
from marketpulse.engines.semiconductor_cycle import build_semiconductor_cycle
from marketpulse.scripts.collect_memory_history import collect_daily_express, validate

PKG = Path(__file__).resolve().parent.parent / "marketpulse"
TPE = timezone(timedelta(hours=8))
AS_OF = datetime(2026, 10, 22, 22, 30, tzinfo=timezone.utc)


def _de_page(published: str, price: float, ett: float) -> str:
    return (f"<html><body>PrintFriendly DRAMeXchange : Weekly Research : 【Daily Express】 【Daily Express】 DXI <span>Published</span> {published} (GMT+8) "
            f"In the mainstream category, the average price of DDR4 8G (1Gx8) 3200 rises to USD {price:.3f}, and the average price of DDR4 512x8-2400/2666 stays at USD 2.817. "
            f"As for the eTT category, the average price of DDR4 1Gx8 drops to USD {ett:.3f}, the average price of DDR4 512x8 rises to USD 1.260.</body></html>")


class TestParsers:
    def test_daily_express_quotes_and_values(self):
        r = parse_daily_express(_de_page("2026-10-22", 47.0, 5.97))
        assert r["published"] == date(2026, 10, 22)
        assert r["items"]["DDR4_8G_SPOT"]["price"] == 47.0 and "DDR4 8G (1Gx8) 3200" in r["items"]["DDR4_8G_SPOT"]["quote"]
        assert r["items"]["DDR4_8G_ETT_SPOT"]["price"] == 5.97

    def test_other_research_kinds_are_ignored(self):
        assert parse_daily_express("Weekly Research : 【Enterprise News】 x Published 2026-06-09 (GMT+8) DDR5 ...") is None

    def test_live_capture_if_present(self):
        f = PKG / "data" / "memory_history" / "dram" / "DDR4_8G_SPOT.csv"
        rows = list(csv.DictReader(f.open(encoding="utf-8")))
        assert len(rows) >= 250 and rows[0]["date"] <= "2025-09-01" and rows[-1]["date"] >= "2026-10-22"
        assert all(r["source_url"].startswith("https://dramexchange.com/WeeklyResearch/") for r in rows if r["source"] == "dramexchange_daily_express")
        # 홈 수집기·TrendForce 주간 기사와 같은 날 값이 같다(교차 검증)
        by = {r["date"]: float(r["price"]) for r in rows if r["source"] == "dramexchange_daily_express"}
        assert by["2026-09-29"] == pytest.approx(46.321) and by["2026-10-22"] == pytest.approx(47.0)

    @pytest.mark.parametrize("article,text,expect", [
        (date(2026, 7, 29), "Spot prices of 512Gb TLC wafers rose by 1.69% this week (July 27), with average quotations arriving at US$19.250. Next.",
         ("NAND_512G_TLC_WAFER", 19.25, date(2026, 7, 27), "TEXT")),
        (date(2025, 12, 31), "The average spot price of mainstream chips (i.e., DDR4 1Gx8 3200MT/s) has increased by 6.80% from US$22.235 last week (Dec. 24) to US$23.746 this week (Dec. 30). End.",
         ("DDR4_8G_SPOT", 23.746, date(2025, 12, 30), "TEXT")),
        (date(2025, 10, 22), "Spots of 512Gb TLC wafers rose by 27.96% this week, arriving at US$$4.576. End.", ("NAND_512G_TLC_WAFER", 4.576, date(2025, 10, 22), "ARTICLE_DATE")),
        (date(2026, 2, 4), "The mainstream DDR4 1Gx8 3200MT/s chip saw a price increase of 0.06% this week (from US$30.86 to US$30.88). X.", ("DDR4_8G_SPOT", 30.88, date(2026, 2, 4), "ARTICLE_DATE")),
    ])
    def test_trendforce_weekly_sentences(self, article, text, expect):
        """소수점이 있는 문장('1.69%')에서도 값을 찾는다 — 첫 러너 실행이 0행이었던 버그."""
        pid, price, obs, basis = expect
        r = parse_trendforce_weekly(f"<p>{text}</p>", article)[pid]
        assert r["price"] == pytest.approx(price) and r["obs_date"] == obs and r["obs_date_basis"] == basis

    def test_trendforce_prefers_dated_sentence(self):
        t = ("The average spot price of 512Gb TLC wafers slipped 1.28% this week to US$18.592. "
             "Spot prices of 512Gb TLC wafers dropped by 1.28% this week (October 19), with average quotations arriving at US$18.592.")
        r = parse_trendforce_weekly(f"<p>{t}</p>", date(2026, 10, 21))["NAND_512G_TLC_WAFER"]
        assert r["obs_date"] == date(2026, 10, 19) and r["obs_date_basis"] == "TEXT"


class TestCollector:
    def test_year_typo_and_duplicates_are_excluded(self, tmp_path):
        cache = tmp_path / "cache"; cache.mkdir()
        (cache / "1.html").write_text(_de_page("2025-12-31", 24.183, 5.8))
        (cache / "2.html").write_text(_de_page("2025-01-02", 24.496, 5.836))   # 2026-01-02 의 연도 오기
        (cache / "3.html").write_text(_de_page("2026-01-02", 24.496, 5.836))
        (cache / "4.html").write_text(_de_page("2026-01-02", 24.496, 5.836))   # 같은 날 두 번
        rep = collect_daily_express(1, 4, cache=cache, root=tmp_path / "db", sleep=0)
        assert rep["added"]["DDR4_8G_SPOT"] == 2 and len(rep["suspect"]) == 2
        again = collect_daily_express(1, 4, cache=cache, root=tmp_path / "db", sleep=0)   # append-only — 다시 쓰지 않는다
        assert again["added"]["DDR4_8G_SPOT"] == 0
        v = validate(tmp_path / "db")
        assert v["spot"]["DDR4_8G_SPOT"]["dramexchange_daily_express"]["duplicates"] == 0


def _raw(d: str, v: float, known: str | None = None) -> Raw:
    k = datetime.fromisoformat(known) if known else datetime.combine(date.fromisoformat(d), datetime.min.time(), tzinfo=TPE).replace(hour=18)
    return Raw(date.fromisoformat(d), k, v, "test")


class TestDailyState:
    def test_raw_and_carried_forward_are_separate(self):
        raw = [_raw("2026-10-01", 55.0), _raw("2026-10-05", 57.0)]
        days = weekdays(date(2026, 10, 1), date(2026, 10, 6))
        st = daily_state(raw, days, AS_OF)
        assert [(s["d"], s["v"], s["origin"], s["src"]) for s in st] == [
            ("2026-10-01", 55.0, "RAW", "2026-10-01"), ("2026-10-02", 55.0, "CARRIED_FORWARD", "2026-10-01"),
            ("2026-10-05", 57.0, "RAW", "2026-10-05"), ("2026-10-06", 57.0, "CARRIED_FORWARD", "2026-10-05")]
        assert all(date.fromisoformat(s["d"]).weekday() < 5 for s in st)   # 토·일 없음

    def test_value_counts_only_after_it_is_published(self):
        """주간 기사: 월요일 관측이 수요일에 공개되면 월·화는 직전 값, 수요일부터 새 값(origin 은 CARRIED_FORWARD, src=월요일)."""
        raw = [_raw("2026-10-12", 18.833), _raw("2026-10-19", 18.592, "2026-10-21T23:59:00+08:00")]
        st = daily_state(raw, weekdays(date(2026, 10, 19), date(2026, 10, 22)), AS_OF)
        assert [(s["d"], s["v"], s["src"]) for s in st] == [("2026-10-19", 18.833, "2026-10-12"), ("2026-10-20", 18.833, "2026-10-12"),
                                                             ("2026-10-21", 18.592, "2026-10-19"), ("2026-10-22", 18.592, "2026-10-19")]

    def test_contract_anchor_has_no_look_ahead(self):
        a = [Anchor("2026-08", datetime(2026, 8, 31, 14, tzinfo=TPE), 25.0, "x"), Anchor("2026-09", datetime(2026, 10, 3, 18, tzinfo=TPE), 26.0, "x")]
        ast = anchor_state(a, weekdays(date(2026, 9, 30), date(2026, 10, 6)), AS_OF)
        assert ast["2026-09-30"].v == 25.0 and ast["2026-10-02"].v == 25.0 and ast["2026-10-05"].v == 26.0

    def test_window_change_needs_fresh_reference(self):
        st = [{"d": "2026-09-01", "v": 10.0, "age": 30}, {"d": "2026-10-01", "v": 12.0, "age": 0}]
        assert state_change(st, 30, max_ref_age=7) == (None, None)
        st[0]["age"] = 0
        assert state_change(st, 30, max_ref_age=7)[0] == pytest.approx(20.0)

    def test_zscore_uses_raw_only_and_needs_min(self):
        assert zstats([1.0] * 19, 20)["status"] == "NOT ENOUGH HISTORY"
        z = zstats([float(i) for i in range(30)], 20)
        assert z["status"] == "OK" and z["percentile"] == 100 and z["z"] > 1

    def test_coverage_partial_reports_available_from(self):
        raw = [_raw("2026-09-29", 57.8), _raw("2026-10-22", 61.1)]
        c = window_coverage(raw, date(2026, 10, 22), 365, max_gap=10)
        assert c["status"] == "PARTIAL" and c["available_from"] == "2026-09-29"


class TestEngineHistory:
    def test_real_db_1y_for_ddr4_8g_and_partial_for_ddr5(self):
        out = build_semiconductor_cycle(as_of=AS_OF)
        p = {x["id"]: x for x in out["memory_prices"]}
        d4, d5 = p["DDR4_8G_SPOT"], p["DDR5_16G_SPOT"]
        assert d4["coverage"]["1Y"]["status"] == "GOOD" and d4["raw_obs_1y"] >= 200 and d4["change_1y"] is not None
        assert len(d4["daily"]) >= 250 and {r[2] for r in d4["daily"]} <= {"R", "C"}
        assert d5["coverage"]["1Y"]["status"] == "PARTIAL" and d5["change_1y"] is None   # 1년 전 관측이 없다 — 만들지 않는다
        prem = next(x for x in out["spot_premium"] if x["spot"] == "DDR4_8G_SPOT")
        assert prem["z_status"] == "OK" and prem["raw_premium_obs"] >= 200 and prem["contract_months"] >= 12
        d5p = next(x for x in out["spot_premium"] if x["spot"] == "DDR5_16G_SPOT")
        assert d5p["proxy"] and d5p["z_status"] == "NOT ENOUGH HISTORY"
        rows = {r["id"]: r for r in out["coverage_table"]}
        assert rows["DDR4_8G_SPOT"]["coverage"] == "GOOD" and rows["DDR5_16G_SPOT"]["coverage"] == "PARTIAL" and rows["DDR5_16G_SPOT"]["reason"]

    def test_archive_date_has_no_look_ahead(self):
        """2026-04-01 저장 화면 — 1Y 차트 끝 = 2026-04-01, 계약 anchor = 그때 공개된 2월분(4월분은 4/30 공개)."""
        out = build_semiconductor_cycle(as_of=datetime(2026, 4, 1, 22, 30, tzinfo=timezone.utc))
        d4 = next(x for x in out["memory_prices"] if x["id"] == "DDR4_8G_SPOT")
        assert d4["daily"][-1][0] == "2026-04-01" and all(r[0] <= "2026-04-01" for r in d4["daily"])
        prem = next(x for x in out["spot_premium"] if x["spot"] == "DDR4_8G_SPOT")
        assert prem["contract_anchor"] == "2026-02" and all(s["t"] <= "2026-04-01" for s in prem["series"])

    def test_contract_history_merges_db_and_home_table(self):
        a = load_contract_raw("DDR4_8G_CONTRACT", AS_OF)
        assert [x.period for x in a][-2:] == ["2026-08", "2026-09"] and a[-1].v == 26.0
        assert next(x for x in a if x.period == "2026-08").source in ("dramexchange_home",)
        s = load_spot_raw("DDR4_8G_SPOT", "DDR4", AS_OF)
        assert not s.conflicts or all(abs(c["kept"][1] / c["other"][1] - 1) > 0.005 for c in s.conflicts)
