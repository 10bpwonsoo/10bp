"""
IntelligenceSnapshot — API 최상위 응답 (설계서 STEP 4.8).

대시보드는 GET /api/v1/snapshot 한 번으로 화면 전체를 그린다.
패널마다 호출을 나누면 패널 간 시점이 어긋나 "Market State 는 10:00 기준인데
Theme 은 10:01 기준" 인 상태가 생긴다. 시장 분석 도구에서 이것은 치명적이다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from .alert import Alert
from .calendar import EventWindow
from .common import Base, DataMode, Direction
from .divergence import Divergence
from .news import NewsEvent
from .relationship import ImpactMap
from .state import MarketState
from .theme import ThemeState
from .thermometer import SentimentThermometer


class MovingItem(Base):
    """What's Moving 패널 한 줄."""

    key: str
    label: str
    kind: Literal["instrument", "theme"]
    z: float | None = None
    change: float | None = None
    change_display: str = ""
    direction: Direction = "flat"
    arrow: str = "→"
    #: 1주 전 그 시점의 z. None 은 히스토리가 짧아 못 잰 것이다.
    z_week_ago: float | None = None
    #: 장기 백분위(0~100)와 그 계산에 쓰인 봉 수. 252 미만이면 '1년' 이 아니다.
    percentile: float | None = None
    percentile_observations: int = 0
    #: 3개월 변화. change 와 같은 표시 단위.
    change_3m: float | None = None
    change_3m_display: str = ""


class DataHealth(Base):
    """요구 12 의 메타데이터를 UI 에 그대로 노출하기 위한 묶음."""

    mode: DataMode
    coverage: float = 0.0
    expected_instruments: int = 0
    available_instruments: int = 0
    missing: list[str] = Field(default_factory=list)
    stale: list[str] = Field(default_factory=list)
    max_freshness_sec: int = 0
    news_items: int = 0
    llm_status: Literal["disabled", "ok", "degraded", "failed"] = "disabled"
    engine_timings_ms: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class IntelligenceSnapshot(Base):
    as_of: datetime
    mode: DataMode
    scenario: str | None = None

    market_state: MarketState
    #: 센티멘트 온도계. None 은 엔진이 돌지 않은 옛 스냅샷이다.
    thermometer: SentimentThermometer | None = None
    #: 이벤트 창 판정. None 은 엔진이 돌지 않은 옛 스냅샷이다.
    calendar: EventWindow | None = None
    themes: list[ThemeState] = Field(default_factory=list)
    divergences: list[Divergence] = Field(default_factory=list)
    alerts: list[Alert] = Field(default_factory=list)
    impact_maps: list[ImpactMap] = Field(default_factory=list)
    events: list[NewsEvent] = Field(default_factory=list)
    whats_moving: list[MovingItem] = Field(default_factory=list)

    data_health: DataHealth
    engine_versions: dict[str, str] = Field(default_factory=dict)
