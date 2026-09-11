"""YAML 레지스트리 로더. 설정은 코드가 아니라 파일에 둔다 (요구 15-9)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ..models.market import InstrumentRegistry
from ..models.theme import ThemeRegistry
from .settings import CONFIG_DIR


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} 최상위는 매핑이어야 한다")
    return data


@lru_cache(maxsize=1)
def get_instruments(config_dir: Path | None = None) -> InstrumentRegistry:
    d = config_dir or CONFIG_DIR
    return InstrumentRegistry.model_validate(load_yaml(d / "instruments.yaml"))


@lru_cache(maxsize=1)
def get_themes(config_dir: Path | None = None) -> ThemeRegistry:
    d = config_dir or CONFIG_DIR
    return ThemeRegistry.model_validate(load_yaml(d / "themes.yaml"))


def reset_registry_cache() -> None:
    get_instruments.cache_clear()
    get_themes.cache_clear()
