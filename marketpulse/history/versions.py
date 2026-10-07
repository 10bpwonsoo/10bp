"""model_version / logic_version. 룰(config)이 바뀌면 logic_version 이 바뀐다 — 과거 snapshot 은 그대로 남아 모델 진화를 추적할 수 있다."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

import yaml

from ..config.settings import CONFIG_DIR


@lru_cache(maxsize=4)
def load_history_config(config_dir: Path | None = None) -> dict:
    return yaml.safe_load(((config_dir or CONFIG_DIR) / "history.yaml").read_text(encoding="utf-8")) or {}


def logic_version(tab_id: str, config_dir: Path | None = None) -> str:
    cfg = load_history_config(config_dir)
    files = list((cfg.get("logic_files") or {}).get(tab_id) or [])
    h = hashlib.sha1()
    for name in files:
        p = (config_dir or CONFIG_DIR) / name
        if p.exists():
            h.update(name.encode()); h.update(p.read_bytes())
    return f"rules_{h.hexdigest()[:8]}" if files else "rules_unversioned"


_MODEL: dict[str, str] = {}


def model_version(tab_id: str) -> str:
    if tab_id in _MODEL:
        return _MODEL[tab_id]
    v = "0"
    try:
        if tab_id == "market_regime":
            from ..engines.market_state import ENGINE_VERSION as v  # noqa: F811
        elif tab_id in ("ai_sentiment", "ai_regime"):
            from ..engines.ai_regime import ENGINE_VERSION as v  # noqa: F811
        elif tab_id == "rates_regime":
            from ..engines.rates_regime import ENGINE_VERSION as v  # noqa: F811
        elif tab_id == "oil_regime":
            from ..engines.oil_regime import ENGINE_VERSION as v  # noqa: F811
        elif tab_id == "memory_cycle":
            from ..engines.semiconductor import ENGINE_VERSION as v  # noqa: F811
    except Exception:
        v = "0"
    _MODEL[tab_id] = f"{tab_id}_v{v}"
    return _MODEL[tab_id]
