"""
예전 저장본의 history 를 KST snapshot 날짜 view 로 보여 준다 (2026-10-21).

2026-10-21 이전에 만든 아카이브·캡처의 history 섹션은 저장 키(as_of 의 UTC 날짜)로 날짜가 붙어 있고, 장중 LIVE 가 daily 띠의 마지막 칸에 들어 있다.
파일은 고치지 않는다(아카이브는 불변). 읽을 때만 같은 규칙(history/dates.py)으로
  · 날짜를 KST Daily Snapshot 날짜로 다시 붙이고(market_date 는 따로)
  · 같은 snapshot 날짜의 저장 행을 하나로 묶고(빠진 행은 merged 에 남긴다)
  · 장중 LIVE 를 intraday 로 뺀 뒤
  · 구간·전환·비중 같은 파생값만 그 daily 점에서 다시 센다.
날짜별 값(판정·확신·점수·factor·driver)은 저장본 그대로다. 공식(display) regime 은 같은 안정화 규칙을 daily 점에 다시 적용한 결과다.
data_asof 는 저장소의 고정된(LOCKED) 행에서 찾는다 — 저장본의 LIVE 칸은 그 저장본의 기준 시각(source_asof)을 쓴다.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable, Mapping

from ..models.ai_regime import SentimentHistory
from ..models.cockpit import RegimeHistory, RegimeIntraday
from ..models.daily_history import DailyHistory, DailySnapshot
from ..models.state_history import MarketStateHistory
from .assemble import daily_view, sentiment_view, state_view
from .dates import load_rule, parse_d, parse_dt, resolve, trim

RowsOf = Callable[[str], Mapping[date, DailySnapshot]]

VIEW = "kst_snapshot"


def _lookup(rows_of: RowsOf, tab: str, live_asof: datetime | None) -> Callable[[date, str], datetime | None]:
    rows = rows_of(tab)

    def f(d: date, source: str) -> datetime | None:
        if source == "LIVE":
            return live_asof
        s = rows.get(d)
        if s is not None and s.is_locked and s.history_source == source:
            return s.data_asof
        return None

    return f


def upgrade_state(h: Mapping[str, Any], look) -> dict:
    m = MarketStateHistory.model_validate(h)
    if m.date_basis == VIEW:
        return dict(h)
    labels = {**m.component_labels, **m.excluded_components}
    out = state_view(m.points, as_of=m.as_of, days=m.days_requested or len(m.points), history_mode=m.history_mode, footnote=m.footnote, note=m.note,
                     component_labels=labels, asof_of=lambda p: look(p.date, p.source) or p.as_of)
    return out.model_dump(mode="json")


def upgrade_daily(tab: str, h: Mapping[str, Any], look) -> dict:
    m = DailyHistory.model_validate(h)
    if m.date_basis == VIEW:
        return dict(h)
    out = daily_view(tab, m.points, as_of=m.as_of, days=m.window_days or len(m.points), asof_of=lambda p: look(p.date, p.source) or p.data_asof)
    return out.model_dump(mode="json")


def upgrade_sentiment(h: Mapping[str, Any], look, cfg: Mapping) -> dict:
    m = SentimentHistory.model_validate(h)
    if m.date_basis == VIEW:
        return dict(h)
    out = sentiment_view(m.points, cfg, days=m.days or len(m.points), foot=m.footnote, history_mode=m.history_mode,
                         asof_of=lambda p: look(parse_d(p.date), p.source) or parse_dt(p.data_asof))
    return out.model_dump(mode="json")


def upgrade_regime(h: Mapping[str, Any], look, hcfg: Mapping) -> dict:
    from ..engines.regime_history import finish_regime_history
    old = RegimeHistory.model_validate(h)
    if old.date_basis == VIEW or not old.days:
        return dict(h)
    rule = load_rule()
    res = trim(resolve(old.days, storage=lambda d: parse_d(d.date), source=lambda d: d.source, asof=lambda d: look(parse_d(d.date), d.source), rule=rule),
               int(hcfg.get("days", 22)))
    drop = {"display_regime", "display_label", "bridged", "is_transition"}
    rows = []
    for d, rd, merged in res.rows:
        r = {k: v for k, v in d.model_dump().items() if k not in drop}
        r.update(date=rd.snapshot_date.isoformat(), market_date=rd.market_date.isoformat() if rd.market_date else "", storage_date=rd.storage_date.isoformat(),
                 data_asof=rd.data_asof.isoformat() if rd.data_asof else "", merged=merged)
        rows.append(r)
    if not rows:
        return dict(h)
    new = finish_regime_history(rows, [r["dominant_regime"] for r in rows], [float(r["evidence_strength"]) for r in rows], [r["dominant_regime_dwell"] for r in rows], hcfg,
                                history_mode=old.history_mode, footnote=old.footnote)
    # 기간 버튼 · 1D/5D 방향(그 시각의 z)은 날짜와 무관한 값이라 저장본 그대로 둔다
    hz = {dr.key: dr for dr in old.drivers}
    drivers = [dr.model_copy(update={"horizons": hz[dr.key].horizons, "horizon_read": hz[dr.key].horizon_read, "horizon_label": hz[dr.key].horizon_label}) if dr.key in hz else dr
               for dr in new.drivers]
    upd: dict[str, Any] = {"ranges": old.ranges, "drivers": drivers, "date_basis": VIEW, "snapshot_time": rule.label, "gaps": [g.isoformat() for g in res.gaps]}
    live = None
    if res.intraday is not None:
        from ..engines.regime_history import live_signal_of
        d, rd = res.intraday
        live_row = {"raw_state": d.raw_state, "dominant_regime": d.dominant_regime, "data_asof": rd.data_asof.isoformat() if rd.data_asof else "",
                    "market_date": rd.market_date.isoformat() if rd.market_date else "", "evidence_strength": d.evidence_strength}
        live = live_signal_of(live_row, rows[-1]["market_date"], hcfg)
        # 장중 요약 — official 은 daily 공식 판정 그대로(장중 값이 공식을 바꾸지 않는다)
        upd["intraday"] = RegimeIntraday(date=rd.snapshot_date.isoformat(), as_of=rd.data_asof.isoformat() if rd.data_asof else "", market_date=rd.market_date.isoformat() if rd.market_date else "",
                                         raw_state=d.raw_state, raw_regime=d.dominant_regime, raw_label=old.palette.get(d.dominant_regime, d.dominant_regime), evidence_strength=d.evidence_strength,
                                         official_regime=new.current_regime, official_label=new.current_label, transition_status=new.transition_status,
                                         transition_status_ko=new.transition_status_ko, calculated_at=d.calculated_at, source=d.source)
    if new.state is not None:
        upd["state"] = new.state.model_copy(update={"live_signal": live})
    return new.model_copy(update=upd).model_dump(mode="json")


def upgrade_cockpit(ck: Mapping[str, Any], hist: Mapping[str, Any], cfg: Mapping) -> dict:
    """
    MARKET NOW · Cross-Asset · Tone 의 공식 regime 을 History 와 같은 daily state 로 다시 그린다(2026-10-22). 저장된 값(z · 확신 · 핵심 변수 · composite)은 그대로 쓰고,
    공식 판정에서 나오는 칸(라벨 · 지속 · 전환 · 문장 · 확인 상태)만 같은 함수(now_regime_fields · cross_eval · tone_confirmation)로 만든다.
    """
    from ..engines.cockpit import cross_eval, now_regime_fields
    from ..engines.market_tone import tone_confirmation
    from ..models.cockpit import CrossAssetRow, KeyVariable, MarketNow
    rh = RegimeHistory.model_validate(hist)
    out = dict(ck)
    now = MarketNow.model_validate(ck["market_now"])
    flat = float(cfg.get("flat_abs", 0.5))
    rf = now_regime_fields(cfg, rh, raw_label=now.raw_label, raw_secondary=now.raw_secondary, keyvars=[KeyVariable.model_validate(k) for k in ck["market_now"].get("key_variables", [])], flat=flat)
    out["market_now"] = now.model_copy(update=rf).model_dump(mode="json")
    label = rf["label"]
    ca = ck.get("cross_asset")
    if isinstance(ca, dict) and ca.get("rows") is not None:
        rows = [CrossAssetRow.model_validate(r) for r in ca["rows"]]
        ev = cross_eval(cfg, label, rows, flat=flat)
        out["cross_asset"] = {**ca, **{k: ([r.model_dump(mode="json") for r in v] if k == "rows" else v) for k, v in ev.items()}}
    tone = ck.get("tone")
    if isinstance(tone, dict):
        conf, cread = tone_confirmation(cfg.get("tone", {}) or {}, tone.get("composite"), rh.current_regime, rh.current_label)
        out["tone"] = {**tone, "regime_key": rh.current_regime, "regime_label": rh.current_label, "confirmation": conf, "confirmation_read": cread}
    return out


def _safe(fn: Callable[[], dict], orig: Any) -> Any:
    """모델에 맞지 않는(부분) 섹션은 손대지 않고 그대로 둔다 — view 변환이 화면을 깨지 않게."""
    from pydantic import ValidationError
    try:
        return fn()
    except (ValidationError, KeyError, TypeError, ValueError):
        return orig


def upgrade_sections(doc: Mapping[str, Any], *, live_asof: datetime | None, rows_of: RowsOf, config_dir=None) -> dict:
    """아카이브 문서(또는 같은 키의 캡처 묶음)의 history 섹션들 → KST snapshot 날짜 view. 원본은 건드리지 않고 새 dict 를 돌려준다."""
    from ..engines.ai_regime import load_ai_regime_config
    from ..engines.cockpit import load_cockpit_config
    from .integrate import sentiment_cfg
    out = dict(doc)
    look = lambda tab: _lookup(rows_of, tab, live_asof)  # noqa: E731
    ck = out.get("cockpit")
    if isinstance(ck, dict) and isinstance(ck.get("history"), dict):
        ccfg = load_cockpit_config(config_dir)
        hist = _safe(lambda: upgrade_regime(ck["history"], look("market_regime"), ccfg.get("history") or {}), ck["history"])
        ck2 = {**ck, "history": hist}
        out["cockpit"] = _safe(lambda: upgrade_cockpit(ck2, hist, ccfg), ck2) if isinstance(ck.get("market_now"), dict) else ck2
    if isinstance(out.get("market_state_history"), dict):
        msh = out["market_state_history"]
        out["market_state_history"] = _safe(lambda: upgrade_state(msh, look("market_regime")), msh)
    dh = out.get("daily_history")
    if isinstance(dh, dict):
        out["daily_history"] = {tab: (_safe(lambda tab=tab, h=h: upgrade_daily(tab, h, look(tab)), h) if isinstance(h, dict) else h) for tab, h in dh.items()}
    ai = out.get("ai_regime")
    sent = ai.get("sentiment") if isinstance(ai, dict) else None
    if isinstance(sent, dict) and isinstance(sent.get("history"), dict):
        cfg = sentiment_cfg(load_ai_regime_config(config_dir))
        out["ai_regime"] = {**ai, "sentiment": {**sent, "history": _safe(lambda: upgrade_sentiment(sent["history"], look("ai_sentiment"), cfg), sent["history"])}}
    return out


def store_rows_of(manager) -> RowsOf:
    cache: dict[str, dict[date, DailySnapshot]] = {}

    def f(tab: str) -> Mapping[date, DailySnapshot]:
        if tab not in cache:
            cache[tab] = {s.snapshot_date: s for s in manager.get_history(tab)}
        return cache[tab]

    return f
