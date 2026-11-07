"""괴리와 알림. P2 DivergenceEngine / AlertEngine 의 출력."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ...config.settings import Settings
from ...models.alert import Alert
from ...models.divergence import Divergence, SeverityBand
from ..deps import load_snapshot, resolve_settings

router = APIRouter(prefix="/api/v1", tags=["signals"])

SettingsDep = Annotated[Settings, Depends(resolve_settings)]

_ORDER = {
    SeverityBand.CRITICAL: 3,
    SeverityBand.HIGH: 2,
    SeverityBand.MEDIUM: 1,
    SeverityBand.LOW: 0,
}


@router.get("/divergences", response_model=list[Divergence])
def get_divergences(
    settings: SettingsDep,
    min_band: Annotated[
        SeverityBand | None,
        Query(description="이 등급 이상만. 생략하면 전부."),
    ] = None,
) -> list[Divergence]:
    """
    뉴스 내러티브와 실제 가격·수급이 어긋나는 지점. severity 내림차순이다.

    min_duration 을 채우지 못한 후보는 여기 나오지 않는다. 한 틱짜리
    노이즈와 지속되는 구조적 괴리는 다르기 때문이다.
    """
    rows = load_snapshot(settings).divergences
    if min_band is None:
        return rows
    floor = _ORDER[min_band]
    return [d for d in rows if _ORDER[d.severity_band] >= floor]


@router.get("/alerts", response_model=list[Alert])
def get_alerts(
    settings: SettingsDep,
    include_resolved: Annotated[
        bool, Query(description="해소된 알림도 포함할지")
    ] = False,
) -> list[Alert]:
    """
    수준이 아니라 변화를 알린다. 모든 알림이 baseline 과 delta 를 들고 있다.
    """
    rows = load_snapshot(settings).alerts
    if include_resolved:
        return rows
    return [a for a in rows if a.state.value != "RESOLVED"]
