"""
AI Trade Intelligence — AI 탭의 응답 모델.

시장 온도·공포/탐욕 같은 broad-market 감성이 아니라 'AI 트레이드 자체' 를 잰다. 절대 수익이 아니라
Nasdaq 100 / S&P 500 대비 상대 수익·상대 z 가 축이고, 점수는 확률이 아니라 증거 크기다.
결측은 0 이 아니다 — 계열이 없으면 None 과 note 로 남는다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from .common import Base

DriverStatus = Literal["CONFIRMED", "UNCONFIRMED", "CONTRADICTED"]
RegimeKey = Literal["ai_specific_derisking", "macro_dragged", "leadership_narrowing", "narrative_ahead", "confirmed_risk_on", "confirmed_risk_off", "price_resilience", "mixed", "unknown"]


class EvidenceItem(Base):
    id: str
    label: str
    kind: Literal["price", "news"] = "price"
    layer: Literal["market", "alternative", "theme", "basket", "narrative"] = "market"
    value: float | None = None
    window: int | None = None
    sign: int
    weight: float
    contribution: float = 0.0
    available: bool = True
    note: str = ""


class DriverScore(Base):
    id: str
    label: str
    label_ko: str
    headline: str
    score: float = Field(ge=-100.0, le=100.0, description="AI 바스켓 가격에 주는 방향·강도. −100 하락 압력 … +100 상승 압력")
    strength: str
    status: DriverStatus
    status_reason: str
    coverage: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    implication: str = ""


class MemberRow(Base):
    id: str
    name: str
    group: str
    available: bool = True
    last_date: str | None = None
    ret_1d: float | None = None
    ret_5d: float | None = None
    ret_21d: float | None = None
    rel_5d: float | None = Field(default=None, description="그룹 벤치마크 대비 5일 상대 수익 %p")
    above_ma5: bool | None = None
    above_ma20: bool | None = None
    advancing: bool | None = None
    note: str = ""


class GroupMomentum(Base):
    key: str
    label: str
    label_ko: str
    benchmark: str
    in_basket: bool = True
    members: int
    available: int
    ret_1d: float | None = None
    ret_5d: float | None = None
    ret_21d: float | None = None
    rel_1d: float | None = Field(default=None, description="벤치마크 대비 %p")
    rel_5d: float | None = None
    rel_21d: float | None = None
    rel_z_1d: float | None = Field(default=None, description="그룹/벤치마크 비율 지수의 하루 z")
    rel_z_5d: float | None = None
    above_ma20_pct: float | None = None
    down_1w: int = Field(default=0, description="1주 하락 구성원 수")
    rank_1w: int | None = None
    role: Literal["leader", "strong", "neutral", "lagging", "laggard", "unknown"] = "unknown"
    note: str = ""


class Leadership(Base):
    groups: list[GroupMomentum] = Field(default_factory=list)
    leader_1d: str | None = None
    leader_1w: str | None = None
    leader_1m: str | None = None
    laggard_1w: str | None = None
    rotation: Literal["none", "rotating", "early", "unknown"] = "unknown"
    sentence: str = ""


class AiVsMarket(Base):
    members_used: int = 0
    members_total: int = 0
    last_date: str | None = None
    basket_ret_1d: float | None = None
    basket_ret_5d: float | None = None
    basket_ret_21d: float | None = None
    basket_z_1d: float | None = None
    basket_z_5d: float | None = None
    basket_z: float | None = Field(default=None, description="하루·5일 중 |z| 큰 쪽")
    basket_window: int | None = None
    ndx_ret_1d: float | None = None
    ndx_ret_5d: float | None = None
    ndx_ret_21d: float | None = None
    spx_ret_5d: float | None = None
    spx_ret_21d: float | None = None
    rel_ndx_1d: float | None = Field(default=None, description="%p")
    rel_ndx_5d: float | None = None
    rel_ndx_21d: float | None = None
    rel_ndx_z_1d: float | None = None
    rel_ndx_z_5d: float | None = None
    rel_ndx_z: float | None = None
    rel_spx_5d: float | None = None
    rel_spx_z_5d: float | None = None
    abs_direction: Literal["up", "down", "flat", "unknown"] = "unknown"
    rel_verdict: Literal["outperform", "inline", "underperform", "unknown"] = "unknown"
    sentence: str = ""


class Breadth(Base):
    members: int = 0
    above_ma5_pct: float | None = None
    above_ma20_pct: float | None = None
    advancing_pct: float | None = None
    above_ma20_pct_1w_ago: float | None = None
    change_1w_pts: float | None = None
    trend: Literal["widening", "narrowing", "stable", "unknown"] = "unknown"
    narrowing_with_index_up: bool = False
    by_group: dict[str, float | None] = Field(default_factory=dict, description="그룹별 20일선 상회 비율")
    sentence: str = ""


class NarrativeDriver(Base):
    key: str
    label: str
    label_ko: str
    tone: float | None = Field(default=None, description="감쇠 가중 AI 톤. 기사 없으면 None")
    count: int = 0
    samples: list[str] = Field(default_factory=list)


class NarrativePrice(Base):
    news_tone: float | None = None
    news_count: int = 0
    news_momentum: float | None = None
    price_z: float | None = None
    price_window: int | None = None
    quadrant: Literal["confirmed", "narrative_ahead", "price_resilience", "confirmed_risk_off", "unclear"] = "unclear"
    label: str = ""
    sentence: str = ""
    drivers: list[NarrativeDriver] = Field(default_factory=list)
    method: str = "룰 기반 키워드 분류 — 수기/LLM 태깅된 AI 기사의 제목을 driver 사전에 대어 나눈다. 한 기사가 여러 driver 에 들어갈 수 있다"


class MacroRow(Base):
    key: str
    label: str
    instrument: str
    z: float | None = None
    window: int | None = None
    expected_sign: int
    status: Literal["EXPLAINS", "DOES_NOT_EXPLAIN", "NEUTRAL", "MISSING"]
    note: str = ""


class MacroConfirmation(Base):
    rows: list[MacroRow] = Field(default_factory=list)
    explains: int = 0
    evaluated: int = 0
    verdict: Literal["macro_driven", "ai_specific", "mixed", "not_weak", "unknown"] = "unknown"
    sentence: str = ""


class StressComponent(Base):
    key: str
    label: str
    value: float | None = None
    display: str = "–"
    points: int = 0
    max_points: int = 2
    note: str = ""


class AiStress(Base):
    level: Literal["LOW", "MODERATE", "HIGH", "UNKNOWN"] = "UNKNOWN"
    score: int = 0
    max_score: int = 0
    components: list[StressComponent] = Field(default_factory=list)
    sentence: str = ""


class TriggerItem(Base):
    text: str
    metric: str
    current: str
    condition: str
    met: bool = False
    measurable: bool = True


class RegimeCheck(Base):
    key: RegimeKey
    label: str
    passed: bool
    detail: str


class GlobalContext(Base):
    market_label: str
    market_confidence: float
    thermometer: float | None = None
    band: str | None = None
    note: str = "Global market regime 은 맥락 입력이다 — AI 판정에는 상대 z 로만 들어간다"


class AiRegime(Base):
    as_of: datetime
    regime: RegimeKey
    regime_label: str
    regime_label_ko: str
    headline: str
    implication: str
    checks: list[RegimeCheck] = Field(default_factory=list)
    ai_vs_market: AiVsMarket
    drivers: list[DriverScore] = Field(default_factory=list)
    dominant: str | None = None
    runner_up: str | None = None
    margin: float = 0.0
    signal_strength: float = Field(default=0.0, ge=0.0, le=100.0)
    signal_strength_label: str = ""
    leadership: Leadership
    breadth: Breadth
    narrative: NarrativePrice
    macro: MacroConfirmation
    stress: AiStress
    triggers: list[TriggerItem] = Field(default_factory=list)
    release: list[TriggerItem] = Field(default_factory=list)
    context: GlobalContext
    members: list[MemberRow] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    note: str
