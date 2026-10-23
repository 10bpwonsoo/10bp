"""
MarketState 스키마 (설계서 STEP 4.4).

요구 6 이 "하나의 Label 만 보여주기보다" 라고 했으므로 hypotheses 전체 순위와
factors 11개를 항상 함께 반환한다. primary_label 은 편의 필드일 뿐이다.

narrative 가 None 이어도 UI 는 완전히 동작해야 한다 (요구 15-7).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field

from .common import Base, Direction, ScoreBreakdown
from .theme import DataQualityBand


class StateLabel(StrEnum):
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    GROWTH_SHOCK = "GROWTH_SHOCK"
    INFLATION_SHOCK = "INFLATION_SHOCK"
    LIQUIDITY_STRESS = "LIQUIDITY_STRESS"
    POLICY_DRIVEN = "POLICY_DRIVEN"
    GEOPOLITICAL_RISK = "GEOPOLITICAL_RISK"
    NEUTRAL = "NEUTRAL"


#: 요구 6 이 명시한 factor 목록.
FACTOR_NAMES: tuple[str, ...] = (
    "Growth",
    "Inflation",
    "Rates",
    "USD",
    "Liquidity",
    "RiskAppetite",
    "Credit",
    "Volatility",
    "China",
    "KoreaFlow",
    "KoreaBreadth",
)


class FactorScore(Base):
    factor: str
    score: float = Field(description="z 단위. 대략 -3 ~ +3")
    breakdown: ScoreBreakdown
    data_quality: DataQualityBand = DataQualityBand.OK
    week_ago: float | None = Field(
        default=None,
        description="5봉 전 시점에 같은 식으로 계산한 factor. 오늘 값 옆의 '1주 전' 표식용",
    )


class RuleMatch(Base):
    """어떤 룰이 통과/실패했는지. 요구 14 의 '어떤 rule 에 의해' 에 답한다."""

    rule_id: str
    expression: str = Field(description='예: "Inflation >= 1.0"')
    kind: Literal["require", "support"] = "support"
    weight: float = 0.0
    passed: bool = False
    observed: float | None = None
    evaluable: bool = Field(
        default=True,
        description=(
            "평가에 필요한 값이 있었는가. False 면 통과로 보지 않는다. "
            "평가 불가를 통과로 처리하면 데이터가 없을수록 라벨이 잘 붙는다."
        ),
    )


class StateHypothesis(Base):
    label: StateLabel
    score: float = Field(ge=0.0, le=1.0)
    matched_rules: list[RuleMatch] = Field(default_factory=list)


class DriverItem(Base):
    """Main Drivers 표기용. 요구 10 의 'Oil ↑↑ / Rates ↑ / USD →'."""

    instrument_id: str
    label: str
    z: float
    direction: Direction
    arrow: str
    z_week_ago: float | None = Field(default=None, description="1주 전 시점의 z_1d")
    percentile: float | None = Field(default=None, description="장기 백분위 0~100")
    percentile_observations: int = Field(default=0, description="백분위에 쓰인 봉 수")


class AxisLink(Base):
    """지배 축과 한 자산의 연동. 60일 변화량 상관이다."""

    instrument_id: str
    label: str
    corr: float = Field(ge=-1.0, le=1.0)
    prior: float | None = Field(default=None, description="한 분기 전 창의 상관")
    z: float | None = Field(default=None, description="그 자산의 오늘 z_1d")


class DominantAxis(Base):
    """
    지금 시장을 가장 크게 흔든 축과, 그 축에 무엇이 얼마나 연동돼 있는가.

    GOAL Kickstart Exhibit 4 ("Fed 가격 반영과의 상관") 의 일반화다. 축은
    후보 중 |z| 가 가장 큰 자산으로 결정론적으로 고른다. 연동은 롤링
    상관이지 인과가 아니다 — 문장도 그렇게 쓴다.
    """

    instrument_id: str
    label: str
    z: float
    z_week_ago: float | None = None
    arrow: str = "→"
    window: int = Field(default=60, description="상관 창 (봉)")
    positive: list[AxisLink] = Field(default_factory=list, description="같은 방향으로 연동")
    negative: list[AxisLink] = Field(default_factory=list, description="반대 방향으로 연동")
    note: str = ""


class ConfirmationResult(Base):
    """cross-asset 확인 결과 (설계서 STEP 5.5)."""

    expected: dict[str, int] = Field(
        default_factory=dict, description="instrument_id -> 기대 부호(+1/-1)"
    )
    confirmed: list[str] = Field(default_factory=list)
    unconfirmed: list[str] = Field(default_factory=list)
    conflicting: list[str] = Field(default_factory=list)
    score: float = Field(default=0.0, ge=-1.0, le=1.0)
    verdict: Literal["HIGH", "MEDIUM", "LOW"] = "LOW"
    note: str = ""


class MarketState(Base):
    as_of: datetime
    primary_label: StateLabel = StateLabel.NEUTRAL
    secondary_label: StateLabel | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=100.0)
    confidence_breakdown: ScoreBreakdown | None = None
    factors: dict[str, FactorScore] = Field(default_factory=dict)
    hypotheses: list[StateHypothesis] = Field(default_factory=list)
    main_drivers: list[DriverItem] = Field(default_factory=list)
    dominant_axis: DominantAxis | None = Field(
        default=None, description="지배 축과 연동 자산. None 은 축 후보가 조용했거나 상관이 없는 것"
    )
    cross_asset_confirmation: ConfirmationResult = Field(
        default_factory=ConfirmationResult
    )
    narrative: str | None = None
    narrative_source: Literal["llm", "template", "none"] = "none"
