"""
금리 탭 POLICY & MACRO EVENTS (2026-10-12).

중앙은행 결정과 미국 주요 지표 중 '금리 방향을 바꿀 수 있는 것' 만 담는다. 값(결정·실제치·컨센서스·전월)은 출처가 확인된 수기 파일
(data/policy_events/*.json)에서만 오고, 금리 반응은 같은 날짜의 미국채 2Y·10Y 일간 종가 차이로 엔진이 잰다. 놀람 판정·regime 영향은
config/policy_events.yaml 의 문턱과 표로 정한다. 없는 값은 None 이다 — 만들어 채우지 않는다. '확률' 이라는 말은 쓰지 않는다.
"""

from __future__ import annotations

from datetime import date as Date, datetime
from typing import Literal

from pydantic import Field

from .common import Base

Importance = Literal["HIGH", "MED", "LOW"]
Impact = Literal["SUPPORTED", "CHALLENGED", "NEUTRAL"]
Tone = Literal["HAWKISH", "NEUTRAL", "DOVISH"]
Decision = Literal["HIKE", "HOLD", "CUT"]


class EventSource(Base):
    title: str
    url: str
    publisher: str = ""


class RateReaction(Base):
    """발표일 종가 − 직전 거래일 종가(FRED 일간). 계열이나 날짜가 없으면 None."""

    date: Date | None = None
    us2y_bp: float | None = None
    us10y_bp: float | None = None
    us2y_arrow: str = ""
    us10y_arrow: str = ""
    note: str = ""


class RegimeImpact(Base):
    impact: Impact | None = Field(default=None, description="None = 미국 금리 regime 직접 판정 대상 아님")
    reason: str = ""


class PolicyDecision(Base):
    bank: Literal["FED", "ECB", "BOJ", "BOK"]
    name: str
    date: Date
    decision: Decision
    decision_label: str = Field(description="HIKE +25bp / HOLD / CUT −25bp")
    previous_rate: str
    current_rate: str
    rate_label: str
    vote: str = ""
    tone: Tone
    tone_basis: str = ""
    line: str = Field(description="한 줄 — 결정의 결")
    statement: str = ""
    chair: str = ""
    projections: str = ""
    market_path: str = ""
    next_meeting: Date | None = None
    next_meeting_start: Date | None = None
    implication: str = ""
    age_days: int = 0
    chain: list[str] = Field(default_factory=list, description="EVENT → 기대 경로 → RATES REACTION")
    reaction: RateReaction | None = None
    regime: RegimeImpact = Field(default_factory=RegimeImpact)
    sources: list[EventSource] = Field(default_factory=list)


class MacroMeasure(Base):
    key: str
    label: str
    unit: str = "%"
    actual: float | None = None
    consensus: float | None = None
    prior: float | None = None
    diff: float | None = Field(default=None, description="actual − consensus")
    judged: bool = Field(default=False, description="놀람 판정에 쓰였나")
    note: str = ""


class MacroRelease(Base):
    key: str
    name: str
    period: str
    date: Date
    importance: Importance = "HIGH"
    measures: list[MacroMeasure] = Field(default_factory=list)
    surprise: Literal["HOT", "INLINE", "COOL", "MIXED", "STRONG", "WEAK", "N/A"]
    surprise_basis: str = ""
    consensus_source: str = ""
    chain: list[str] = Field(default_factory=list)
    reaction: RateReaction = Field(default_factory=RateReaction)
    read: str = ""
    regime: RegimeImpact = Field(default_factory=RegimeImpact)
    age_days: int = 0
    note: str = ""
    sources: list[EventSource] = Field(default_factory=list)


class RecentItem(Base):
    kind: Literal["release", "policy"]
    key: str
    date: Date
    title: str
    label: str
    reaction_text: str = ""
    impact: Impact | None = None
    importance: Importance = "MED"


class UpcomingEvent(Base):
    date: Date
    date_start: Date | None = None
    importance: Importance
    kind: str
    name: str
    note: str = ""
    days_ahead: int
    sources: list[EventSource] = Field(default_factory=list)
    release_utc: datetime | None = Field(default=None, description="발표 시각(UTC). 있으면 같은 날이라도 이 시각 전까지는 UPCOMING(2026-10-14)")


class RegimeLink(Base):
    """최근 핵심 물가 지표가 현재 금리 regime 을 지지하는가 — 17번 요구."""

    current_driver: str
    current_driver_ko: str
    direction_ko: str
    latest_key: str
    latest_label: str
    latest_surprise: str
    impact: Impact
    sentence: str
    counts: dict[str, int] = Field(default_factory=dict, description="최근 미국 이벤트의 SUPPORTED / CHALLENGED / NEUTRAL 수")


class PolicyMacroEvents(Base):
    as_of: datetime
    collected: Date = Field(description="수기 확인 파일의 수집일")
    policy: list[PolicyDecision] = Field(default_factory=list)
    releases: list[MacroRelease] = Field(default_factory=list)
    recent: list[RecentItem] = Field(default_factory=list)
    recent_default: int = 5
    upcoming: list[UpcomingEvent] = Field(default_factory=list)
    upcoming_default: int = 5
    link: RegimeLink | None = None
    note: str = ""
    missing: list[str] = Field(default_factory=list, description="확인하지 못해 비워 둔 값")
