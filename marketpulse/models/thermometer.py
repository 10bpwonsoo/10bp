"""
SentimentThermometer 스키마 (P5).

"지금 시장이 얼마나 뜨거운가" 를 -100(결빙) ~ +100(과열) 한 눈금으로 잰다.
바늘이 셋이다 — 가격이 말하는 온도, 뉴스가 말하는 온도, 그 둘의 종합.
종합 하나만 내지 않는 이유는 이 제품의 1번 질문이 "내러티브와 가격이
맞는가" 이기 때문이다. 두 바늘의 거리가 곧 그 답이다.

모든 온도는 ScoreBreakdown 을 들고 다닌다 (요구 15-6). None 은 '측정하지
못했다' 지 0 이 아니다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from .common import Base, Direction, ScoreBreakdown

Band = Literal["overheated", "warm", "neutral", "cool", "frozen", "unknown"]
GapFlag = Literal["none", "narrative_hot", "narrative_cold"]


class SentimentThermometer(Base):
    as_of: datetime

    composite: float | None = Field(default=None, description="-100 ~ +100. None 은 측정 불가")
    price: float | None = Field(default=None, description="가격이 말하는 온도")
    news: float | None = Field(default=None, description="뉴스가 말하는 온도")
    gap: float | None = Field(default=None, description="news - price. 둘 다 있을 때만")
    gap_flag: GapFlag = Field(
        default="none",
        description="|gap| 이 임계를 넘으면 뉴스가 가격보다 뜨거운지/차가운지",
    )

    band: Band = "unknown"
    band_label: str = "측정 불가"

    trend: Direction = "flat"
    trend_arrow: str = "→"
    delta: float | None = Field(default=None, description="직전 틱 대비 종합 변화")

    confidence: float = Field(default=0.0, ge=0.0, le=100.0)

    composite_breakdown: ScoreBreakdown | None = None
    price_breakdown: ScoreBreakdown | None = None
    news_breakdown: ScoreBreakdown | None = None
    confidence_breakdown: ScoreBreakdown | None = None

    news_events: int = Field(default=0, description="뉴스 온도에 쓴 기사 수")
    llm_events: int = Field(default=0, description="그중 LLM 이 구조화한 기사 수")

    note: str = Field(default="", description="템플릿 문장. LLM 없이도 나온다")
