"""
Investment Intelligence 스키마 (2026-09-16 신설).

기존 스키마(market·state·theme·divergence·relationship·thermometer)는 손대지
않는다. 여기는 그 아래 계층 — MARKET → ALTERNATIVE DATA → INDUSTRY → STOCK →
PRICE/FLOW → FUNDAMENTAL → ANALYST → CLAUDE INTERPRETATION — 의 데이터
계약이다.

세 원칙을 그대로 잇는다.
  1. 모든 값은 DataMeta(출처·모드·신선도)와 근거(ScoreBreakdown)를 들고 다닌다.
  2. None 은 '측정하지 못했다' 다. 0 이 아니다.
  3. 상관은 인과가 아니다. 원인 후보에는 반드시 종류(kind)와 확신(confidence)이 붙는다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from .common import Base, DataMeta, DataMode, Direction, ScoreBreakdown
from .market import AssetClass, Instrument, MarketFeature, SeriesKind, Unit

SourceType = Literal[
    "OFFICIAL", "EXCHANGE", "MARKET_DATA", "RESEARCH", "NEWS", "ALTERNATIVE", "UNKNOWN"
]
Confidence = Literal["HIGH", "MEDIUM", "LOW"]
CauseKind = Literal[
    "CONFIRMED_DATA", "CONFIRMED_NEWS", "ANALYST_VIEW", "MARKET_INFERENCE",
    "CLAUDE_INTERPRETATION", "UNKNOWN",
]
ExposureKind = Literal["revenue", "cost", "demand", "financial"]
Importance = Literal["high", "medium", "low"]
Quality = Literal["OK", "STALE", "PARTIAL", "MISSING"]


# ──────────────────────────────────────────────────────────
# 유니버스 (설정)
# ──────────────────────────────────────────────────────────
class SourceSpec(Base):
    provider: str
    symbol: str
    scale: float = 1.0


class StockMeta(Base):
    id: str
    name: str
    symbol: str
    market: str = "KOSPI"
    sector: str
    industry: str = ""
    peers: list[str] = Field(default_factory=list, description="universe.alternative 의 peer id")
    drivers: list[str] = Field(default_factory=list, description="노출을 잴 드라이버 id")
    themes: list[str] = Field(default_factory=list, description="themes.yaml 의 테마 id")
    aliases: list[str] = Field(default_factory=list, description="기사 본문에서 이 종목을 가리키는 다른 표기 (영문명·약칭)")
    mock_base: float = 100.0
    mock_vol: float = 0.02
    #: 이 계열을 받아들이는 최소 봉 수. None 이면 공통 기준(MIN_POINTS=20). 공개 이력이 없어 오늘부터 쌓는
    #: 현물(DRAMeXchange)이나 분기 추정치(HBM)는 1 로 두어 값·변화는 보이되 z 는 봉이 찰 때까지 None 이다.
    min_points: int | None = Field(default=None, ge=1)
    #: daily 가 아니면 z·백분위를 계산하지 않는다 — 분기 추정치에 60봉 z 는 의미가 없다.
    frequency: Literal["daily", "weekly", "monthly", "quarterly"] = "daily"

    def as_instrument(self) -> Instrument:
        return Instrument(
            id=self.id, name=self.name, asset_class=AssetClass.EQUITY, unit="price",
            series_kind="price", region="KR", currency="KRW", higher_is_risk_on=True,
            calendar="KRX", tags=["stock", self.sector],
        )


class AltInstrument(Base):
    id: str
    name: str
    group: str
    asset_class: AssetClass = AssetClass.COMMODITY
    unit: Unit = "price"
    series_kind: SeriesKind = "price"
    sources: list[SourceSpec] = Field(default_factory=list)
    source_type: SourceType = "UNKNOWN"
    futures: bool = False
    proxy_for: str | None = Field(default=None, description="대리 지표면 무엇의 대리인지")
    why: str = Field(default="", description="왜 투자에 의미가 있는가. 화면에 그대로 나간다")
    affected: list[str] = Field(default_factory=list, description="영향받는 종목 id")
    mock_base: float = 100.0
    mock_vol: float = 0.02
    #: 이 계열을 받아들이는 최소 봉 수. None 이면 공통 기준(MIN_POINTS=20). 공개 이력이 없어 오늘부터 쌓는
    #: 현물(DRAMeXchange)이나 분기 추정치(HBM)는 1 로 두어 값·변화는 보이되 z 는 봉이 찰 때까지 None 이다.
    min_points: int | None = Field(default=None, ge=1)
    #: daily 가 아니면 z·백분위를 계산하지 않는다 — 분기 추정치에 60봉 z 는 의미가 없다.
    frequency: Literal["daily", "weekly", "monthly", "quarterly"] = "daily"

    def as_instrument(self) -> Instrument:
        return Instrument(
            id=self.id, name=self.name, asset_class=self.asset_class, unit=self.unit,
            series_kind=self.series_kind, region="GLOBAL", higher_is_risk_on=None,
            calendar="24H" if self.asset_class is AssetClass.COMMODITY else "NYSE",
            tags=["alternative", self.group] + (["futures"] if self.futures else []),
            min_points=self.min_points,
        )


class FundamentalExposure(Base):
    driver_id: str
    kind: ExposureKind
    direction: Literal[-1, 1]
    importance: Importance
    rationale: str = ""


class Universe(Base):
    stocks: list[StockMeta]
    alternative: list[AltInstrument]
    benchmark_market: str = "KOSPI"

    def stock_by_id(self) -> dict[str, StockMeta]:
        return {s.id: s for s in self.stocks}

    def alt_by_id(self) -> dict[str, AltInstrument]:
        return {a.id: a for a in self.alternative}


# ──────────────────────────────────────────────────────────
# 종목 계층
# ──────────────────────────────────────────────────────────
class StockFeature(Base):
    """가격 feature(기존 MarketFeature 그대로) + 거래량·상대 수익률."""

    stock_id: str
    price: MarketFeature
    volume_z: float | None = Field(default=None, description="로그 거래량의 60일 z. 없으면 None")
    volume_ratio_20d: float | None = Field(default=None, description="오늘 거래량 / 20일 평균")
    relative_return_1d: float | None = Field(default=None, description="종목 − 시장 (%p)")
    relative_z: float | None = Field(default=None, description="상대 수익률의 60일 z")
    sector_return_1d: float | None = Field(default=None, description="같은 업종 평균 수익률 (%)")
    # 확보하지 못한 것들. 자리를 남겨 화면이 '없음' 을 말하게 한다.
    foreign_flow_z: float | None = None
    institution_flow_z: float | None = None
    intraday_range_z: float | None = None
    meta: DataMeta


class ExposureWindow(Base):
    window: int
    beta: float | None = None
    corr: float | None = None
    observations: int = 0


class ExposureRow(Base):
    driver_id: str
    driver_label: str
    windows: list[ExposureWindow] = Field(default_factory=list)
    #: primary 창의 값. 점수 계산에 쓴다.
    beta: float | None = None
    corr: float | None = None
    fundamental: FundamentalExposure | None = None
    #: 통계 부호와 사업 부호가 같은가. None 은 어느 한쪽이 없는 것.
    sign_agreement: bool | None = None
    note: str = ""


class StockExposure(Base):
    stock_id: str
    rows: list[ExposureRow] = Field(default_factory=list)
    primary_window: int = 60


class StockImpact(Base):
    """시장 충격 하나가 종목 하나에 미치는 추정 영향."""

    stock_id: str
    stock_name: str
    driver_id: str
    driver_label: str
    shock_z: float
    exposure: float = Field(description="primary 창 beta 또는 corr 기반 노출 (부호 포함)")
    stat_confidence: float = Field(ge=0.0, le=1.0)
    fund_relevance: float = Field(ge=0.0, le=1.0)
    current_relevance: float = Field(ge=0.0, le=1.0)
    score: float = Field(ge=0.0, le=100.0)
    direction: Direction = "flat"
    sign_conflict: bool = False
    breakdown: ScoreBreakdown
    rationale: str = ""


class DriverCard(Base):
    """Today's Market Drivers 한 장."""

    instrument_id: str
    label: str
    value: float
    unit: str
    change_1d_display: str
    change_1w: float | None = None
    change_3m: float | None = None
    z: float
    percentile: float | None = None
    percentile_observations: int = 0
    affected_sectors: list[str] = Field(default_factory=list)
    top_stocks: list[StockImpact] = Field(default_factory=list)
    source: str
    freshness_sec: int = 0
    stale: bool = False
    note: str = ""


class AltDataPoint(Base):
    """Alternative Data Pulse 한 줄. 단순 시세가 아니라 '왜 중요한가' 를 든다."""

    id: str
    label: str
    group: str
    value: float | None = None
    unit: str = "price"
    change_1d: float | None = None
    change_1w: float | None = None
    change_1m: float | None = None
    change_3m: float | None = None
    z: float | None = None
    percentile: float | None = None
    percentile_observations: int = 0
    quality: Quality = "MISSING"
    stale: bool = False
    rollover_suspect: bool = False
    rollover_followup: Literal["reverted", "persisted"] | None = Field(
        default=None, description="직전 실행에서 롤오버 의심이던 계열의 다음 봉 판정. 되돌리면 reverted, 이어지면 persisted")
    source: str | None = None
    source_type: SourceType = "UNKNOWN"
    #: daily 가 아니면 화면이 '분기 추정' 같은 표식을 붙이고 z 를 기대하지 않는다
    frequency: Literal["daily", "weekly", "monthly", "quarterly"] = "daily"
    #: 봉 수. 공통 기준(20) 미만이면 z 가 없는 이유가 이것이다
    observations: int = 0
    proxy_for: str | None = None
    why: str = ""
    affected: list[str] = Field(default_factory=list)
    affected_names: list[str] = Field(default_factory=list)
    as_of: datetime | None = None
    note: str = ""


# ──────────────────────────────────────────────────────────
# 원인 · 이상 · 괴리
# ──────────────────────────────────────────────────────────
class Evidence(Base):
    key: str
    label: str
    value: float | None = None
    display: str = ""
    source: str = ""


class CauseCandidate(Base):
    kind: CauseKind
    confidence: Confidence
    text: str
    evidence: list[Evidence] = Field(default_factory=list)
    weight: float = Field(default=0.0, description="후보 정렬용. 인과 확률이 아니다")


class StockExplanation(Base):
    stock_id: str
    stock_name: str
    as_of: datetime
    return_1d: float | None = None
    return_z: float | None = None
    volume_z: float | None = None
    market_return_1d: float | None = None
    sector_return_1d: float | None = None
    relative_return_1d: float | None = None
    causes: list[CauseCandidate] = Field(default_factory=list)
    unexplained: bool = Field(default=False, description="설명 가능한 후보가 없다")
    summary: str = ""


AnomalyLabel = Literal[
    "NONE", "UNEXPLAINED_ACTIVITY", "VOLUME_SPIKE", "RELATIVE_MOVE", "RETURN_SPIKE", "NEWS_DRIVEN_MOVE"
]


class StockAnomaly(Base):
    stock_id: str
    stock_name: str
    as_of: datetime
    return_z: float | None = None
    volume_z: float | None = None
    relative_z: float | None = None
    news_events: int = 0
    flags: list[str] = Field(default_factory=list)
    label: AnomalyLabel = "NONE"
    severity: float = Field(default=0.0, ge=0.0, le=100.0)
    note: str = ""
    #: 확보하지 못한 feature. '매집' 같은 단정을 막는 근거이기도 하다.
    missing: list[str] = Field(default_factory=list)


StockDivergenceKind = Literal[
    "PRICE_DOWN_EPS_UP", "PRICE_UP_EPS_DOWN",
    "PRICE_DOWN_FOREIGN_BUY", "PRICE_UP_FOREIGN_SELL",
    "PRICE_DOWN_COMMODITY_TAILWIND", "PRICE_UP_INDUSTRY_DOWN",
    "PRICE_DOWN_TP_UP", "PRICE_UP_TP_DOWN",
    "SECTOR_UP_STOCK_DOWN", "SECTOR_DOWN_STOCK_UP",
]


class DivergenceSide(Base):
    name: str
    value: float
    display: str = ""


class StockDivergence(Base):
    id: str
    kind: StockDivergenceKind
    stock_id: str
    stock_name: str
    as_of: datetime
    left: DivergenceSide
    right: DivergenceSide
    severity: float = Field(default=0.0, ge=0.0, le=100.0)
    duration_periods: int = 1
    first_detected_at: datetime
    explanation: str = ""


# ──────────────────────────────────────────────────────────
# 애널리스트 · 선행/후행 · 반도체 · 원자재 → 산업 → 종목
# ──────────────────────────────────────────────────────────
class AnalystSnapshot(Base):
    stock_id: str
    stock_name: str
    as_of: datetime | None = None
    rating: str | None = None
    rating_change: str | None = None
    target_price: float | None = None
    tp_change_1w: float | None = None
    tp_change_1m: float | None = None
    tp_change_3m: float | None = None
    eps_fy1: float | None = None
    eps_revision_1w: float | None = None
    eps_revision_1m: float | None = None
    eps_revision_3m: float | None = None
    brokers: int = 0
    price_change_1m: float | None = None
    quadrant: Literal["PRICE_UP_EPS_UP", "PRICE_DOWN_EPS_UP", "PRICE_UP_EPS_DOWN", "PRICE_DOWN_EPS_DOWN", "UNKNOWN"] = "UNKNOWN"
    source: str | None = None
    source_type: SourceType = "UNKNOWN"
    available: bool = False
    note: str = ""


class LeadLag(Base):
    lead_id: str
    lag_id: str
    label: str
    best_lag_days: int | None = None
    corr_at_best: float | None = None
    corr_at_zero: float | None = None
    observations: int = 0
    verdict: Literal["tends_to_lead", "coincident", "no_relationship", "insufficient"] = "insufficient"
    note: str = ""


class StockRow(Base):
    """종목 한 줄 요약. 반도체·원자재·테마·워치리스트 패널이 공유한다."""

    stock_id: str
    name: str
    sector: str
    price: float | None = None
    change_1d: float | None = None
    change_1w: float | None = None
    change_1m: float | None = None
    z: float | None = None
    volume_z: float | None = None
    relative_z: float | None = None
    percentile: float | None = None
    stale: bool = False
    source: str | None = None


class SemiconductorIntelligence(Base):
    memory: list[AltDataPoint] = Field(default_factory=list)
    peers: list[AltDataPoint] = Field(default_factory=list)
    korea: list[StockRow] = Field(default_factory=list)
    #: 방향 합의. 값은 -1(하락 합의) ~ +1(상승 합의), None 은 셀 것이 없음
    peer_direction: float | None = None
    korea_direction: float | None = None
    memory_direction: float | None = None
    eps_direction: float | None = None
    interpretation: str = ""
    missing: list[str] = Field(default_factory=list)


class CommodityStockLink(Base):
    stock_id: str
    stock_name: str
    kind: ExposureKind
    direction: Literal[-1, 1]
    importance: Importance
    rationale: str
    stat_corr: float | None = None
    price_reaction_z: float | None = None
    #: 원자재 방향 × 사업 방향 → 기대 효과 (+수혜 / -피해), 실제 반응과의 일치
    expected_effect: Direction = "flat"
    agreement: Literal["confirmed", "muted", "mismatch", "unknown"] = "unknown"


class CommodityImpactRow(Base):
    commodity_id: str
    label: str
    z: float
    change_1d_display: str
    change_1w: float | None = None
    industries: list[str] = Field(default_factory=list)
    links: list[CommodityStockLink] = Field(default_factory=list)
    rollover_suspect: bool = False
    note: str = ""


class ThemeStockRow(Base):
    theme_id: str
    theme_name: str
    theme_score: float
    news_sentiment: float | None = None
    stocks: list[StockRow] = Field(default_factory=list)
    #: 테마 방향과 종목 평균 반응의 일치
    agreement: Literal["confirmed", "muted", "mismatch", "unknown"] = "unknown"


# ──────────────────────────────────────────────────────────
# 해설 · 종목 상세 · 워치리스트
# ──────────────────────────────────────────────────────────
class CommentarySections(Base):
    fact: list[str] = Field(default_factory=list, description="데이터로 확인된 사실")
    news: list[str] = Field(default_factory=list, description="기사·공시 내용")
    analyst: list[str] = Field(default_factory=list, description="리서치 의견")
    interpretation: list[str] = Field(default_factory=list, description="데이터를 결합한 해석")
    unknown: list[str] = Field(default_factory=list, description="근거 부족")


class Commentary(Base):
    kind: Literal["market", "stock", "alternative", "analyst"]
    entity: str
    date: str
    as_of: datetime
    created_at: datetime
    source_mode: Literal["manual", "api", "none"] = "manual"
    confidence: Confidence = "MEDIUM"
    sections: CommentarySections = Field(default_factory=CommentarySections)
    evidence: list[Evidence] = Field(default_factory=list)
    what_next: list[str] = Field(default_factory=list)
    stale: bool = False


class StockIntelligence(Base):
    meta: StockMeta
    feature: StockFeature | None = None
    row: StockRow
    headline_what: str = ""
    headline_why: str = ""
    headline_changed: str = ""
    headline_next: str = ""
    exposure: StockExposure | None = None
    impacts: list[StockImpact] = Field(default_factory=list)
    explanation: StockExplanation | None = None
    anomaly: StockAnomaly | None = None
    divergences: list[StockDivergence] = Field(default_factory=list)
    analyst: AnalystSnapshot | None = None
    peers: list[AltDataPoint] = Field(default_factory=list)
    alternative: list[AltDataPoint] = Field(default_factory=list)
    theme_scores: dict[str, float] = Field(default_factory=dict)
    lead_lag: list[LeadLag] = Field(default_factory=list)
    commentary: Commentary | None = None
    missing: list[str] = Field(default_factory=list)


Badge = Literal[
    "NEW_EVENT", "FLOW_INFLECTION", "EPS_REVISION", "ANALYST_CHANGE", "ALTERNATIVE_DATA_SIGNAL",
    "COMMODITY_IMPACT", "UNUSUAL_MOVE", "THEME_STRENGTHENING", "THEME_WEAKENING",
]


class WatchlistRow(Base):
    stock_id: str
    name: str
    sector: str
    price: float | None = None
    change_1d: float | None = None
    change_1w: float | None = None
    volume_z: float | None = None
    flow_z: float | None = None
    theme: str | None = None
    theme_score: float | None = None
    macro_impact: float | None = None
    macro_driver: str | None = None
    alt_signal: str | None = None
    eps_revision_1m: float | None = None
    analyst_change: str | None = None
    unusual: AnomalyLabel = "NONE"
    badges: list[Badge] = Field(default_factory=list)
    commentary_excerpt: str | None = None


class IntelligenceHealth(Base):
    mode: DataMode
    stocks_expected: int = 0
    stocks_available: int = 0
    alt_expected: int = 0
    alt_available: int = 0
    stale: list[str] = Field(default_factory=list)
    not_available: list[str] = Field(default_factory=list, description="확보하지 못한 데이터와 이유")
    warnings: list[str] = Field(default_factory=list)
    timings_ms: dict[str, float] = Field(default_factory=dict)


class InvestmentIntelligence(Base):
    as_of: datetime
    mode: DataMode
    scenario: str | None = None
    drivers: list[DriverCard] = Field(default_factory=list)
    alternative: list[AltDataPoint] = Field(default_factory=list)
    market_stock_impact: list[StockImpact] = Field(default_factory=list)
    semiconductor: SemiconductorIntelligence = Field(default_factory=SemiconductorIntelligence)
    commodity_impact: list[CommodityImpactRow] = Field(default_factory=list)
    unusual_movers: list[StockAnomaly] = Field(default_factory=list)
    theme_stocks: list[ThemeStockRow] = Field(default_factory=list)
    analyst: list[AnalystSnapshot] = Field(default_factory=list)
    fundamental_divergences: list[StockDivergence] = Field(default_factory=list)
    stocks: dict[str, StockIntelligence] = Field(default_factory=dict)
    watchlist: list[WatchlistRow] = Field(default_factory=list)
    lead_lag: list[LeadLag] = Field(default_factory=list)
    commentary: list[Commentary] = Field(default_factory=list)
    health: IntelligenceHealth
    engine_versions: dict[str, str] = Field(default_factory=dict)
