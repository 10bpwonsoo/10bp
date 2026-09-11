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
from ..engines.orchestrator import run_pipeline_detailed
from ..models.common import DataMode
from ..models.divergence import Divergence
from ..models.snapshot import IntelligenceSnapshot
from ..storage.repository import SnapshotRepository

logger = logging.getLogger(__name__)

#: 프론트가 5초 간격으로 폴링한다. 그 사이 재계산은 낭비다.
CACHE_TTL_SEC = 4.0

#: 모드별 캐시 수명.
#
# MOCK 은 순수 계산이라 4초면 된다. 실데이터는 다르다 — 공급자 47곳을
# 도는 데 수 초에서 수십 초가 걸리고, **TTL 이 그보다 짧으면 매 폴링이
# 새 수집을 띄워 어떤 요청도 끝나지 않는다.** 실제로 그 상태가 되어
# 화면이 영영 비어 있었다.
#
# 값 자체도 데이터의 성질을 따라야 한다. 무료 공급자는 일봉 종가를 준다.
# 하루에 한 번 바뀌는 값을 4초마다 다시 받을 이유가 없다.
MODE_CACHE_TTL_SEC: dict[DataMode, float] = {
    DataMode.MOCK: CACHE_TTL_SEC,
    DataMode.DELAYED: 300.0,
    DataMode.LIVE: 300.0,
}


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

    def __init__(
        self,
        ttl_sec: float = CACHE_TTL_SEC,
        repository: SnapshotRepository | None = None,
    ) -> None:
        self._ttl = ttl_sec
        #: 선택적이다. 없으면 프로세스 메모리만 쓴다 — 데모는 그것으로 충분하고,
        #: 의존성이 하나 줄면 데모가 죽을 경로도 하나 준다.
        self._repo = repository
        self._cache: dict[str, _Entry] = {}
        self._lock = threading.Lock()
        #: 과거 스냅샷(오래된 것부터). 상태 판정의 지속성과 테마 점수의
        #: 안정성을 재려면 한 틱 전만으로는 부족하다. P2 의 divergence
        #: duration 과 alert baseline 도 여기서 온다.
        self._history: dict[str, deque[IntelligenceSnapshot]] = defaultdict(
            lambda: deque(maxlen=HISTORY_LIMIT)
        )
        #: 아직 지속 기간을 못 채운 divergence 후보. 다음 틱에서 이어붙인다.
        self._pending: dict[str, list[Divergence]] = defaultdict(list)

    def ttl_for(self, mode: DataMode) -> float:
        """MOCK 은 짧게, 실데이터는 길게. 수집 시간보다 짧으면 안 된다."""
        if self._ttl != CACHE_TTL_SEC:
            return self._ttl  # 테스트가 명시적으로 지정한 값을 존중한다
        return MODE_CACHE_TTL_SEC.get(mode, CACHE_TTL_SEC)

    def get(self, settings: Settings, *, force: bool = False) -> IntelligenceSnapshot:
        key = f"{settings.data_mode.value}:{settings.scenario}"
        now = time.monotonic()
        ttl = self.ttl_for(settings.data_mode)

        with self._lock:
            entry = self._cache.get(key)
            if entry and not force and (now - entry.created_at) < ttl:
                return entry.snapshot

            history = list(self._history[key])
            pending = list(self._pending[key])

        if not history and self._repo is not None:
            # 프로세스가 재시작돼도 지속 기간이 끊기지 않게 저장소에서 잇는다.
            history = self._repo.recent(key, limit=HISTORY_LIMIT)
            pending = self._repo.latest_pending(key)

        result = run_pipeline_detailed(
            settings, history=history, pending_divergences=pending
        )

        with self._lock:
            # 방금 계산한 스냅샷을 히스토리에 넣는다. 캐시에 있던 것을 넣으면
            # 엔진이 보는 '직전 스냅샷' 이 한 틱 밀리고, divergence 의 지속
            # 기간이 이어지지 않아 결과가 매 틱 나타났다 사라진다.
            # 히스토리는 캐시와 독립이어야 한다 — 캐시는 TTL 최적화일 뿐이고,
            # 비워도 시계열이 끊기면 안 된다.
            self._history[key].append(result.snapshot)
            self._pending[key] = result.pending
            self._cache[key] = _Entry(
                snapshot=result.snapshot, created_at=time.monotonic()
            )

        if self._repo is not None:
            try:
                self._repo.save(key, result.snapshot, result.pending)
            except Exception:
                # 저장 실패가 화면을 막으면 안 된다.
                logger.exception("스냅샷 저장 실패. 화면은 그대로 진행한다.")
        return result.snapshot

    def history(self, settings: Settings) -> list[IntelligenceSnapshot]:
        key = f"{settings.data_mode.value}:{settings.scenario}"
        with self._lock:
            return list(self._history[key])

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._history.clear()
            self._pending.clear()


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
