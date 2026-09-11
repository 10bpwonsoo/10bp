"""
런타임 설정. 시크릿은 환경변수로만 받는다 (요구 15-8).

기존 upbit_trading/config.py 가 import 시점에 전역 인스턴스를 만들어
테스트가 어려웠던 문제를 피하기 위해, 여기서는 lru_cache 된 팩토리를 쓴다.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..models.common import DataMode

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PACKAGE_ROOT / "config"
MOCK_DIR = PACKAGE_ROOT / "data" / "mock"


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
    #: 시나리오 생성 시 만드는 히스토리 길이. zscore_window 보다 넉넉해야 한다.
    history_bars: int = 180

    llm_enabled: bool = Field(
        default=False,
        description="false 이면 정량 파이프라인만 동작한다. LLM 실패와 동일한 경로.",
    )
    llm_timeout_sec: float = 8.0

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """테스트에서 환경변수를 바꾼 뒤 호출한다."""
    get_settings.cache_clear()
