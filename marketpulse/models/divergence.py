"""
Divergence 스키마 (설계서 STEP 4.5).

요구 7 이 핵심 차별화 기능으로 지목한 부분이다.
explanation 은 템플릿으로 생성한다 — LLM 없이도 문장이 나와야 한다 (요구 15-7).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from .common import Base, Direction


class DivergenceType(StrEnum):
    NEWS_VS_PRICE = "NEWS_VS_PRICE"
    NEWS_VS_FLOW = "NEWS_VS_FLOW"
    PRICE_VS_FLOW = "PRICE_VS_FLOW"
    THEME_VS_ASSET = "THEME_VS_ASSET"
    RISK_VS_VOL = "RISK_VS_VOL"
    OIL_VS_INFLATION_EXP = "OIL_VS_INFLATION_EXP"
    BREADTH_VS_INDEX = "BREADTH_VS_INDEX"


class SeverityBand(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DivergenceLeg(Base):
    """괴리를 이루는 신호 한 쪽. 재현용 원자료."""

    name: str = Field(description='예: "News Sentiment"')
    value: float
    z: float | None = None
    direction: Direction = "flat"


class Divergence(Base):
    id: str
    type: DivergenceType
    as_of: datetime

    severity: float = Field(default=0.0, ge=0.0, le=100.0)
    severity_band: SeverityBand = SeverityBand.LOW
    duration_periods: int = 1
    first_detected_at: datetime

    related_theme: str | None = None
    related_assets: list[str] = Field(default_factory=list)

    legs: list[DivergenceLeg] = Field(default_factory=list)
    gap: float = 0.0
    rule_id: str = ""

    explanation: str = Field(default="", description="템플릿 생성. LLM 불필요.")
    llm_commentary: str | None = None
