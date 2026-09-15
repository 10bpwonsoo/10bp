"""공통 픽스처. 테스트는 네트워크 없이 돈다 — 엔진이 순수 함수이기 때문이다."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from marketpulse.adapters.market.mock import MockMarketAdapter
from marketpulse.adapters.news.mock import MockNewsAdapter
from marketpulse.config.registry import get_instruments, get_themes
from marketpulse.config.settings import MOCK_DIR, Settings, reset_settings_cache

#: 모든 테스트가 같은 기준 시각을 쓴다. 시계에 의존하면 재현성이 깨진다.
AS_OF = datetime(2026, 9, 11, 7, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _no_llm_credentials(monkeypatch):
    """
    테스트는 네트워크도 키도 없이 돈다. 개발자 셸에 ANTHROPIC_API_KEY 가
    있으면 llm_enabled 가 자동으로 켜져 모든 스냅샷이 'degraded' 가 되고,
    lru_cache 된 Settings 가 그 상태를 다음 테스트로 끌고 간다. 여기서
    매 테스트마다 지운다. 키가 필요한 테스트는 스스로 monkeypatch 로 넣는다.
    """
    for key in ("ANTHROPIC_API_KEY", "MARKETPULSE_ANTHROPIC_API_KEY", "MARKETPULSE_LLM_ENABLED"):
        monkeypatch.delenv(key, raising=False)
    reset_settings_cache()
    yield
    reset_settings_cache()


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
