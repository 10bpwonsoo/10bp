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
from typing import Literal

from pydantic import Field

from .common import Base
from .daily_history import MergedRow
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
    #: 온도계 밴드 — 공포·탐욕 분류. frozen(결빙=극단적 공포) cool(냉각=공포) neutral warm(온기=탐욕) overheated(과열=극단적 탐욕) unknown
    band: str = "unknown"
    band_label: str = "측정 불가"
    coverage: float = Field(ge=0.0, le=1.0, description="그날 확보 instrument 비율")
    factors: dict[str, float] = Field(default_factory=dict, description="factor → z 단위 점수")
    hypotheses: dict[str, float] = Field(default_factory=dict, description="라벨 → 가설 점수 (0 초과만)")
    drivers: list[str] = Field(default_factory=list, description="그날 주도 변수 상위 3 — '라벨 +1.2σ'")
    #: Daily snapshot 출처 (2026-10-07). RECORDED = 그날 당시 저장한 판정 · BACKFILLED = snapshot 이 없어 나중에 그 날짜를 1회 복원 · LIVE = 오늘, 확정 전.
    #: RECOMPUTED = 현재 모델로 과거를 다시 계산한 값(별도 RECOMPUTED HISTORY 에서만). 저장 후 고정된 값은 locked.
    source: Literal["RECORDED", "BACKFILLED", "LIVE", "RECOMPUTED"] = "RECOMPUTED"
    calculated_at: datetime | None = None
    model_version: str = ""
    logic_version: str = ""
    locked: bool = False
    #: 날짜 기준 분리 (2026-10-21) — date 는 KST snapshot 날짜(date_basis='kst_snapshot'), market_date 는 미국 정규장 날짜
    market_date: date | None = None
    storage_date: date | None = None
    merged: list[MergedRow] = Field(default_factory=list)


class BandSegment(Base):
    """같은 온도 밴드(공포·탐욕)가 이어진 구간."""

    band: str
    band_label: str
    start: date
    end: date
    days: int
    mean_composite: float | None = None


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
    #: 공포·탐욕(온도 밴드) 기준의 같은 통계. 어느 쪽을 1차로 보일지는 화면이 뷰별로 고른다
    #: (실데이터·물가 충격 등은 판정 라벨, AI 센티멘트는 공포·탐욕).
    band_segments: list[BandSegment] = Field(default_factory=list)
    days_by_band: dict[str, int] = Field(default_factory=dict, description="밴드 id → 일수")
    band_labels: dict[str, str] = Field(default_factory=dict, description="밴드 id → 화면 라벨 (온도계 설정 순서)")
    band_changes: int = 0
    current_band_streak: int = 0
    previous_band: str | None = None
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
    band_summary: str = Field(default="", description="같은 요약을 공포·탐욕(온도 밴드) 기준으로")
    note: str = Field(default="", description="계산 방식·한계")
    #: "stored" = 저장된 daily snapshot 의 sequence(기본) · "recomputed" = 현재 모델로 과거를 다시 계산한 별도 뷰
    history_mode: Literal["stored", "recomputed"] = "recomputed"
    recorded_days: int = 0
    backfilled_days: int = 0
    date_basis: str = "storage_utc"
    intraday: StateHistoryPoint | None = None
    gaps: list[date] = Field(default_factory=list)
    live_today: bool = False
    footnote: str = ""
