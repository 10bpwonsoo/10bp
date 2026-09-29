"""
물가 충격 탭 — Inflation & Rates Intelligence 결과. 판정 룰이 아니라 증거 집계다.
숫자는 config/rates_regime.yaml 의 표에서 나온다. 화면은 만들지 않는다. '확률' 이라는 말은 쓰지 않는다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from .common import Base

DriverStatus = Literal["CONFIRMED", "UNCONFIRMED", "CONTRADICTED"]
ConfirmStatus = Literal["CONFIRMED", "MIXED", "NOT_CONFIRMED", "MISSING"]


class EvidenceItem(Base):
    id: str
    label: str
    kind: Literal["price", "news"] = "price"
    layer: Literal["market", "alternative", "theme"] = "market"
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
    score: float = Field(ge=-100.0, le=100.0, description="장기 명목금리에 주는 방향·강도. −100 하락 압력 … +100 상승 압력")
    strength: str
    status: DriverStatus
    status_reason: str
    coverage: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    implication: str = ""


class RateMove(Base):
    instrument: str
    z: float | None = None
    window: int | None = None
    direction: Literal["up", "down", "flat", "unknown"] = "unknown"
    change_5d_bp: float | None = None
    level: float | None = None


class ComponentScore(Base):
    key: str
    label: str
    label_ko: str
    score: float | None = Field(default=None, description="−100~+100. None 은 계열 없음")
    status: Literal["up", "down", "flat", "missing"]
    coverage: float = 0.0
    evidence: list[EvidenceItem] = Field(default_factory=list)
    note: str = ""


class TenorPoint(Base):
    id: str
    label: str
    level: float | None = None
    z_1d: float | None = None
    z_5d: float | None = None
    z: float | None = Field(default=None, description="하루·5일 중 큰 쪽")
    change_5d_bp: float | None = None


class CurveView(Base):
    tenors: list[TenorPoint] = Field(default_factory=list)
    spread_z: float | None = Field(default=None, description="2s10s 의 z. + 스티프닝, − 플래트닝")
    shape: Literal["bear_steepening", "bear_flattening", "bull_steepening", "bull_flattening", "parallel_up", "parallel_down", "flat", "unknown"] = "unknown"
    lead: Literal["front", "long", "parallel", "none"] = "none"
    sentence: str = ""


class YieldDecomposition(Base):
    tenor: str
    window_days: int
    nominal_bp: float | None = None
    breakeven_bp: float | None = None
    real_implied_bp: float | None = Field(default=None, description="명목 − 기대인플레 (항등식)")
    real_measured_bp: float | None = Field(default=None, description="TIPS 실측. 없으면 None")
    dominant: Literal["real", "breakeven", "mixed", "unknown"] = "unknown"
    sentence: str = ""
    missing: list[str] = Field(default_factory=list)


class ConfirmationRow(Base):
    key: str
    label: str
    instruments: list[str] = Field(default_factory=list)
    values: dict[str, float | None] = Field(default_factory=dict)
    expected_sign: int | None = None
    status: ConfirmStatus
    note: str = ""


class KeyDivergence(Base):
    key: str
    label: str
    why: str
    severity: float = Field(ge=0.0, description="관련 z 절댓값 중 작은 쪽")
    values: dict[str, float | None] = Field(default_factory=dict)


class ImplicationRow(Base):
    key: str
    label: str
    pressure: Literal[-1, 0, 1, 2] = Field(description="−1 하락 압력 / 0 중립 / +1 상승 압력 / 2 양방향(상쇄)")


class MarketImplication(Base):
    driver: str
    why: str
    rows: list[ImplicationRow] = Field(default_factory=list)


class TriggerItem(Base):
    text: str
    metric: str
    current: str
    condition: str
    met: bool = False
    measurable: bool = True


class RatesRegime(Base):
    as_of: datetime
    rate_move: RateMove
    drivers: list[DriverScore]
    dominant: str
    runner_up: str | None = None
    margin: float = 0.0
    signal_strength: float = Field(ge=0.0, le=100.0)
    signal_strength_label: str
    inflation_status: DriverStatus
    regime_label: str = Field(description="예: LONG-END RATE / TERM PREMIUM SHOCK — Inflation Repricing Not Confirmed")
    headline: str
    implication: str
    inflation_components: list[ComponentScore] = Field(default_factory=list)
    curve: CurveView
    decomposition: list[YieldDecomposition] = Field(default_factory=list)
    confirmations: list[ConfirmationRow] = Field(default_factory=list)
    divergences: list[KeyDivergence] = Field(default_factory=list)
    market_implication: MarketImplication
    triggers: list[TriggerItem] = Field(default_factory=list)
    release: list[TriggerItem] = Field(default_factory=list)
    note: str
