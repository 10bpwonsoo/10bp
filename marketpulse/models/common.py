"""
공통 타입 — 모든 스키마가 공유하는 기본 블록.

설계 원칙 (설계서 STEP 4.0):
  1. 모든 데이터는 출처/모드/신선도 메타데이터(DataMeta)를 들고 다닌다.
  2. 모든 합성 점수는 값이 아니라 ScoreBreakdown(값 + 기여도 + 입력 해시)을 반환한다.
     요구 15-6 "모든 주요 score는 계산 근거를 추적 가능하게 한다" 를 구조로 강제한다.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, computed_field


def utcnow() -> datetime:
    """모든 시각은 UTC 로 통일한다. 표시만 KST 로 한다 (설계서 STEP 7.8-2)."""
    return datetime.now(timezone.utc)


class Base(BaseModel):
    """프로젝트 공통 모델 설정."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        ser_json_timedelta="float",
    )


# ──────────────────────────────────────────────────────────
# Data mode / quality
# ──────────────────────────────────────────────────────────
class DataMode(StrEnum):
    LIVE = "LIVE"
    DELAYED = "DELAYED"
    MOCK = "MOCK"


class DataQuality(StrEnum):
    OK = "OK"
    PARTIAL = "PARTIAL"
    STALE = "STALE"
    MISSING = "MISSING"


#: 이 초를 넘으면 is_stale 로 본다. 모드별로 기대 신선도가 다르다.
STALE_THRESHOLD_SEC: dict[DataMode, int] = {
    DataMode.LIVE: 120,
    DataMode.DELAYED: 20 * 60 + 120,  # 무료 소스의 15~20분 지연을 정상으로 본다
    DataMode.MOCK: 24 * 3600,
}


class DataMeta(Base):
    """데이터 한 조각의 출처 추적 정보 (요구 12)."""

    # freshness_sec / is_stale 는 computed_field 라 출력에는 실리지만 입력
    # 필드가 아니다. 직렬화한 스냅샷을 다시 읽어들일 때(P2 storage, 테스트)
    # extra="forbid" 면 그 두 키에서 실패한다. 이 모델만 무시하도록 연다.
    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    source: str = Field(description='예: "yfinance", "mock:scenario_baseline"')
    mode: DataMode
    retrieved_at: datetime = Field(description="수집 시각 (UTC)")
    as_of: datetime = Field(description="데이터 기준 시각 (UTC)")
    quality: DataQuality = DataQuality.OK

    # computed_field 로 두면 API 응답에도 자동으로 실린다.
    # UI 는 freshness 를 항상 표시해야 한다 — 지연된 데이터를 실시간이라
    # 부르지 않는 것이 이 시스템의 약속이다 (설계서 STEP 7.2).
    @computed_field  # type: ignore[prop-decorator]
    @property
    def freshness_sec(self) -> int:
        """retrieved_at - as_of. 음수가 나오면 0으로 본다."""
        return max(0, int((self.retrieved_at - self.as_of).total_seconds()))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_stale(self) -> bool:
        return self.freshness_sec > STALE_THRESHOLD_SEC[self.mode]


# ──────────────────────────────────────────────────────────
# Score 설명가능성
# ──────────────────────────────────────────────────────────
class ScoreContribution(Base):
    """합성 점수를 구성하는 항목 하나의 기여도."""

    key: str = Field(description='기여 항목 식별자. 예: "BRENT"')
    raw_value: float | None = Field(default=None, description="원 단위 값 (%, bp 등)")
    normalized: float = Field(description="표준화 값 (보통 z-score)")
    weight: float = Field(description="적용된 가중치")
    contribution: float = Field(description="normalized * weight")
    note: str = ""


class ScoreBreakdown(Base):
    """
    점수 + 계산 근거.

    inputs_hash 는 정렬된 'key=value' 문자열의 SHA-256 앞 16자다.
    테스트에서 '같은 입력 -> 같은 해시 -> 같은 값' 을 단언해 재현성을 검증한다
    (요구 14).
    """

    value: float
    method: str = Field(description='계산 방식 식별자. 예: "weighted_z_tanh_v1"')
    contributions: list[ScoreContribution] = Field(default_factory=list)
    missing_inputs: list[str] = Field(
        default_factory=list,
        description="결측이라 가중치 재정규화로 제외된 항목. 0으로 채우지 않는다.",
    )
    inputs_hash: str = ""
    computed_at: datetime = Field(default_factory=utcnow)

    @staticmethod
    def hash_inputs(inputs: Mapping[str, float | None]) -> str:
        """입력 딕셔너리를 결정론적으로 해싱한다."""
        parts = []
        for k in sorted(inputs):
            v = inputs[k]
            parts.append(f"{k}=" + ("None" if v is None else f"{v:.10g}"))
        digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
        return digest[:16]

    @classmethod
    def build(
        cls,
        *,
        value: float,
        method: str,
        contributions: Sequence[ScoreContribution],
        missing_inputs: Sequence[str] = (),
    ) -> "ScoreBreakdown":
        inputs = {c.key: c.normalized for c in contributions}
        inputs.update({k: None for k in missing_inputs})
        return cls(
            value=value,
            method=method,
            contributions=list(contributions),
            missing_inputs=list(missing_inputs),
            inputs_hash=cls.hash_inputs(inputs),
        )


Direction = Literal["up", "down", "flat"]


def arrow_for(z: float) -> str:
    """z-score 를 화살표로. 대시보드 Main Drivers 표기용 (요구 10)."""
    if z >= 1.5:
        return "↑↑"
    if z >= 0.5:
        return "↑"
    if z <= -1.5:
        return "↓↓"
    if z <= -0.5:
        return "↓"
    return "→"


def direction_for(z: float, deadband: float = 0.5) -> Direction:
    if z >= deadband:
        return "up"
    if z <= -deadband:
        return "down"
    return "flat"
