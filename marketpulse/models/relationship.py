"""
Relationship 스키마 (설계서 STEP 4.7).

origin 과 status 가 LLM 추론 관계를 사전 정의 관계와 분리한다.
UI 에서 predefined 는 실선, llm_proposed 는 점선으로 그린다.
불확실한 시장 관계를 확정 사실처럼 제시하지 않는다 (요구 8, 15-11).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field

from .common import Base, utcnow


class NodeType(StrEnum):
    EVENT = "EVENT"
    THEME = "THEME"
    MACRO_FACTOR = "MACRO_FACTOR"
    ASSET = "ASSET"
    SECTOR = "SECTOR"


class RelationshipNode(Base):
    id: str
    type: NodeType
    label: str
    ref_id: str | None = Field(
        default=None, description="NewsEvent.id / Theme.id / Instrument.id"
    )


class RelationshipEdge(Base):
    id: str
    source_id: str
    target_id: str
    direction: Literal["positive", "negative", "ambiguous"] = "positive"
    strength: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    lag: Literal["immediate", "hours", "days", "weeks"] = "immediate"
    reason: str = ""

    origin: Literal["predefined", "llm_proposed", "statistical"] = "predefined"
    status: Literal["active", "candidate", "rejected"] = "active"
    evidence: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    verified_by: str | None = None


class ImpactMap(Base):
    as_of: datetime
    root_event_id: str | None = None
    nodes: list[RelationshipNode] = Field(default_factory=list)
    edges: list[RelationshipEdge] = Field(default_factory=list)
    max_depth: int = 0
