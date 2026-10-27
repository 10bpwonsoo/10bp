"""
archive 섹션을 모으는 두 경로.

live_collectors(settings)   API 서버와 같은 서비스·캐시를 부른다. 순서가 곧 정합성이다:
                            1) snapshot 을 강제로 새로 수집 → 2) 하위 서비스는 그 snapshot(같은 as_of)을 캐시에서 받아 계산.
                            Investment 는 시간 TTL 캐시라 먼저 비워 같은 snapshot 위에서 다시 만든다.
capture_dir_collectors(dir) 이미 커밋된 캡처 디렉터리(data/captures/*)의 JSON 을 그대로 섹션으로 읽는다 — 정적 배포본이
                            보여 준 바로 그 화면. 과거 날짜 저장본을 처음 채울 때 쓴다(created_by=capture_import).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

Collector = Callable[[], Any]

#: 캡처 디렉터리 파일 → archive 섹션
CAPTURE_FILES = {
    "snapshot": "live.json",
    "cockpit": "cockpit.json",
    "market_state_history": "state_history.json",
    "ai_regime": "ai_regime.json",
    "rates_regime": "rates_regime.json",
    "oil_regime": "oil_regime.json",
    "investment": "investment.json",
    "scenario_checks": "scenario_check.json",
    "analyst_views": "analyst_views.json",
    "daily_history": "daily_history.json",
    "news": "news_live.json",
    "semiconductor_cycle": "semiconductor_cycle.json",
}


def live_collectors(settings) -> dict[str, Collector]:
    from ..adapters.registry import build_news_adapter
    from ..api import deps

    state: dict[str, Any] = {}

    def snapshot():
        snap = deps.get_service().get(settings, force=True)  # 1) 강제 refresh
        state["snapshot"] = snap
        deps.get_investment_service().clear()  # 시간 TTL 캐시 — 이 snapshot 위에서 다시 만든다
        return snap

    def daily_history():
        svc = deps.get_history_service()
        return {tab: svc.get(settings, tab) for tab in svc.PRODUCERS}

    return {
        "snapshot": snapshot,
        "cockpit": lambda: deps.get_cockpit_service().get(settings),
        "market_state_history": lambda: deps.get_state_history_service().get(settings),
        "ai_regime": lambda: deps.get_ai_regime_service().get(settings),
        "rates_regime": lambda: deps.get_rates_regime_service().get(settings),
        "oil_regime": lambda: deps.get_oil_regime_service().get(settings),
        "investment": lambda: deps.get_investment_service().get(settings),
        "scenario_checks": lambda: deps.get_scenario_check_service().get(settings),
        "analyst_views": lambda: deps.get_analyst_view_service().get(settings, None),
        "daily_history": daily_history,
        "news": lambda: build_news_adapter(settings).fetch_news(limit=50),
        "semiconductor_cycle": lambda: _semi(settings),
    }


def _semi(settings):
    from ..api.semi_service import get_semiconductor_cycle_service
    return get_semiconductor_cycle_service().get(settings)


def capture_dir_collectors(directory: Path) -> dict[str, Collector]:
    """파일이 없으면 그 섹션은 수집 실패로 남는다(null + errors) — 다른 날짜 파일로 메우지 않는다."""
    def reader(name: str) -> Collector:
        def read():
            p = directory / name
            if not p.is_file():
                raise FileNotFoundError(f"캡처에 {name} 이 없다")
            return json.loads(p.read_text(encoding="utf-8"))
        return read
    return {section: reader(fname) for section, fname in CAPTURE_FILES.items()}


def capture_dir_asof(directory: Path) -> datetime:
    """캡처의 기준 시각 = live.json 의 as_of. 가져온 저장본의 날짜·generated_at 이 이것을 따른다."""
    snap = json.loads((directory / "live.json").read_text(encoding="utf-8"))
    return datetime.fromisoformat(str(snap["as_of"]).replace("Z", "+00:00"))
