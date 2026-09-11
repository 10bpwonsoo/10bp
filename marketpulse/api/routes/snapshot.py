"""
대시보드가 화면 전체를 그리는 데 쓰는 단일 엔드포인트.

패널마다 호출을 나누면 패널 간 시점이 어긋나 "Market State 는 10:00 기준인데
Theme 은 10:01 기준" 인 상태가 생긴다. 시장 분석 도구에서 이것은 치명적이다
(설계서 STEP 4.8).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...config.settings import Settings
from ...models.snapshot import IntelligenceSnapshot, MovingItem
from ...models.state import MarketState
from ..deps import load_snapshot, resolve_settings

router = APIRouter(prefix="/api/v1", tags=["snapshot"])

SettingsDep = Annotated[Settings, Depends(resolve_settings)]


@router.get("/snapshot", response_model=IntelligenceSnapshot)
def get_snapshot(settings: SettingsDep) -> IntelligenceSnapshot:
    """현재 시장 인텔리전스 전체."""
    return load_snapshot(settings)


@router.get("/market-state", response_model=MarketState)
def get_market_state(settings: SettingsDep) -> MarketState:
    """시장 상태만. 전체 스냅샷과 같은 계산 결과의 일부다."""
    return load_snapshot(settings).market_state


@router.get("/whats-moving", response_model=list[MovingItem])
def get_whats_moving(settings: SettingsDep) -> list[MovingItem]:
    """|z| 가 큰 순서의 변수 목록."""
    return load_snapshot(settings).whats_moving
