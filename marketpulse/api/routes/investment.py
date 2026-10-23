"""
Investment Intelligence API (2026-09-16 신설).

기존 /api/v1/snapshot 은 손대지 않는다. 종목·대체데이터 계층은 계산이
무거워(수십 종목 × 드라이버 × 창) 별도 엔드포인트와 별도 캐시로 분리한다.
기존 화면은 이 계층이 느려도 먼저 뜬다.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from ...config.settings import Settings
from ...models.intelligence import AltDataPoint, InvestmentIntelligence, StockIntelligence
from ..deps import load_investment, resolve_settings

router = APIRouter(prefix="/api/v1/investment", tags=["investment"])

SettingsDep = Annotated[Settings, Depends(resolve_settings)]


@router.get("", response_model=InvestmentIntelligence)
def get_investment(
    settings: SettingsDep,
    refresh: Annotated[bool, Query(description="TTL 캐시를 건너뛰고 지금 새로 계산")] = False,
) -> InvestmentIntelligence:
    """Investment Intelligence 전체. 기존 스냅샷을 먼저 만든 뒤 그 위에 쌓는다."""
    return load_investment(settings, force=refresh)


@router.get("/stocks/{stock_id}", response_model=StockIntelligence)
def get_stock(settings: SettingsDep, stock_id: str) -> StockIntelligence:
    inv = load_investment(settings)
    if stock_id not in inv.stocks:
        raise HTTPException(status_code=404, detail=f"알 수 없는 종목 '{stock_id}'. 사용 가능: {sorted(inv.stocks)[:10]}…")
    return inv.stocks[stock_id]


@router.get("/alternative", response_model=list[AltDataPoint])
def get_alternative(settings: SettingsDep, group: str | None = None) -> list[AltDataPoint]:
    rows = load_investment(settings).alternative
    return [r for r in rows if group is None or r.group == group]
