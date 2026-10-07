"""
실시간 메인 탭 — decision cockpit 응답 모델.

기존 층(판정·테마·괴리·뉴스·Investment·AI/금리/유가 판별)의 값을 다시 계산하지 않고 우선순위대로 고른 것이다.
REGIME → DRIVERS → CONFIRMATION → LEADERSHIP → TRANSMISSION → CATALYSTS → RISKS / WATCH.
확률 표현 없음. 데이터가 없으면 None/빈 목록 — 화면은 그 카드를 숨긴다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from .common import Base

Arrow = Literal["↑↑", "↑", "→", "↓", "↓↓", "?"]
PathStatus = Literal["CONFIRMED", "PARTIAL", "UNCONFIRMED", "CONTRADICTED", "DATA MISSING"]


class KeyVariable(Base):
    id: str
    label: str
    z: float
    arrow: Arrow
    change_display: str = ""


class SparkPoint(Base):
    date: str
    label: str


class MarketNow(Base):
    label: str
    secondary: str | None = None
    label_text: str
    conviction: Literal["HIGH", "MEDIUM", "LOW"]
    confidence: float
    persistence_days: int = 0
    previous_label: str | None = None
    change_text: str = ""
    key_variables: list[KeyVariable] = Field(default_factory=list)
    sentence: str
    interpretation: str = Field(default="", description="2~3문장 — 판정 엔진의 템플릿 서술")
    spark: list[SparkPoint] = Field(default_factory=list)
    last_update: datetime
    coverage: str = ""
    latency: str = ""


class EvidenceRow(Base):
    id: str
    label: str
    z: float | None = None
    display: str = ""
    context: bool = Field(default=False, description="점수에 안 들어가는 참고 값(예: BE10Y)")
    available: bool = True


class Driver(Base):
    key: str
    label: str
    label_ko: str
    direction: Literal["up", "down"]
    arrow: Arrow
    strength: float = Field(description="−1…+1 가중 clip 평균")
    importance: float
    coverage: float
    confirmed_by_regime: bool = False
    persistent: bool = False
    news_tone: float | None = None
    evidence: list[EvidenceRow] = Field(default_factory=list)
    why: str
    source: Literal["market", "alternative"] = "market"


class CrossAssetRow(Base):
    key: str
    label: str
    instrument: str
    instrument_label: str = Field(default="", description="대표 지표 이름 — 'S&P 500', 'US HY OAS'")
    group: Literal["RISK", "MACRO", "COMMODITY"] = "RISK"
    z: float | None = None
    arrow: Arrow
    status: Literal["CONFIRM", "DIVERGE", "HEADWIND", "FLAT", "NEUTRAL", "MISSING"]
    note: str = ""
    meaning: str = Field(default="", description="영어 상태값 옆의 짧은 한글 의미 — 지금 판정 기준")


class KeyDivergence(Base):
    title: str
    meaning: str
    severity: float
    source: Literal["divergence", "rates_regime", "oil_regime"] = "divergence"
    assets: list[str] = Field(default_factory=list)
    phenomenon: str = Field(default="", description="현상 한 줄 — 'VIX 는 상승했지만 금은 오히려 하락'")
    why: str = Field(default="", description="왜 중요한가")
    reference: list[str] = Field(default_factory=list, description="통계 근거 — 'Expected relationship +70', 'Recent correlation −45'")


class CrossAsset(Base):
    rows: list[CrossAssetRow] = Field(default_factory=list)
    confirm: int = 0
    evaluated: int = 0
    sentence: str = ""
    current_view: str = Field(default="", description="지금 검증하는 판정 — 'LIQUIDITY STRESS / RISK-OFF'")
    regime_short: str = Field(default="", description="문장용 짧은 이름 — 'Risk-Off'")
    confirm_text: str = Field(default="", description="'7개 주요 자산군 중 5개가 현재 Risk-Off 판단과 같은 방향'")
    market_read: str = Field(default="", description="MARKET READ — 표 앞에 오는 1~2문장")
    divergences: list[KeyDivergence] = Field(default_factory=list)
    total_divergences: int = 0


class ConfirmRow(Base):
    key: str
    label: str
    value: str = ""
    status: PathStatus = "DATA MISSING"
    meaning: str = ""


class StreetView(Base):
    institution: str
    analyst: str = Field(default="", description="확인된 경우에만")
    published_date: str
    source_url: str
    source_title: str = ""
    quote: str = Field(default="", description="원문 한 줄(있으면)")
    summary: str = Field(description="무엇을 핵심 driver 로 보는가 — 1~2줄 요약")
    stance: Literal["constructive", "cautious", "neutral", "mixed"] = "neutral"
    key_variables: list[str] = Field(default_factory=list)
    age_days: int = 0
    freshness: str = ""
    retrieved_by: Literal["manual", "llm_web"] = "manual"


class KeyStock(Base):
    id: str
    name: str
    role: str = Field(default="", description="'Equipment leader'")
    note: str = Field(default="", description="'relative strength ↑'")
    in_radar: bool = False
    z: float | None = None


class LeadershipDetail(Base):
    why: list[str] = Field(default_factory=list, description="WHY LEADING? 1~3개 — 시장 데이터 기반")
    confirmation: list[ConfirmRow] = Field(default_factory=list, description="PRICE / RELATIVE STRENGTH / BREADTH / NEWS / FUNDAMENTAL / FLOW")
    system_view: str = ""
    driver: str = ""
    quality: str = ""
    quality_ko: str = ""
    quality_detail: str = ""
    risk: str = ""
    street: list[StreetView] = Field(default_factory=list, description="확인된 외부 view 만 — 없으면 빈 목록(영역 숨김)")
    street_read: str = Field(default="", description="여러 기관 견해가 갈릴 때 SYSTEM READ")
    key_stocks: list[KeyStock] = Field(default_factory=list)
    watch: list[str] = Field(default_factory=list)


class LeaderRow(Base):
    key: str
    label: str
    kind: Literal["theme", "sector"]
    z_1d: float | None = None
    rel_1w: float | None = None
    breadth: float | None = None
    arrow: Arrow
    instruments: int = 0
    available: int = 0
    system_view: str = Field(default="", description="기본 화면 한 줄")
    detail: LeadershipDetail | None = None


class ThemePulseRow(Base):
    theme_id: str
    name: str
    price: Arrow
    news: Arrow
    rel: Arrow
    theme_score: float
    news_sentiment: float | None = None
    price_momentum: float | None = None
    rel_1w: float | None = None
    why: str = ""


class Leadership(Base):
    leaders: list[LeaderRow] = Field(default_factory=list)
    laggards: list[LeaderRow] = Field(default_factory=list)
    all_rows: list[LeaderRow] = Field(default_factory=list)
    pulse: list[ThemePulseRow] = Field(default_factory=list)
    sentence: str = ""
    read: str = Field(default="", description="LEADERSHIP READ — 판정 · 크로스에셋 · 상대강도 · breadth 종합 한두 문장")


class TransmissionStock(Base):
    id: str
    name: str
    status: Literal["CONFIRMED", "UNCONFIRMED", "CONTRADICTED", "NO DATA"]
    z: float | None = None
    change_1d: float | None = None
    note: str = ""
    industry: str = Field(default="", description="전파 read 용 산업/세그먼트 표시 이름")


class TransmissionChain(Base):
    driver_key: str
    driver_label: str
    arrow: Arrow
    mechanism: str
    industries: list[str] = Field(default_factory=list)
    stocks: list[TransmissionStock] = Field(default_factory=list)
    confirmed: int = 0
    source: Literal["driver", "commodity"] = "driver"
    evaluated: int = Field(default=0, description="NO DATA 를 뺀 종목 수")
    strength: Literal["STRONG", "PARTIAL", "LIMITED", "UNCONFIRMED"] = "UNCONFIRMED"
    strength_ko: str = ""
    read: str = Field(default="", description="TRANSMISSION READ — 1~2문장, 지금 데이터만")


class SystemAxis(Base):
    key: str
    label: str
    arrow: Arrow
    detail: str = ""


class RadarStock(Base):
    id: str
    name: str
    change_1d: float | None = None
    tag: str
    why: str
    kind: Literal["why", "watch"] = "why"
    score: float
    signals: list[str] = Field(default_factory=list)
    #: 시스템 판단(THEME / FUNDAMENTAL / MARKET / MACRO 등) — 외부 ANALYST VIEW 와 나란히 두되 섞지 않는다
    system_axes: list[SystemAxis] = Field(default_factory=list)
    #: 이 종목이 등장하는 WHAT MATTERS NEXT 이슈 id — MARKET ISSUE ↔ STOCK 양방향
    related_issues: list[str] = Field(default_factory=list)


class CatalystItem(Base):
    id: str
    time: str
    tag: str
    headline: str
    level: Literal["CRITICAL", "HIGH", "MEDIUM"]
    kind: Literal["news", "alert"] = "news"
    impact: str = ""
    confidence: str = ""
    cluster_size: int = 1
    cluster_titles: list[str] = Field(default_factory=list)
    why: str = ""
    related_assets: list[str] = Field(default_factory=list)
    related_stocks: list[str] = Field(default_factory=list)
    price_confirmation: str = ""
    url: str | None = None
    source: str = ""
    importance: float = 0.0


class EarningsPulse(Base):
    rows: list[dict[str, str]] = Field(default_factory=list)
    note: str = ""




class PathCheck(Base):
    label: str
    id: str = ""
    kind: Literal["instrument", "segment", "theme"] = "instrument"
    expect: int = Field(description="기대 부호 +1 / −1")
    observed: float | None = None
    observed_text: str = ""
    status: PathStatus = "DATA MISSING"


class PathStage(Base):
    key: str
    label: str
    text: list[str] = Field(default_factory=list)
    checks: list[PathCheck] = Field(default_factory=list)
    status: PathStatus = "DATA MISSING"
    explain: str = Field(default="", description="영어 단계명 아래 한글 — 왜 이 단계로 연결되는가")


class PathStock(Base):
    id: str
    name: str
    expect: int
    arrow: Literal["↑", "↓"] = "↓"
    z: float | None = None
    change_1d: float | None = None
    status: PathStatus = "DATA MISSING"
    segment: str = ""
    in_radar: bool = False
    note: str = ""
    expected_text: str = Field(default="", description="'↓ 금리 상승 시 약세 예상'")
    priority: float = Field(default=0.0, description="메인 노출 우선순위 — radar → |z| → 뚜렷한 확인 → 중요한 contradiction")


class PathSummary(Base):
    main_impact: list[str] = Field(default_factory=list, description="'장기금리 상승 → 실질금리 / 할인율 상승 → 고 duration 자산 부담'")
    stages_confirmed: int = 0
    stages_total: int = 0
    stages_text: str = ""
    most_exposed: list[str] = Field(default_factory=list)
    exception: list[str] = Field(default_factory=list, description="RELATIVE EXCEPTION — 예상과 반대로 버티는 것")
    observed_read: str = Field(default="", description="EXPECTED vs OBSERVED 한 줄 해석")
    confirm_read: str = Field(default="", description="WHAT WOULD CONFIRM 한 줄 해석")


class PathTier(Base):
    tier: Literal["DIRECT", "SECONDARY", "TERTIARY"]
    stocks: list[PathStock] = Field(default_factory=list)


class IssuePath(Base):
    """예상 전파(EXPECTED) 와 지금 관측(OBSERVED) 을 단계별로 나란히 둔다. 교과서 매핑을 확정하지 않는다."""

    trigger: PathStage
    first_order: PathStage
    assets: PathStage
    themes: PathStage
    tiers: list[PathTier] = Field(default_factory=list)
    tier_max: int = 5
    expected: str = ""
    observed: str = ""
    conclusion: str = ""
    confirm: list[PathCheck] = Field(default_factory=list, description="WHAT WOULD CONFIRM? 체크리스트")
    confirm_count: int = 0
    source: Literal["config", "ai_value_chain"] = "config"
    summary: PathSummary | None = None
    tier_show: dict[str, int] = Field(default_factory=dict, description="메인에 보이는 tier 당 종목 수(0 = 접기)")


class Horizon(Base):
    key: Literal["1D", "5D", "1M"]
    z: float | None = None
    arrow: Arrow = "?"


class NextItem(Base):
    id: str = ""
    text: str
    status: Literal["CONFIRMING", "WATCH", "REVERSING"]
    metric: str
    current: str
    driver_key: str
    path: IssuePath | None = None
    horizons: list[Horizon] = Field(default_factory=list, description="같은 지표의 1D · 5D · 1M z — 기간을 늘 함께 보여준다")
    horizon_read: str = Field(default="", description="'오늘은 일부 되돌렸지만 최근 5일 상승 흐름은 유지'")
    why_next: str = Field(default="", description="닫힌 상태에서도 보이는 WHY IT MATTERS 한 줄")


class UpcomingEvent(Base):
    date: str
    label: str
    days_until: int | None = None
    verified: bool = True


class WatchLink(Base):
    key: str
    label: str


class WatchRow(Base):
    id: str
    name: str
    change_1d: float | None = None
    watch: str = ""
    indicators: list[str] = Field(default_factory=list)
    theme: str = Field(default="", description="'HBM / Semiconductor'")
    why: str = Field(default="", description="WHY WATCH — 1~2줄, 지금 데이터")
    key_drivers: list[str] = Field(default_factory=list, description="최대 3")
    trigger: str = Field(default="", description="무엇이 나타나면 다시 판단하는가 — 시스템 임계가 없으면 숫자 없음")
    reasons: list[str] = Field(default_factory=list, description="WATCH REASON 태그 ≤3 — NEWS · THEME · MACRO · FUNDAMENTAL · DIVERGENCE · ALT DATA · TRANSMISSION")
    priority: Literal["HIGH", "MEDIUM"] = "MEDIUM"
    transmission: list[WatchLink] = Field(default_factory=list, description="이 종목이 등장하는 MARKET → STOCK TRANSMISSION 체인")
    issues: list[WatchLink] = Field(default_factory=list, description="이 종목이 등장하는 WHAT MATTERS NEXT 이슈")
    commentary: str = Field(default="", description="펼침 — 수기 해설 발췌(있을 때)")
    eps_revision: float | None = None


class DataStatus(Base):
    line: str
    warnings: list[str] = Field(default_factory=list)
    coverage: float
    available: int
    expected: int
    stale: int
    max_lag_days: int
    news_judgment: str = ""


# ── MARKET REGIME HISTORY · 1M (실시간 2 전용 히스토리 층) ─────────────────────
class RegimeDay(Base):
    """거래일별 regime 스냅샷. raw(순간 판정)와 display(안정화) 를 같은 줄에 둔다 — 시각화를 위해 데이터를 왜곡하지 않는다."""

    date: str
    raw_state: str = Field(description="재생 엔진의 그날 마지막 판정(StateLabel)")
    raw_secondary: str | None = None
    dominant_regime: str = Field(description="taxonomy key — 그날 가장 오래 유지된 regime(장중 관측이 없으면 raw 와 같다)")
    end_regime: str = Field(description="taxonomy key — 그날 마지막 관측 regime")
    display_regime: str = Field(description="taxonomy key — 안정화된 화면용 regime")
    display_label: str
    evidence_strength: float = Field(ge=0.0, le=100.0, description="그날 판정 확신")
    dominant_driver: str = Field(default="", description="그날 주도 변수 1 — '라벨 +1.2σ'")
    top_driver_1: str = ""
    top_driver_2: str = ""
    top_evidence: list[str] = Field(default_factory=list)
    dominant_regime_dwell: float | None = Field(default=None, description="하루 중 dominant regime 이 유지된 비중 0~1. 장중 관측이 2회 미만이면 None")
    observations: int = Field(default=1, description="그날 장중 관측 수(재생 1회 포함)")
    transition_count: int = Field(default=0, description="그날 장중 raw 판정이 바뀐 횟수")
    key_change: str = Field(default="", description="예: 'Late-session deterioration' — dominant ≠ end 일 때")
    data_quality: str = ""
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    composite: float | None = None
    factors: dict[str, float | None] = Field(default_factory=dict, description="heat strip driver → factor z")
    bridged: bool = Field(default=False, description="raw 가 display 와 달라 직전 display 가 이어진 날")
    source: str = Field(default="RECOMPUTED", description="daily snapshot 출처 — RECORDED · BACKFILLED · LIVE (RECOMPUTED 는 저장 sequence 가 없을 때)")
    calculated_at: str = ""
    model_version: str = ""
    logic_version: str = ""
    locked: bool = False
    is_transition: bool = Field(default=False, description="display regime 이 이날 바뀌었다")


class RegimeBlock(Base):
    regime: str
    label: str
    start: str
    end: str
    days: int
    current: bool = False


class RegimeTransition(Base):
    date: str
    from_regime: str
    from_label: str
    to_regime: str
    to_label: str
    primary_driver: str = Field(default="", description="factor 변화가 가장 큰 driver — 'Credit ↑'")
    confirmation: str = Field(default="", description="그날 주도 변수 1~2 — 'HY OAS ↑ / VIX ↑'")
    evidence: list[str] = Field(default_factory=list, description="클릭 시 상세 — factor 변화·raw 판정·확신")
    evidence_strength: float = 0.0


class DriverHeat(Base):
    key: str
    label: str
    values: list[float | None] = Field(default_factory=list, description="날짜순 factor z (결측 None)")
    current: float | None = None
    arrow: Arrow = "?"
    label_ui: str = Field(default="", description="'Credit Stress'")
    label_ko: str = Field(default="", description="'신용 스트레스'")
    meaning: str = Field(default="", description="현재 경제적 의미 — '신용 스트레스 확대'")
    horizon_label: str = ""
    horizons: list["Horizon"] = Field(default_factory=list, description="대표 계열의 1D / 5D (부호 = factor 방향)")
    horizon_read: str = ""


class RegimeShare(Base):
    regime: str
    label: str
    days: int
    share: float = Field(ge=0.0, le=100.0, description="기간 중 비중 % — 확률이 아니다")


class HistoryRange(Base):
    key: str
    days: int
    available: bool
    reason: str = ""


class RegimeHistory(Base):
    range: str = "1M"
    ranges: list[HistoryRange] = Field(default_factory=list)
    current_regime: str
    current_label: str
    duration_days: int = 0
    previous_regime: str | None = None
    previous_label: str | None = None
    transitions_1m: int = 0
    share_pct: float = Field(default=0.0, description="현재 display regime 의 기간 내 비중 %")
    raw_today: str | None = Field(default=None, description="오늘 raw 판정이 display 와 다를 때 그 라벨")
    days: list[RegimeDay] = Field(default_factory=list)
    blocks: list[RegimeBlock] = Field(default_factory=list)
    composite: list[float | None] = Field(default_factory=list, description="날짜순 대표 composite(온도계 종합, 없으면 가격 온도)")
    composite_current: float | None = None
    composite_slope: float | None = Field(default=None, description="최근 slope_days 변화")
    composite_slope_days: int = 5
    drivers: list[DriverHeat] = Field(default_factory=list)
    share: list[RegimeShare] = Field(default_factory=list)
    transitions: list[RegimeTransition] = Field(default_factory=list, description="최근 것부터 max 개")
    total_transitions: int = 0
    palette: dict[str, str] = Field(default_factory=dict, description="taxonomy key → 라벨 (화면 순서)")
    history_mode: str = Field(default="recomputed", description="stored = 저장된 daily snapshot sequence · recomputed = 재생")
    recorded_days: int = 0
    backfilled_days: int = 0
    footnote: str = ""
    note: str = ""


class Cockpit(Base):
    as_of: datetime
    market_now: MarketNow
    history: RegimeHistory | None = Field(default=None, description="MARKET REGIME HISTORY · 1M — 히스토리 재생이 없으면 None(카드 숨김)")
    drivers: list[Driver] = Field(default_factory=list)
    cross_asset: CrossAsset
    leadership: Leadership
    transmission: list[TransmissionChain] = Field(default_factory=list)
    radar: list[RadarStock] = Field(default_factory=list)
    catalysts: list[CatalystItem] = Field(default_factory=list)
    earnings: EarningsPulse | None = None
    what_matters_next: list[NextItem] = Field(default_factory=list)
    upcoming: list[UpcomingEvent] = Field(default_factory=list)
    watchlist: list[WatchRow] = Field(default_factory=list)
    data_status: DataStatus
    note: str
