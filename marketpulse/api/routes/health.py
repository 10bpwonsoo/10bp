"""데이터 상태와 시나리오 목록. 요구 12 의 메타데이터를 그대로 노출한다."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...adapters.market.scenario import available_scenarios, load_scenario
from ...config.settings import Settings, get_settings
from ...models.common import Base, DataMode
from ...models.snapshot import DataHealth
from ..deps import load_snapshot, resolve_settings

router = APIRouter(prefix="/api/v1", tags=["health"])

SettingsDep = Annotated[Settings, Depends(resolve_settings)]


class ScenarioInfo(Base):
    name: str
    title: str
    description: str
    is_active: bool


class ServiceInfo(Base):
    status: str
    version: str
    mode: DataMode
    scenario: str | None
    llm_enabled: bool
    zscore_window: int


@router.get("/health", response_model=DataHealth)
def get_health(settings: SettingsDep) -> DataHealth:
    """커버리지, 결측, 신선도, 엔진 소요 시간."""
    return load_snapshot(settings).data_health


@router.get("/info", response_model=ServiceInfo)
def get_info() -> ServiceInfo:
    """파이프라인을 돌리지 않는 가벼운 상태 확인. 기동 점검용이다."""
    s = get_settings()
    return ServiceInfo(
        status="ok",
        version=s.api_version,
        mode=s.data_mode,
        scenario=s.scenario if s.data_mode is DataMode.MOCK else None,
        llm_enabled=s.llm_enabled,
        zscore_window=s.zscore_window,
    )


@router.get("/scenarios", response_model=list[ScenarioInfo])
def get_scenarios() -> list[ScenarioInfo]:
    """재생 가능한 시나리오 목록. 데모 중 화면에서 전환할 수 있게 한다."""
    settings = get_settings()
    out: list[ScenarioInfo] = []
    for name in available_scenarios(settings.mock_dir):
        sc = load_scenario(settings.mock_dir, name)
        out.append(
            ScenarioInfo(
                name=sc.name,
                title=sc.title or sc.name,
                description=sc.description,
                is_active=(name == settings.scenario),
            )
        )
    return out
