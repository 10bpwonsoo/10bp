"""
MarketData 스키마 (설계서 STEP 4.1).

핵심 설계 결정 두 가지:
  · unit 과 change_bp 를 분리한다. US10Y 가 4.20% -> 4.35% 로 갔을 때
    "3.6% 상승" 은 현업에서 쓸 수 없다. "15bp 상승" 이어야 한다.
  · higher_is_risk_on 을 Instrument 에 둔다. VIX 가 오르면 위험선호가 내린다는
    사실이 데이터에 박혀 있어야 factor 계산에서 부호를 자동 결정할 수 있다.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from .common import Base, DataMeta, DataMode
from .correlation import CorrelationBook


class AssetClass(StrEnum):
    EQUITY = "equity"
    RATE = "rate"
    FX = "fx"
    COMMODITY = "commodity"
    VOLATILITY = "volatility"
    FLOW = "flow"
    BREADTH = "breadth"
    CREDIT = "credit"


Unit = Literal["price", "percent", "index", "bp", "krw_bn", "count", "ratio"]

#: 시계열 생성/변화량 계산 방식.
#: price  = 로그수익률 기반 (지수, 원자재, FX, VIX)
#: level  = 레벨 차분 기반 (금리 %, 수급 억/십억원, breadth 비율)
SeriesKind = Literal["price", "level"]


class DerivedSpec(Base):
    """
    다른 instrument 두 개에서 파생되는 값.

    ratio       = a / b        (예: Copper/Gold)
    spread      = a - b        (예: 2s10s 커브 = US10Y - US2Y)
    vol_premium = a - 실현변동성(b)
                  a 는 내재변동성 지수(VIX, 연율 %), b 는 그 기초 가격 지수(SPX).
                  실현변동성은 b 의 20봉 로그수익률 표준편차를 연율화한 것이다.
                  양수면 시장이 실현된 것보다 더 큰 변동을 값으로 치르고 있고,
                  음수면 실현된 변동조차 값에 반영하지 않는 안일함이다.
                  처음 20봉은 실현변동성을 잴 수 없어 비어 있다 (0 이 아니다).

    어댑터가 기초 자산을 확보한 뒤 계산한다. 실데이터 어댑터(P4)에서도
    같은 규칙이 적용되므로 엔진은 파생 여부를 알 필요가 없다.
    """

    op: Literal["ratio", "spread", "vol_premium"]
    a: str
    b: str


class Instrument(Base):
    """관측 대상 하나. config/instruments.yaml 의 레지스트리 항목."""

    id: str
    name: str
    asset_class: AssetClass
    unit: Unit
    series_kind: SeriesKind = "price"
    region: str | None = Field(default=None, description="KR | US | CN | EU | GLOBAL")
    currency: str | None = None
    higher_is_risk_on: bool | None = Field(
        default=None,
        description="상승이 위험선호 강화를 뜻하는가. VIX 는 False, SPX 는 True.",
    )
    calendar: str = Field(
        default="24H",
        description="거래 캘린더. KRX | NYSE | 24H. 휴장 처리에 쓴다 (설계서 STEP 7.8-3).",
    )
    derived_from: DerivedSpec | None = Field(
        default=None, description="파생 지표면 계산 규칙. 아니면 None."
    )
    tags: list[str] = Field(default_factory=list)
    #: 이 계열을 받아들이는 최소 봉 수. None 이면 공통 기준(MIN_POINTS). 공개 이력이 없어 오늘부터 쌓는
    #: 계열(현물 표·분기 추정치)은 1 — 값은 보이되 z 는 봉이 찰 때까지 None 이다.
    min_points: int | None = Field(default=None, ge=1)


class InstrumentRegistry(Base):
    """instruments.yaml 전체."""

    instruments: list[Instrument]

    @model_validator(mode="after")
    def _unique_ids(self) -> "InstrumentRegistry":
        seen: set[str] = set()
        for ins in self.instruments:
            if ins.id in seen:
                raise ValueError(f"instrument id 중복: {ins.id}")
            seen.add(ins.id)
        return self

    def by_id(self) -> dict[str, Instrument]:
        return {i.id: i for i in self.instruments}


class MarketDataPoint(Base):
    """한 시점의 관측치."""

    instrument_id: str
    as_of: datetime
    value: float
    prev_close: float | None = None
    change: float | None = None
    change_pct: float | None = None
    change_bp: float | None = Field(
        default=None, description="금리 전용. 퍼센트포인트 * 100."
    )
    volume: float | None = None
    meta: DataMeta


class MarketFeature(Base):
    """
    FeatureEngine 산출. 표준화된 파생 지표.

    z_* 는 rolling window(zscore_window) 대비 표준화 값이다.
    관측치가 부족하면 None 이다. 0 으로 채우지 않는다 — 0 은 '중립' 이라는
    거짓 정보를 만든다 (설계서 STEP 5.0 원칙 3).
    """

    instrument_id: str
    as_of: datetime
    ret_1d: float | None = None
    ret_5d: float | None = None
    ret_20d: float | None = None
    ret_3m: float | None = Field(
        default=None, description="63봉(≈3개월) 변화. ret_1d 와 같은 표시 단위"
    )
    z_1d: float | None = None
    z_5d: float | None = None
    z_20d: float | None = None
    z_1d_week_ago: float | None = Field(
        default=None,
        description="5봉 전 시점에 계산한 z_1d. 오늘 값 옆의 '1주 전' 표식용",
    )
    zscore_window: int = 60
    realized_vol_20d: float | None = None
    rsi_14: float | None = None
    ma_dist_20: float | None = None
    ma_dist_60: float | None = None
    percentile_1y: float | None = Field(
        default=None,
        description="최근 최대 252봉 안에서의 백분위 0~100. 히스토리가 짧으면 그만큼만",
    )
    percentile_observations: int = Field(
        default=0, description="백분위 계산에 실제로 쓰인 봉 수. 252 미만이면 '1년' 이 아니다"
    )
    observations: int = Field(default=0, description="z 계산에 실제로 쓰인 관측치 수")
    meta: DataMeta


class MarketSeries(Base):
    """
    어댑터가 돌려주는 단위. 한 instrument 의 시계열.

    한 점이 아니라 시계열을 돌려주는 이유는 z-score 때문이다. rolling window
    대비 표준화를 하려면 최소 zscore_window 만큼의 히스토리가 필요하다.
    실데이터 어댑터(yfinance 등)도 히스토리를 돌려주는 것이 자연스럽다.
    """

    instrument_id: str
    timestamps: list[datetime]
    values: list[float]
    volumes: list[float] | None = None
    meta: DataMeta

    @model_validator(mode="after")
    def _aligned(self) -> "MarketSeries":
        if len(self.timestamps) != len(self.values):
            raise ValueError(
                f"{self.instrument_id}: timestamps/values 길이 불일치 "
                f"({len(self.timestamps)} vs {len(self.values)})"
            )
        if self.volumes is not None and len(self.volumes) != len(self.values):
            raise ValueError(f"{self.instrument_id}: volumes 길이 불일치")
        if not self.values:
            raise ValueError(f"{self.instrument_id}: 빈 시계열")
        return self

    @property
    def as_of(self) -> datetime:
        return self.timestamps[-1]

    @property
    def last(self) -> float:
        return self.values[-1]

    @property
    def prev(self) -> float | None:
        return self.values[-2] if len(self.values) >= 2 else None


class MarketSnapshot(Base):
    """한 tick 의 시장 전체 상태. 엔진들의 공통 입력."""

    as_of: datetime
    mode: DataMode
    points: dict[str, MarketDataPoint] = Field(default_factory=dict)
    features: dict[str, MarketFeature] = Field(default_factory=dict)
    expected_instruments: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    #: 자산 간 롤링 상관. None 은 계산하지 않은 것이다 (시계열이 없는 경로).
    correlations: CorrelationBook | None = None

    @property
    def coverage(self) -> float:
        """요구 instrument 중 실제 확보 비율. Confidence 계산에 들어간다."""
        if not self.expected_instruments:
            return 1.0 if self.points else 0.0
        have = sum(1 for i in self.expected_instruments if i in self.points)
        return have / len(self.expected_instruments)

    def z(self, instrument_id: str, horizon: str = "1d") -> float | None:
        """편의 접근자. 없으면 None 이다 (0 이 아니다)."""
        f = self.features.get(instrument_id)
        return None if f is None else getattr(f, f"z_{horizon}", None)
