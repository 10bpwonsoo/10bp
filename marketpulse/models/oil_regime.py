"""
유가 탭 — 시장 원인 판별 결과. 판정 룰(require/support)이 아니라 증거 집계다.

  드라이버 4개(거시·유동성 / 수요 / 공급 / 지정학 프리미엄)의 점수(−100~+100, 부호 = 유가에 주는 방향)와
  유가 관측(브렌트·WTI)에 비춘 상태 CONFIRMED / UNCONFIRMED / CONTRADICTED.
  숫자는 전부 config/oil_regime.yaml 의 표에서 나온다. 화면은 만들지 않는다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from .common import Base

DriverStatus = Literal["CONFIRMED", "UNCONFIRMED", "CONTRADICTED"]
ConfirmStatus = Literal["confirms", "contradicts", "neutral", "missing"]


class EvidenceItem(Base):
    id: str
    label: str
    kind: Literal["price", "news"] = "price"
    layer: Literal["market", "alternative", "theme"] = "market"
    #: 원 관측치 — 가격이면 z, 뉴스면 톤(−100~+100)
    value: float | None = None
    window: int | None = Field(default=None, description="가격 z 의 창(1 또는 5일). 뉴스는 None")
    sign: int
    weight: float
    #: 정규화·부호 반영 뒤 기여(−1~+1)×weight. 결측이면 0 이고 분모에서도 빠진다
    contribution: float = 0.0
    available: bool = True
    note: str = ""


class DriverScore(Base):
    id: str
    label: str
    label_ko: str
    score: float = Field(ge=-100.0, le=100.0, description="유가에 주는 방향·강도. −100 하락 압력 … +100 상승 압력")
    strength: str = Field(description="WEAK / MODERATE / STRONG — |score| 의 밴드")
    status: DriverStatus
    status_reason: str
    coverage: float = Field(ge=0.0, le=1.0, description="확보된 증거 가중치 비율")
    evidence: list[EvidenceItem] = Field(default_factory=list)
    implication: str = ""


class OilMove(Base):
    brent_z: float | None = None
    wti_z: float | None = None
    oil_z: float | None = Field(default=None, description="둘의 평균(있는 것만)")
    direction: Literal["up", "down", "flat", "unknown"] = "unknown"
    suspect: bool = Field(default=False, description="브렌트·WTI 가 크게 갈린다 — 계약 교체·봉 오류 의심")
    note: str = ""


class ConfirmationRow(Base):
    key: str
    label: str
    instruments: list[str] = Field(default_factory=list)
    values: dict[str, float | None] = Field(default_factory=dict, description="계열 → z")
    expected_sign: int | None = Field(default=None, description="dominant driver 아래서 기대되는 부호. None 이면 그 driver 와 무관")
    status: ConfirmStatus
    note: str = ""


class NarrativeRow(Base):
    theme_id: str
    name: str
    news: float | None = None
    price: float | None = None
    sentence: str
    divergence_severity: float | None = None


class WatchItem(Base):
    text: str
    metric: str
    current: str
    condition: str
    effect: str


class OilRegime(Base):
    as_of: datetime
    oil_move: OilMove
    drivers: list[DriverScore]
    dominant: str
    runner_up: str | None = None
    margin: float = Field(default=0.0, description="|dominant| − |runner-up|")
    signal_strength: float = Field(ge=0.0, le=100.0)
    signal_strength_label: str
    regime_label: str = Field(description="예: Macro / Liquidity Risk-Off — CONFIRMED")
    headline: str
    implication: str
    confirmations: list[ConfirmationRow] = Field(default_factory=list)
    narrative: list[NarrativeRow] = Field(default_factory=list)
    watch: list[WatchItem] = Field(default_factory=list)
    note: str
