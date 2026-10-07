"""
AI Trade Intelligence — AI 탭의 응답 모델.

시장 온도·공포/탐욕 같은 broad-market 감성이 아니라 'AI 트레이드 자체' 를 잰다. 절대 수익이 아니라
Nasdaq 100 / S&P 500 대비 상대 수익·상대 z 가 축이고, 점수는 확률이 아니라 증거 크기다.
결측은 0 이 아니다 — 계열이 없으면 None 과 note 로 남는다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, PrivateAttr

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


class PriceCheck(Base):
    label: str
    value: str


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
    # ── 표시 층 (2026-09-30): 점수의 질적 라벨 · 한 줄 의미 · 시장 → AI 연결 · 가격 확인 · 상태 뜻. 점수 계산은 바꾸지 않는다 ──
    band: str = ""
    band_ko: str = ""
    why: str = ""
    transmission: list[str] = Field(default_factory=list)
    price_check: list[PriceCheck] = Field(default_factory=list)
    status_ko: str = ""
    status_meaning: str = ""
    aux_label: str = ""
    aux_ko: str = ""
    top_evidence: list[str] = Field(default_factory=list)


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
    read: str = Field(default="", description="BASKET READ — 진짜 leadership 인지 · 상대강도의 질 · 구조적 laggard. 최대 3문장, 숫자 나열 없음")


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
    # ── 표시 층 (2026-09-30): 4개 핵심 판단 + 상대성과 읽기. 값은 위 수치의 재표현이다 ──
    absolute_trend: str = ""
    absolute_ko: str = ""
    absolute_text: str = ""
    relative_trend: str = ""
    relative_ko: str = ""
    relative_text: str = ""
    relative_z_text: str = ""
    relative_z_ko: str = ""
    market_read_label: str = ""
    market_read: str = ""
    relative_read: str = ""
    connector: str = ""
    connector_ko: str = ""


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
    read: str = Field(default="", description="BREADTH READ — 단기 확산 · 중기 추세 · 다음 확인 포인트. 최대 3문장, 숫자 나열 없음")


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


Arrow = Literal["↑↑", "↑", "→", "↓", "↓↓", "?"]
StageStatus = Literal["ACCELERATING", "POSITIVE", "STRONG", "IMPROVING", "STABLE", "MIXED", "DETERIORATING", "UNCONFIRMED"]
AreaStatus = Literal["STRONG", "LEADING", "IMPROVING", "MIXED", "NEUTRAL", "WEAK", "UNCONFIRMED"]


class StatusItem(Base):
    key: str
    label: str
    value: str
    tone: Literal["good", "warn", "bad", "muted"] = "muted"
    detail: str = ""
    meaning: str = Field(default="", description="이 상태가 지금 시장에서 뜻하는 것 — 한 줄 한국어(번역이 아니라 투자적 의미)")


class FundamentalConfirmation(Base):
    level: Literal["STRONG", "PARTIAL", "WEAK", "UNCONFIRMED"] = "UNCONFIRMED"
    confirming: list[str] = Field(default_factory=list)
    lagging: list[str] = Field(default_factory=list)
    sentence: str = ""


class TransmissionStage(Base):
    key: str
    label: str
    status: StageStatus
    score: float | None = Field(default=None, description="−100…+100 증거 점수. 없으면 None")
    evidence: str = ""
    basis: list[str] = Field(default_factory=list, description="실제로 점수에 들어간 근거 유형 — NEWS(기사 톤) · PRICE(세그먼트 상대강도) · DATA(메모리 데이터 · EPS). 결측 입력은 빼고 적는다")


class Transmission(Base):
    stages: list[TransmissionStage] = Field(default_factory=list)
    sentence: str = ""


class SegmentRow(Base):
    key: str
    label: str
    label_ko: str
    exposure: str
    members: int
    available: int
    ret_1d: float | None = None
    ret_5d: float | None = None
    ret_21d: float | None = None
    rel_1d: float | None = None
    rel_5d: float | None = None
    rel_21d: float | None = None
    rel_z_5d: float | None = None
    above_ma20_pct: float | None = None
    eps: float | None = Field(default=None, description="구성원 EPS revision 평균(%). 컨센서스 없으면 None")
    eps_note: str = ""
    arrow_1w: Arrow = "?"
    arrow_rel: Arrow = "?"
    arrow_eps: Arrow = "?"
    rank_1w: int | None = None
    role: Literal["leading", "neutral", "lagging", "unknown"] = "unknown"
    macro_score: float | None = None


class ValueChain(Base):
    segments: list[SegmentRow] = Field(default_factory=list)
    leadership: list[str] = Field(default_factory=list)
    lagging: list[str] = Field(default_factory=list)
    sentence: str = ""


class SemiArea(Base):
    key: str
    label: str
    status: AreaStatus
    price_momentum: Arrow = "?"
    relative_strength: Arrow = "?"
    breadth: Arrow = "?"
    news_evidence: Arrow = "?"
    eps: Arrow = "?"
    detail: str = ""


class MemoryRow(Base):
    id: str
    label: str
    structural: bool = False
    value: float | None = None
    unit: str = "price"
    change_1d: float | None = None
    change_1w: float | None = None
    change_1m: float | None = None
    z: float | None = None
    observations: int = 0
    frequency: str = "daily"
    freshness_days: int | None = None
    quality: str = "MISSING"
    status: Literal["STRONG", "IMPROVING", "NEUTRAL", "DETERIORATING", "N/A"] = "N/A"
    note: str = ""


class SemiConfirmation(Base):
    areas: list[SemiArea] = Field(default_factory=list)
    memory: list[MemoryRow] = Field(default_factory=list)
    sentence: str = ""


class StockAxis(Base):
    key: Literal["theme", "fundamental", "market", "macro"]
    value: float | None = None
    arrow: Arrow = "?"
    detail: str = ""


class StockImpactRow(Base):
    id: str
    name: str
    segments: list[str] = Field(default_factory=list)
    region: str = "US"
    available: bool = True
    theme_exposure: str = "MEDIUM"
    axes: list[StockAxis] = Field(default_factory=list)
    ai_demand: str = "–"
    semiconductor: str = "–"
    relative_strength: str = "–"
    news_flow: str = "–"
    eps_revision: str = "N/A"
    rates_sensitivity: str = "–"
    overall: Literal["STRONG", "CONFIRMED", "MIXED", "UNCONFIRMED", "NEGATIVE PRESSURE", "NO DATA"] = "NO DATA"
    confirmation: Literal["CONFIRMED", "NEWS POSITIVE / MARKET UNCONFIRMED", "FUNDAMENTALS / PRICE LEADING NARRATIVE", "MIXED", "NEGATIVE", "NO DATA"] = "NO DATA"
    ret_5d: float | None = None
    rel_5d: float | None = None
    ret_21d: float | None = None
    mentions: int = 0
    interpretation: str = ""


class RadarBucket(Base):
    key: Literal["strongest", "improving", "narrative_ahead", "fundamentals_ahead", "macro_pressure"]
    label: str
    items: list[dict[str, str]] = Field(default_factory=list, description="[{id, name, reason}]")


class NewsImpact(Base):
    event: str
    source: str
    url: str | None = None
    tone: float
    drivers: list[str] = Field(default_factory=list)
    primary: list[str] = Field(default_factory=list)
    secondary: list[str] = Field(default_factory=list)
    infrastructure: list[str] = Field(default_factory=list)
    primary_stocks: list[str] = Field(default_factory=list)
    secondary_stocks: list[str] = Field(default_factory=list)
    infrastructure_stocks: list[str] = Field(default_factory=list)
    confirmation: str = ""


class GapRow(Base):
    key: str
    label: str
    market_pricing: float | None = None
    fundamental: float | None = None
    gap: float | None = None
    note: str = ""


class MattersItem(Base):
    key: str
    text: str
    status: Literal["CONFIRMING", "WATCH", "DETERIORATING", "N/A"]
    metric: str
    current: str
    detail: str = ""


class SentimentInput(Base):
    id: str
    label: str
    label_ko: str = ""
    component: str
    value: float | None = None
    display: str = "–"
    score: float | None = Field(default=None, ge=0.0, le=100.0, description="0~100 (50 = 중립). 결측이면 None")
    weight: float = 1.0
    available: bool = True
    note: str = ""


class SentimentComponent(Base):
    key: str
    label: str
    label_ko: str
    score: float | None = None
    state: str = "UNKNOWN"
    state_label: str = "–"
    read: str = ""
    weight: float
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    inputs: list[SentimentInput] = Field(default_factory=list)
    desc_ko: str = Field(default="", description="구성요소가 무엇을 재는지 한 줄")


class SentimentFactor(Base):
    id: str
    label: str
    label_ko: str = ""
    component: str
    score: float
    display: str = ""


class SentimentPoint(Base):
    date: str
    index: float | None = None
    components: dict[str, float | None] = Field(default_factory=dict)
    #: Daily snapshot 출처 (2026-10-07): RECORDED · BACKFILLED · LIVE, 또는 RECOMPUTED(엔진 내부 재생 — 저장 sequence 로 대체되기 전)
    source: str = "RECOMPUTED"
    state: str = ""
    calculated_at: str = ""
    model_version: str = ""
    coverage: float | None = None
    missing: list[str] = Field(default_factory=list)


class SentimentHistory(Base):
    points: list[SentimentPoint] = Field(default_factory=list)
    basis: list[str] = Field(default_factory=list, description="1M 이력을 만든 구성요소 — 이력이 없는 구성요소는 뺀다")
    excluded: dict[str, str] = Field(default_factory=dict)
    days: int = 0
    range_min: float | None = None
    range_max: float | None = None
    change_1d: float | None = None
    change_1w: float | None = None
    note: str = ""
    state_1w: str = ""
    read: str = Field(default="", description="1주 변화의 뜻 한 줄")
    history_mode: str = Field(default="recomputed", description="stored = 저장된 daily snapshot sequence · recomputed = 같은 공식을 하루씩 되돌린 값")
    recorded_days: int = 0
    backfilled_days: int = 0
    footnote: str = ""


class AiSentiment(Base):
    """AI SENTIMENT · GREED & FEAR — AI 테마 내부의 투자심리 + 시장 확인 강도. 확률·전망이 아니라 현재 상태(0~100)."""

    #: daily snapshot backfill 이 쓰는 날짜별 입력 계산기(DayValues). 직렬화되지 않는다.
    _day_values: object = PrivateAttr(default=None)
    index: float | None = Field(default=None, ge=0.0, le=100.0)
    state: str = "UNKNOWN"
    state_label: str = "–"
    state_ko: str = ""
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    components: list[SentimentComponent] = Field(default_factory=list)
    secondary_key: str = "none"
    secondary_label: str = ""
    secondary_ko: str = ""
    read: str = Field(default="", description="AI SENTIMENT READ — 최대 2문장")
    gap_read: str = Field(default="", description="KEY TENSION 아래 한 문장 — 구성요소 단위 지지/미확인")
    net_effect: str = Field(default="", description="SUPPORT vs PRESSURE 의 순효과 한 줄")
    support: list[SentimentFactor] = Field(default_factory=list)
    pressure: list[SentimentFactor] = Field(default_factory=list)
    history: SentimentHistory = Field(default_factory=SentimentHistory)
    bands: list[dict[str, str | float]] = Field(default_factory=list)
    note: str = ""


class ChainRow(Base):
    """FUNDAMENTAL × PRICE 한 행 — 전파 단계(펀더멘털)와 밸류체인 세그먼트(가격)를 잇는다."""

    key: str
    label: str
    segment: str
    segment_label: str = ""
    stage: str | None = None
    fund_status: str = "UNCONFIRMED"
    fund_score: float | None = None
    price_status: str = "MIXED"
    rank: int | None = None
    rel_5d: float | None = None
    breadth: float | None = None
    view: str = "MIXED"
    view_ko: str = ""


class ChainStage(Base):
    key: str
    label: str
    status: str
    score: float | None = None
    evidence: str = ""
    basis: list[str] = Field(default_factory=list)


class ChainSemiArea(Base):
    key: str
    label: str
    status: str
    meaning: str = ""
    key_evidence: list[str] = Field(default_factory=list)
    arrows: dict[str, str] = Field(default_factory=dict)


class ChainSnapshot(Base):
    fundamentals: str = ""
    fundamentals_ko: str = ""
    price_leadership: str = ""
    semi_confirmation: str = ""
    key_gap: str = ""
    read: str = ""


class ChainView(Base):
    """AI CHAIN VIEW — SNAPSHOT → FUNDAMENTAL × PRICE → TRANSMISSION → LEADERSHIP → SEMI CONFIRMATION. 계산 없음, 재표현만."""

    snapshot: ChainSnapshot = Field(default_factory=ChainSnapshot)
    subtitles: dict[str, str] = Field(default_factory=dict)
    score_tip: str = ""
    rows: list[ChainRow] = Field(default_factory=list)
    main_rows: int = 6
    views: dict[str, str] = Field(default_factory=dict)
    stages: list[ChainStage] = Field(default_factory=list)
    fundamental_read: str = ""
    leaders: list[ChainRow] = Field(default_factory=list)
    laggards: list[ChainRow] = Field(default_factory=list)
    leadership_read: str = ""
    semi_areas: list[ChainSemiArea] = Field(default_factory=list)
    semi_columns: list[dict[str, str]] = Field(default_factory=list)


class StockSignal(Base):
    """STOCK IMPACT MAP 한 행 — 왜 이 종목이 눈에 띄는가 하나만. 기본 화면용 압축 + 클릭 상세."""

    id: str
    name: str
    segment: str
    segment_ko: str = ""
    region: str = "US"
    ret_5d: float | None = None
    rel_5d: float | None = None
    ret_21d: float | None = None
    label: str = "IN LINE"
    label_ko: str = ""
    signal: str = ""
    signal_value: str = ""
    fundamental: str = "N/A"
    macro: str = "N/A"
    news: str = ""
    tension: str = ""
    read: str = ""
    what_changed: str = ""
    price_relative: str = ""
    fundamentals: str = ""
    news_sentiment: str = ""
    macro_exposure: str = ""
    watch: list[str] = Field(default_factory=list)
    rank_value: float = 0.0


class RadarItem(Base):
    id: str
    name: str
    segment: str
    relative: str = "–"
    price: str = "N/A"
    fundamental: str = "N/A"
    why_watch: str = ""
    detail: str = ""


class RadarBucketView(Base):
    key: str
    label: str
    desc: str
    items: list[RadarItem] = Field(default_factory=list)


class NewsCard(Base):
    event: str
    source: str
    url: str | None = None
    tone: float
    impact: str = "NEUTRAL"
    category: str = ""
    primary: list[str] = Field(default_factory=list)
    secondary: list[str] = Field(default_factory=list)
    tertiary: list[str] = Field(default_factory=list)
    key_stocks: list[str] = Field(default_factory=list)
    all_stocks: list[str] = Field(default_factory=list)
    reaction: str = "UNCLEAR"
    reaction_ko: str = ""
    reaction_read: str = ""
    why: str = ""
    cluster_size: int = 1
    priority: float = 0.0
    _drivers: list[str] = PrivateAttr(default_factory=list)


class StockView(Base):
    """STOCK IMPACT MAP · STOCK RADAR · NEWS 의 표시 층 — 계산 없음, 선별·라벨·문장만."""

    impact_subtitle: str = ""
    signals: list[StockSignal] = Field(default_factory=list, description="TOP STOCK SIGNALS — anomaly 가 있는 종목, 강도 순")
    all_signals: list[StockSignal] = Field(default_factory=list, description="전체 종목(계열 있는 것) — View all")
    label_legend: dict[str, str] = Field(default_factory=dict)
    radar_subtitle: str = ""
    radar: list[RadarBucketView] = Field(default_factory=list)
    radar_default: int = 3
    news_subtitle: str = ""
    news_top: list[NewsCard] = Field(default_factory=list)
    news_others: list[NewsCard] = Field(default_factory=list)
    news_others_default: int = 6
    news_legend: dict[str, str] = Field(default_factory=dict)
    note: str = ""


class DriverRef(Base):
    id: str
    label: str
    score: float
    status: str
    role: str
    rank_value: float = 0.0


class DriverVerdict(Base):
    """DRIVER VERDICT — AI vs MARKET 의 차이를 어떤 driver 가 설명하는가. 순위는 |score| × 확인 가중 × 확보율."""

    gap_label: str = ""
    gap_value: str = ""
    gap_question: str = ""
    primary: DriverRef | None = None
    secondary: DriverRef | None = None
    offset: list[DriverRef] = Field(default_factory=list)
    unconfirmed: list[DriverRef] = Field(default_factory=list)
    conclusion: str = ""
    method: str = ""
    score_legend: dict[str, str] = Field(default_factory=dict)
    status_meaning: dict[str, str] = Field(default_factory=dict)


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
    # ── 확장 층 (2026-09-29 (6)): 펀더멘털 확인 · 전파 체인 · 밸류체인 · 종목 영향도 ──
    regime_subtitle: str = ""
    status_strip: list[StatusItem] = Field(default_factory=list)
    fundamental_confirmation: FundamentalConfirmation = Field(default_factory=FundamentalConfirmation)
    summary: str = ""
    transmission: Transmission = Field(default_factory=Transmission)
    value_chain: ValueChain = Field(default_factory=ValueChain)
    semi_confirmation: SemiConfirmation = Field(default_factory=SemiConfirmation)
    stocks: list[StockImpactRow] = Field(default_factory=list)
    radar: list[RadarBucket] = Field(default_factory=list)
    news_impact: list[NewsImpact] = Field(default_factory=list)
    expectation_gap: list[GapRow] = Field(default_factory=list)
    what_matters: list[MattersItem] = Field(default_factory=list)
    # ── AI SENTIMENT · GREED & FEAR (2026-09-30) ──
    sentiment: AiSentiment | None = None
    regime_read: str = Field(default="", description="AI REGIME READ — FUNDAMENTAL CONFIRMATION · SUMMARY · 맥락을 대신하는 2~3문장")
    driver_verdict: DriverVerdict = Field(default_factory=DriverVerdict)
    chain_view: ChainView = Field(default_factory=ChainView)
    stock_view: StockView = Field(default_factory=StockView)
