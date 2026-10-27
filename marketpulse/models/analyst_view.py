"""
STOCK RADAR · ANALYST VIEW (2026-09-29).

외부 애널리스트 코멘트는 시스템 판단이 아니다. 웹에서 실제 확인된 것만 싣는다 —
이름 · 증권사 · 날짜 · 출처 URL · 맥락이 모두 있어야 한 줄이 된다. 하나라도 없으면 그 종목은
빈 줄이 아니라 아예 없다. 생성·추정·attribution 위조는 구조로 막는다: 저장 전 검증(validate_view)에서
필드가 비었거나 날짜가 max_age_days 를 넘으면 버린다.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from .common import Base

Stance = Literal["constructive", "cautious", "neutral", "mixed"]


class AnalystView(Base):
    stock_id: str
    stock_name: str = ""
    analyst: str = Field(description="애널리스트 이름 — 웹에서 확인된 것")
    broker: str = Field(description="증권사 / 리서치 하우스")
    published_date: date
    source_url: str
    source_title: str = ""
    summary: str = Field(description="한 줄 paraphrase — 투자의견이 아니라 '왜 그렇게 보는가'")
    key_view: str = Field(default="", description="핵심 요약 1~2문장")
    key_variables: list[str] = Field(default_factory=list, description="HBM pricing / capex / margin 같은 핵심 변수")
    stance: Stance = "neutral"
    rating: str = Field(default="", description="투자의견 — 있을 때만 (추정 금지)")
    target_change: str = Field(default="", description="목표가 변화 — 기사에 있을 때만")
    retrieved_at: datetime
    retrieved_by: Literal["manual", "llm_web"] = "manual"
    age_days: int = Field(default=0, ge=0, description="as_of 기준 코멘트 나이(일)")
    freshness: str = Field(default="", description="'1D' / '5D' / '18D'")


class AnalystViews(Base):
    as_of: datetime
    views: list[AnalystView] = Field(default_factory=list, description="확인된 종목만")
    requested: list[str] = Field(default_factory=list, description="조회한 radar 종목")
    pending: list[str] = Field(default_factory=list, description="백그라운드 검색이 도는 종목 — 화면은 기다리지 않는다")
    missing: list[str] = Field(default_factory=list, description="확인된 코멘트가 없어 숨긴 종목")
    provider: str = Field(default="unavailable", description="llm_web / unavailable / disabled")
    note: str = ""
