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
    z: float | None = None
    arrow: Arrow
    status: Literal["CONFIRM", "DIVERGE", "HEADWIND", "FLAT", "NEUTRAL", "MISSING"]
    note: str = ""


class KeyDivergence(Base):
    title: str
    meaning: str
    severity: float
    source: Literal["divergence", "rates_regime", "oil_regime"] = "divergence"
    assets: list[str] = Field(default_factory=list)


class CrossAsset(Base):
    rows: list[CrossAssetRow] = Field(default_factory=list)
    confirm: int = 0
    evaluated: int = 0
    sentence: str = ""
    divergences: list[KeyDivergence] = Field(default_factory=list)
    total_divergences: int = 0


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


class TransmissionStock(Base):
    id: str
    name: str
    status: Literal["CONFIRMED", "UNCONFIRMED", "CONTRADICTED", "NO DATA"]
    z: float | None = None
    change_1d: float | None = None
    note: str = ""


class TransmissionChain(Base):
    driver_key: str
    driver_label: str
    arrow: Arrow
    mechanism: str
    industries: list[str] = Field(default_factory=list)
    stocks: list[TransmissionStock] = Field(default_factory=list)
    confirmed: int = 0
    source: Literal["driver", "commodity"] = "driver"


class RadarStock(Base):
    id: str
    name: str
    change_1d: float | None = None
    tag: str
    why: str
    kind: Literal["why", "watch"] = "why"
    score: float
    signals: list[str] = Field(default_factory=list)


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


class NextItem(Base):
    text: str
    status: Literal["CONFIRMING", "WATCH", "REVERSING"]
    metric: str
    current: str
    driver_key: str


class UpcomingEvent(Base):
    date: str
    label: str
    days_until: int | None = None
    verified: bool = True


class WatchRow(Base):
    id: str
    name: str
    change_1d: float | None = None
    watch: str = ""
    indicators: list[str] = Field(default_factory=list)


class DataStatus(Base):
    line: str
    warnings: list[str] = Field(default_factory=list)
    coverage: float
    available: int
    expected: int
    stale: int
    max_lag_days: int
    news_judgment: str = ""


class Cockpit(Base):
    as_of: datetime
    market_now: MarketNow
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
