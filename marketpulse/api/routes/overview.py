"""MARKET OVERVIEW 탭 (2026-11-12). 응답 = LLM 시장 종합(status · source · view). 숫자 칸은 화면이 기존 엔드포인트(같은 스냅샷)에서 그린다."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from ...config.settings import Settings
from ..deps import resolve_settings
from ..overview_service import get_market_overview

router = APIRouter(prefix="/api/v1", tags=["overview"])
SettingsDep = Annotated[Settings, Depends(resolve_settings)]


@router.get("/market-overview")
def market_overview(settings: SettingsDep) -> dict[str, Any]:
    return get_market_overview(settings)
