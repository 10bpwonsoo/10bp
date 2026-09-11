"""ThemeState 스키마 (설계서 STEP 4.3)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from .common import Base, ScoreBreakdown


class Confirmation(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    CONFLICT = "CONFLICT"


class DataQualityBand(StrEnum):
    OK = "OK"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"


class ThemeInstrument(Base):
    """테마와 자산의 연결. direction 은 +1(정방향) / -1(역방향)."""

    instrument_id: str
    weight: float = 1.0
    direction: int = Field(default=1, description="+1 또는 -1")

    @model_validator(mode="after")
    def _check_direction(self) -> "ThemeInstrument":
        if self.direction not in (1, -1):
            raise ValueError("direction 은 +1 또는 -1 이어야 한다")
        return self


class Theme(Base):
    """config/themes.yaml 의 레지스트리 항목."""

    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(
        default_factory=list, description="RuleExtractor 가 뉴스 태깅에 쓴다"
    )
    parent: str | None = None
    instruments: list[ThemeInstrument] = Field(default_factory=list)
    macro_factors: list[str] = Field(default_factory=list)


class ThemeRegistry(Base):
    themes: list[Theme]

    @model_validator(mode="after")
    def _unique_ids(self) -> "ThemeRegistry":
        seen: set[str] = set()
        for t in self.themes:
            if t.id in seen:
                raise ValueError(f"theme id 중복: {t.id}")
            seen.add(t.id)
        return self

    def by_id(self) -> dict[str, Theme]:
        return {t.id: t for t in self.themes}


class ThemeState(Base):
    """한 테마의 한 시점 상태."""

    theme_id: str
    name: str = ""
    as_of: datetime

    theme_score: float = Field(default=0.0, ge=-100.0, le=100.0)
    breakdown: ScoreBreakdown

    news_sentiment: float = 0.0
    news_volume: float = 0.0
    news_momentum: float = 0.0
    price_momentum: float = 0.0
    flow_momentum: float = 0.0
    volatility: float = 0.0

    cross_asset_confirmation: Confirmation = Confirmation.LOW
    confirmation_score: float = 0.0
    confidence: float = Field(default=0.0, ge=0.0, le=100.0)
    confidence_breakdown: ScoreBreakdown | None = None

    last_change: float = 0.0
    last_change_window: str = "1tick"

    supporting_events: list[str] = Field(default_factory=list)
    supporting_instruments: list[str] = Field(default_factory=list)
    data_quality: DataQualityBand = DataQualityBand.OK
