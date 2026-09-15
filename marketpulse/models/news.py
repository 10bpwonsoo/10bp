"""
NewsEvent 스키마 (설계서 STEP 4.2).

extractor / validation 필드가 이 스키마의 핵심이다.
LLM 이 만든 것인지, 룰이 만든 것인지, 사람이 넣은 것인지가 데이터에 남는다.
clamped_fields 는 LLM 이 sentiment 를 150 으로 뱉었을 때 100 으로 자른 사실을
기록한다 — 조용히 고치지 않고 기록한다 (요구 15-11).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field

from .common import Base, DataMeta
from .relationship import RelationshipEdge

TimeHorizon = Literal["intraday", "short", "medium", "long"]
Direction = Literal["up", "down", "neutral"]
Magnitude = Literal["low", "medium", "high"]


class EventType(StrEnum):
    GEOPOLITICAL = "geopolitical"
    MACRO = "macro"
    POLICY = "policy"
    EARNINGS = "earnings"
    SUPPLY = "supply"
    REGULATION = "regulation"
    FLOW = "flow"
    OTHER = "other"


class EntityType(StrEnum):
    COMPANY = "company"
    COUNTRY = "country"
    PERSON = "person"
    ORGANIZATION = "organization"
    COMMODITY = "commodity"
    CURRENCY = "currency"
    INDEX = "index"
    SECTOR = "sector"


class Entity(Base):
    name: str
    type: EntityType
    ticker: str | None = None


class AssetImpact(Base):
    """뉴스가 특정 자산에 미칠 것으로 본 영향."""

    instrument_id: str | None = Field(
        default=None, description="Instrument 레지스트리와 연결되면 채운다"
    )
    label: str = Field(description='미연결이어도 표시는 가능해야 한다. 예: "Airlines"')
    direction: Direction
    magnitude: Magnitude = "medium"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    rationale: str = ""


class RawNewsItem(Base):
    """어댑터가 가져온 원본 기사."""

    id: str
    title: str
    body: str = ""
    url: str | None = None
    publisher: str = ""
    published_at: datetime
    language: str = "ko"
    meta: DataMeta


class ValidationReport(Base):
    """구조화 출력 검증 결과 (요구 14)."""

    schema_ok: bool = True
    errors: list[str] = Field(default_factory=list)
    clamped_fields: list[str] = Field(default_factory=list)


class NewsEvent(Base):
    """뉴스에서 추출한 구조화 이벤트. 요구 4 의 JSON Schema 를 따른다."""

    id: str
    source_item_ids: list[str] = Field(default_factory=list)
    event: str
    event_type: EventType = EventType.OTHER
    themes: list[str] = Field(default_factory=list, description="Theme.id 참조")
    theme_sentiment: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "테마별 감성. 기사 하나가 여러 테마를 건드릴 때 기사 전체 감성을 "
            "모든 테마에 그대로 붙이면 틀린다. '정유주 강세, 항공주 약세' 는 "
            "Energy 에 +, Airlines 에 -여야 한다. 비어 있으면 sentiment 로 대체한다."
        ),
    )
    theme_direction: dict[str, Direction] = Field(
        default_factory=dict,
        description=(
            "테마별 방향. **감성과 다른 축이다.** 감성은 호재냐 악재냐를, "
            "방향은 그 값이 오르냐 내리냐를 말한다. '물가 둔화 흐름 확인' 은 "
            "감성 + 이지만 물가 방향은 ↓ 다. 둘을 한 필드로 합치면 Impact Map "
            "의 연쇄 전체가 뒤집힌다. 읽을 수 없으면 비워 둔다 — 추측하지 않는다."
        ),
    )
    entities: list[Entity] = Field(default_factory=list)

    sentiment: int = Field(default=0, ge=-100, le=100)
    impact_score: int = Field(default=0, ge=0, le=100)
    novelty_score: int = Field(default=50, ge=0, le=100)
    time_horizon: TimeHorizon = "short"

    affected_assets: list[AssetImpact] = Field(default_factory=list)
    direction: dict[str, Direction] = Field(
        default_factory=dict, description="요구 4 원문 스키마의 direction 맵"
    )
    second_order: list[RelationshipEdge] = Field(
        default_factory=list,
        description="2차 영향 연쇄. Oil↑ → Inflation↑ → Rates↑ → Growth Equity↓",
    )

    reason: str = ""
    source: str = ""
    #: 원문 링크. 화면에서 헤드라인을 누르면 기사로 간다. 검색 결과처럼
    #: 링크가 곧 출처인 경우가 있어 provenance 의 일부다.
    url: str | None = None
    timestamp: datetime

    # ── 출처 추적 ──
    extractor: Literal["llm", "rule", "manual"] = "rule"
    extractor_model: str | None = None
    validation: ValidationReport = Field(default_factory=ValidationReport)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
