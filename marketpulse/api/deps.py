"""API 의존성. 스냅샷 생성과 짧은 TTL 캐시."""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import HTTPException, Query

from ..adapters.base import AdapterError
from ..adapters.market.scenario import available_scenarios
from ..config.settings import Settings, get_settings
from ..engines.orchestrator import run_pipeline
from ..models.common import DataMode
from ..models.snapshot import IntelligenceSnapshot

logger = logging.getLogger(__name__)

#: 프론트가 5초 간격으로 폴링한다. 그 사이 재계산은 낭비다.
CACHE_TTL_SEC = 4.0


#: Persistence / Stability / (P2) duration 계산에 쓸 과거 틱 보관 수.
HISTORY_LIMIT = 12


@dataclass
class _Entry:
    snapshot: IntelligenceSnapshot
    created_at: float


class SnapshotService:
    """
    스냅샷 생성 + 프로세스 내 TTL 캐시.

    Redis 는 P4 옵션이다. 단일 프로세스 데모에서는 dict 로 충분하고,
    의존성이 하나 줄면 데모가 죽을 경로도 하나 줄어든다.
    """

    def __init__(self, ttl_sec: float = CACHE_TTL_SEC) -> None:
        self._ttl = ttl_sec
        self._cache: dict[str, _Entry] = {}
        self._lock = threading.Lock()
        #: 과거 스냅샷(오래된 것부터). 상태 판정의 지속성과 테마 점수의
        #: 안정성을 재려면 한 틱 전만으로는 부족하다. P2 의 divergence
        #: duration 과 alert baseline 도 여기서 온다.
        self._history: dict[str, deque[IntelligenceSnapshot]] = defaultdict(
            lambda: deque(maxlen=HISTORY_LIMIT)
        )

    def get(self, settings: Settings, *, force: bool = False) -> IntelligenceSnapshot:
        key = f"{settings.data_mode.value}:{settings.scenario}"
        now = time.monotonic()

        with self._lock:
            entry = self._cache.get(key)
            if entry and not force and (now - entry.created_at) < self._ttl:
                return entry.snapshot

        with self._lock:
            history = list(self._history[key])

        snapshot = run_pipeline(settings, history=history)

        with self._lock:
            prior = self._cache.get(key)
            if prior is not None:
                self._history[key].append(prior.snapshot)
            self._cache[key] = _Entry(snapshot=snapshot, created_at=time.monotonic())
        return snapshot

    def history(self, settings: Settings) -> list[IntelligenceSnapshot]:
        key = f"{settings.data_mode.value}:{settings.scenario}"
        with self._lock:
            return list(self._history[key])

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._history.clear()


_service = SnapshotService()


def get_service() -> SnapshotService:
    return _service


def resolve_settings(
    scenario: str | None = Query(
        default=None,
        description=(
            "MOCK 모드에서 재생할 시나리오. 시연을 우연이 아니라 의도로 "
            "통제하기 위한 파라미터다."
        ),
    ),
) -> Settings:
    """쿼리 파라미터로 시나리오를 바꿀 수 있게 한 설정."""
    settings = get_settings()
    if scenario is None or scenario == settings.scenario:
        return settings

    if settings.data_mode is not DataMode.MOCK:
        raise HTTPException(
            status_code=400,
            detail=f"scenario 파라미터는 MOCK 모드에서만 쓸 수 있다 (현재 {settings.data_mode.value}).",
        )
    known = available_scenarios(settings.mock_dir)
    if scenario not in known:
        raise HTTPException(
            status_code=404,
            detail=f"알 수 없는 시나리오 '{scenario}'. 사용 가능: {known}",
        )
    return settings.model_copy(update={"scenario": scenario})


def load_snapshot(settings: Settings) -> IntelligenceSnapshot:
    try:
        return get_service().get(settings)
    except AdapterError as exc:
        # 어댑터 부재는 설정 문제다. 500 이 아니라 503 으로 알린다.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
