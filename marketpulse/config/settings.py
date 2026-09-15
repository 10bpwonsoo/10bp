"""
런타임 설정. 시크릿은 환경변수로만 받는다 (요구 15-8).

기존 upbit_trading/config.py 가 import 시점에 전역 인스턴스를 만들어
테스트가 어려웠던 문제를 피하기 위해, 여기서는 lru_cache 된 팩토리를 쓴다.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..models.common import DataMode

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PACKAGE_ROOT / "config"
MOCK_DIR = PACKAGE_ROOT / "data" / "mock"
REPLAY_DIR = PACKAGE_ROOT / "data" / "replay"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MARKETPULSE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_mode: DataMode = Field(
        default=DataMode.MOCK,
        description="LIVE | DELAYED | MOCK. 기본은 MOCK — LIVE 는 명시적 opt-in 이다.",
    )
    scenario: str = Field(
        default="baseline", description="MOCK 모드에서 재생할 시나리오 이름"
    )

    #: z-score rolling window. 일봉 60, 인트라데이 120 (설계서 STEP 5.1).
    zscore_window: int = 60
    #: 어댑터에 요청하는 히스토리 길이(봉). zscore_window 보다 넉넉해야 하고,
    #: 1년 백분위(252봉)와 "3개월 전 상관"(60+63봉) 을 재려면 그보다 길어야
    #: 한다. 무료 공급자는 1년치를 그냥 준다.
    history_bars: int = 300

    #: LIVE/DELAYED 어댑터의 HTTP 타임아웃. 공급자 하나가 느리다고
    #: 전체 틱이 늘어지면 안 된다.
    http_timeout_sec: float = 8.0
    #: 실데이터에서 뉴스를 몇 건까지 받을지.
    news_limit: int = 60

    #: Anthropic API 키. 보통은 SDK 가 ANTHROPIC_API_KEY 에서 직접 읽는다.
    #: 이 필드(MARKETPULSE_ANTHROPIC_API_KEY)는 실행 환경이 ANTHROPIC_API_KEY
    #: 라는 이름을 따로 다루거나 걸러낼 때의 우회로다. 값은 로그·화면 어디에도
    #: 나가지 않는다 (요구 15-8).
    anthropic_api_key: str | None = Field(default=None, repr=False)
    llm_enabled: bool = Field(
        default_factory=lambda: bool(
            os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("MARKETPULSE_ANTHROPIC_API_KEY")
        ),
        description=(
            "기본값은 '키가 있으면 켠다'. 켜 두고 키가 없으면 매 틱 인증 실패를 "
            "겪고, 꺼 두고 키가 있으면 기능이 논다. MARKETPULSE_LLM_ENABLED 로 "
            "명시하면 그것이 우선한다. false 면 정량 파이프라인만 동작한다."
        ),
    )
    llm_timeout_sec: float = 8.0
    #: 웹검색 호출은 Anthropic 서버가 검색을 여러 번 돌리고 돌아오므로 추출보다
    #: 훨씬 길다 (실측 60초). 8초로 자르면 항상 timeout 이다. 이 경로는 RSS 가
    #: 죽었을 때만 타므로 파이프라인 지연 상한(STEP 7.4)의 예외로 둔다.
    llm_search_timeout_sec: float = 90.0
    #: LLM 웹검색으로 기사를 찾는 경로. 검색은 Anthropic 서버가 하므로 RSS
    #: 호스트가 막혀 있어도 동작한다. auto 는 RSS 가 0건일 때만 쓴다 —
    #: 매 틱 검색을 돌리면 비용이 들고, RSS 가 살아 있으면 필요도 없다.
    news_search: Literal["auto", "on", "off"] = Field(
        default="auto",
        description="auto: RSS 가 비었을 때만 / on: 항상 병합 / off: 쓰지 않음",
    )

    api_title: str = "Market Pulse AI"
    api_version: str = "0.1.0"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    @property
    def config_dir(self) -> Path:
        return CONFIG_DIR

    @property
    def mock_dir(self) -> Path:
        return MOCK_DIR

    @property
    def replay_dir(self) -> Path:
        """로컬 CSV 리플레이. 막힌 네트워크의 탈출구다."""
        return REPLAY_DIR


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """테스트에서 환경변수를 바꾼 뒤 호출한다."""
    get_settings.cache_clear()
