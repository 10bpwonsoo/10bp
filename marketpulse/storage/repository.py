"""저장소 인터페이스. 구현체 교체를 흡수한다 (설계서 STEP 3.1)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Sequence

from ..models.divergence import Divergence
from ..models.snapshot import IntelligenceSnapshot


class SnapshotRepository(ABC):
    """
    스냅샷 저장소.

    엔진은 이 인터페이스를 모른다. 오케스트레이터와 API 만 쓴다.
    분석 로직과 저장을 섞지 않는다 (요구 15-4, 15-5).
    """

    @abstractmethod
    def save(
        self,
        stream_key: str,
        snapshot: IntelligenceSnapshot,
        pending: Sequence[Divergence] = (),
    ) -> None:
        """스냅샷과 미확정 divergence 후보를 저장한다."""

    @abstractmethod
    def recent(self, stream_key: str, limit: int = 12) -> list[IntelligenceSnapshot]:
        """오래된 것부터 정렬된 최근 스냅샷."""

    @abstractmethod
    def latest_pending(self, stream_key: str) -> list[Divergence]:
        """가장 최근 틱의 미확정 divergence 후보."""

    @abstractmethod
    def prune(self, stream_key: str, keep: int) -> int:
        """오래된 스냅샷을 지운다. 지운 개수를 돌려준다."""

    @abstractmethod
    def at_or_before(
        self, stream_key: str, target: datetime, *, max_distance: timedelta
    ) -> IntelligenceSnapshot | None:
        """
        target 이전 것 중 가장 최근 스냅샷. target 보다 max_distance 이상
        오래됐으면 None — "1주 전" 을 묻는데 한 달 전 것을 주면 안 된다.
        """

    def close(self) -> None:
        """자원 정리. 기본은 아무것도 하지 않는다."""
