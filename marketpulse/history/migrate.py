"""
기존 캡처(data/captures/*/)의 판정을 RECORDED snapshot 으로 옮긴다 — 그 날짜 당시 시스템이 실제로 저장한 값이다.
state_history.json 처럼 당시에 재계산한 값은 옮기지 않는다(출처가 '그날 저장' 이 아니므로 BACKFILLED 로 다시 만든다).
같은 날짜에 캡처가 여럿이면 마지막 as_of 를 쓴다. 이미 RECORDED 가 있으면 건드리지 않는다. BACKFILLED 가 먼저 있었다면 진짜 RECORDED 로 교체하되 audit trail 을 남긴다.
"""

from __future__ import annotations

import json
import logging
from datetime import timezone
from pathlib import Path

from ..models.ai_regime import AiRegime
from ..models.daily_history import DailySnapshot
from ..models.intelligence import InvestmentIntelligence
from ..models.oil_regime import OilRegime
from ..models.rates_regime import RatesRegime
from ..models.snapshot import IntelligenceSnapshot
from .calculators import ai_regime_snapshot, market_snapshot_from_intelligence, memory_snapshot, oil_snapshot, rates_snapshot, sentiment_snapshot
from .manager import DailySnapshotManager

logger = logging.getLogger(__name__)


def _recorded(s: DailySnapshot, as_of) -> DailySnapshot:
    return s.model_copy(update={"history_source": "RECORDED", "is_final": True, "is_locked": True, "is_backfilled": False, "finalization": "migrated", "calculated_at": as_of})


def _place(manager: DailySnapshotManager, s: DailySnapshot, *, by: str) -> str:
    cur = manager.get_snapshot(s.tab_id, s.snapshot_date)
    if s.snapshot_date >= manager.today():
        # 오늘 캡처는 아직 확정 전일 수 있다 — record() 가 finalize_time 으로 LIVE / RECORDED 를 가른다
        if cur is not None and cur.is_locked:
            return "kept"
        manager.record(s.model_copy(update={"finalization": "live"}), as_of=s.calculated_at); return "recorded_today"
    if cur is None:
        manager.save_snapshot(s); return "added"
    if cur.history_source == "RECORDED":
        return "kept"
    if cur.history_source == "BACKFILLED":
        manager.correct(s.tab_id, s.snapshot_date, s, reason="migration: 그날 당시 캡처에 실제 저장된 판정이 있어 BACKFILLED 를 RECORDED 로 교체", by=by)
        return "replaced_backfilled"
    manager.save_snapshot(s); return "replaced_live"


def migrate_captures(manager: DailySnapshotManager, captures_dir: Path, *, by: str = "migrate_captures", config_dir=None) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    latest: dict[tuple[str, object], tuple] = {}
    for cap in sorted(p for p in Path(captures_dir).iterdir() if p.is_dir()):
        live_p = cap / "live.json"
        if not live_p.exists():
            continue
        snap = IntelligenceSnapshot.model_validate_json(live_p.read_text(encoding="utf-8"))
        d = snap.as_of.astimezone(timezone.utc).date()
        cands = [("market_regime", _recorded(market_snapshot_from_intelligence(snap, config_dir=config_dir), snap.as_of))]
        ai_p = cap / "ai_regime.json"
        if ai_p.exists():
            try:
                r = AiRegime.model_validate_json(ai_p.read_text(encoding="utf-8"))
                cands.append(("ai_regime", _recorded(ai_regime_snapshot(r, as_of=r.as_of, d=d, config_dir=config_dir), r.as_of)))
                if r.sentiment is not None and r.sentiment.index is not None:
                    cands.append(("ai_sentiment", _recorded(sentiment_snapshot(r.sentiment, as_of=r.as_of, d=d, config_dir=config_dir), r.as_of)))
            except Exception:
                logger.exception("%s ai_regime.json 을 읽지 못했다 — 건너뛴다", cap.name)
        for name, model, fn in (("rates_regime.json", RatesRegime, rates_snapshot), ("oil_regime.json", OilRegime, oil_snapshot)):
            p = cap / name
            if p.exists():
                try:
                    r = model.model_validate_json(p.read_text(encoding="utf-8"))
                    cands.append((fn.__name__.replace("_snapshot", "_regime"), _recorded(fn(r, as_of=r.as_of, d=d, config_dir=config_dir), r.as_of)))
                except Exception:
                    logger.exception("%s %s 을 읽지 못했다 — 건너뛴다", cap.name, name)
        inv_p = cap / "investment.json"
        if inv_p.exists():
            try:
                inv = InvestmentIntelligence.model_validate_json(inv_p.read_text(encoding="utf-8"))
                cands.append(("memory_cycle", _recorded(memory_snapshot(inv.semiconductor, as_of=inv.as_of, d=d, config_dir=config_dir), inv.as_of)))
            except Exception:
                logger.exception("%s investment.json 을 읽지 못했다 — 건너뛴다", cap.name)
        for tab, s in cands:
            key = (tab, d)
            if key not in latest or latest[key][0] < s.calculated_at:
                latest[key] = (s.calculated_at, s, cap.name)
    for (tab, d), (_, s, cap_name) in sorted(latest.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        res = _place(manager, s, by=f"{by}:{cap_name}")
        out.setdefault(tab, {})[res] = out.setdefault(tab, {}).get(res, 0) + 1
    return out
