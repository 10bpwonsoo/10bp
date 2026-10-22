"""
저장 기록 날짜 view (2026-10-22) — history 화면은 저장 당시 그대로(저장 키 = as_of 의 UTC 날짜, 저장 당시 공식 판정)를 보인다.

2026-10-21~22 사이 잠깐 KST Daily Snapshot 날짜로 다시 묶은 view(date_basis='kst_snapshot')로 만든 저장본(10/22 아카이브·캡처)이 있다.
파일은 고치지 않는다(아카이브는 불변). 읽을 때만 같은 날짜까지의 저장 기록(LOCKED 행 — 값이 바뀌지 않는다)으로
예전 방식의 history 섹션을 다시 조립해 다른 날짜 화면과 같은 기준으로 보인다. 그 밖의 섹션(MARKET NOW 등)은 저장본 그대로.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

KST_BASIS = "kst_snapshot"


def _kst(section: Any) -> bool:
    return isinstance(section, Mapping) and section.get("date_basis") == KST_BASIS


def needs_view(doc: Mapping[str, Any]) -> bool:
    ck = doc.get("cockpit") or {}
    ai = doc.get("ai_regime") or {}
    return (_kst(ck.get("history")) or _kst(doc.get("market_state_history")) or any(_kst(h) for h in (doc.get("daily_history") or {}).values())
            or _kst(((ai.get("sentiment") or {}).get("history"))))


def storage_view(doc: Mapping[str, Any], *, as_of: datetime, manager, config_dir=None) -> dict:
    """KST view 로 저장된 history 섹션 → 저장 키(UTC 날짜) 기준 history. as_of = 그 저장본의 기준 시각(source_asof). 저장소는 읽기만 한다."""
    if not needs_view(doc):
        return dict(doc)
    from ..engines.ai_regime import load_ai_regime_config
    from ..engines.cockpit import load_cockpit_config
    from ..engines.regime_history import build_regime_history
    from .assemble import market_history, sentiment_history
    from .integrate import _window, history_of
    out = dict(doc)
    days = manager.window_days
    hist = market_history(_window(manager, "market_regime", as_of, days), as_of=as_of, days=days, config_dir=config_dir)
    if _kst(out.get("market_state_history")):
        out["market_state_history"] = hist.model_dump(mode="json")
    ck = out.get("cockpit")
    if isinstance(ck, Mapping) and _kst(ck.get("history")):
        old = ck["history"]
        rh = build_regime_history(hist, load_cockpit_config(config_dir).get("history") or {}, as_of=as_of, stored_days=len(hist.points))
        if rh is not None:
            new = rh.model_dump(mode="json")
            # 1D/5D 방향(그 시각의 z)·기간 버튼은 날짜와 무관한 값이라 저장본 그대로
            hz = {d.get("key"): d for d in old.get("drivers") or []}
            for d in new.get("drivers") or []:
                o = hz.get(d.get("key"))
                if o:
                    d.update({k: o.get(k) for k in ("horizons", "horizon_read", "horizon_label") if k in o})
            new["ranges"] = old.get("ranges", new.get("ranges"))
            out["cockpit"] = {**ck, "history": new}
    dh = out.get("daily_history")
    if isinstance(dh, Mapping):
        out["daily_history"] = {tab: (history_of(manager, tab, as_of=as_of, days=days, config_dir=config_dir).model_dump(mode="json") if _kst(h) else h) for tab, h in dh.items()}
    ai = out.get("ai_regime")
    sent = (ai or {}).get("sentiment") if isinstance(ai, Mapping) else None
    if isinstance(sent, Mapping) and _kst(sent.get("history")):
        cfg_all = load_ai_regime_config(config_dir)
        cfg = dict(cfg_all.get("sentiment") or {})
        cfg["_narrative_drivers"] = [s for s in cfg_all.get("narrative_drivers", []) if any(i.get("source") == "narrative" and i.get("key") == s.get("key") for c in cfg.get("components", []) for i in c.get("inputs", []))]
        n = int((cfg.get("history") or {}).get("days", days))
        sh = sentiment_history(_window(manager, "ai_sentiment", as_of, n), cfg, days=n, config_dir=config_dir)
        out["ai_regime"] = {**ai, "sentiment": {**sent, "history": sh.model_dump(mode="json")}}
    return out


def doc_as_of(doc: Mapping[str, Any]) -> datetime | None:
    src = (doc.get("meta") or {}).get("source_asof") or (doc.get("snapshot") or {}).get("as_of") or doc.get("as_of")
    return datetime.fromisoformat(str(src).replace("Z", "+00:00")) if src else None
