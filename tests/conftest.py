"""공통 픽스처. 테스트는 네트워크 없이 돈다 — 엔진이 순수 함수이기 때문이다."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from marketpulse.adapters.market.mock import MockMarketAdapter
from marketpulse.adapters.news.mock import MockNewsAdapter
from marketpulse.config.registry import get_instruments, get_themes
from marketpulse.config.settings import MOCK_DIR, Settings

#: 모든 테스트가 같은 기준 시각을 쓴다. 시계에 의존하면 재현성이 깨진다.
AS_OF = datetime(2026, 9, 11, 7, 0, tzinfo=timezone.utc)


@pytest.fixture
def as_of() -> datetime:
    """모든 테스트의 공통 기준 시각."""
    return AS_OF


@pytest.fixture
def settings() -> Settings:
    return Settings(data_mode="MOCK", scenario="baseline", llm_enabled=False)


@pytest.fixture
def instruments():
    return get_instruments().instruments


@pytest.fixture
def instruments_by_id():
    return get_instruments().by_id()


@pytest.fixture
def themes():
    return get_themes().themes


@pytest.fixture
def market_adapter() -> MockMarketAdapter:
    return MockMarketAdapter(MOCK_DIR, "baseline")


@pytest.fixture
def news_adapter() -> MockNewsAdapter:
    return MockNewsAdapter(MOCK_DIR, "baseline")


@pytest.fixture
def series(market_adapter, instruments, as_of):
    return market_adapter.fetch_series(instruments, bars=180, as_of=as_of)
