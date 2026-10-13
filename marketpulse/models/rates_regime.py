"""
물가 충격 탭 — Inflation & Rates Intelligence 결과. 판정 룰이 아니라 증거 집계다.
숫자는 config/rates_regime.yaml 의 표에서 나온다. 화면은 만들지 않는다. '확률' 이라는 말은 쓰지 않는다.
"""

from __future__ import annotations

from datetime import date, datetime
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
    start_date: date | None = Field(default=None, description="변화 구간 시작(세 계열 공통 관측일)")
    end_date: date | None = Field(default=None, description="변화 구간 끝(세 계열 공통 관측일)")
    aligned: bool | None = Field(default=None, description="명목·기대인플레·TIPS 를 같은 날짜로 맞춰 쟀나. None = 옛 캡처")


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


class DriverRef(Base):
    id: str
    label: str
    label_ko: str
    score: float
    status: DriverStatus


class RatesTop(Base):
    """상단 정리(2026-10-12) — 기존 계산값을 다시 읽어 방향 · 주도 driver · 물가/Fed 여부 · 신뢰도를 먼저 보인다. 새 계산 없음."""
    direction: Literal["up", "down", "flat", "unknown"]
    direction_arrow: str
    direction_en: str = Field(description="RISING / FALLING / IN RANGE")
    direction_ko: str
    segment: str = Field(description="LONG-END YIELD 처럼 움직이는 구간 — curve.lead 에서")
    driver_title: str = Field(description="TERM PREMIUM / SUPPLY DRIVEN")
    primary: DriverRef
    counter: DriverRef | None = Field(default=None, description="반대 방향(CONTRADICTED 또는 반대 부호)의 가장 큰 driver")
    not_confirmed: list[DriverRef] = Field(default_factory=list, description="물가·Fed 처럼 늘 확인하는 driver 중 미확인")
    not_confirmed_text: str = Field(default="", description="Inflation / Fed Policy")
    market_read: str = Field(description="화면에 보이는 MARKET READ — LLM 해석(검증 통과) 또는 규칙 기반 문장")
    driver_lines: dict[str, str] = Field(default_factory=dict, description="compact WHAT IS DRIVING RATES 의 한 줄 — primary · counter · 미확인만")
    market_read_meta: MarketReadMeta | None = Field(default=None, description="MARKET READ 출처·상태. 옛 캡처는 None(= 규칙 기반)")


class MarketReadMeta(Base):
    """
    MARKET READ 출처(2026-10-13). source=llm 이면 컨텍스트 숫자 대조·금지어·문장 수 검증을 통과한 해석이다.
    source=rule 이면 규칙 기반 문장이고 reason 에 LLM 해석이 없는 이유를 적는다. 모델 이름은 남기지 않는다.
    """
    source: Literal["llm", "rule"]
    status: Literal["ok", "fallback", "pending", "skipped"]
    generator: Literal["api", "session", "none"] = Field(default="none", description="api = 파이프라인 API 호출, session = 같은 컨텍스트·프롬프트·검증으로 오프라인 생성")
    reason: str = Field(default="", description="규칙 기반으로 남은 이유 — 화면에 그대로 보인다")
    themes: list[str] = Field(default_factory=list, description="LLM 이 고른 1~3개 테마 키")
    themes_ko: list[str] = Field(default_factory=list)
    move_quality: str | None = Field(default=None, description="금리 움직임의 성격(내부 판단) — growth_scare · flight_to_quality …")
    move_quality_ko: str | None = None
    regime_fit: Literal["consistent", "partly_consistent", "inconsistent"] | None = Field(default=None, description="regime 모델과 실제 cross-asset 이 맞는 정도")
    data_caveat: str = Field(default="", description="지연·결측 데이터에 대한 한 줄 — 없으면 빈칸")
    generated_at: datetime | None = None
    context_as_of: datetime | None = None
    rule_read: str = Field(default="", description="같은 시점의 규칙 기반 문장(비교·폴백용)")
    warnings: list[str] = Field(default_factory=list, description="검증에서 걸러진 이유 — 재시도 기록")


class AnalysisTile(Base):
    key: Literal["driver", "curve", "real_yield", "breakeven"]
    label: str
    value: str
    sub: str = ""
    arrow: str = ""
    move: Literal["up", "down", "flat", "missing", "none"] = "none"
    detail: str = Field(default="", description="툴팁용 — 5일 bp · z")


class CurrentRatesAnalysis(Base):
    tiles: list[AnalysisTile]
    sentence: str


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
    #: 상단 정리(2026-10-12). 옛 캡처에는 없다 — 없으면 화면은 예전 머리를 그린다.
    top: RatesTop | None = None
    current_analysis: CurrentRatesAnalysis | None = None
    #: POLICY & MACRO EVENTS — 확인된 정책 결정·지표만. 없거나 MOCK 이면 None.
    events: "PolicyMacroEvents | None" = None
    #: 아래 세 패널 정리(2026-10-13) — INFLATION PRESSURE MAP → TREASURY CURVE → YIELD MOVE BREAKDOWN. 옛 캡처는 None → 예전 패널.
    inflation_map: InflationPressureMap | None = None
    curve_move: CurveMoveView | None = None
    yield_breakdown: YieldMoveBreakdown | None = None


class PressureItem(Base):
    """INFLATION PRESSURE MAP 한 줄 — 상태 → 점수 → 근거 순으로 읽힌다. 결측은 점수 없이 DATA MISSING."""
    key: str
    label: str = Field(description="Realized Inflation 같은 영어명(그대로)")
    label_ko: str = Field(description="실제 물가 같은 짧은 한글 설명")
    state: str = Field(description="COOLING · EASING · MILD EASING · NEUTRAL · MILD PRESSURE · PRESSURE · STRONG PRESSURE · DATA MISSING")
    state_ko: str = ""
    tone: Literal["up", "down", "flat", "missing"]
    score: float | None = None
    evidence_text: str = Field(default="", description="10Y BE -1.2σ · 5Y BE -1.1σ")
    missing_text: str = ""


class InflationPressureMap(Base):
    """INFLATION PRESSURE MAP(2026-10-13) — 기존 구성요소 점수를 상태 · 신호 · 확인 정도로 다시 읽는다. 결측은 0 이 아니라 분모에서 빠진다."""
    signal: str = Field(description="COOLING BIAS · MIXED · UPSIDE BIAS · COOLING · REACCELERATING · NO SIGNAL")
    signal_ko: str
    signal_tone: Literal["up", "down", "flat", "missing"]
    confirmation: Literal["FULL", "PARTIAL", "INSUFFICIENT"]
    confirmation_ko: str
    available: int
    total: int
    summary: str = Field(description="상단 한 줄 — 숫자 없음")
    items: list[PressureItem] = Field(default_factory=list)
    read: str = Field(default="", description="하단 해석 최대 2문장 — LLM(검증 통과) 또는 규칙 기반")
    read_meta: MarketReadMeta | None = None
    scale_note: str = ""
    link: str = Field(default="", description="아래 TREASURY CURVE 로 잇는 한 줄")


class CurvePoint(Base):
    label: str
    today: float | None = Field(default=None, description="수익률 %")
    ago: float | None = Field(default=None, description="window 전 수익률 % (today − 변화)")
    chg_bp: float | None = None
    z: float | None = Field(default=None, description="평소 변동성 대비(엔진 z — 하루·5일 중 큰 쪽)")
    z_window: str = ""


class SpreadMove(Base):
    key: str = Field(description="2s10s · 5s30s")
    level_bp: float | None = None
    chg_bp: float | None = None
    direction: Literal["steepening", "flattening", "flat", "missing"]


class CurveMoveView(Base):
    """TREASURY CURVE(2026-10-13) — 모양은 실제 bp 스프레드 변화로, 이례성은 z 로. 둘을 섞지 않는다."""
    window_label: str = Field(description="5D")
    as_of_date: date | None = None
    shape_key: str = Field(description="bull_steepening · bull_flattening · bear_steepening · bear_flattening · parallel_down · parallel_up · twist · flat · unknown")
    shape: str = Field(description="MILD BULL STEEPENING")
    level_dir: str = Field(description="ALL YIELDS ↓ · ALL YIELDS ↑ · MIXED")
    points: list[CurvePoint] = Field(default_factory=list)
    spreads: list[SpreadMove] = Field(default_factory=list)
    short_window: str = Field(default="", description="1D 모양 한 줄 — 상단 REGIME 칸(1D 기준)과 맞춰 읽게")
    intensity: str = Field(default="", description="LONG-END MOVE MORE UNUSUAL")
    most_unusual: str | None = None
    most_unusual_z: float | None = None
    read: str = ""
    link: str = ""


class BreakdownTenor(Base):
    tenor: str
    window_days: int
    start_date: date | None = None
    end_date: date | None = None
    aligned: bool = False
    nominal_bp: float | None = None
    real_bp: float | None = Field(default=None, description="MODEL REAL YIELD = 명목 − 기대인플레(항등식)")
    breakeven_bp: float | None = None
    tips_bp: float | None = Field(default=None, description="OBSERVED TIPS — 실측")
    primary: Literal["real", "breakeven", "both", "unknown"]
    primary_label: str = Field(description="INFLATION EXPECTATION ↓ · REAL YIELD ↑ · BOTH ↓")
    line: str = Field(default="", description="금리 하락은 … 이(가) 주도 — 숫자 없음")
    small_move: bool = False
    divergence: bool = Field(default=False, description="MODEL REAL 과 OBSERVED TIPS 가 방향·크기에서 갈림")
    divergence_text: str = ""
    missing: list[str] = Field(default_factory=list)


class YieldMoveBreakdown(Base):
    """YIELD MOVE BREAKDOWN(2026-10-13, 옛 이름 Nominal Yield Decomposition) — 기존 분해값을 주도 요인 · 성격으로 다시 읽는다."""
    tenors: list[BreakdownTenor] = Field(default_factory=list)
    default_tenors: list[str] = Field(default_factory=list)
    headline_tenor: str | None = None
    character_key: str = ""
    character: str = Field(default="", description="투자적 성격 한 문장")
    link: str = ""
    note: str = ""


from .policy_events import PolicyMacroEvents  # noqa: E402  — 순환 참조를 피해 끝에서 읽는다

RatesTop.model_rebuild()
InflationPressureMap.model_rebuild()
RatesRegime.model_rebuild()
