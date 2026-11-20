"""Impact Map. Event → Theme → Macro → Asset → Sector 관계 그래프 (요구 8)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ...config.settings import Settings
from ...engines.relationship import predefined_edges
from ...models.relationship import ImpactMap, RelationshipEdge
from ..deps import load_snapshot, resolve_settings

router = APIRouter(prefix="/api/v1", tags=["graph"])

SettingsDep = Annotated[Settings, Depends(resolve_settings)]


@router.get("/impact-map", response_model=list[ImpactMap])
def get_impact_maps(
    settings: SettingsDep,
    event_id: Annotated[
        str | None, Query(description="이 이벤트를 뿌리로 하는 맵만")
    ] = None,
) -> list[ImpactMap]:
    """
    현재 스냅샷의 영향 경로.

    edge 의 origin 이 predefined 인지 llm_proposed 인지 구분되어 있다.
    화면은 전자를 실선, 후자를 점선으로 그린다 (요구 8, 15-11).
    """
    maps = load_snapshot(settings).impact_maps
    if event_id is None:
        return maps
    return [m for m in maps if m.root_event_id == event_id]


@router.get("/relationships", response_model=list[RelationshipEdge])
def get_relationships() -> list[RelationshipEdge]:
    """
    사전 정의 관계 전체.

    여기 있는 것은 모두 origin="predefined" 다. 사람이 relationships.yaml 에
    적은 것이며, LLM 이 제안한 관계는 여기 섞이지 않는다.
    """
    return predefined_edges()
