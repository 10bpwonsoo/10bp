"""
PacedHttpClient — Daily Snapshot 입력 수집 전용 클라이언트(2026-11-20).

같은 요청은 한 번만 · 처음부터 간격 · 429 면 쉬었다가 이어 받기. 값은 공급자 응답 그대로다(재사용도 원문 그대로).
네트워크와 실제 sleep 은 쓰지 않는다.
"""

from __future__ import annotations

import io
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import pytest

from marketpulse.adapters import http as H
from marketpulse.adapters.http import FetchError, PacedHttpClient
from marketpulse.adapters.market.providers import YahooProvider

FIXTURES = Path(__file__).resolve().parent / "fixtures"
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/"


class Net:
    """urlopen 대역: URL 조각 → 응답 목록(순서대로 소비, 마지막 것은 계속). 429 는 예외로."""

    def __init__(self, script: dict[str, list]):
        self.script = {k: list(v) for k, v in script.items()}
        self.urls: list[str] = []

    def __call__(self, request, timeout=None):
        url = request.full_url
        self.urls.append(url)
        for key, seq in self.script.items():
            if key in url:
                item = seq.pop(0) if len(seq) > 1 else seq[0]
                if isinstance(item, int):
                    raise urllib.error.HTTPError(url, item, "Too Many Requests" if item == 429 else "Error", {}, io.BytesIO(b""))
                return io.BytesIO(item)
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(b""))


@pytest.fixture
def paced(monkeypatch):
    def make(script, **kw):
        net = Net(script)
        monkeypatch.setattr(H.urllib.request, "urlopen", net)
        c = PacedHttpClient(**kw)
        c.sleeps = []
        c._sleep = c.sleeps.append  # 실제로 자지 않는다
        return c, net
    return make


def test_same_request_is_sent_once_and_reused_verbatim(paced):
    c, net = paced({"/NVDA": [b"payload-1", b"payload-2"]})
    a = c.get(YAHOO + "NVDA", params={"period1": 100, "period2": 900, "interval": "1d"})
    b = c.get(YAHOO + "NVDA", params={"period1": 100, "period2": 900, "interval": "1d"})
    assert a == b == b"payload-1" and len(net.urls) == 1
    assert c.stats["requests"] == 1 and c.stats["reused"] == 1


def test_longer_range_response_covers_a_shorter_request_but_not_the_reverse(paced):
    c, net = paced({"/NVDA": [b"long"], "/AMD": [b"short", b"long"]})
    assert c.get(YAHOO + "NVDA", params={"period1": 100, "period2": 900}) == b"long"
    assert c.get(YAHOO + "NVDA", params={"period1": 400, "period2": 900}) == b"long"   # 더 늦은 시작 → 재사용
    assert len(net.urls) == 1
    assert c.get(YAHOO + "AMD", params={"period1": 400, "period2": 900}) == b"short"
    assert c.get(YAHOO + "AMD", params={"period1": 100, "period2": 900}) == b"long"    # 더 이른 시작 → 새로 받는다
    assert c.get(YAHOO + "AMD", params={"period1": 100, "period2": 901}) == b"long" and len(net.urls) == 4  # period2 가 다르면 다른 요청


def test_requests_to_one_host_are_spaced_from_the_start(paced):
    c, net = paced({"/A": [b"a"], "/B": [b"b"], "other.test": [b"o"]}, min_gap_sec=2.0)
    c.get(YAHOO + "A")
    assert c.sleeps == []                       # 첫 요청은 기다리지 않는다
    c.get(YAHOO + "B")
    assert len(c.sleeps) == 1 and 1.9 < c.sleeps[0] <= 2.0
    c.get("https://other.test/x")               # 다른 호스트는 따로 센다
    c.get(YAHOO + "A")                          # 재사용은 기다리지 않는다
    assert len(c.sleeps) == 1


def test_429_cools_down_then_resumes_without_opening_the_circuit(paced):
    c, net = paced({"/A": [429, b"a"], "/B": [b"b"]}, min_gap_sec=1.0, cooldowns_sec=(30.0, 60.0))
    assert c.get(YAHOO + "A") == b"a"
    assert 30.0 in c.sleeps and c.stats["throttled"] == 1 and c.stats["gave_up"] == 0
    assert c._gap["query1.finance.yahoo.com"] == 2.0       # 막힌 뒤에는 간격을 늘린다
    assert c.get(YAHOO + "B") == b"b"                       # 남은 계열은 이어서 받는다(회로 차단 없음)
    assert "차단" not in c.status().get("query1.finance.yahoo.com", "")


def test_gives_up_when_the_wait_budget_is_spent_and_never_caches_a_failure(paced):
    c, net = paced({"/A": [429], "/B": [b"b"], "other.test": [b"o"]}, cooldowns_sec=(30.0, 60.0), wait_budget_sec=40.0)
    with pytest.raises(FetchError) as exc:
        c.get(YAHOO + "A")
    assert exc.value.kind == "http_429" and c.stats["gave_up"] == 1
    assert [s for s in c.sleeps if s >= 30.0] == [30.0]     # 60초는 예산(40초)을 넘어 기다리지 않는다
    assert c._cache == {}                                    # 실패는 값이 아니다 — 결측으로 남는다
    # 예산을 다 쓴 호스트의 남은 요청은 보내지도 기다리지도 않고 바로 실패한다(수집이 빨리 끝나야 나중에 다시 시도할 수 있다)
    sent, slept = len(net.urls), len(c.sleeps)
    with pytest.raises(FetchError) as exc2:
        c.get(YAHOO + "B")
    assert exc2.value.kind == "http_429" and "건너뜀" in str(exc2.value)
    assert len(net.urls) == sent and len(c.sleeps) == slept and c.stats["skipped"] == 1
    assert c.get("https://other.test/x") == b"o"              # 다른 호스트는 그대로 받는다


def test_keeps_waiting_on_one_request_while_budget_remains(paced):
    """공급자가 통째로 막힌 동안에는 그 요청을 포기하고 다음으로 넘어가지 않는다 — 마지막 쉬는 시간을 되풀이한다(2026-11-24)."""
    c, net = paced({"/A": [429, 429, 429, 429, 429, b"a"]}, cooldowns_sec=(30.0, 60.0), wait_budget_sec=1000.0)
    assert c.get(YAHOO + "A") == b"a"
    assert [s for s in c.sleeps if s >= 30.0] == [30.0, 60.0, 60.0, 60.0, 60.0]
    assert c.stats["throttled"] == 5 and c.stats["gave_up"] == 0 and len(net.urls) == 6


def test_other_errors_are_not_retried_here(paced):
    c, net = paced({"/A": [404]})
    with pytest.raises(FetchError) as exc:
        c.get(YAHOO + "A")
    assert exc.value.kind == "http_404" and len(net.urls) == 1 and c.sleeps == []


def test_market_and_alt_fetches_of_one_symbol_share_a_single_request(paced):
    """기본 묶음(fetch)과 종목 묶음(fetch_with_volume), AI 바스켓(120봉)이 같은 심볼을 따로 받던 것 — 이제 한 번."""
    raw = (FIXTURES / "yahoo_spx.json").read_bytes()
    c, net = paced({"/%5EGSPC": [raw], "/^GSPC": [raw]})
    y = YahooProvider(c)
    as_of = datetime(2026, 11, 20, tzinfo=timezone.utc)
    spec = {"provider": "yahoo", "symbol": "^GSPC"}
    a = y.fetch(spec, bars=300, as_of=as_of)
    b, _vol = y.fetch_with_volume(spec, bars=300, as_of=as_of)
    short, _ = y.fetch_with_volume(spec, bars=120, as_of=as_of)
    assert len(net.urls) == 1 and c.stats["reused"] == 2
    assert a == b == short == YahooProvider.parse(raw, bars=300, as_of=as_of)   # 값은 응답 그대로
