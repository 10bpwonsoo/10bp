"""
어댑터 선택. MARKETPULSE_DATA_MODE 하나로 전환된다 (요구 15-9).

P0 시점에는 MOCK 어댑터만 등록되어 있다. LIVE/DELAYED 어댑터는 P4 에서
추가한다. LIVE 를 요청했는데 어댑터가 없으면 조용히 MOCK 으로 떨어지지
않고 명확히 실패한다 — MOCK 데이터를 LIVE 라고 표시하는 것은 이 시스템이
피하려는 바로 그 부정직함이다 (설계서 STEP 7.2).
"""

from __future__ import annotations

from ..config.settings import Settings
from ..models.common import DataMode
from .base import AdapterError, MarketAdapter, NewsAdapter
from .market.mock import MockMarketAdapter
from .news.mock import MockNewsAdapter


def build_market_adapter(settings: Settings) -> MarketAdapter:
    if settings.data_mode is DataMode.MOCK:
        return MockMarketAdapter(
            settings.mock_dir,
            settings.scenario,
            zscore_window=settings.zscore_window,
        )
    raise AdapterError(
        f"{settings.data_mode.value} 마켓데이터 어댑터가 아직 없다 (P4 예정). "
        "MARKETPULSE_DATA_MODE=MOCK 으로 실행하라. "
        "실데이터를 쓰려면 CSV 리플레이 어댑터(P4)에 파일을 넣는 방법도 있다."
    )


def build_news_adapter(settings: Settings) -> NewsAdapter:
    if settings.data_mode is DataMode.MOCK:
        return MockNewsAdapter(settings.mock_dir, settings.scenario)
    raise AdapterError(
        f"{settings.data_mode.value} 뉴스 어댑터가 아직 없다 (P4 예정). "
        "MARKETPULSE_DATA_MODE=MOCK 으로 실행하라."
    )
