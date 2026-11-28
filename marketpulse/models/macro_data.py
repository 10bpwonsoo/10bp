"""
신뢰도 기반 macro fallback data layer(2026-10-13).

목적은 빈 칸을 억지로 채우는 것이 아니라, 공식 원자료가 직접 연결되지 않은 날에도 공신력 있는 경로로 가능한 만큼 보완하고
그 출처의 급(tier)을 숫자와 함께 항상 들고 다니는 것이다.

  Tier 1 PRIMARY    공식기관 원자료(BLS · BEA · Fed …) — FRED API 경유 포함
  Tier 1' MIRROR    같은 원자료의 공개 미러(FRED 그래프 CSV 등) — 값은 같고 경로만 다르다
  Tier 2 SECONDARY  공식 발표값을 보도한 신뢰 매체(Reuters · CNBC …)에서 확인한 값 — 출처가 붙은 수기 파일
  Tier 3 PROXY      원 series 가 없어 경제적으로 비슷한 지표 조합으로 만든 대체 추정 — 절대 원자료처럼 보이지 않는다
  Tier 4 NEWS       수치를 대체하지 않는 방향·서사 보조 신호
  UNAVAILABLE       찾지 못했다 — 숫자를 만들지 않는다
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from .common import Base

SourceClass = Literal["PRIMARY", "MIRROR", "SECONDARY", "PROXY", "NEWS", "UNAVAILABLE"]
Frequency = Literal["daily", "weekly", "monthly", "quarterly", "meeting"]


class MacroDataPoint(Base):
    """정규화한 macro series 하나 — 값과 함께 출처의 급 · 신선도 · 신뢰도 · 원자료 여부를 늘 들고 다닌다."""
    series: str = Field(description="CPI · CORE_PCE · WAGE_SERVICES_PRESSURE …")
    label: str
    value: float | None = None
    unit: str = Field(default="%", description="% · %p · score")
    measure: str = Field(default="", description="YoY · MoM · QoQ 연율 · score")
    previous: float | None = None
    consensus: float | None = None
    period: str = Field(default="", description="2026-08 · 2026-Q2")
    release_date: date | None = None
    source: str = Field(default="", description="BLS via FRED · CNBC · AHE · ECI · Services CPI 조합")
    source_tier: SourceClass
    is_original_data: bool
    proxy_components: list[str] = Field(default_factory=list)
    fallback_reason: str = ""
    last_updated: date | None = Field(default=None, description="이 값이 마지막으로 발표·갱신된 날(FRED vintage 일자 · 보도일)")
    freshness_days: int | None = None
    frequency: Frequency = "monthly"
    stale: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    momentum_ann: float | None = Field(default=None, description="최근 모멘텀 연율(월간 3개월 · 분기 1분기) % — 점수는 이것과 12개월 상승률의 차이로 낸다")
    pressure_z: float | None = Field(default=None, description="가속도(3개월 연율 − 12개월) 를 과거 변동으로 나눈 z — 점수의 근거")
    note: str = ""


class MacroComponent(Base):
    """INFLATION PRESSURE MAP 의 macro 구성요소(실제 물가 · 임금·서비스) — 어떤 급의 데이터로 점수를 냈는지까지."""
    key: str
    display_label: str = Field(description="Realized Inflation · REALIZED INFLATION PROXY · Wage / Services")
    score: float | None = None
    source_class: SourceClass
    source_label: str = ""
    is_original_data: bool
    proxy_components: list[str] = Field(default_factory=list)
    fallback_reason: str = ""
    last_updated: date | None = None
    freshness_days: int | None = None
    stale: bool = False
    confidence: float = 0.0
    series: list[MacroDataPoint] = Field(default_factory=list, description="점수에 쓴 series(실제 또는 대체)")
    reference: list[MacroDataPoint] = Field(default_factory=list, description="점수에는 넣지 않은 참고 값(실데이터가 있을 때의 proxy 등)")
    comment: str = ""


class NewsDriver(Base):
    label: str
    theme: str
    arrow: str
    tone: float | None = None


class NewsPulse(Base):
    """INFLATION NEWS PULSE — 공식 통계를 대체하지 않는 방향 보조 신호."""
    score: float | None = None
    articles: int = 0
    drivers: list[NewsDriver] = Field(default_factory=list)
    comment: str = ""
    confidence: float = 0.0


class MacroInflationLayer(Base):
    as_of: datetime
    components: dict[str, MacroComponent] = Field(default_factory=dict)
    news: NewsPulse | None = None
    series: list[MacroDataPoint] = Field(default_factory=list, description="수집한 모든 series — 화면의 DATA SOURCES 목록")
    note: str = ""
