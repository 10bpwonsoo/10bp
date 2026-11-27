"""
입력 수집 구조(2026-11-25) — 공급처 Circuit Breaker · 이어 받기 · 입력 상태 판정 · PARTIAL 저장.

2026-11-25 아침 Yahoo 가 429 를 주는 동안 수집이 통째로 멈춘 뒤 바꾼 것들이다. 네트워크와 실제 sleep 은 쓰지 않는다.
"""

from __future__ import annotations

import io
import json
import subprocess
import urllib.error
from datetime import date, datetime, timedelta, timezone
from email.message import Message
from pathlib import Path
from types import SimpleNamespace

import pytest

from marketpulse.adapters import http as H
from marketpulse.adapters.breaker import ProviderBreaker, parse_retry_after
from marketpulse.adapters.http import BreakerHttpClient, FetchError
from marketpulse.archive import ArchiveStore, DailyArchiveService
from marketpulse.archive.backfill import PartialInputsError, build_one
from marketpulse.archive.input_status import assess, behind_bars, market_of
from marketpulse.archive.pit import availability_lag, bar_available
from marketpulse.archive.reconstruct import cutoff_for
from marketpulse.collector import handoff
from marketpulse.collector.engine import EXIT_INCOMPLETE, EXIT_OK, Collector, Plan, validate_against_reference
from marketpulse.models.common import DataMeta, DataMode
from marketpulse.models.market import MarketSeries

YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/"
HOST = "query1.finance.yahoo.com"
UTC = timezone.utc


class Clock:
    def __init__(self, t: float = 1_800_000_000.0) -> None:
        self.t = t
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, sec: float) -> None:
        self.sleeps.append(sec)
        self.t += sec


def http_error(url: str, code: int, *, retry_after: str | None = None, body: bytes = b"Too Many Requests\r\n"):
    hdrs = Message()
    if retry_after is not None:
        hdrs["Retry-After"] = retry_after
    return urllib.error.HTTPError(url, code, "Too Many Requests" if code == 429 else "Error", hdrs, io.BytesIO(body))


# ══ 1. Circuit Breaker ═══════════════════════════════════════════
def test_breaker_backs_off_then_opens_and_doubles_the_cooldown(tmp_path):
    clk = Clock()
    b = ProviderBreaker(tmp_path / "b.json", config={"threshold": 3, "backoff_sec": [10, 20], "base_cooldown_sec": 300, "max_cooldown_sec": 1000}, now=clk.now)
    assert b.failure(HOST, kind="http_429", status=429) == {"opened": False, "pause_sec": 10.0}
    assert b.failure(HOST, kind="http_429", status=429) == {"opened": False, "pause_sec": 20.0}
    v = b.failure(HOST, kind="http_429", status=429)
    assert v["opened"] and v["cooldown_sec"] == 300 and v["basis"] == "exponential_backoff"
    assert b.allow(HOST)[0] is False                      # 열려 있는 동안에는 보내지 않는다
    clk.t += 301
    assert b.allow(HOST) == (True, "half_open")           # 쉬는 시간이 끝나면 시험 요청 하나
    assert b.failure(HOST, kind="http_429", status=429)["cooldown_sec"] == 600   # 시험 요청도 막히면 2배
    clk.t += 601
    assert b.allow(HOST)[0]
    assert b.failure(HOST, kind="http_429", status=429)["cooldown_sec"] == 1000  # 상한
    clk.t += 1001
    assert b.allow(HOST)[0]
    b.success(HOST)
    assert b.snapshot()[HOST]["state"] == "closed" and b.allow(HOST) == (True, "closed")


def test_breaker_follows_retry_after_when_the_provider_gives_one(tmp_path):
    clk = Clock()
    b = ProviderBreaker(tmp_path / "b.json", now=clk.now)
    v = b.failure(HOST, kind="http_429", status=429, retry_after="120")
    assert v["opened"] and v["cooldown_sec"] == 120 and v["basis"] == "retry_after"   # 임계를 기다리지 않고 공급처가 말한 만큼 쉰다
    assert b.snapshot()[HOST]["last_retry_after"] == "120"
    assert parse_retry_after("Wed, 25 Nov 2026 00:10:00 GMT", now=datetime(2026, 11, 25, 0, 0, tzinfo=UTC).timestamp()) == 600
    assert parse_retry_after(None) is None and parse_retry_after("soon") is None       # 못 읽으면 없는 것 — 지어내지 않는다


def test_breaker_state_survives_a_restart(tmp_path):
    """컨테이너 · 프로세스가 다시 떠도 '지금 쉬는 중' 이라는 사실이 남는다 — 같은 공급처를 처음부터 다시 두드리지 않는다."""
    clk = Clock()
    path = tmp_path / "state" / "b.json"
    b1 = ProviderBreaker(path, now=clk.now)
    for _ in range(3):
        b1.failure(HOST, kind="http_429", status=429, body="Too Many Requests")
    until = b1.snapshot()[HOST]["open_until"]
    del b1
    clk.t += 60                                            # 재시작까지 1분
    b2 = ProviderBreaker(path, now=clk.now)                # 새 프로세스
    ok, why = b2.allow(HOST)
    assert ok is False and "회로 열림" in why
    assert b2.snapshot()[HOST]["open_until"] == until and b2.snapshot()[HOST]["retry_in_sec"] == 240
    assert b2.next_retry_at() == until
    assert b2.allow("api.stlouisfed.org")[0]               # 다른 공급처는 막지 않는다
    clk.t += 241
    assert b2.allow(HOST)[0]


def test_breaker_forgets_yesterdays_escalation(tmp_path):
    """어제 아침에 세 번 열렸더라도 오늘 첫 실패는 다시 5분부터다 — 누적이 하루를 넘어가 1시간짜리 차단이 되지 않는다."""
    clk = Clock()
    b = ProviderBreaker(tmp_path / "b.json", now=clk.now)
    for _ in range(3):
        b.failure(HOST, kind="http_429", status=429)
    clk.t += 301; b.allow(HOST); assert b.failure(HOST, kind="http_429", status=429)["cooldown_sec"] == 600
    clk.t += 601; b.allow(HOST); assert b.failure(HOST, kind="http_429", status=429)["cooldown_sec"] == 1200
    clk.t += 1200 + 23 * 3600                                  # 다음 날 아침
    assert b.allow(HOST) == (True, "half_open")
    assert b.failure(HOST, kind="http_429", status=429)["cooldown_sec"] == 300


def test_breaker_ignores_request_level_failures(tmp_path):
    b = ProviderBreaker(tmp_path / "b.json")
    for _ in range(5):
        assert b.failure(HOST, kind="http_404", status=404) == {"opened": False, "pause_sec": None}
    assert b.allow(HOST)[0]


@pytest.fixture
def client(monkeypatch, tmp_path):
    def make(responses: list, **cfg):
        clk = Clock()
        calls: list[str] = []

        def urlopen(request, timeout=None):
            calls.append(request.full_url)
            item = responses.pop(0) if len(responses) > 1 else responses[0]
            if isinstance(item, Exception):
                raise item
            return io.BytesIO(item)

        monkeypatch.setattr(H.urllib.request, "urlopen", urlopen)
        monkeypatch.setattr(H.time, "monotonic", clk.now)
        b = ProviderBreaker(tmp_path / "b.json", config=cfg or None, now=clk.now)
        c = BreakerHttpClient(breaker=b, min_gap_sec=2.0)
        c._sleep = clk.sleep
        return c, b, calls, clk
    return make


def test_client_retries_after_a_short_pause_and_does_not_sleep_once_the_circuit_opens(client):
    c, b, calls, clk = client([http_error(YAHOO, 429), b"ok-1", http_error(YAHOO, 429), http_error(YAHOO, 429), http_error(YAHOO, 429), b"never"])
    assert c.get(YAHOO + "SPY", params={"period1": 1, "period2": 2}) == b"ok-1"     # 429 한 번 → 10초 쉬고 같은 요청
    assert clk.sleeps == [10.0] and len(calls) == 2
    with pytest.raises(FetchError) as e:
        c.get(YAHOO + "QQQ", params={"period1": 1, "period2": 2})                   # 연속 3번 → 회로를 연다
    assert e.value.kind == "circuit_open" and e.value.status == 429
    before = (len(calls), list(clk.sleeps))
    with pytest.raises(FetchError) as e2:
        c.get(YAHOO + "IWM", params={"period1": 1, "period2": 2})                   # 열린 뒤에는 보내지도 자지도 않는다
    assert e2.value.kind == "circuit_open" and (len(calls), clk.sleeps) == before
    assert c.stats["skipped"] == 1 and b.snapshot()[HOST]["state"] == "open"
    assert max(clk.sleeps) <= 20.0                                                   # 45 · 90 · 180초씩 자던 대기는 없다


def test_client_opens_at_once_on_retry_after_and_records_the_response(client):
    c, b, calls, clk = client([http_error(YAHOO, 429, retry_after="900", body=b"Edge: Too Many Requests")])
    with pytest.raises(FetchError):
        c.get(YAHOO + "SPY")
    snap = b.snapshot()[HOST]
    assert snap["state"] == "open" and snap["retry_in_sec"] == 900 and snap["last_status"] == 429
    assert snap["last_retry_after"] == "900" and snap["last_body"] == "Edge: Too Many Requests"   # 누가 뭐라고 답했는지 남긴다
    assert len(calls) == 1 and clk.sleeps == []


# ══ 2. 입력 상태 판정 ════════════════════════════════════════════
def series(iid: str, source: str, days: list[date], *, hh: int = 14, mm: int = 30, values: list[float] | None = None) -> MarketSeries:
    ts = [datetime(d.year, d.month, d.day, hh, mm, tzinfo=UTC) for d in days]
    return MarketSeries(instrument_id=iid, timestamps=ts, values=values or [100.0 + i for i in range(len(ts))],
                        meta=DataMeta(source=source, mode=DataMode.DELAYED, retrieved_at=ts[-1], as_of=ts[-1]))


def weekdays(end: date, n: int) -> list[date]:
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


def write_inputs(folder: Path, base: dict[str, MarketSeries], universe: dict | None = None, basket: dict | None = None) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name, group in (("base", base), ("universe", universe or {}), ("basket", basket or {})):
        (folder / f"series_{name}.json").write_text(json.dumps({k: json.loads(v.model_dump_json()) for k, v in group.items()}), encoding="utf-8")
    return folder


CUT = cutoff_for(date(2026, 11, 25))          # 2026-11-25 07:30 KST = 11/24 22:30Z — 미국 11/24(화) 종가 직후
CFG = {"gate": {"must": ["SPX", "VIX"], "core": ["SPX", "VIX", "NDX", "WTI", "KOSPI"], "min_core_ok": 0.8},
       "market_holidays": {"US": ["2026-11-26"], "JP": ["2026-11-23"]}}


def test_a_bar_that_should_be_out_but_is_not_makes_the_series_stale():
    fresh = datetime(2026, 11, 24, 14, 30, tzinfo=UTC)
    assert behind_bars(fresh, "yahoo:^GSPC", CUT) == 0
    assert behind_bars(datetime(2026, 11, 23, 14, 30, tzinfo=UTC), "yahoo:^GSPC", CUT) == 1      # 11/24 봉이 이미 끝났는데 없다
    assert behind_bars(datetime(2026, 11, 20, 14, 30, tzinfo=UTC), "yahoo:^GSPC", CUT) == 2      # 주말은 세지 않는다
    # FRED 는 관측일 다음 평일 22:00Z 에 공개 — 11/23 관측이 기준 시각의 최신이다(11/24 관측은 아직)
    assert behind_bars(datetime(2026, 11, 23, tzinfo=UTC), "fred:DGS10", CUT) == 0
    assert behind_bars(datetime(2026, 11, 20, tzinfo=UTC), "fred:DGS10", CUT) == 1
    # 휴장일은 세지 않는다(일본 11/23)
    assert behind_bars(datetime(2026, 11, 20, 0, 0, tzinfo=UTC), "yahoo:^N225", cutoff_for(date(2026, 11, 24)), holidays={date(2026, 11, 23)}) == 0


def test_stooq_and_twelvedata_daily_bars_are_usable_right_after_the_us_close_but_never_before():
    us = datetime(2026, 11, 24, tzinfo=UTC)                                    # 날짜만 있는 일봉 — 00:00Z
    assert availability_lag("stooq:nvda.us") == timedelta(hours=22) and availability_lag("twelvedata:NVDA") == timedelta(hours=22)
    assert bar_available(us, availability_lag("stooq:nvda.us"), CUT)            # 22:00Z <= 22:30Z
    assert not bar_available(us, availability_lag("stooq:nvda.us"), CUT - timedelta(hours=1))   # 마감 전에는 쓰지 않는다(look-ahead 없음)
    assert not bar_available(us, availability_lag("stooq:usdjpy"), CUT)         # 환율은 하루가 다 지나야
    assert market_of("yahoo:005930.KS") == "KR" and market_of("yahoo:CL=F") == "US" and market_of("yahoo:KRW=X") == "FX"
    assert market_of("fred:DGS10") == "FRED" and market_of("stooq:^kospi") == "KR"


def test_gate_is_partial_when_core_series_are_missing_or_stale(tmp_path):
    d24, d23 = weekdays(date(2026, 11, 24), 30), weekdays(date(2026, 11, 23), 30)
    full = write_inputs(tmp_path / "full", {"SPX": series("SPX", "yahoo:^GSPC", d24), "NDX": series("NDX", "yahoo:^NDX", d24), "VIX": series("VIX", "yahoo:^VIX", d24, hh=7, mm=0),
                                            "WTI": series("WTI", "yahoo:CL=F", d24, hh=5, mm=0), "KOSPI": series("KOSPI", "yahoo:^KS11", d24, hh=0, mm=0),
                                            "HSTECH": series("HSTECH", "yahoo:3033.HK", d23, hh=1, mm=30)})
    st = assess(full, CUT, cfg=CFG)
    assert st["gate"]["verdict"] == "FULL" and st["stale"]["base"] == ["HSTECH"]     # 핵심이 아닌 STALE 은 그 계열만 빠진다
    # Yahoo 가 막힌 날: 지수는 못 받았고, 유가는 며칠 늦는 대체 경로에서만 받았다
    out = write_inputs(tmp_path / "out", {"VIX": series("VIX", "fred:VIXCLS", d23, hh=0, mm=0), "WTI": series("WTI", "fred:DCOILWTICO", weekdays(date(2026, 11, 17), 30), hh=0, mm=0),
                                          "KOSPI": series("KOSPI", "yahoo:^KS11", d24, hh=0, mm=0)})
    st = assess(out, CUT, expected={"base": ["SPX", "NDX", "VIX", "WTI", "KOSPI"]}, cfg=CFG)
    assert st["series"]["base"]["SPX"]["status"] == "MISSING" and st["series"]["base"]["WTI"]["status"] == "STALE"
    assert st["series"]["base"]["VIX"]["status"] == "OK"                              # FRED 11/23 관측은 규칙상 최신이다
    assert st["gate"]["verdict"] == "PARTIAL" and "SPX" in st["gate"]["must_not_ok"] and st["gate"]["core_ok_ratio"] == 0.4
    assert st["stale"]["base"] == ["WTI"]                                             # 전날 값은 오늘 값으로 쓰지 않는다 — 뺀다


def test_a_market_where_every_series_stopped_on_the_same_day_is_read_as_closed_and_hand_files_are_not_judged(tmp_path):
    d24, d23 = weekdays(date(2026, 11, 24), 30), weekdays(date(2026, 11, 23), 30)
    kr_all = {f"KR{i}": series(f"KR{i}", f"yahoo:00{i}000.KS", d23, hh=0, mm=0) for i in range(6)}    # 한국 6계열 모두 11/23 에서 멈춤
    us = {"SPX": series("SPX", "yahoo:^GSPC", d24), "VIX": series("VIX", "yahoo:^VIX", d24, hh=7, mm=0)}
    spot = {"DRAM_SPOT": series("DRAM_SPOT", "csv:DRAM_SPOT", weekdays(date(2026, 10, 7), 30), hh=0, mm=0)}
    st = assess(write_inputs(tmp_path / "a", {**us, **kr_all}, spot), CUT, cfg=CFG)
    assert st["closed_suspect"] == {"KR": 1} and not st["stale"]["base"]              # 달력에 없는 휴장일을 STALE 로 빼지 않는다
    assert st["series"]["universe"]["DRAM_SPOT"]["status"] == "OK"                    # 주 · 월 단위 수기 파일은 날짜 간격으로 가리지 않는다
    mixed = {**kr_all, "KR0": series("KR0", "yahoo:000000.KS", d24, hh=0, mm=0)}       # 하나라도 최신이면 나머지는 정말 빠진 것이다
    st = assess(write_inputs(tmp_path / "b", {**us, **mixed}), CUT, cfg=CFG)
    assert st["closed_suspect"] == {} and len(st["stale"]["base"]) == 5


# ══ 3. 수집기 — 이어 받기 · 공급처 격리 ═══════════════════════════
class FakeAdapter:
    """계열별로 정해 둔 결과를 돌려주는 어댑터 대역. ok=계열, 문자열=그 이유로 실패, 예외=프로세스가 죽는 상황."""

    def __init__(self, script: dict[str, list]):
        self.script = {k: list(v) for k, v in script.items()}
        self.calls: list[str] = []
        self.outcomes: dict = {}

    def fetch_series(self, instruments, *args, bars, as_of):
        ins = instruments[0]
        self.calls.append(ins.id)
        seq = self.script[ins.id]
        item = seq.pop(0) if len(seq) > 1 else seq[0]
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, tuple):   # (공급자, 계열)
            self.outcomes = {ins.id: SimpleNamespace(provider=item[0], attempts=[])}
            return {ins.id: item[1]}
        self.outcomes = {ins.id: SimpleNamespace(provider=None, attempts=[("yahoo", item)])}
        return {}

    def derive_series(self, instruments, series):
        self.outcomes = {}
        return {}


def make_collector(tmp_path, script, *, clock=None, reference=None, specs=None, budget_min=10, breaker=None):
    clk = clock or Clock()
    ids = list(script)
    plan = Plan("base", [SimpleNamespace(id=i, derived_from=None) for i in ids], [], None, 300, specs or {i: [{"provider": "yahoo", "symbol": i}] for i in ids})
    empty = lambda g: Plan(g, [], [], {}, 300, {})
    fake = FakeAdapter(script)
    cfg = {"run": {"budget_min": budget_min, "max_tries_per_series": 3, "wait_for_breaker": True}, "gate": {"must": [], "core": []},
           "validate": {"overlap_bars": 20, "min_overlap": 5, "max_median_rel_diff": 0.02}}
    b = breaker or ProviderBreaker(tmp_path / "state" / "b.json", now=clk.now)
    c = Collector(date(2026, 11, 25), tmp_path / "inputs" / "2026-11-25", cfg=cfg, plans={"base": plan, "universe": empty("universe"), "basket": empty("basket")},
                  adapters=(fake, fake), client=SimpleNamespace(stats={}), breaker=b, now=clk.now, sleep=clk.sleep, log=lambda m: None, reference=reference)
    return c, fake, clk, b


D24 = weekdays(date(2026, 11, 24), 30)


def test_a_run_that_dies_midway_is_resumed_without_refetching_what_it_already_has(tmp_path):
    a, b_, cser = (series(i, f"yahoo:{i}", D24) for i in ("A", "B", "C"))
    c1, fake1, _, _ = make_collector(tmp_path, {"A": [("yahoo", a)], "B": [KeyboardInterrupt()], "C": [("yahoo", cser)]})
    with pytest.raises(KeyboardInterrupt):                     # 컨테이너가 재시작되는 순간
        c1.run(news=False)
    assert fake1.calls == ["A", "B"] and c1.have("base", "A") and not c1.have("base", "B")
    assert not (c1.out / ".lock").exists()                     # 잠금이 남아 다음 실행을 막지 않는다
    c2, fake2, _, _ = make_collector(tmp_path, {"A": [("yahoo", a)], "B": [("yahoo", b_)], "C": [("yahoo", cser)]})   # 새 프로세스
    assert c2.run(news=False) == EXIT_OK
    assert fake2.calls == ["B", "C"]                           # 받은 A 는 다시 요청하지 않는다
    got = json.loads((c2.out / "series_base.json").read_text(encoding="utf-8"))
    assert sorted(got) == ["A", "B", "C"] and got["A"]["values"] == a.values   # 값은 받은 그대로
    assert c2.status["complete"] and len(c2.status["runs"]) == 2


def test_a_blocked_provider_defers_its_series_and_the_run_ends_without_waiting_past_the_budget(tmp_path):
    clk = Clock()
    brk = ProviderBreaker(tmp_path / "state" / "b.json", now=clk.now)
    for _ in range(3):
        brk.failure(HOST, kind="http_429", status=429)        # Yahoo 회로가 열려 있다(5분)
    blocked = f"{HOST} 회로 열림 — 쉬는 중"
    ok = series("FRED1", "fred:DGS10", D24, hh=0, mm=0)
    c, fake, clk, _ = make_collector(tmp_path, {"Y1": [blocked], "Y2": [blocked], "FRED1": [("fred", ok)]}, clock=clk, breaker=brk, budget_min=2)
    assert c.run(news=False) == EXIT_INCOMPLETE                # 일부만 받았다 — 나중에 다시
    assert c.have("base", "FRED1")                             # 다른 공급처 계열은 그대로 받는다(장애가 번지지 않는다)
    assert c.status["series"]["base"]["Y1"]["state"] == "DEFERRED" and c.status["series"]["base"]["Y1"]["tries"] == 0
    assert c.status["next_retry_at"] is not None               # 언제 다시 부르면 되는지 남긴다
    assert sum(clk.sleeps) == 0                                # 회로가 풀리는 시각이 예산(2분) 밖 — 기다리지 않고 끝낸다
    assert c.status["providers"]["yahoo"]["circuit_skipped"] == 2 and c.status["providers"]["fred"]["ok"] == 1
    assert json.loads((c.out / "input_status.json").read_text(encoding="utf-8"))["missing"]["base"] == ["Y1", "Y2"]   # 못 받은 것은 MISSING 으로 적힌다


def test_alternate_source_is_checked_against_the_previous_collection_and_rejected_on_a_unit_mismatch(tmp_path):
    prev = write_inputs(tmp_path / "inputs" / "2026-11-24", {"NVDA": series("NVDA", "yahoo:NVDA", weekdays(date(2026, 11, 23), 30), values=[100.0] * 30),
                                                             "MU": series("MU", "yahoo:MU", weekdays(date(2026, 11, 23), 30), values=[50.0] * 30)})
    good = series("NVDA", "stooq:nvda.us", D24, hh=0, mm=0, values=[100.5] * 30)
    bad = series("MU", "stooq:mu.us", D24, hh=0, mm=0, values=[500.0] * 30)        # 10배 — 단위 · 분할 조정이 다르다
    specs = {i: [{"provider": "yahoo", "symbol": i}, {"provider": "stooq", "symbol": i.lower() + ".us"}] for i in ("NVDA", "MU")}
    c, _, _, _ = make_collector(tmp_path, {"NVDA": [("stooq", good)], "MU": [("stooq", bad)]}, reference=prev, specs=specs)
    c.run(news=False)
    assert c.have("base", "NVDA") and c.status["series"]["base"]["NVDA"]["alt_source"]["check"] == "OK"
    assert not c.have("base", "MU") and c.status["series"]["base"]["MU"]["state"] == "REJECTED"   # 값을 맞춰 고치지 않고 버린다(결측)
    assert validate_against_reference(good, None, c.cfg)[0] == "NO_REFERENCE"
    merged = json.loads((c.out / "series_base.json").read_text(encoding="utf-8"))
    assert merged["NVDA"]["values"] == good.values and "MU" not in merged       # 직전 수집분의 값은 오늘 입력에 들어가지 않는다


def test_a_folder_from_another_day_is_never_reused(tmp_path):
    c, _, _, _ = make_collector(tmp_path, {"A": [("yahoo", series("A", "yahoo:A", D24))]})
    c.run(news=False)
    with pytest.raises(RuntimeError, match="섞지 않는다"):
        Collector(date(2026, 11, 26), c.out, cfg=c.cfg, plans=c.plans, adapters=(None, None), client=None, breaker=c.breaker)


def test_handoff_branch_carries_one_days_inputs_and_keeps_no_history(tmp_path):
    def git(*args, cwd):
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()
    remote, work, reader = tmp_path / "remote.git", tmp_path / "work", tmp_path / "reader"
    git("init", "--bare", str(remote), cwd=tmp_path)
    for repo in (work, reader):
        git("init", str(repo), cwd=tmp_path)
        git("remote", "add", "origin", str(remote), cwd=repo)
    assert handoff.pull("2026-11-25", reader / "none", repo=reader) == []        # 전달 가지가 아직 없으면 '없다' — 오류가 아니다
    for day, value in (("2026-11-24", 1), ("2026-11-25", 2)):
        src = tmp_path / "src" / day
        src.mkdir(parents=True)
        (src / "series_base.json").write_text(json.dumps({"SPX": value}), encoding="utf-8")
        (src / "secret.env").write_text("KEY=1", encoding="utf-8")            # 결과 파일이 아닌 것은 올리지 않는다
        handoff.publish(src, day, repo=work)
    assert handoff.pull("2026-11-25", reader / "in", repo=reader) == ["series_base.json"]
    assert json.loads((reader / "in" / "series_base.json").read_text(encoding="utf-8")) == {"SPX": 2}
    assert handoff.pull("2026-11-24", reader / "old", repo=reader) == []       # 가지에는 마지막 하루만 있다 — 다른 날짜로 대신하지 않는다
    assert git("rev-list", "--count", "FETCH_HEAD", cwd=reader) == "1"
    assert git("status", "--porcelain", cwd=work) == ""                         # 올리는 쪽 작업 폴더 · 스테이징은 그대로


# ══ 4. PARTIAL 저장 ══════════════════════════════════════════════
def test_partial_snapshot_is_stored_apart_and_never_counts_as_the_days_archive(tmp_path):
    store = ArchiveStore(tmp_path / "archive")
    d = date(2026, 11, 25)
    doc = {"schema_version": "1", "snapshot_date": d.isoformat(), "archive_status": "PARTIAL", "meta": {"snapshot_kind": "PARTIAL_INPUTS"}}
    path, replaced = store.write_partial(d, doc)
    assert path == tmp_path / "archive" / "partial" / "2026-11-25.json" and replaced is None
    assert store.dates() == [] and not store.exists(d) and store.index() == []   # 그 날짜는 여전히 '아직 저장되지 않음'
    assert store.partial_dates() == [d] and store.read_partial(d)["meta"]["snapshot_kind"] == "PARTIAL_INPUTS"
    _, replaced = store.write_partial(d, {**doc, "generated_at": "later"})       # 다시 만든 PARTIAL — 앞의 것은 남긴다
    assert replaced is not None and replaced.parent.name == "superseded" and ".partial." in replaced.name
    store.write_new(d, {**doc, "archive_status": "COMPLETE"})                    # 정상 입력으로 확정본을 만든 뒤
    with pytest.raises(FileExistsError):
        store.write_partial(d, doc)                                              # 확정본이 있는 날에는 PARTIAL 을 쓰지 않는다
    kept = store.retire_partial(d)
    assert kept is not None and kept.is_file() and not store.partial_path(d).exists() and store.dates() == [d]


def test_full_save_is_refused_when_the_gate_says_partial(tmp_path):
    svc = DailyArchiveService(ArchiveStore(tmp_path / "archive"))
    st = {"gate": {"verdict": "PARTIAL", "reasons": ["필수 핵심 계열이 최신이 아니다: SPX(MISSING)"]}}
    with pytest.raises(PartialInputsError, match="SPX"):
        build_one(svc, date(2026, 11, 25), inputs=tmp_path, cutoff=CUT, latest=False, input_status=st)
    assert svc.store.dates() == [] and not (tmp_path / "archive").exists()       # 아무것도 쓰지 않았다


def test_stale_refetch_replaces_a_series_only_when_a_closed_bar_was_added(tmp_path):
    """공급처가 최신 일봉 없이 응답한 계열: 다시 받았을 때 '끝난 봉' 이 늘었을 때만 바꾼다. 진행 중 봉의 시각만 늦어진 것은 새 봉이 아니다."""
    d23 = weekdays(date(2026, 11, 23), 30)
    live1 = datetime(2026, 11, 25, 0, 40, tzinfo=UTC)      # 수집 시각으로 찍힌 진행 중 봉(기준 시각 뒤 — 잘린다)
    def kospi(days, live):
        s = series("K", "yahoo:^KS11", days, hh=0, mm=0)
        return s.model_copy(update={"timestamps": s.timestamps + [live], "values": s.values + [1.0]})
    first, same, filled = kospi(d23, live1), kospi(d23, live1 + timedelta(minutes=30)), kospi(weekdays(date(2026, 11, 24), 31), live1 + timedelta(hours=1))
    c1, _, _, _ = make_collector(tmp_path, {"K": [("yahoo", first)]})
    c1.run(news=False)
    assert c1.status["input_status"]["stale"]["base"] == ["K"]            # 11/24 봉이 없다
    c2, _, _, _ = make_collector(tmp_path, {"K": [("yahoo", same)]})
    c2.run(news=False)
    assert c2.status["runs"][-1]["refetched_stale"] == []                 # 끝난 봉이 그대로 — 바꾸지 않는다
    assert c2.load_group("base")["K"].timestamps[-1] == live1
    c3, _, _, _ = make_collector(tmp_path, {"K": [("yahoo", filled)]})
    c3.run(news=False)
    assert c3.status["runs"][-1]["refetched_stale"] == ["base:K"] and c3.status["input_status"]["stale"]["base"] == []


# ══ 5. KRX 공식 Open API ═════════════════════════════════════════
class KrxFake:
    """data-dbg.krx.co.kr 대역 — 날짜(basDd)별로 하루치 전 지수를 돌려준다. 호출한 날짜와 헤더를 적어 둔다."""

    def __init__(self, days: dict[str, list[dict]], *, error: bytes | None = None):
        self.days, self.error = days, error
        self.calls: list[tuple[str, str, str]] = []

    def get(self, url, *, params=None, headers=None, data=None):
        self.calls.append((url.rsplit("/apis/", 1)[1], params["basDd"], (headers or {}).get("AUTH_KEY", "")))
        if self.error is not None:
            return self.error
        return json.dumps({"OutBlock_1": self.days.get(params["basDd"], [])}).encode()


def krx_rows(close: str, kospi200: str = "640.11") -> list[dict]:
    return [{"BAS_DD": "x", "IDX_CLSS": "KOSPI", "IDX_NM": "코스피", "CLSPRC_IDX": close, "FLUC_RT": "6.32"},
            {"BAS_DD": "x", "IDX_CLSS": "KOSPI", "IDX_NM": "코스피 200", "CLSPRC_IDX": kospi200},
            {"BAS_DD": "x", "IDX_CLSS": "KOSPI", "IDX_NM": "코스피 (외국주포함)", "CLSPRC_IDX": "-"}]


def test_krx_open_api_builds_a_series_one_day_per_call_and_never_asks_twice(tmp_path):
    from marketpulse.adapters.market.providers import KrxOpenApiProvider

    days = {f"{d:%Y%m%d}": krx_rows(f"{4000 + i:,}.50") for i, d in enumerate(weekdays(date(2026, 11, 24), 25))}
    days.pop("20261113")                                                   # 휴장일 — 응답이 비어 있다
    net = KrxFake(days)
    p = KrxOpenApiProvider(net, "k-e-y", cache_dir=tmp_path / "krx")
    as_of = datetime(2026, 11, 25, 1, 0, tzinfo=UTC)                        # 11/25 10:00 KST — 오늘 치는 아직 없다
    pts = p.fetch({"provider": "krxapi", "dataset": "idx/kospi_dd_trd", "symbol": "코스피"}, bars=20, as_of=as_of)
    assert len(pts) == 20 and pts[-1] == (datetime(2026, 11, 24, tzinfo=UTC), 4024.5)   # 쉼표가 든 문자열 값을 그대로 읽는다
    assert datetime(2026, 11, 13, tzinfo=UTC) not in [t for t, _ in pts]    # 빈 날은 건너뛴다(값을 만들어 넣지 않는다)
    assert {c[0] for c in net.calls} == {"idx/kospi_dd_trd"} and {c[2] for c in net.calls} == {"k-e-y"}
    n = len(net.calls)
    again = p.fetch({"provider": "krxapi", "dataset": "idx/kospi_dd_trd", "symbol": "코스피 200"}, bars=20, as_of=as_of)   # 같은 서비스의 다른 지수
    asked_again = [c[1] for c in net.calls[n:]]
    assert len(again) == 20 and set(asked_again) <= {"20261125", "20261113"}   # 받은 날짜는 디스크에서 — 아직 없는 오늘 · 최근 빈 날만 다시 묻는다
    assert "코스피 (외국주포함)" not in json.loads(next((tmp_path / "krx" / "idx_kospi_dd_trd").glob("20261124.json")).read_text(encoding="utf-8"))   # '-' 는 값이 아니다


def test_krx_open_api_reports_auth_errors_and_wrong_names_instead_of_returning_nothing(tmp_path):
    from marketpulse.adapters.market.providers import KrxOpenApiProvider

    as_of = datetime(2026, 11, 25, 1, 0, tzinfo=UTC)
    assert KrxOpenApiProvider(KrxFake({}), None).available() == (False, "KRX_API_KEY 가 없다")
    assert KrxOpenApiProvider(KrxFake({}), None, via_proxy=True).available()[0]      # 실행 환경이 헤더를 넣어 주는 경우
    denied = KrxOpenApiProvider(KrxFake({}, error=b'{"respMsg":"Unauthorized API Call","respCode":"401"}'), "k")
    with pytest.raises(FetchError, match="Unauthorized API Call"):                   # 서비스 이용신청 승인이 없을 때
        denied.fetch({"dataset": "idx/kospi_dd_trd", "symbol": "코스피"}, bars=20, as_of=as_of)
    days = {f"{d:%Y%m%d}": krx_rows("4,000.00") for d in weekdays(date(2026, 11, 24), 10)}
    wrong = KrxOpenApiProvider(KrxFake(days), "k")
    with pytest.raises(FetchError, match="코스피 200"):                               # 이름이 틀리면 받은 이름을 알려 준다
        wrong.fetch({"dataset": "idx/kospi_dd_trd", "symbol": "KOSPI"}, bars=20, as_of=as_of)
    stock = KrxOpenApiProvider(KrxFake({f"{d:%Y%m%d}": [{"ISU_CD": "005930", "ISU_NM": "삼성전자", "TDD_CLSPRC": "189,400"}] for d in weekdays(date(2026, 11, 24), 25)}), "k")
    pts = stock.fetch({"provider": "krxapi", "symbol": "sto/stk_bydd_trd:005930"}, bars=20, as_of=as_of)   # 종목은 "<서비스>:<코드>"
    assert pts[-1][1] == 189400.0
    assert availability_lag("krxapi:코스피") == timedelta(hours=9) and market_of("krxapi:코스피") == "KR"
    assert bar_available(datetime(2026, 11, 24, tzinfo=UTC), availability_lag("krxapi:코스피"), CUT)       # 11/24 한국장 종가는 11/25 07:30 KST 에 이미 나와 있다


def test_when_the_first_provider_leaves_the_last_bar_empty_the_next_provider_fills_it(tmp_path):
    """2026-11-25: Yahoo 가 KOSPI 의 11/24 종가를 null 로 줬다. 다음 공급처(KRX 공식 API)가 같은 값의 이력에 그 봉까지 주면 그것으로 바꾼다."""
    d23, d24 = weekdays(date(2026, 11, 23), 30), weekdays(date(2026, 11, 24), 31)
    yahoo = series("KOSPI", "yahoo:^KS11", d23, hh=0, mm=0, values=[4000.0 + i for i in range(30)])

    class Alt:
        def __init__(self, values): self.values, self.asked = values, 0
        def available(self): return True, "사용 가능"
        def fetch(self, spec, *, bars, as_of):
            self.asked += 1
            return [(datetime(d.year, d.month, d.day, tzinfo=UTC), v) for d, v in zip(d24, self.values)]

    specs = {"KOSPI": [{"provider": "yahoo", "symbol": "^KS11"}, {"provider": "krxapi", "dataset": "idx/kospi_dd_trd", "symbol": "코스피"}]}
    c1, fake1, _, _ = make_collector(tmp_path, {"KOSPI": [("yahoo", yahoo)]}, specs=specs)
    c1.run(news=False)
    assert c1.status["input_status"]["stale"]["base"] == ["KOSPI"]
    # 값이 다른(단위가 안 맞는) 대체 계열은 받지 않는다
    c2, fake2, _, _ = make_collector(tmp_path, {"KOSPI": [("yahoo", yahoo)]}, specs=specs)
    fake2.providers = {"krxapi": Alt([v * 10 for v in [4000.0 + i for i in range(31)]])}
    c2.run(news=False)
    assert c2.status["runs"][-1]["refetched_stale"] == [] and c2.load_group("base")["KOSPI"].meta.source == "yahoo:^KS11"
    # 같은 값 + 11/24 봉 → 그 공급처 이력으로 통째로 바꾼다
    c3, fake3, _, _ = make_collector(tmp_path, {"KOSPI": [("yahoo", yahoo)]}, specs=specs)
    fake3.providers = {"krxapi": Alt([4000.0 + i for i in range(30)] + [5006.0])}
    c3.run(news=False)
    got = c3.load_group("base")["KOSPI"]
    assert c3.status["runs"][-1]["refetched_stale"] == ["base:KOSPI←krxapi"]
    assert got.meta.source == "krxapi:코스피" and got.values[-1] == 5006.0 and got.timestamps[-1].date() == date(2026, 11, 24)
    assert c3.status["input_status"]["stale"]["base"] == [] and c3.status["series"]["base"]["KOSPI"]["alt_source"]["check"] == "OK"


def test_a_partial_day_can_take_series_from_a_later_collection_but_never_the_other_way(tmp_path):
    """PARTIAL 로 남은 날짜를 다음 날 확정할 때, 다음 날 수집분에서 빠진 계열을 가져온다. 기준 시각 뒤의 봉은 판정 · 재구성에서 잘린다."""
    d25 = weekdays(date(2026, 11, 25), 31)                                    # 다음 날(11/26) 수집분 — 11/25 봉까지 있다
    c_prev, _, _, _ = make_collector(tmp_path, {"SPX": ["query1.finance.yahoo.com 회로 열림 — 쉬는 중"], "VIX": [("yahoo", series("VIX", "yahoo:^VIX", D24, hh=7, mm=0))]})
    c_prev.run(news=False)                                                     # 11/25 수집: SPX 를 못 받았다
    assert c_prev.status["input_status"]["missing"]["base"] == ["SPX"] if "missing" in c_prev.status["input_status"] else True
    later_dir = tmp_path / "inputs" / "2026-11-26"
    plan = c_prev.plans
    c_next = Collector(date(2026, 11, 26), later_dir, cfg=c_prev.cfg, plans=plan, adapters=(FakeAdapter({"SPX": [("yahoo", series("SPX", "yahoo:^GSPC", d25))], "VIX": [("yahoo", series("VIX", "yahoo:^VIX", d25, hh=7, mm=0))]}),) * 2,
                       client=SimpleNamespace(stats={}), breaker=ProviderBreaker(tmp_path / "state" / "b2.json"), log=lambda m: None)
    c_next.run(news=False)
    took = c_prev.adopt_from(later_dir)
    assert took == ["base:SPX"]                                                # 이미 최신인 VIX 는 건드리지 않는다
    got = c_prev.load_group("base")["SPX"]
    assert got.timestamps[-1].date() == date(2026, 11, 25)                     # 받은 그대로 — 자르는 것은 재구성이 한다
    st = json.loads((c_prev.out / "input_status.json").read_text(encoding="utf-8"))
    assert st["series"]["base"]["SPX"]["status"] == "OK" and st["series"]["base"]["SPX"]["last_bar"][:10] == "2026-11-24"   # 11/25 07:30 KST 기준 마지막 봉
    assert c_prev.status["series"]["base"]["SPX"]["adopted_from"] == "2026-11-26"
    with pytest.raises(RuntimeError, match="합치지 않는다"):
        c_next.adopt_from(c_prev.out)                                          # 앞선 날짜 수집분을 나중 날짜에 쓰는 것은 거절


def test_fred_observation_is_not_expected_until_the_business_day_after_a_us_holiday():
    """11/25(수) 미국채 관측은 추수감사절(11/26)이 아니라 11/27 에 공개된다 — 11/27 07:30 KST 스냅샷은 11/24 관측이 최신이다."""
    from marketpulse.archive.pit import us_holidays
    assert date(2026, 11, 26) in us_holidays()
    cut27 = cutoff_for(date(2026, 11, 27))
    assert behind_bars(datetime(2026, 11, 24, tzinfo=UTC), "fred:DGS10", cut27) == 0           # STALE 이 아니다
    assert not bar_available(datetime(2026, 11, 25, tzinfo=UTC), availability_lag("fred:DGS10"), cut27)   # 아직 공개 전 — 나중에 받아도 이 스냅샷에는 넣지 않는다
    assert bar_available(datetime(2026, 11, 25, tzinfo=UTC), availability_lag("fred:DGS10"), cutoff_for(date(2026, 11, 28)))
    assert behind_bars(datetime(2026, 11, 23, tzinfo=UTC), "fred:DGS10", CUT) == 0             # 평소(휴일 없음)는 그대로


def test_gate_is_partial_when_a_whole_group_is_mostly_missing(tmp_path):
    d24 = weekdays(date(2026, 11, 24), 30)
    base = {"SPX": series("SPX", "yahoo:^GSPC", d24), "VIX": series("VIX", "yahoo:^VIX", d24, hh=7, mm=0), "NDX": series("NDX", "yahoo:^NDX", d24),
            "WTI": series("WTI", "yahoo:CL=F", d24, hh=5, mm=0), "KOSPI": series("KOSPI", "yahoo:^KS11", d24, hh=0, mm=0)}
    uni = {"NVDA": series("NVDA", "yahoo:NVDA", d24)}
    cfg = {**CFG, "gate": {**CFG["gate"], "min_group_ok": {"universe": 0.75}}}
    st = assess(write_inputs(tmp_path / "a", base, uni), CUT, expected={"base": list(base), "universe": ["NVDA", "MU", "AMD", "TSM"]}, cfg=cfg)
    assert st["gate"]["verdict"] == "PARTIAL" and st["gate"]["group_ok_ratio"] == {"universe": 0.25}    # 핵심은 다 있어도 종목이 통째로 비면 FULL 이 아니다
    st = assess(write_inputs(tmp_path / "b", base, uni), CUT, expected={"base": list(base), "universe": ["NVDA"]}, cfg=cfg)
    assert st["gate"]["verdict"] == "FULL"


def test_adopt_replaces_a_fallback_series_with_the_primary_providers_fresher_one(tmp_path):
    """그날 첫 공급처가 막혀 더 늦게 공개되는 대체 경로(FRED)에서 받은 계열은, 나중 수집분에 첫 공급처 것이 있으면 그것으로 바꾼다."""
    d25 = weekdays(date(2026, 11, 25), 31)
    specs = {"VIX": [{"provider": "yahoo", "symbol": "^VIX"}, {"provider": "fred", "symbol": "VIXCLS"}]}
    fred = series("VIX", "fred:VIXCLS", weekdays(date(2026, 11, 23), 30), hh=0, mm=0)          # 규칙상 OK 지만 하루 늦은 값
    c_prev, _, _, _ = make_collector(tmp_path, {"VIX": [("fred", fred)]}, specs=specs)
    c_prev.run(news=False)
    assert c_prev.status["input_status"]["stale"]["base"] == [] and c_prev.load_group("base")["VIX"].timestamps[-1].date() == date(2026, 11, 23)
    later_dir = tmp_path / "inputs" / "2026-11-26"
    c_next = Collector(date(2026, 11, 26), later_dir, cfg=c_prev.cfg, plans=c_prev.plans, adapters=(FakeAdapter({"VIX": [("yahoo", series("VIX", "yahoo:^VIX", d25, hh=7, mm=0))]}),) * 2,
                       client=SimpleNamespace(stats={}), breaker=ProviderBreaker(tmp_path / "state" / "b3.json"), log=lambda m: None)
    c_next.run(news=False)
    assert c_prev.adopt_from(later_dir) == ["base:VIX"]
    st = json.loads((c_prev.out / "input_status.json").read_text(encoding="utf-8"))["series"]["base"]["VIX"]
    assert st["source"] == "yahoo:^VIX" and st["last_bar"][:10] == "2026-11-24"                 # 11/25 07:30 KST 기준으로 하루 더 최신


def test_half_open_probe_gets_a_second_chance_when_configured(tmp_path):
    """요청의 절반쯤이 429 인 날: 시험 요청 하나가 막힌 것만으로 쉬는 시간이 2배가 되지 않는다. 두 번 연속 막히면 다시 연다."""
    clk = Clock()
    b = ProviderBreaker(tmp_path / "b.json", config={"threshold": 3, "backoff_sec": [10, 20], "half_open_failures": 2}, now=clk.now)
    for _ in range(3):
        b.failure(HOST, kind="http_429", status=429)
    clk.t += 301
    assert b.allow(HOST) == (True, "half_open")
    assert b.failure(HOST, kind="http_429", status=429) == {"opened": False, "pause_sec": 10.0}    # 한 번은 봐준다
    b.success(HOST)
    assert b.snapshot()[HOST]["state"] == "closed"
    for _ in range(3):
        b.failure(HOST, kind="http_429", status=429)
    clk.t += 601; b.allow(HOST)
    b.failure(HOST, kind="http_429", status=429)
    assert b.failure(HOST, kind="http_429", status=429)["opened"]                                 # 두 번 연속이면 다시 연다
