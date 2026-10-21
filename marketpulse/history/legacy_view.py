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
    if res.intraday is not None:
        d, rd = res.intraday
        # 저장본의 공식 판정(LIVE 를 마지막 칸으로 본 결과)을 그대로 장중 요약에 둔다 — 그날 MARKET NOW 와 같은 값
        upd["intraday"] = RegimeIntraday(date=rd.snapshot_date.isoformat(), as_of=rd.data_asof.isoformat() if rd.data_asof else "", market_date=rd.market_date.isoformat() if rd.market_date else "",
                                         raw_state=d.raw_state, raw_regime=d.dominant_regime, raw_label=old.palette.get(d.dominant_regime, d.dominant_regime), evidence_strength=d.evidence_strength,
                                         official_regime=old.current_regime, official_label=old.current_label, transition_status=old.transition_status,
                                         transition_status_ko=old.transition_status_ko, calculated_at=d.calculated_at, source=d.source)
    return new.model_copy(update=upd).model_dump(mode="json")


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
        hc = load_cockpit_config(config_dir).get("history") or {}
        out["cockpit"] = {**ck, "history": _safe(lambda: upgrade_regime(ck["history"], look("market_regime"), hc), ck["history"])}
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
