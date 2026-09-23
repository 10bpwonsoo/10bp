"""
Market State 히스토리 (2026-09-23 신설).

"지난 한 달 흐름이 어땠고 지금이 어디인가" 에 답하는 모델. 저장된 스냅샷을
꺼내 쓰는 것이 아니라 **같은 시계열을 하루씩 잘라 같은 엔진(compute_market_state)
을 다시 돌린** 결과다. 그래서 오늘 판정과 같은 잣대이고, 저장소가 없는
정적 배포본에서도 나온다. 뉴스는 과거 시점 것을 재현할 수 없으므로 온도는
가격 온도만 싣는다 — 없는 것을 0 으로 채우지 않는다.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from .common import Base
from .state import StateLabel


class StateHistoryPoint(Base):
    date: date
    as_of: datetime
    label: StateLabel
    secondary_label: StateLabel | None = None
    confidence: float = Field(ge=0.0, le=100.0)
    #: 온도계와 같은 식의 세 온도 (-100~+100). None 은 못 잰 날 — 뉴스는 그 시점까지 캡처된 기사가 있어야 나온다
    price_temperature: float | None = None
    news_temperature: float | None = None
    composite: float | None = None
    news_events: int = Field(default=0, description="그날 뉴스 온도에 쓴 기사 수")
    thermo_confidence: float = Field(default=0.0, ge=0.0, le=100.0, description="온도계 신뢰도")
    #: 온도계 재료 스트립과 같은 항목 (위험선호·변동성·성장·신용·한국 수급·뉴스 감성). None 은 결측
    components: dict[str, float | None] = Field(default_factory=dict)
    coverage: float = Field(ge=0.0, le=1.0, description="그날 확보 instrument 비율")
    factors: dict[str, float] = Field(default_factory=dict, description="factor → z 단위 점수")
    hypotheses: dict[str, float] = Field(default_factory=dict, description="라벨 → 가설 점수 (0 초과만)")
    drivers: list[str] = Field(default_factory=list, description="그날 주도 변수 상위 3 — '라벨 +1.2σ'")


class StateSegment(Base):
    """같은 라벨이 이어진 구간."""

    label: StateLabel
    start: date
    end: date
    days: int
    mean_confidence: float


class MarketStateHistory(Base):
    as_of: datetime
    days_requested: int
    points: list[StateHistoryPoint] = Field(default_factory=list)
    segments: list[StateSegment] = Field(default_factory=list)
    changes: int = Field(default=0, description="라벨이 바뀐 횟수")
    days_by_label: dict[str, int] = Field(default_factory=dict)
    current_streak: int = Field(default=0, description="현재 라벨이 이어진 거래일 수")
    previous_label: StateLabel | None = Field(default=None, description="현재 구간 직전의 라벨")
    #: 확신·가격 온도의 전반 vs 후반 평균. 흐름이 굳어지는지 풀리는지 한 줄로.
    confidence_first_half: float | None = None
    confidence_second_half: float | None = None
    temperature_first_half: float | None = None
    temperature_second_half: float | None = None
    component_labels: dict[str, str] = Field(default_factory=dict, description="components 의 키 → 화면 라벨 (온도계 순서). 기간 내내 결측인 재료는 뺀다")
    excluded_components: dict[str, str] = Field(default_factory=dict, description="기간 내내 결측이라 표에서 뺀 재료 (키 → 라벨). 숨긴 것이 아니라 여기 적는다")
    summary: str = ""
    note: str = Field(default="", description="계산 방식·한계")
