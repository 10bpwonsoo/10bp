"""MARKET OVERVIEW (2026-11-12) — 기존 서비스 결과(cockpit · 금리 · 유가 · AI · 반도체)를 같은 스냅샷 위에서 모아 LLM 시장 종합을 붙인다.
새 계산 없음. LLM 은 의미 있는 변화(판정 지문)에서만 다시 부른다 — 새로고침 · 탭 이동마다 부르지 않는다."""

from __future__ import annotations

import json
import logging
from typing import Any

from ..config.settings import Settings

logger = logging.getLogger(__name__)


def _j(x: Any) -> Any:
    return json.loads(x.model_dump_json()) if hasattr(x, "model_dump_json") else x


def get_market_overview(settings: Settings) -> dict:
    from ..ai import market_overview as MO
    from ..ai.client import build_client
    from . import deps
    from .semi_service import get_semiconductor_cycle_service

    def _try(f):
        try:
            return _j(f())
        except Exception:  # noqa: BLE001
            logger.exception("MARKET OVERVIEW 입력 섹션 실패 — 그 섹션은 결측으로")
            return None

    doc = {"snapshot": _try(lambda: deps.get_service().get(settings)), "cockpit": _try(lambda: deps.get_cockpit_service().get(settings)),
           "rates_regime": _try(lambda: deps.get_rates_regime_service().get(settings)), "oil_regime": _try(lambda: deps.get_oil_regime_service().get(settings)),
           "ai_regime": _try(lambda: deps.get_ai_regime_service().get(settings)), "semiconductor_cycle": _try(lambda: get_semiconductor_cycle_service().get(settings))}
    return MO.live_overview(doc, client=build_client(settings) if settings.llm_enabled else None)
