"""
Alert 스키마 (설계서 STEP 4.6).

요구 9 가 "단순 수준보다 변화를 중요하게 본다" 고 했으므로 baseline 과 delta 를
필수 필드로 둔다. 값만 있고 기준선이 없는 알림은 스키마가 만들지 못하게 막는다.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from .common import Base
from .divergence import SeverityBand


class AlertType(StrEnum):
    THEME_SENTIMENT_SPIKE = "THEME_SENTIMENT_SPIKE"
    NEWS_VOLUME_SPIKE = "NEWS_VOLUME_SPIKE"
    PRICE_ZSCORE_SPIKE = "PRICE_ZSCORE_SPIKE"
    FLOW_REVERSAL = "FLOW_REVERSAL"
    VOL_SPIKE = "VOL_SPIKE"
    DIVERGENCE_OPENED = "DIVERGENCE_OPENED"
    STATE_CHANGE = "STATE_CHANGE"
    DATA_QUALITY = "DATA_QUALITY"


class AlertState(StrEnum):
    NEW = "NEW"
    ONGOING = "ONGOING"
    RESOLVED = "RESOLVED"


class AlertTrigger(Base):
    """무엇이 얼마나 변했는가. 화면에 표시되는 모든 숫자가 여기 남는다."""

    rule_id: str
    metric: str = Field(description='예: "news_volume_3h"')
    current: float
    baseline: float
    delta: float
    delta_pct: float | None = None
    threshold: float
    window: str = ""


class Alert(Base):
    id: str
    as_of: datetime
    type: AlertType
    severity: float = Field(default=0.0, ge=0.0, le=100.0)
    severity_band: SeverityBand = SeverityBand.LOW
    subject: str = Field(
        description=(
            "이 알림이 무엇에 대한 것인가. divergence id, instrument id, "
            "theme id 등. 조건이 아직 참인지 판정할 때 이 값으로 대조한다."
        )
    )
    title: str
    message: str = ""
    trigger: AlertTrigger

    related_theme: str | None = None
    related_assets: list[str] = Field(default_factory=list)
    related_events: list[str] = Field(default_factory=list)

    dedupe_key: str
    first_fired_at: datetime
    last_fired_at: datetime
    fire_count: int = 1
    state: AlertState = AlertState.NEW
