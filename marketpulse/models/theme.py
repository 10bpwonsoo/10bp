"""ThemeState 스키마 (설계서 STEP 4.3)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

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
    sentiment_polarity: Literal["directional", "risk"] = Field(
        default="directional",
        description=(
            "directional: 테마가 강해지는 방향이 +. Oil 테마는 유가 상승이 +다. "
            "risk: 악재가 테마를 키운다. Geopolitical Risk 는 긴장 고조가 +다. "
            "요구 5 의 예시 히트맵에서 'Geopolitical Risk +88' 이 이 경우다."
        ),
    )
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

    # None 은 '측정되지 않음' 이다. 0.0 은 '측정했고 중립' 이다.
    # 둘을 같은 값으로 뭉개면 뉴스가 없는 테마와 뉴스가 팽팽한 테마를
    # 구분할 수 없다 (설계서 STEP 5.0 원칙 3).
    news_sentiment: float | None = None
    news_volume: float | None = None
    news_momentum: float | None = None
    price_momentum: float | None = None
    flow_momentum: float | None = None
    volatility: float | None = None

    cross_asset_confirmation: Confirmation = Confirmation.LOW
    confirmation_score: float | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=100.0)
    confidence_breakdown: ScoreBreakdown | None = None

    last_change: float = 0.0
    last_change_window: str = "1tick"
    #: 약 1주 전 저장 스냅샷의 테마 점수. 저장이 없으면 None — 0 이 아니다.
    week_ago_score: float | None = None

    supporting_events: list[str] = Field(default_factory=list)
    supporting_instruments: list[str] = Field(default_factory=list)
    data_quality: DataQualityBand = DataQualityBand.OK
