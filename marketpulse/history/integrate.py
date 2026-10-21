"""
탭별 sync — 한 번의 호출로 lifecycle 전체를 돈다:
  promote_stale_live → backfill_missing(과거 창 안의 빈 날짜만) → record(오늘 LIVE/RECORDED) → 저장 sequence 로 화면 모델 조립.
API 서비스와 캡처 파이프라인이 같은 함수를 쓴다. 저장 sequence 가 source of truth 다.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Mapping, Sequence

from ..engines.state_history import trading_dates
from ..models.daily_history import DailyHistory, DailySnapshot
from .assemble import daily_history, market_history, sentiment_history
from .calculators import (AiInputs, MarketInputs, MemoryInputs, RegimeInputs, ai_regime_calculator, ai_regime_snapshot, market_calculator,
                          market_snapshot_from_intelligence, memory_calculator, memory_snapshot, oil_calculator, oil_snapshot, rates_calculator, rates_snapshot,
                          sentiment_calculator, sentiment_snapshot)
from .manager import DailySnapshotManager

logger = logging.getLogger(__name__)


def past_dates(series_by_id: Mapping, as_of: datetime, days: int) -> list[date]:
    """창 안의 과거 거래일(오늘 제외). 봉이 넓게 있는 날만 거래일이다."""
    today = DailySnapshotManager.snapshot_date_of(as_of)
    return [d for d in trading_dates(series_by_id, as_of, days + 1) if d < today][-days:]


def _window(manager: DailySnapshotManager, tab_id: str, as_of: datetime, days: int) -> list[DailySnapshot]:
    """저장 키 순서의 마지막 행들. 화면 view 는 KST snapshot 날짜로 다시 묶어(같은 날짜의 저장 행은 하나로) days 개를 고르므로 여유분을 더 읽는다."""
    today = manager.snapshot_date_of(as_of)
    rows = manager.get_history(tab_id, None, today)
    return rows[-(days + days // 2 + 5):]


def _run(manager: DailySnapshotManager, tab_id: str, *, dates: Sequence[date], calc, live: DailySnapshot | None, as_of: datetime, backfill: bool = True) -> None:
    manager.promote_stale_live(tab_id, today=manager.snapshot_date_of(as_of))
    if backfill:
        manager.backfill_missing(tab_id, dates, calc)
    if live is not None:
        manager.record(live, as_of=as_of)


# ── market_regime ──────────────────────────────────────────
def sync_market(manager: DailySnapshotManager, *, inputs: MarketInputs, snapshot=None, as_of: datetime, days: int | None = None, backfill: bool = True):
    days = days or manager.window_days
    dates = past_dates(inputs.series_by_id, as_of, manager.backfill_days)
    live = market_snapshot_from_intelligence(snapshot, config_dir=inputs.config_dir) if snapshot is not None else None
    if live is None:
        got = market_calculator(inputs, as_of=as_of)(manager.snapshot_date_of(as_of), manager.get_snapshot("market_regime", manager.snapshot_date_of(as_of) - timedelta(days=1)))
        live = got
    _run(manager, "market_regime", dates=dates, calc=market_calculator(inputs, as_of=as_of), live=live, as_of=as_of, backfill=backfill)
    return market_history(_window(manager, "market_regime", as_of, days), as_of=as_of, days=days, config_dir=inputs.config_dir)


def market_context(manager: DailySnapshotManager) -> dict[date, tuple[str, float]]:
    return {s.snapshot_date: (s.state, float(s.confidence or 0.0)) for s in manager.get_history("market_regime")}


# ── ai_sentiment / ai_regime (같은 AiRegime 에서) ──────────
def sentiment_cfg(cfg_all: Mapping) -> dict:
    cfg = dict(cfg_all.get("sentiment") or {})
    cfg["_narrative_drivers"] = [s for s in cfg_all.get("narrative_drivers", []) if any(i.get("source") == "narrative" and i.get("key") == s.get("key") for c in cfg.get("components", []) for i in c.get("inputs", []))]
    return cfg


def sync_sentiment(manager: DailySnapshotManager, regime, *, cfg_all: Mapping, dv, bench_dates: Sequence[date], as_of: datetime, days: int | None = None, config_dir=None, backfill: bool = True):
    """regime.sentiment.history 를 저장 sequence 로 바꿔 끼운다. dv = DayValues(backfill 입력)."""
    cfg = sentiment_cfg(cfg_all)
    days = days or int((cfg.get("history") or {}).get("days", manager.window_days))
    today = manager.snapshot_date_of(as_of)
    dates = [d for d in bench_dates if d < today][-manager.backfill_days:]
    live = sentiment_snapshot(regime.sentiment, as_of=as_of, config_dir=config_dir) if regime.sentiment is not None and regime.sentiment.index is not None else None
    _run(manager, "ai_sentiment", dates=dates, calc=sentiment_calculator(cfg, dv, config_dir=config_dir), live=live, as_of=as_of, backfill=backfill)
    hist = sentiment_history(_window(manager, "ai_sentiment", as_of, days), cfg, days=days, config_dir=config_dir)
    if regime.sentiment is not None:
        regime.sentiment.history = hist
    return hist


def sync_ai_regime(manager: DailySnapshotManager, regime, *, inputs: AiInputs, as_of: datetime, days: int | None = None, backfill: bool = True) -> DailyHistory:
    days = days or manager.window_days
    dates = past_dates(inputs.basket_series, as_of, manager.backfill_days)
    inputs.market_context = market_context(manager)
    live = ai_regime_snapshot(regime, as_of=as_of, config_dir=inputs.config_dir)
    _run(manager, "ai_regime", dates=dates, calc=ai_regime_calculator(inputs, as_of=as_of), live=live, as_of=as_of, backfill=backfill)
    return daily_history("ai_regime", _window(manager, "ai_regime", as_of, days), as_of=as_of, days=days, config_dir=inputs.config_dir)


# ── rates / oil ────────────────────────────────────────────
def sync_rates(manager: DailySnapshotManager, rates, *, inputs: RegimeInputs, as_of: datetime, days: int | None = None, backfill: bool = True) -> DailyHistory:
    days = days or manager.window_days
    dates = past_dates(inputs.series_by_id, as_of, manager.backfill_days)
    _run(manager, "rates_regime", dates=dates, calc=rates_calculator(inputs, as_of=as_of), live=rates_snapshot(rates, as_of=as_of, config_dir=inputs.config_dir), as_of=as_of, backfill=backfill)
    return daily_history("rates_regime", _window(manager, "rates_regime", as_of, days), as_of=as_of, days=days, config_dir=inputs.config_dir)


def sync_oil(manager: DailySnapshotManager, oil, *, inputs: RegimeInputs, as_of: datetime, days: int | None = None, backfill: bool = True) -> DailyHistory:
    days = days or manager.window_days
    dates = past_dates(inputs.series_by_id, as_of, manager.backfill_days)
    _run(manager, "oil_regime", dates=dates, calc=oil_calculator(inputs, as_of=as_of), live=oil_snapshot(oil, as_of=as_of, config_dir=inputs.config_dir), as_of=as_of, backfill=backfill)
    return daily_history("oil_regime", _window(manager, "oil_regime", as_of, days), as_of=as_of, days=days, config_dir=inputs.config_dir)


# ── memory cycle ───────────────────────────────────────────
def sync_memory(manager: DailySnapshotManager, investment, *, inputs: MemoryInputs, as_of: datetime, days: int | None = None, backfill: bool = True) -> DailyHistory:
    days = days or manager.window_days
    dates = past_dates(inputs.series_by_id, as_of, manager.backfill_days) if inputs.series_by_id else []
    live = memory_snapshot(investment.semiconductor, as_of=as_of, config_dir=inputs.config_dir) if investment is not None else None
    _run(manager, "memory_cycle", dates=dates, calc=memory_calculator(inputs, as_of=as_of), live=live, as_of=as_of, backfill=backfill)
    return daily_history("memory_cycle", _window(manager, "memory_cycle", as_of, days), as_of=as_of, days=days, config_dir=inputs.config_dir)


def history_of(manager: DailySnapshotManager, tab_id: str, *, as_of: datetime, days: int | None = None, config_dir=None) -> DailyHistory:
    """계산 없이 저장된 것만 조립한다 (API 의 /history/{tab})."""
    days = days or manager.window_days
    return daily_history(tab_id, _window(manager, tab_id, as_of, days), as_of=as_of, days=days, config_dir=config_dir)
