"""
어댑터 선택. MARKETPULSE_DATA_MODE 하나로 전환된다 (요구 15-9).

MOCK    결정론적 시나리오. 기본값이고 네트워크를 쓰지 않는다.
DELAYED 무료 공급자의 일봉 종가 + RSS. P4 에서 추가됐다.
LIVE    같은 어댑터지만 "실시간" 을 요구한 것이다. 무료 공급자로는
        장중 틱을 받을 수 없으므로 **경고를 남기고** DELAYED 와 같은
        데이터를 쓴다. 조용히 실시간인 척하지 않는다 (설계서 STEP 7.2).

어댑터는 캐시한다. 회로 차단기와 직전 수집 결과가 틱을 넘겨 살아남아야
하기 때문이다 — LLM 클라이언트를 메모이즈한 것과 같은 이유다.
"""

from __future__ import annotations

from functools import lru_cache

from ..config.settings import Settings
from ..models.common import DataMode
from .base import AdapterError, MarketAdapter, NewsAdapter
from .http import HttpClient
from .market.live import LiveMarketAdapter
from .market.mock import MockMarketAdapter
from .news.mock import MockNewsAdapter
from .news.rss import RssNewsAdapter

#: LIVE 를 요구했을 때 남기는 경고. data_health 에 그대로 실린다.
LIVE_IS_DELAYED = (
    "LIVE 를 요청했으나 무료 공급자는 일봉 종가만 준다. 실시간이 아니라 "
    "지연 데이터다. 장중 갱신이 필요하면 유료 피드를 붙여야 한다."
)


@lru_cache(maxsize=4)
def _live_market(replay_dir, config_dir, mode, timeout) -> LiveMarketAdapter:
    return LiveMarketAdapter(
        replay_dir=replay_dir,
        config_dir=config_dir,
        mode=mode,
        client=HttpClient(timeout_sec=timeout),
    )


@lru_cache(maxsize=4)
def _live_news(config_dir, mode, timeout) -> RssNewsAdapter:
    return RssNewsAdapter(
        config_dir=config_dir, client=HttpClient(timeout_sec=timeout), mode=mode
    )


def reset_adapter_cache() -> None:
    """테스트에서 회로 상태를 초기화한다."""
    _live_market.cache_clear()
    _live_news.cache_clear()


def build_market_adapter(settings: Settings) -> MarketAdapter:
    if settings.data_mode is DataMode.MOCK:
        return MockMarketAdapter(
            settings.mock_dir,
            settings.scenario,
            zscore_window=settings.zscore_window,
        )
    if settings.data_mode in (DataMode.DELAYED, DataMode.LIVE):
        return _live_market(
            settings.replay_dir,
            settings.config_dir,
            # 어떤 모드를 요청했든 데이터는 지연분이다. 표시도 그렇게 한다.
            DataMode.DELAYED,
            settings.http_timeout_sec,
        )
    raise AdapterError(f"알 수 없는 데이터 모드: {settings.data_mode}")


def build_news_adapter(settings: Settings) -> NewsAdapter:
    if settings.data_mode is DataMode.MOCK:
        return MockNewsAdapter(settings.mock_dir, settings.scenario)
    if settings.data_mode in (DataMode.DELAYED, DataMode.LIVE):
        return _live_news(settings.config_dir, DataMode.DELAYED, settings.http_timeout_sec)
    raise AdapterError(f"알 수 없는 데이터 모드: {settings.data_mode}")


def mode_warnings(settings: Settings) -> list[str]:
    """모드 선택 자체에서 오는 경고. 파이프라인이 data_health 에 싣는다."""
    return [LIVE_IS_DELAYED] if settings.data_mode is DataMode.LIVE else []
