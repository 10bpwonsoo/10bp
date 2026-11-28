"""
CorrelationBook — 자산 간 롤링 상관 행렬 (GOAL Kickstart Exhibit 46~50 차용).

사전 정의 관계(relationships.yaml)는 "보통 이렇게 움직인다" 는 가설이다.
불확실한 시장 관계를 확정 사실처럼 다루지 않으려면(개발 규칙 11) 그 가설을
실측 상관으로 계속 대조해야 한다. 이 모델이 그 실측이다.

두 장의 행렬을 든다 — 현재 창(window)의 상관과 prior_shift 봉 전 같은
창의 상관. 둘의 부호가 갈리면 관계가 바뀐 것이고, 그것이 곧 레짐 변화다.

값이 None 인 칸은 "관측이 부족해 재지 못했다" 다. 0 이 아니다.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .common import Base


class PairCorrelation(Base):
    """한 쌍의 상관. 화면과 규칙이 쓰는 최소 단위."""

    a: str
    b: str
    corr: float | None = Field(default=None, description="현재 창의 상관 -1~+1")
    prior: float | None = Field(default=None, description="prior_shift 봉 전 창의 상관")
    observations: int = Field(default=0, description="현재 창에서 두 값이 모두 있던 봉 수")


class CorrelationBook(Base):
    as_of: datetime
    ids: list[str] = Field(default_factory=list)
    window: int = Field(default=60, description="상관 창 (봉)")
    prior_shift: int = Field(default=63, description="'이전 창' 을 몇 봉 전으로 볼지")
    min_observations: int = Field(default=40, description="이 미만이면 상관을 내지 않는다")
    #: ids 순서의 정방 행렬. None 은 관측 부족.
    current: list[list[float | None]] = Field(default_factory=list)
    prior: list[list[float | None]] = Field(default_factory=list)
    observations: list[list[int]] = Field(default_factory=list)

    def _index(self, iid: str) -> int | None:
        try:
            return self.ids.index(iid)
        except ValueError:
            return None

    def pair(self, a: str, b: str) -> PairCorrelation | None:
        """두 자산의 상관. 어느 한쪽이 책에 없으면 None."""
        i, j = self._index(a), self._index(b)
        if i is None or j is None or i == j:
            return None
        return PairCorrelation(
            a=a,
            b=b,
            corr=self.current[i][j] if self.current else None,
            prior=self.prior[i][j] if self.prior else None,
            observations=self.observations[i][j] if self.observations else 0,
        )

    def row(self, a: str) -> list[PairCorrelation]:
        """a 와 다른 모든 자산의 상관. 측정된 것만."""
        i = self._index(a)
        if i is None:
            return []
        out: list[PairCorrelation] = []
        for j, b in enumerate(self.ids):
            if j == i:
                continue
            c = self.current[i][j] if self.current else None
            if c is None:
                continue
            out.append(
                PairCorrelation(
                    a=a,
                    b=b,
                    corr=c,
                    prior=self.prior[i][j] if self.prior else None,
                    observations=self.observations[i][j] if self.observations else 0,
                )
            )
        return out
