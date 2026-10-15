"""
이벤트 달력 스키마 (GOAL Kickstart 의 '바쁜 중앙은행 주간' 프레이밍 차용).

달력 자체는 설정(calendar.yaml)이고, 여기 있는 것은 "지금 이벤트 창 안에
있는가" 의 판정 결과다. 판정은 as_of 와 설정만으로 결정된다 — 시계를
읽지 않는다.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from .common import Base


class CalendarEvent(Base):
    id: str
    date: date
    label: str
    kind: str = "central_bank"
    region: str | None = None
    weight: float = Field(default=1.0, ge=0.0, le=1.0, description="시장 영향의 상대 크기")
    verified: bool = Field(
        default=False,
        description="1차 출처로 확인한 날짜인가. false 면 화면에 '(미확인)' 이 붙는다",
    )
    note: str = ""
    #: as_of 기준 며칠 남았는가. 음수는 지난 것. 판정 시점에 채운다.
    days_until: int | None = None


class EventWindow(Base):
    """
    이벤트 창 판정.

    active 이면 confidence 의 persistence 가중과 알림 임계가 조정된다.
    무엇이 얼마나 조정됐는지가 여기 그대로 남는다 (요구 15-6).
    """

    as_of: datetime
    active: bool = False
    #: 창 안에 든 이벤트. 비어 있으면 active 는 거짓이다.
    in_window: list[CalendarEvent] = Field(default_factory=list)
    #: 창 밖이지만 곧 오는 것. 화면의 '다음 이벤트' 줄.
    upcoming: list[CalendarEvent] = Field(default_factory=list)
    window_days_before: int = 2
    window_days_after: int = 0
    persistence_scale: float = Field(default=1.0, description="적용된 persistence 가중 배율")
    alert_threshold_scale: float = Field(default=1.0, description="적용된 알림 임계 배율")
    note: str = ""
