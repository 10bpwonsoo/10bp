"""
LIVE 어댑터의 공통 HTTP 계층.

바깥 세상은 자주 죽는다. 죽는 방식도 제각각이다 — 타임아웃, 429, 5xx,
프록시의 403, TLS 실패, 그리고 200 을 주면서 HTML 을 주는 경우. 그때마다
대시보드가 같이 죽으면 안 된다. 엔진은 순수 함수이므로 여기서 막으면 된다.

LLM 클라이언트(ai/client.py)와 같은 구조다. 호스트마다 회로 차단기를 두고,
연속 실패가 임계를 넘으면 일정 시간 호출을 멈춘다. 죽은 공급자를 매 틱
두드리는 것은 지연만 늘린다.

**프록시를 절대 끄지 않는다.** HTTPS_PROXY 가 걸린 환경에서는 그것을 통해
나가고, 막혀 있으면 막혔다고 보고한다. 우회하지 않는다.
"""

from __future__ import annotations

import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SEC = 8.0
DEFAULT_RETRIES = 2
RETRY_BACKOFF_SEC = 0.6
CIRCUIT_FAILURE_THRESHOLD = 3
CIRCUIT_RESET_SEC = 180.0

#: 공급자 다수가 기본 urllib UA 를 거른다. 정직한 식별자를 보낸다.
USER_AGENT = "MarketPulseAI/0.1 (+https://github.com/10bpwonsoo/10bp)"


class FetchError(RuntimeError):
    """HTTP 요청 실패. 호출자는 다음 공급자로 넘어간다."""

    def __init__(self, message: str, *, kind: str = "error", permanent: bool = False,
                 status: int | None = None, retry_after: str | None = None, body: str | None = None):
        super().__init__(message)
        self.kind = kind
        #: True 면 재시도해도 소용없다. 차단·인증·404 가 여기 해당한다.
        self.permanent = permanent
        #: HTTP 오류면 응답 그대로 — 상태 코드 · Retry-After 헤더 원문(없으면 None) · 본문 앞부분.
        #: 429 를 '누가 왜' 냈는지(공급자 엣지인지 프록시인지, 쉬라는 시간이 있는지) 판단하는 근거다. 추측하지 않는다.
        self.status = status
        self.retry_after = retry_after
        self.body = body


@dataclass
class _Circuit:
    failures: int = 0
    opened_at: float | None = None
    last_error: str | None = None

    def open(self) -> bool:
        if self.opened_at is None:
            return False
        if time.monotonic() - self.opened_at < CIRCUIT_RESET_SEC:
            return True
        # 창이 지났다. 한 번 더 기회를 준다.
        self.failures = 0
        self.opened_at = None
        return False


@dataclass
class HttpClient:
    """호스트별 회로 차단기를 가진 최소 HTTP 클라이언트."""

    timeout_sec: float = DEFAULT_TIMEOUT_SEC
    retries: int = DEFAULT_RETRIES
    _circuits: dict[str, _Circuit] = field(default_factory=dict, repr=False)

    def _circuit(self, host: str) -> _Circuit:
        return self._circuits.setdefault(host, _Circuit())

    def status(self) -> dict[str, str]:
        """호스트별 상태. /api/v1/health 와 probe CLI 가 읽는다."""
        out: dict[str, str] = {}
        for host, c in self._circuits.items():
            if c.open():
                out[host] = f"차단 ({c.last_error})"
            elif c.failures:
                out[host] = f"불안정 {c.failures}회 ({c.last_error})"
            else:
                out[host] = "정상"
        return out

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, str | int | float] | None = None,
        headers: Mapping[str, str] | None = None,
        data: Mapping[str, str] | None = None,
    ) -> bytes:
        """
        GET (data 를 주면 POST). 실패하면 FetchError 를 던진다.

        조용히 빈 값을 돌려주지 않는다. 호출자가 실패를 알아야 다음
        공급자로 넘어가고, 그것도 실패하면 missing 으로 남는다.
        """
        if params:
            url = f"{url}?{urlencode(params)}"
        host = url.split("/")[2] if "//" in url else url

        circuit = self._circuit(host)
        if circuit.open():
            raise FetchError(
                f"{host} 회로 차단 중 — 직전 오류: {circuit.last_error}",
                kind="circuit",
                permanent=False,
            )

        body = urlencode(data).encode() if data else None
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "*/*",
                **({"Content-Type": "application/x-www-form-urlencoded"} if body else {}),
                **(headers or {}),
            },
        )

        last: FetchError | None = None
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_sec) as resp:
                    payload = resp.read()
                circuit.failures = 0
                circuit.opened_at = None
                circuit.last_error = None
                return payload
            except urllib.error.HTTPError as exc:
                permanent = exc.code in (401, 403, 404, 451)
                try:
                    snippet = exc.read(200).decode("utf-8", errors="replace").strip()
                except Exception:  # noqa: BLE001 — 본문을 못 읽어도 오류 처리는 계속한다
                    snippet = None
                last = FetchError(
                    f"HTTP {exc.code} {exc.reason}", kind=f"http_{exc.code}", permanent=permanent,
                    status=exc.code, retry_after=(exc.headers.get("Retry-After") if exc.headers else None), body=snippet,
                )
            except urllib.error.URLError as exc:
                reason = str(getattr(exc, "reason", exc))
                # 프록시가 CONNECT 를 막으면 여기로 온다. 차단은 재시도해도
                # 똑같다 — 사용자에게 네트워크 정책 문제임을 알려야 한다.
                permanent = "403" in reason or "forbidden" in reason.lower()
                last = FetchError(f"연결 실패: {reason}", kind="network", permanent=permanent)
            except TimeoutError:
                last = FetchError(f"{self.timeout_sec:.0f}초 안에 응답 없음", kind="timeout")
            except Exception as exc:  # noqa: BLE001 — 어떤 실패도 대시보드를 막지 않는다
                last = FetchError(f"알 수 없는 오류: {exc}", kind="unknown")

            if last.permanent or attempt >= self.retries:
                break
            time.sleep(RETRY_BACKOFF_SEC * (attempt + 1))

        assert last is not None
        circuit.failures += 1
        circuit.last_error = str(last)
        if circuit.failures >= CIRCUIT_FAILURE_THRESHOLD:
            circuit.opened_at = time.monotonic()
            logger.warning("%s 회로 차단 — %s", host, last)
        raise last


@dataclass
class PacedHttpClient(HttpClient):
    """
    일괄 수집(Daily Snapshot 입력) 전용 클라이언트 — 2026-11-20.

    화면이 쓰는 HttpClient 는 죽은 공급자를 빨리 포기해야 한다. 일괄 수집은 반대다:
    시간이 조금 더 걸려도 계열을 빠뜨리지 않는 쪽이 낫다. 그래서 셋을 다르게 한다.

      1. 같은 요청은 한 번만 보낸다. 응답 원문을 그대로 다시 쓴다(값을 만들거나 고치지 않는다).
         `superset_param`(Yahoo 의 period1) 만 다른 요청은, 더 이른 시작점으로 이미 받은
         응답이 있으면 그것을 쓴다 — 더 긴 기간의 응답은 짧은 기간을 포함한다.
      2. 같은 호스트 요청 사이에 처음부터 간격을 둔다(몰아 보내다 429 로 막히지 않게).
      3. 429 를 받으면 그 호스트를 쉬었다가 같은 요청을 다시 보낸다. 회로를 열어 남은 계열을
         전부 실패시키지 않는다. 쉬는 시간은 45 → 90 → 180초로 늘고 그 뒤로는 마지막 값을 되풀이한다 —
         예산이 남아 있는 동안에는 그 요청을 포기하지 않는다(2026-11-24: 공급자가 통째로 막힌 아침에
         계열마다 세 번 쉬고 넘어가느라 예산만 쓰고 아무것도 못 받았다).
      4. 쉬는 시간의 합이 `wait_budget_sec` 를 넘으면 그 호스트는 '막힘' 으로 표시하고, 남은 요청은
         보내지도 기다리지도 않고 바로 실패로 남긴다(결측 — 0 이나 전날 값으로 채우지 않는다).
         수집이 빨리 끝나야 호출한 쪽이 나중에 다시 시도할 수 있다.
    """

    retries: int = 0  # 재시도는 아래에서 간격을 두고 한다 — 0.6초 뒤 재시도는 429 를 키울 뿐이다
    min_gap_sec: float = 1.5
    max_gap_sec: float = 12.0
    cooldowns_sec: tuple[float, ...] = (45.0, 90.0, 180.0)
    wait_budget_sec: float = 1200.0
    superset_param: str = "period1"
    _cache: dict[tuple, tuple[float | None, bytes]] = field(default_factory=dict, repr=False)
    _last_at: dict[str, float] = field(default_factory=dict, repr=False)
    _gap: dict[str, float] = field(default_factory=dict, repr=False)
    _waited: float = field(default=0.0, repr=False)
    _blocked: dict[str, str] = field(default_factory=dict, repr=False)
    stats: dict[str, int] = field(default_factory=lambda: {"requests": 0, "reused": 0, "throttled": 0, "gave_up": 0, "skipped": 0})
    _sleep = staticmethod(time.sleep)

    def _key(self, url: str, params: Mapping[str, str | int | float] | None) -> tuple[tuple, float | None]:
        rest = tuple(sorted((k, str(v)) for k, v in (params or {}).items() if k != self.superset_param))
        start = (params or {}).get(self.superset_param)
        return (url, rest), (float(start) if start is not None else None)

    def get(self, url, *, params=None, headers=None, data=None) -> bytes:  # type: ignore[override]
        if data:  # POST 는 캐시하지 않는다
            return super().get(url, params=params, headers=headers, data=data)
        key, start = self._key(url, params)
        hit = self._cache.get(key)
        if hit is not None and (start is None or (hit[0] is not None and hit[0] <= start)):
            self.stats["reused"] += 1
            return hit[1]

        host = url.split("/")[2] if "//" in url else url
        if host in self._blocked:  # 예산을 다 쓴 호스트 — 보내지도 기다리지도 않는다
            self.stats["skipped"] += 1
            raise FetchError(f"{host} 수집 대기 예산 소진 — 건너뜀({self._blocked[host]})", kind="http_429", permanent=False)
        attempt = 0
        while True:
            gap = self._gap.get(host, self.min_gap_sec)
            wait = self._last_at.get(host, -1e9) + gap - time.monotonic()
            if wait > 0:
                self._sleep(wait)
            self.stats["requests"] += 1
            try:
                payload = super().get(url, params=params, headers=headers)
            except FetchError as exc:
                self._last_at[host] = time.monotonic()
                if exc.kind != "http_429":
                    raise
                self.stats["throttled"] += 1
                cooldown = self.cooldowns_sec[min(attempt, len(self.cooldowns_sec) - 1)] if self.cooldowns_sec else None
                attempt += 1
                if cooldown is None or self._waited + cooldown > self.wait_budget_sec:
                    self.stats["gave_up"] += 1
                    self._blocked[host] = str(exc)
                    logger.warning("%s 429 — 대기 예산(%.0f초)을 다 썼다. 이 호스트의 남은 요청은 건너뛴다", host, self.wait_budget_sec)
                    raise
                # 막혔다 — 간격을 늘리고 쉬었다가 같은 요청을 다시. 회로는 닫아 둔다(남은 계열을 살린다).
                self._gap[host] = min(self.max_gap_sec, gap * 2)
                logger.warning("%s 429 — %.0f초 쉬고 다시 (요청 간격 %.1f초)", host, cooldown, self._gap[host])
                self._sleep(cooldown)
                self._waited += cooldown
                circuit = self._circuit(host)
                circuit.failures = 0
                circuit.opened_at = None
                continue
            self._last_at[host] = time.monotonic()
            self._cache[key] = (start, payload)
            return payload


@dataclass
class BreakerHttpClient(PacedHttpClient):
    """
    수집기(marketpulse.collector) 전용 — PacedHttpClient 의 중복 제거 · 요청 간격은 그대로 쓰고, 429 대응만 바꾼다 (2026-11-25).

    PacedHttpClient 는 429 를 받으면 45 → 90 → 180초를 **그 자리에서 자면서** 같은 요청을 되풀이했다. 공급처가 통째로
    막힌 아침에는 20분 예산을 다 자고도 받은 것이 없었고, 그동안 다른 공급처로도 넘어가지 못했다. 여기서는

      · 429 · 503 · 연결 실패를 파일에 남는 ProviderBreaker 에 기록한다(공급처 전체 · 재시작 뒤에도 유지).
      · 공급처가 Retry-After 를 주면 그 시간만큼 회로를 연다. 없으면 연속 실패마다 짧게 쉬고(기본 10 · 20초) 임계(3)에
        닿으면 회로를 연다 — 쉬는 시간은 5분에서 2배씩 늘어난다.
      · 회로가 열리면 **자지 않는다**. 곧바로 FetchError(kind="circuit_open") 를 던져 호출자가 다음 공급처로 넘어가게 한다.
    """

    breaker: object | None = None  # ProviderBreaker — 없으면 PacedHttpClient 와 같은 동작

    def get(self, url, *, params=None, headers=None, data=None) -> bytes:  # type: ignore[override]
        if self.breaker is None:
            return super().get(url, params=params, headers=headers, data=data)
        host = url.split("/")[2] if "//" in url else url
        if data:  # POST(KRX OTP) — 캐시하지 않지만 회로는 지킨다
            ok, why = self.breaker.allow(host)
            if not ok:
                self.stats["skipped"] += 1
                raise FetchError(f"{host} {why}", kind="circuit_open")
            return HttpClient.get(self, url, params=params, headers=headers, data=data)
        key, start = self._key(url, params)
        hit = self._cache.get(key)
        if hit is not None and (start is None or (hit[0] is not None and hit[0] <= start)):
            self.stats["reused"] += 1
            return hit[1]
        while True:
            ok, why = self.breaker.allow(host)
            if not ok:
                self.stats["skipped"] += 1
                raise FetchError(f"{host} {why}", kind="circuit_open")
            wait = max(self._last_at.get(host, -1e9) + self._gap.get(host, self.min_gap_sec) - time.monotonic(), self.breaker.pause_remaining(host))
            if wait > 0:
                self._sleep(wait)
            self.stats["requests"] += 1
            try:
                payload = HttpClient.get(self, url, params=params, headers=headers)
            except FetchError as exc:
                self._last_at[host] = time.monotonic()
                verdict = self.breaker.failure(host, kind=exc.kind, status=exc.status, retry_after=exc.retry_after, body=exc.body, message=str(exc))
                if verdict.get("pause_sec") is None and not verdict.get("opened"):
                    raise  # 404 · 403 · 파싱 오류 — 공급처가 아니라 그 요청의 문제다
                self.stats["throttled"] += 1
                circuit = self._circuit(host)  # 메모리 회로는 닫아 둔다 — 판단은 파일에 남는 breaker 하나가 한다
                circuit.failures = 0
                circuit.opened_at = None
                if verdict["opened"]:
                    self.stats["gave_up"] += 1
                    logger.warning("%s %s — 회로를 열었다(%s 까지, %s)", host, exc, verdict["open_until"], verdict["basis"])
                    raise FetchError(f"{host} {exc} — 회로 열림({verdict['open_until']} 까지)", kind="circuit_open",
                                     status=exc.status, retry_after=exc.retry_after, body=exc.body) from exc
                logger.warning("%s %s — 공급처 전체 %.0f초 쉬고 다시", host, exc, verdict["pause_sec"])
                continue  # 쉬는 시간은 다음 바퀴의 pause_remaining 이 지킨다(파일에 남아 재시작 뒤에도)
            self._last_at[host] = time.monotonic()
            self.breaker.success(host)
            self._cache[key] = (start, payload)
            return payload
