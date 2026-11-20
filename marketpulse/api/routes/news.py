"""뉴스 원문. P3 에서 LLM 이 추출한 NewsEvent 가 여기에 더해진다."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...adapters.registry import build_news_adapter
from ...config.settings import Settings
from ...models.news import NewsEvent, RawNewsItem
from ..deps import load_snapshot, resolve_settings

router = APIRouter(prefix="/api/v1", tags=["news"])

SettingsDep = Annotated[Settings, Depends(resolve_settings)]


@router.get("/news", response_model=list[RawNewsItem])
def get_news(settings: SettingsDep, limit: int = 50) -> list[RawNewsItem]:
    """수집된 기사 원문."""
    return build_news_adapter(settings).fetch_news(limit=limit)


@router.get("/events", response_model=list[NewsEvent])
def get_events(settings: SettingsDep) -> list[NewsEvent]:
    """구조화된 이벤트. P1(룰 추출) 이후 채워진다."""
    return load_snapshot(settings).events
