"""
대시보드가 화면 전체를 그리는 데 쓰는 단일 엔드포인트.

패널마다 호출을 나누면 패널 간 시점이 어긋나 "Market State 는 10:00 기준인데
Theme 은 10:01 기준" 인 상태가 생긴다. 시장 분석 도구에서 이것은 치명적이다
(설계서 STEP 4.8).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ...config.settings import Settings
from ...models.snapshot import IntelligenceSnapshot, MovingItem
from ...models.state import MarketState
from ...models.theme import ThemeState
from ...models.state_history import MarketStateHistory
from ...models.scenario_check import ScenarioCheck
from ...models.oil_regime import OilRegime
from ..deps import get_oil_regime_service, get_scenario_check_service, get_state_history_service, load_snapshot, resolve_settings

router = APIRouter(prefix="/api/v1", tags=["snapshot"])

SettingsDep = Annotated[Settings, Depends(resolve_settings)]


@router.get("/snapshot", response_model=IntelligenceSnapshot)
def get_snapshot(
    settings: SettingsDep,
    refresh: Annotated[
        bool,
        Query(description="참이면 TTL 캐시를 건너뛰고 지금 새로 수집·계산한다. 화면의 '지금 업데이트' 버튼."),
    ] = False,
) -> IntelligenceSnapshot:
    """현재 시장 인텔리전스 전체."""
    return load_snapshot(settings, force=refresh)


@router.get("/market-state", response_model=MarketState)
def get_market_state(settings: SettingsDep) -> MarketState:
    """시장 상태만. 전체 스냅샷과 같은 계산 결과의 일부다."""
    return load_snapshot(settings).market_state


@router.get("/market-state/history", response_model=MarketStateHistory)
def get_market_state_history(
    settings: SettingsDep,
    days: Annotated[int | None, Query(ge=5, le=120, description="재생할 거래일 수. 기본은 설정(22 ≈ 한 달)")] = None,
) -> MarketStateHistory:
    """최근 한 달의 Market State 흐름. 같은 시계열을 날짜별로 잘라 같은 엔진으로 다시 판정한 값."""
    return get_state_history_service().get(settings, days=days)


@router.get("/scenario-check", response_model=list[ScenarioCheck])
def get_scenario_check(settings: SettingsDep) -> list[ScenarioCheck]:
    """모의 시나리오의 충격 서명을 지금 데이터에 대어 본 결과. 모의 탭을 실데이터로 바꾼 것 — 예측이 아니다."""
    return get_scenario_check_service().get(settings)


@router.get("/oil-regime", response_model=OilRegime)
def get_oil_regime(settings: SettingsDep) -> OilRegime:
    """유가 시장 원인 판별 — 거시·유동성/수요/공급/지정학 driver 의 증거 점수와 확인 상태. 판정 룰이 아니라 증거 집계다."""
    return get_oil_regime_service().get(settings)


@router.get("/themes", response_model=list[ThemeState])
def get_themes(settings: SettingsDep) -> list[ThemeState]:
    """테마 점수. theme_score 내림차순이다."""
    return load_snapshot(settings).themes


@router.get("/whats-moving", response_model=list[MovingItem])
def get_whats_moving(settings: SettingsDep) -> list[MovingItem]:
    """|z| 가 큰 순서의 변수 목록."""
    return load_snapshot(settings).whats_moving
