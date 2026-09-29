"""
Anthropic 클라이언트 래퍼.

설계 원칙 (요구 15-7)
---------------------
LLM 은 파이프라인 바깥의 enrichment 다. 이 모듈의 모든 실패는 호출자에게
예외로 새어 나가지 않고 None 또는 LLMFailure 로 돌아온다. 정량 대시보드는
LLM 이 꺼져 있든, 키가 없든, API 가 죽어 있든 똑같이 동작해야 한다.

서킷 브레이커
-------------
연속 실패가 임계를 넘으면 일정 시간 호출을 아예 하지 않는다. API 가 죽었을
때 매 틱마다 8초씩 기다리면 대시보드가 8초씩 늦어진다. 인증 실패는 시간이
지난다고 낫지 않으므로 영구 차단한다.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Literal

logger = logging.getLogger(__name__)

#: 설계서 STEP 7.4. 파이프라인을 8초 넘게 붙잡지 않는다.
DEFAULT_TIMEOUT_SEC = 8.0
#: 연속 실패 임계와 차단 시간.
CIRCUIT_FAILURE_THRESHOLD = 3
CIRCUIT_RESET_SEC = 300.0

#: 추출은 저비용·저지연이 중요하다. 요약은 문장 품질이 중요하다.
#: 두 경로의 effort 를 다르게 둔다 (설계서 STEP 7.5).
EXTRACT_EFFORT = "low"
SUMMARY_EFFORT = "medium"

LLMStatus = Literal["disabled", "ok", "degraded", "failed"]


@dataclass
class LLMFailure:
    """실패를 예외가 아니라 값으로 돌려준다. 호출자가 분기하기 쉽다."""

    reason: str
    kind: Literal["disabled", "unavailable", "auth", "timeout", "rate_limit", "api", "refusal", "parse"]
    permanent: bool = False


@dataclass(frozen=True)
class SearchHit:
    """
    web_search 가 돌려준 결과 하나.

    모델이 쓴 문장이 아니라 **검색 엔진이 돌려준 항목**이다. 제목과 URL 은
    실재하는 페이지의 것이고, 그래서 뉴스 어댑터가 이것만 믿는다.
    """

    title: str
    url: str
    page_age: str | None
    query: str


@dataclass
class _Circuit:
    failures: int = 0
    opened_at: float | None = None
    permanently_open: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record_success(self) -> None:
        with self.lock:
            self.failures = 0
            self.opened_at = None

    def record_failure(self, *, permanent: bool = False) -> None:
        with self.lock:
            if permanent:
                self.permanently_open = True
                return
            self.failures += 1
            if self.failures >= CIRCUIT_FAILURE_THRESHOLD:
                self.opened_at = time.monotonic()

    def is_open(self) -> bool:
        with self.lock:
            if self.permanently_open:
                return True
            if self.opened_at is None:
                return False
            if (time.monotonic() - self.opened_at) >= CIRCUIT_RESET_SEC:
                # 한 번 더 시도해 본다. 실패하면 다시 열린다.
                self.opened_at = None
                self.failures = 0
                return False
            return True

    def reset(self) -> None:
        with self.lock:
            self.failures = 0
            self.opened_at = None
            self.permanently_open = False


def _status_reason(exc: Any) -> str:
    """오류 응답의 message 만 뽑는다. 없으면 예외 문자열 그대로."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
    return str(exc)


class LLMClient:
    """
    구조화 출력 전용 얇은 래퍼.

    SDK 를 직접 쓰지 않고 한 겹 두는 이유는 두 가지다. 실패를 값으로 바꾸는
    지점을 한 곳에 모으고, 테스트에서 네트워크 없이 갈아끼울 수 있게 한다.
    """

    def __init__(
        self,
        *,
        enabled: bool = False,
        model: str = "claude-opus-5",
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
        max_retries: int = 1,
        api_key: str | None = None,
        search_timeout_sec: float = 90.0,
    ) -> None:
        self.enabled = enabled
        self.model = model
        self.search_timeout_sec = search_timeout_sec
        #: None 이면 SDK 가 환경변수·프로필에서 찾는다. 값은 절대 로그에 남기지 않는다.
        self._api_key = api_key
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self._circuit = _Circuit()
        self._client: Any = None
        self._client_error: str | None = None

    # ── 가용성 ────────────────────────────────────────────
    @property
    def status(self) -> LLMStatus:
        if not self.enabled:
            return "disabled"
        if self._circuit.permanently_open:
            return "failed"
        if self._circuit.is_open() or self._circuit.failures:
            return "degraded"
        return "ok"

    def available(self) -> bool:
        return self.enabled and not self._circuit.is_open()

    @property
    def last_error(self) -> str | None:
        """마지막으로 확인된 실패 사유. 화면에 이유를 계속 띄우기 위한 것이다."""
        return self._client_error

    def _ensure_client(self) -> Any | LLMFailure:
        if self._client is not None:
            return self._client
        try:
            import anthropic  # 지연 import: 패키지가 없어도 정량 경로는 돈다
        except ImportError:
            self._client_error = "anthropic 패키지가 설치되어 있지 않다"
            self._circuit.record_failure(permanent=True)
            return LLMFailure(self._client_error, "unavailable", permanent=True)

        try:
            # 키를 코드에 넣지 않는다. 설정으로 받은 것이 있으면 그것을, 없으면
            # SDK 가 환경변수와 프로필에서 찾는다.
            self._client = anthropic.Anthropic(
                api_key=self._api_key or None,
                timeout=self.timeout_sec,
                max_retries=self.max_retries,
            )
        except Exception as exc:  # 구성 오류
            self._client_error = str(exc)
            self._circuit.record_failure(permanent=True)
            return LLMFailure(self._client_error, "unavailable", permanent=True)
        return self._client

    # ── 호출 ──────────────────────────────────────────────
    def structured(
        self,
        *,
        system: str,
        user: str,
        schema: dict,
        effort: str = EXTRACT_EFFORT,
        max_tokens: int = 8000,
    ) -> dict | LLMFailure:
        """
        JSON 스키마에 맞는 응답 하나를 받는다.

        output_config.format 이 형식을 보장하므로 프롬프트로 "JSON 으로
        답하라" 고 빌지 않는다. 그래도 파싱은 감싸 둔다 — 형식이 맞아도
        내용이 스키마와 어긋날 수 있고, 그 검증은 ai/validation.py 가 한다.
        """
        if not self.enabled:
            return LLMFailure("LLM 이 비활성화되어 있다", "disabled")
        if self._circuit.is_open():
            return LLMFailure(
                self._client_error or "연속 실패로 호출을 잠시 멈춘 상태다",
                "unavailable",
                permanent=self._circuit.permanently_open,
            )

        client = self._ensure_client()
        if isinstance(client, LLMFailure):
            return client

        response = self._invoke(
            lambda: client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=[
                    # 스키마와 지침은 매 호출 동일하다. 캐시 경계를 여기 둔다.
                    {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
                ],
                messages=[{"role": "user", "content": user}],
                output_config={
                    "effort": effort,
                    "format": {"type": "json_schema", "schema": schema},
                },
            )
        )
        if isinstance(response, LLMFailure):
            return response

        if getattr(response, "stop_reason", None) == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            self._circuit.record_success()  # 모델이 답한 것이다. 장애가 아니다.
            return LLMFailure(f"모델이 응답을 거절했다 (category={category})", "refusal")

        text = next(
            (b.text for b in response.content if getattr(b, "type", None) == "text"),
            None,
        )
        if not text:
            self._circuit.record_failure()
            return LLMFailure("응답에 텍스트 블록이 없다", "parse")

        import json

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            self._circuit.record_failure()
            return LLMFailure(f"JSON 파싱 실패: {exc}", "parse")

        if not isinstance(data, dict):
            self._circuit.record_failure()
            return LLMFailure("최상위가 객체가 아니다", "parse")

        self._circuit.record_success()
        return data

    def _invoke(self, call: Any) -> Any | LLMFailure:
        """
        SDK 호출 하나를 실행하고 실패를 값으로 바꾼다.

        structured() 와 search_news() 가 같은 실패 분류를 써야 서킷 브레이커가
        일관되게 동작한다. 인증 실패는 어느 경로에서 나든 영구 차단이다.
        """
        import anthropic

        try:
            return call()
        except anthropic.AuthenticationError as exc:
            # 시간이 지난다고 낫지 않는다. 영구 차단한다.
            self._circuit.record_failure(permanent=True)
            self._client_error = "인증 실패. ANTHROPIC_API_KEY 를 확인하라."
            return LLMFailure(str(exc), "auth", permanent=True)
        except anthropic.PermissionDeniedError as exc:
            self._circuit.record_failure(permanent=True)
            return LLMFailure(str(exc), "auth", permanent=True)
        except anthropic.RateLimitError as exc:
            self._circuit.record_failure()
            self._client_error = f"요청 한도 초과: {exc}"
            return LLMFailure(str(exc), "rate_limit")
        except anthropic.APITimeoutError as exc:
            self._circuit.record_failure()
            self._client_error = f"응답 시간 초과: {exc}"
            return LLMFailure(str(exc), "timeout")
        except anthropic.APIConnectionError as exc:
            self._circuit.record_failure()
            self._client_error = f"연결 실패: {exc}"
            return LLMFailure(str(exc), "api")
        except anthropic.APIStatusError as exc:
            self._circuit.record_failure()
            # 400 "credit balance is too low" 처럼 키는 맞는데 계정이 막힌 경우가
            # 여기로 온다. 이유가 화면에 나가야 사용자가 조치한다.
            self._client_error = f"API {exc.status_code}: {_status_reason(exc)}"
            return LLMFailure(f"{exc.status_code}: {exc}", "api")
        except TypeError as exc:
            # SDK 는 자격 증명을 찾지 못하면 요청을 만들 때 TypeError 를 낸다
            # ("Could not resolve authentication method"). 예외 종류만 보면
            # 버그처럼 보이지만 사실은 설정 문제이고, 시간이 지난다고 낫지
            # 않는다. 영구 차단해 매 틱 재시도하지 않게 한다.
            if "authentication" in str(exc).lower():
                self._circuit.record_failure(permanent=True)
                self._client_error = (
                    "자격 증명을 찾을 수 없다. ANTHROPIC_API_KEY 를 설정하거나 "
                    "`ant auth login` 으로 프로필을 만들어라."
                )
                logger.warning("LLM 사용 불가: %s", self._client_error)
                return LLMFailure(self._client_error, "auth", permanent=True)
            logger.exception("LLM 호출 중 예상치 못한 타입 오류")
            self._circuit.record_failure()
            return LLMFailure(str(exc), "api")
        except Exception as exc:  # 예상 못한 경로도 파이프라인을 막지 않는다
            logger.exception("LLM 호출 중 예상치 못한 오류")
            self._circuit.record_failure()
            return LLMFailure(str(exc), "api")

    def search_news(
        self,
        *,
        system: str,
        user: str,
        max_uses: int = 4,
        max_tokens: int = 4000,
    ) -> list[SearchHit] | LLMFailure:
        """
        web_search 서버 도구를 돌리고 **검색 결과 블록만** 모아 돌려준다.

        모델의 답변 텍스트는 읽지 않는다. 검색 결과는 검색 엔진이 돌려준
        실재 페이지이고, 텍스트는 모델이 쓴 것이다. 뉴스 어댑터가 믿어도
        되는 것은 앞쪽뿐이다. 존재하지 않는 기사가 화면에 오르는 경로를
        구조로 막는다 (요구 15-11).
        """
        if not self.enabled:
            return LLMFailure("LLM 이 비활성화되어 있다", "disabled")
        if self._circuit.is_open():
            return LLMFailure(
                self._client_error or "연속 실패로 호출을 잠시 멈춘 상태다",
                "unavailable",
                permanent=self._circuit.permanently_open,
            )
        client = self._ensure_client()
        if isinstance(client, LLMFailure):
            return client

        response = self._invoke(
            lambda: client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=[
                    {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
                ],
                messages=[{"role": "user", "content": user}],
                tools=[
                    {"type": "web_search_20260209", "name": "web_search", "max_uses": max_uses}
                ],
                output_config={"effort": EXTRACT_EFFORT},
                # 검색은 서버가 여러 번 돌리고 돌아온다. 추출용 8초로는 항상 끊긴다.
                timeout=self.search_timeout_sec,
            )
        )
        if isinstance(response, LLMFailure):
            return response

        hits: list[SearchHit] = []
        current_query = ""
        for block in getattr(response, "content", None) or []:
            kind = getattr(block, "type", None)
            if kind == "server_tool_use":
                inp = getattr(block, "input", None) or {}
                current_query = str(inp.get("query", "") if isinstance(inp, dict) else "")
                continue
            if kind != "web_search_tool_result":
                continue
            content = getattr(block, "content", None)
            # 실패한 검색은 content 가 목록이 아니라 오류 객체다. 건너뛴다.
            if not isinstance(content, list):
                continue
            for item in content:
                if getattr(item, "type", None) != "web_search_result":
                    continue
                url = str(getattr(item, "url", "") or "").strip()
                title = str(getattr(item, "title", "") or "").strip()
                if not url or not title:
                    continue
                age = getattr(item, "page_age", None)
                hits.append(
                    SearchHit(
                        title=title,
                        url=url,
                        page_age=str(age) if age else None,
                        query=current_query,
                    )
                )

        # 검색이 한 번도 돌지 않았다면 모델이 도구를 안 쓴 것이다. 장애는
        # 아니지만 결과도 아니다 — 호출자가 "0건" 으로 다룬다.
        self._circuit.record_success()
        return hits

    def search_structured(
        self,
        *,
        system: str,
        user: str,
        schema: dict,
        max_uses: int = 3,
        max_tokens: int = 4000,
    ) -> tuple[dict, list[SearchHit]] | LLMFailure:
        """
        web_search 를 돌린 뒤 JSON 스키마 응답을 받는다. (응답 dict, 검색 결과 목록) 을 함께 돌려주므로
        호출자가 응답의 URL 이 실제 검색 결과 안에 있는지 대조할 수 있다 — 애널리스트 코멘트처럼
        attribution 이 붙는 정보는 그 대조를 통과해야만 쓴다.
        """
        if not self.enabled:
            return LLMFailure("LLM 이 비활성화되어 있다", "disabled")
        if self._circuit.is_open():
            return LLMFailure(self._client_error or "연속 실패로 호출을 잠시 멈춘 상태다", "unavailable", permanent=self._circuit.permanently_open)
        client = self._ensure_client()
        if isinstance(client, LLMFailure):
            return client
        response = self._invoke(
            lambda: client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
                tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": max_uses}],
                output_config={"effort": EXTRACT_EFFORT, "format": {"type": "json_schema", "schema": schema}},
                timeout=self.search_timeout_sec,
            )
        )
        if isinstance(response, LLMFailure):
            return response
        if getattr(response, "stop_reason", None) == "refusal":
            self._circuit.record_success()
            return LLMFailure("모델이 응답을 거절했다", "refusal")
        hits: list[SearchHit] = []
        current_query = ""
        text = None
        for block in getattr(response, "content", None) or []:
            kind = getattr(block, "type", None)
            if kind == "server_tool_use":
                inp = getattr(block, "input", None) or {}
                current_query = str(inp.get("query", "") if isinstance(inp, dict) else "")
            elif kind == "web_search_tool_result":
                content = getattr(block, "content", None)
                if isinstance(content, list):
                    for item in content:
                        if getattr(item, "type", None) == "web_search_result":
                            url = str(getattr(item, "url", "") or "").strip(); title = str(getattr(item, "title", "") or "").strip()
                            if url and title:
                                age = getattr(item, "page_age", None)
                                hits.append(SearchHit(title=title, url=url, page_age=str(age) if age else None, query=current_query))
            elif kind == "text":
                text = getattr(block, "text", None)
        if not text:
            self._circuit.record_failure()
            return LLMFailure("응답에 텍스트 블록이 없다", "parse")
        import json

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            self._circuit.record_failure()
            return LLMFailure(f"JSON 파싱 실패: {exc}", "parse")
        if not isinstance(data, dict):
            self._circuit.record_failure()
            return LLMFailure("응답이 객체가 아니다", "parse")
        self._circuit.record_success()
        return data, hits

    def reset(self) -> None:
        self._circuit.reset()
        self._client = None
        self._client_error = None


@lru_cache(maxsize=8)
def _cached_client(
    enabled: bool, model: str, timeout_sec: float, api_key: str | None, search_timeout_sec: float
) -> LLMClient:
    return LLMClient(
        enabled=enabled,
        model=model,
        timeout_sec=timeout_sec,
        api_key=api_key,
        search_timeout_sec=search_timeout_sec,
    )


def build_client(settings: Any) -> LLMClient:
    """
    설정에서 클라이언트를 만든다. 모델은 환경변수로 덮어쓸 수 있다.

    같은 설정이면 같은 인스턴스를 돌려준다. 서킷 브레이커 상태가 틱을
    넘어 유지되어야 하기 때문이다 — 매 틱 새 클라이언트를 만들면 인증
    실패를 매번 다시 겪는다.
    """
    return _cached_client(
        bool(getattr(settings, "llm_enabled", False)),
        os.getenv("MARKETPULSE_LLM_MODEL", "claude-opus-5"),
        float(getattr(settings, "llm_timeout_sec", DEFAULT_TIMEOUT_SEC)),
        getattr(settings, "anthropic_api_key", None) or None,
        float(getattr(settings, "llm_search_timeout_sec", 90.0)),
    )


def reset_client_cache() -> None:
    """테스트에서 서킷 상태를 초기화할 때 쓴다."""
    for client in list(_cached_client.cache_parameters() and []):  # pragma: no cover
        client.reset()
    _cached_client.cache_clear()
