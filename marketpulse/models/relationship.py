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

    # ── 전파 위치와 실측 반응 ────────────────────────────────────
    # 지도가 '가설' 만 그리면 이 제품의 1번 질문 — 내러티브와 실제 가격이
    # 일치하는가 — 에 답하지 못한다. 아래 네 필드가 가설 옆에 실측을 둔다.
    hop: int = Field(default=0, ge=0, description="뿌리에서 몇 단계 떨어졌는가")
    expected_sign: Literal[-1, 0, 1] = Field(
        default=0,
        description="대표 경로의 관계 부호 곱. 0 은 뿌리이거나 판정 불가",
    )
    sign_conflict: bool = Field(
        default=False,
        description="같은 단계의 다른 경로가 반대 부호를 준다. 단정하면 안 된다",
    )
    via_edge_id: str | None = Field(
        default=None, description="이 노드로 들어온 대표 관계. 부호 계산 근거다"
    )
    path_strength: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "대표 경로의 **가장 약한 고리**. 사슬은 가장 약한 고리만큼만 "
            "버틴다. 이 값이 낮으면 예상 부호 자체가 약한 주장이라 "
            "'예상과 반대' 로 단정하지 않는다."
        ),
    )
    observed_z: float | None = Field(
        default=None, description="실측 z_1d. 가격이 있는 노드만"
    )
    observed_display: str | None = Field(
        default=None, description='화면용 변화율 문자열. 예 "+3.16%"'
    )
    reaction: Literal["confirmed", "mismatch", "muted", "unknown"] = Field(
        default="unknown",
        description=(
            "confirmed 예상 부호대로 움직였다 / mismatch 반대로 움직였다 / "
            "muted 유의미하게 움직이지 않았다 / unknown 가격이 없거나 부호 미정"
        ),
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

    @property
    def mismatches(self) -> list[RelationshipNode]:
        """예상과 반대로 움직인 노드. 화면이 먼저 보여줘야 할 것들이다."""
        return [n for n in self.nodes if n.reaction == "mismatch"]
