"""
반도체 사이클 탭 서비스 (2026-10-23) — 다른 탭 서비스와 따로 둔다(기존 탭 계산 경로를 건드리지 않는다).

같은 스냅샷(as_of) 위에서: 스냅샷 · Investment(종목 계열)를 캐시에서 받고 → 엔진 → daily snapshot 기록(semiconductor_cycle) → 화면.
MARKET READ(LLM)는 GET 을 붙잡지 않는다 — 준비되면 붙이고, 그동안은 규칙 기반 문장 + '생성 중'.
LLM 이 꺼져 있거나 실패해도 정량 화면은 그대로 나온다.
"""

from __future__ import annotations

import logging
import threading

from ..config.settings import DataMode, Settings

logger = logging.getLogger(__name__)


class SemiconductorCycleService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[object, dict]] = {}
        self._reads: dict[str, tuple[object, dict]] = {}
        self._pending: set[str] = set()

    def _series(self, settings: Settings) -> dict:
        from . import deps
        series = dict(deps.get_service().series(settings))
        try:
            inv = deps.get_investment_service().get(settings)
            series.update(dict(getattr(inv, "_series_by_id", {}) or {}))
        except Exception:
            logger.exception("종목 계열을 받지 못했다 — 주가 확인은 NO DATA 로 둔다")
        return series

    def _generate(self, settings: Settings, key: str, as_of, cyc: dict) -> None:
        from ..ai.client import build_client
        from ..ai.semi_read import attach_read
        try:
            out = attach_read(dict(cyc), client=build_client(settings))
            read = out["market_read"]
        except Exception:
            logger.exception("반도체 MARKET READ 생성 실패 — 규칙 기반 문장 유지")
            read = None
        with self._lock:
            if read is not None:
                self._reads[key] = (as_of, read)
            self._pending.discard(key)

    def get(self, settings: Settings) -> dict:
        from ..engines.semiconductor_cycle import build_semiconductor_cycle
        from ..history.semi import sync_semiconductor
        from . import deps

        key = f"{settings.data_mode.value}:{settings.scenario}"
        snapshot = deps.get_service().get(settings)
        with self._lock:
            hit = self._cache.get(key)
        if hit and hit[0] == snapshot.as_of:
            cyc = dict(hit[1])
        else:
            series = self._series(settings)
            cyc = build_semiconductor_cycle(as_of=snapshot.as_of, series_by_id=series, events=[e.model_dump(mode="json") for e in snapshot.events])
            try:
                hist = sync_semiconductor(deps.get_history_service().manager(settings), cyc, series_by_id=series, as_of=snapshot.as_of, config_dir=settings.config_dir)
                cyc["memory_history"] = hist.model_dump(mode="json")
            except Exception:
                logger.exception("반도체 사이클 daily snapshot 기록 실패 — 화면은 그대로 진행한다")
            with self._lock:
                self._cache[key] = (snapshot.as_of, cyc)
        return self._with_read(settings, key, snapshot.as_of, cyc)

    def _with_read(self, settings: Settings, key: str, as_of, cyc: dict) -> dict:
        mr = dict(cyc.get("market_read") or {})
        if settings.data_mode is DataMode.MOCK:
            return {**cyc, "market_read": {**mr, "status": "skipped", "reason": "MOCK 시나리오 — 실데이터가 아니라 AI 해석을 만들지 않는다"}}
        if not settings.llm_enabled:
            return cyc
        with self._lock:
            hit = self._reads.get(key)
            if hit and hit[0] == as_of:
                return {**cyc, "market_read": hit[1]}
            start = key not in self._pending
            if start:
                self._pending.add(key)
        if start:
            threading.Thread(target=self._generate, args=(settings, key, as_of, cyc), daemon=True, name="semi-market-read").start()
        return {**cyc, "market_read": {**mr, "status": "pending", "reason": "AI 해석 생성 중 — 준비되면 다음 갱신에 바뀐다"}}

    def clear(self) -> None:
        with self._lock:
            self._cache.clear(); self._reads.clear(); self._pending.clear()


_semi = SemiconductorCycleService()


def get_semiconductor_cycle_service() -> SemiconductorCycleService:
    return _semi
