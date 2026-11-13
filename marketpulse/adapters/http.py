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

    def __init__(self, message: str, *, kind: str = "error", permanent: bool = False):
        super().__init__(message)
        self.kind = kind
        #: True 면 재시도해도 소용없다. 차단·인증·404 가 여기 해당한다.
        self.permanent = permanent


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
                last = FetchError(
                    f"HTTP {exc.code} {exc.reason}", kind=f"http_{exc.code}", permanent=permanent
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
