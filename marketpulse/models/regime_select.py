"""MARKET REGIME v2 — 후보 · 주식 확인 · 선택 결과 (2026-11-04)."""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import Base

EquityStatus = Literal["STRONG", "CONFIRMED", "PARTIAL", "CONTRADICTED", "MIXED", "UNAVAILABLE"]
SignalState = Literal["AVAILABLE", "PARTIAL", "EXCLUDED"]


class EquitySignalRead(Base):
    key: str
    label: str
    market: Literal["us", "kr"]
    value: float | None = Field(default=None, description="z 단위(상승 비율은 0~1). None = 데이터 없음 → EXCLUDED")
    expected: int = Field(description="이 regime 에서 기대하는 방향 +1 / −1")
    score: float | None = Field(default=None, description="clip(sign × value / scale, −1, 1). None = 제외")
    state: SignalState = "AVAILABLE"
    note: str = ""


class MarketConfirmation(Base):
    status: EquityStatus
    score: float | None = None
    available: int = 0
    total: int = 0
    coverage: float = Field(default=0.0, description="있는 신호의 가중 비중 0~1 — confidence 와 별개")
    signals: list[EquitySignalRead] = Field(default_factory=list)


class EquityConfirmation(Base):
    us: MarketConfirmation
    kr: MarketConfirmation
    global_: MarketConfirmation = Field(alias="global")

    model_config = {"populate_by_name": True}


class SupportRead(Base):
    id: str
    expr: str
    passed: bool | None = Field(default=None, description="None = 평가할 데이터 없음 → EXCLUDED")
    observed: float | None = None


class RegimeCandidate(Base):
    label: str
    display: str
    trigger_expr: str
    trigger_value: float | None
    trigger_threshold: float | None
    trigger_margin: float | None = Field(default=None, description="threshold 를 얼마나 넘었나(같은 단위)")
    support: list[SupportRead] = Field(default_factory=list)
    support_ratio: float | None = Field(default=None, description="평가 가능한 보조 조건 중 충족 비중. None = 평가 가능한 것이 없음")
    cross_asset: float | None = Field(default=None, description="state_rules expected_response 확인 −1~+1")
    equity: EquityConfirmation
    quant_confidence: float = Field(ge=0, le=100)
    interpretation: str = ""


class AlternativeCandidate(Base):
    regime: str
    reason: str


class RegimeSelection(Base):
    selected_regime: str = Field(description="eligible 후보 중 하나 또는 NEUTRAL")
    regime_confidence: int = Field(ge=0, le=100)
    selection_status: Literal["CONFIRMED", "TENTATIVE", "LOW_CONFIDENCE", "NO_ELIGIBLE"] = "TENTATIVE"
    primary_reason: str
    alternative_candidates: list[AlternativeCandidate] = Field(default_factory=list)
    us_equity_confirmation: EquityStatus
    korea_equity_confirmation: EquityStatus
    global_equity_confirmation: EquityStatus
    persistence_assessment: str
    data_coverage: int = Field(ge=0, le=100)
    selection_rationale: str
    commentary: str = Field(default="", description="WHY — 화면에 보일 2~4문장. 선택과 모순되지 않는다")
    source: Literal["llm", "session", "quant"] = "quant"
    status: str = "ok"
    reason: str = ""
    quant_label: str = Field(default="NEUTRAL", description="기존 정량 1등(참고) — 선택과 다를 수 있다")
    candidates: list[RegimeCandidate] = Field(default_factory=list)
    neutral_equity: EquityConfirmation | None = Field(default=None, description="후보가 없을 때 Risk-On 기준으로 본 주식 방향(참고)")
    primary_signal: str = ""
    coverage_detail: dict[str, float] = Field(default_factory=dict, description="factor · us · kr · global coverage 0~1")
    excluded: list[str] = Field(default_factory=list, description="데이터가 없어 계산에서 뺀 항목")
    warnings: list[str] = Field(default_factory=list)
