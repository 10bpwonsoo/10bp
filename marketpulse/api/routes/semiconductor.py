"""반도체 사이클 탭 (2026-10-23). 응답 키는 화면 섹션과 1:1 — 없는 데이터는 null / 'NO DATA' 로 온다(0 으로 채우지 않는다)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from ...config.settings import Settings
from ..deps import resolve_settings
from ..semi_service import get_semiconductor_cycle_service

router = APIRouter(prefix="/api/v1", tags=["semiconductor"])

SettingsDep = Annotated[Settings, Depends(resolve_settings)]


@router.get("/semiconductor-cycle")
def get_semiconductor_cycle(settings: SettingsDep) -> dict[str, Any]:
    """regime · market_read · memory_prices · spot_premium · momentum · breadth · normalized · dram_map · nand_map · contract · memory_history ·
    spot_to_contract · hbm_supply · export_nowcast · price_to_export · fundamental_confirmation · equity_confirmation · stock_impact · news ·
    what_matters_next · data_quality."""
    return get_semiconductor_cycle_service().get(settings)
