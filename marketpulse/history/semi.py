"""
반도체 사이클 탭 daily snapshot (2026-10-23) — 다른 탭과 같은 lifecycle(promote_stale_live → backfill_missing → record)을 쓴다.

오늘 값 = 화면이 보여 준 국면(engines/semiconductor_cycle). 과거 빈 날짜 = 그 날짜 끝(UTC) 이전에 공개된 현물·계약가·HBM 앵커·수출 발표·주가만으로
1회 계산(BACKFILLED) 후 고정. 과거 날짜의 뉴스는 저장본이 없어 넣지 않는다(supply_news 증거 None — 0 이 아니다).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Mapping

from ..models.daily_history import DailyHistory, DailySnapshot
from .assemble import daily_history
from .calculators import _base, _end_of, _label_of, _sliced
from .integrate import _run, _window, past_dates
from .manager import DailySnapshotManager

TAB = "semiconductor_cycle"


def semi_snapshot(cyc: Mapping[str, Any], *, as_of: datetime, d: date | None = None, config_dir=None, note: str = "") -> DailySnapshot | None:
    reg = cyc.get("regime") or {}
    state = str(reg.get("state") or "")
    if not state or state in ("NO DATA", "INSUFFICIENT_DATA") or reg.get("composite") is None:
        return None
    d = d or as_of.astimezone(timezone.utc).date()
    comps = {c["key"]: c.get("score") for c in reg.get("components") or []}
    prem = {x["spot"]: x.get("current") for x in cyc.get("spot_premium") or [] if x.get("available")}
    ex = cyc.get("export_nowcast") or {}
    return _base(TAB, d, as_of, config_dir=config_dir, state=state, state_label=_label_of(TAB, state, config_dir), state_score=reg.get("composite"),
                 confidence=reg.get("confidence"), component_scores=comps, data_coverage=reg.get("coverage"),
                 key_drivers=[c["label"] for c in sorted((c for c in reg.get("components") or [] if c.get("score") is not None), key=lambda c: -abs(c["score"]) * c.get("weight", 1.0))][:3],
                 missing_components=[k for k, v in comps.items() if v is None],
                 summary=f"{reg.get('label')} · composite {reg.get('composite'):+.0f} · 신뢰도 {reg.get('confidence'):.0f}",
                 payload={"chips": {c["key"]: c["value"] for c in reg.get("chips") or []}, "premium": prem,
                          "export": {"scope": ex.get("latest_scope_label"), "yoy": ex.get("latest_yoy"), "nowcast_yoy": (ex.get("nowcast") or {}).get("yoy_mid")},
                          "equity": (cyc.get("equity_confirmation") or {}).get("status"), "note": note})


def semi_calculator(series_by_id: Mapping[str, Any], *, as_of: datetime, config_dir=None):
    from ..engines.semiconductor_cycle import build_semiconductor_cycle

    def calc(d: date, prev: DailySnapshot | None) -> DailySnapshot | None:
        cutoff = min(as_of, _end_of(d))
        cyc = build_semiconductor_cycle(as_of=cutoff, series_by_id=_sliced(dict(series_by_id), cutoff), events=())
        return semi_snapshot(cyc, as_of=cutoff, d=d, config_dir=config_dir, note="BACKFILL — 그 날짜까지 공개된 가격·수출·주가만, 뉴스 제외")
    return calc


def sync_semiconductor(manager: DailySnapshotManager, cyc: Mapping[str, Any] | None, *, series_by_id: Mapping[str, Any], as_of: datetime,
                       days: int | None = None, backfill: bool = True, config_dir=None) -> DailyHistory:
    days = days or manager.window_days
    dates = past_dates(series_by_id, as_of, manager.backfill_days) if series_by_id else []
    live = semi_snapshot(cyc, as_of=as_of, config_dir=config_dir) if cyc is not None else None
    _run(manager, TAB, dates=dates, calc=semi_calculator(series_by_id, as_of=as_of, config_dir=config_dir), live=live, as_of=as_of, backfill=backfill)
    return daily_history(TAB, _window(manager, TAB, as_of, days), as_of=as_of, days=days, config_dir=config_dir)
