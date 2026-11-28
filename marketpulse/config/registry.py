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


# ── Investment Intelligence (2026-09-16 신설, 전부 추가) ──────────
@lru_cache(maxsize=4)
def get_universe(config_dir: Path | None = None):
    """universe.yaml — 종목과 대체데이터 정의."""
    from ..models.intelligence import Universe

    d = config_dir or CONFIG_DIR
    with (d / "universe.yaml").open(encoding="utf-8") as fh:
        spec = yaml.safe_load(fh) or {}
    return Universe(
        stocks=spec.get("stocks", []) or [],
        alternative=spec.get("alternative", []) or [],
        benchmark_market=(spec.get("benchmarks") or {}).get("market", "KOSPI"),
    )


@lru_cache(maxsize=4)
def get_stock_exposures(config_dir: Path | None = None) -> dict:
    """stock_exposures.yaml — 종목별 사업 노출. {stock_id: {driver_id: FundamentalExposure}}"""
    from ..models.intelligence import FundamentalExposure

    d = config_dir or CONFIG_DIR
    with (d / "stock_exposures.yaml").open(encoding="utf-8") as fh:
        spec = yaml.safe_load(fh) or {}
    out: dict[str, dict[str, FundamentalExposure]] = {}
    for stock_id, drivers in spec.items():
        out[stock_id] = {
            driver_id: FundamentalExposure(driver_id=driver_id, **e) for driver_id, e in (drivers or {}).items()
        }
    return out


@lru_cache(maxsize=4)
def get_intelligence_config(config_dir: Path | None = None) -> dict:
    d = config_dir or CONFIG_DIR
    with (d / "intelligence.yaml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def reset_intelligence_cache() -> None:
    get_universe.cache_clear()
    get_stock_exposures.cache_clear()
    get_intelligence_config.cache_clear()
