"""저장된 daily snapshot sequence → 화면 모델. 파생값(구간·비중·전환·변화)은 전부 이 sequence 에서만 계산한다."""

from __future__ import annotations

from datetime import date, datetime
from typing import Callable, Mapping, Sequence

from ..models.ai_regime import SentimentHistory, SentimentPoint
from ..models.daily_history import DailyHistory, DailyHistoryPoint, DailyHistorySegment, DailyHistoryShare, DailyHistoryTransition, DailySnapshot
from ..models.state_history import MarketStateHistory, StateHistoryPoint
from .dates import RowDate, load_rule, parse_dt, resolve, trim
from .versions import load_history_config

AsofOf = Callable[[object], datetime | None]


def _src(s: DailySnapshot) -> str:
    return s.history_source


def footnote(config_dir=None) -> str:
    return str(load_history_config(config_dir).get("footnote", "각 거래일 최종 snapshot 기준 · 저장 후 고정"))


# ── market_regime → MarketStateHistory ──────────────────────
def to_state_point(s: DailySnapshot) -> StateHistoryPoint | None:
    if not s.payload or "label" not in s.payload:
        return None
    p = StateHistoryPoint.model_validate(s.payload)
    return p.model_copy(update={"source": _src(s), "calculated_at": s.calculated_at, "model_version": s.model_version, "logic_version": s.logic_version, "locked": s.is_locked})


def market_history(snaps: Sequence[DailySnapshot], *, as_of: datetime, days: int, config_dir=None) -> MarketStateHistory:
    points = [p.model_copy(update={"date": s.snapshot_date}) for s, p in ((s, to_state_point(s)) for s in snaps) if p is not None]
    labels: dict[str, str] = {}
    for s in snaps:
        for k in (s.payload.get("components") or {}):
            labels.setdefault(k, k)
    asof = {s.snapshot_date: s.data_asof for s in snaps}
    return state_view(points, as_of=as_of, days=days, config_dir=config_dir, history_mode="stored", footnote=footnote(config_dir), note=MARKET_NOTE,
                      asof_of=lambda p: asof.get(p.date) or p.as_of)


MARKET_NOTE = ("저장된 daily snapshot 의 sequence 다 — RECORDED(그날 당시 저장한 판정) 와 BACKFILLED(당시 기록이 없어 그 날짜까지의 데이터로 1회 복원한 판정), "
                                  "오늘은 LIVE(확정 전). 저장 후에는 모델·룰·데이터가 바뀌어도 과거 날짜를 다시 계산하지 않는다. 날짜별 색·확신·온도·재료는 같은 snapshot 에서 나온다. "
                                  "날짜는 KST Daily Snapshot 날짜이고 그 snapshot 이 쓴 미국 정규장 날짜는 market_date 에 따로 있다. 장중 LIVE 는 daily 띠에 넣지 않고 intraday 로 따로 둔다.")


def state_view(points: Sequence[StateHistoryPoint], *, as_of: datetime, days: int, config_dir=None, history_mode: str = "stored", footnote: str = "", note: str = "",
               component_labels: Mapping[str, str] | None = None, asof_of: AsofOf | None = None) -> MarketStateHistory:
    """저장 키(UTC 날짜) 순서의 점 → KST snapshot 날짜 view. 파생값(구간·비중·요약)은 view 의 daily 점에서만 계산한다."""
    from ..engines.state_history import summarize_points
    rule = load_rule(config_dir)
    res = trim(resolve(list(points), storage=lambda p: p.date, source=lambda p: p.source, asof=asof_of or (lambda p: p.as_of), rule=rule), days)

    def lab(p: StateHistoryPoint, rd: RowDate, merged) -> StateHistoryPoint:
        return p.model_copy(update={"date": rd.snapshot_date, "market_date": rd.market_date, "storage_date": rd.storage_date, "merged": merged})

    daily = [lab(p, rd, m) for p, rd, m in res.rows]
    h = summarize_points(daily, as_of=as_of, days=days, component_labels=component_labels, config_dir=config_dir, history_mode=history_mode, footnote=footnote, note=note)
    intr = lab(res.intraday[0], res.intraday[1], []) if res.intraday else None
    return h.model_copy(update={"date_basis": "kst_snapshot", "intraday": intr, "gaps": res.gaps, "live_today": intr is not None})


# ── ai_sentiment → SentimentHistory ─────────────────────────
def sentiment_history(snaps: Sequence[DailySnapshot], cfg: Mapping, *, days: int, config_dir=None) -> SentimentHistory:
    pts: list[SentimentPoint] = []
    for s in snaps:
        comps = dict(s.payload.get("components") or s.component_scores or {})
        pts.append(SentimentPoint(date=s.snapshot_date.isoformat(), index=s.state_score, components=comps, source=_src(s), state=s.state,
                                  calculated_at=s.calculated_at.isoformat(), model_version=s.model_version, coverage=s.data_coverage, missing=list(s.missing_components),
                                  data_asof=s.data_asof.isoformat() if s.data_asof else ""))
    return sentiment_view(pts, cfg, days=days, config_dir=config_dir, foot=footnote(config_dir))


def sentiment_view(points: Sequence[SentimentPoint], cfg: Mapping, *, days: int, config_dir=None, foot: str = "", history_mode: str = "stored",
                   asof_of: AsofOf | None = None) -> SentimentHistory:
    """저장 키 순서의 센티먼트 점 → KST snapshot 날짜 view (장중 LIVE 는 intraday)."""
    from ..engines.ai_sentiment import finish_history, history_read
    rule = load_rule(config_dir)
    res = trim(resolve(list(points), storage=lambda p: date.fromisoformat(p.date[:10]), source=lambda p: p.source,
                       asof=asof_of or (lambda p: parse_dt(p.data_asof)), rule=rule), days)

    def lab(p: SentimentPoint, rd: RowDate, merged) -> SentimentPoint:
        return p.model_copy(update={"date": rd.snapshot_date.isoformat(), "market_date": rd.market_date.isoformat() if rd.market_date else "",
                                    "storage_date": rd.storage_date.isoformat(), "data_asof": rd.data_asof.isoformat() if rd.data_asof else p.data_asof, "merged": merged})

    pts = [lab(p, rd, m) for p, rd, m in res.rows]
    hist = SentimentHistory(days=days, history_mode=history_mode, footnote=foot, date_basis="kst_snapshot",
                            intraday=lab(res.intraday[0], res.intraday[1], []) if res.intraday else None, gaps=[g.isoformat() for g in res.gaps])
    hist.points = pts
    hist.recorded_days = sum(1 for p in pts if p.source == "RECORDED"); hist.backfilled_days = sum(1 for p in pts if p.source == "BACKFILLED")
    comp_specs = list(cfg.get("components", []))
    used = sorted({k for p in pts for k, v in p.components.items() if v is not None})
    hist.basis = [str(c["key"]) for c in comp_specs if str(c["key"]) in used]
    labels = {str(c["key"]): str(c.get("label", c["key"])) for c in comp_specs}
    never = [str(c["key"]) for c in comp_specs if str(c["key"]) not in used]
    for k in never:
        hist.excluded[k] = "창 안의 어느 snapshot 에도 값이 없다"
    finish_history(cfg, hist)
    history_read(cfg, hist)
    partial = sum(1 for p in pts if p.missing)
    hist.note = ("저장된 daily snapshot 의 지수를 그대로 잇는다 — 날짜마다 그날 확보된 구성요소(" + " · ".join(labels.get(k, k) for k in hist.basis) + ")의 가중을 재정규화해 만든 값이고, "
                 f"오늘 시점에서 과거를 다시 계산하지 않는다. RECORDED {hist.recorded_days} · BACKFILLED {hist.backfilled_days}"
                 + (f" · 구성요소가 일부 빠진 날 {partial}(툴팁에 표시)" if partial else "") + ". 날짜는 KST Daily Snapshot 날짜, 장중 LIVE 는 intraday 로 따로 둔다.") if pts else "저장된 센티먼트 snapshot 이 없다."
    return hist


# ── 모든 탭 → DailyHistory (범용 strip) ─────────────────────
def _tab_labels(tab_id: str, config_dir=None) -> tuple[dict, dict[str, str], dict[str, str]]:
    cfg = load_history_config(config_dir); tcfg = (cfg.get("tabs") or {}).get(tab_id) or {}
    states = tcfg.get("states") or {}
    labels = {k: str(v.get("label", k)) for k, v in states.items()}
    palette = {k: f"var({v.get('color', '--lbl-neutral')})" for k, v in states.items()}
    ins = cfg.get("insufficient") or {}
    labels.setdefault(str(ins.get("state", "INSUFFICIENT_DATA")), str(ins.get("label", "Insufficient data"))); palette.setdefault(str(ins.get("state", "INSUFFICIENT_DATA")), "var(--lbl-neutral)")
    return tcfg, labels, palette


def daily_history(tab_id: str, snaps: Sequence[DailySnapshot], *, as_of: datetime, days: int, config_dir=None) -> DailyHistory:
    _tcfg, labels, _palette = _tab_labels(tab_id, config_dir)
    rows = list(snaps)
    pts = [DailyHistoryPoint(date=s.snapshot_date, data_asof=s.data_asof, state=s.state, label=labels.get(s.state, s.state_label or s.state), label_ko=s.state_label_ko, score=s.state_score, confidence=s.confidence,
                             source=_src(s), calculated_at=s.calculated_at, model_version=s.model_version, logic_version=s.logic_version, locked=s.is_locked, coverage=s.data_coverage,
                             components={k: v for k, v in s.component_scores.items() if not k.startswith("factor:")}, drivers=list(s.key_drivers), missing=list(s.missing_components),
                             summary=s.summary, detail={k: v for k, v in s.payload.items() if k in ("leadership", "lagging", "leader_1w", "breadth_trend", "price_confirmation", "fundamental_confirmation",
                                                                                                   "narrative", "ai_vs_market", "regime_label", "runner_up", "inflation_status", "rate_direction", "curve",
                                                                                                   "oil_direction", "directions", "key_tension", "secondary", "subtitle", "stress", "dominant")})
           for s in rows]
    return daily_view(tab_id, pts, as_of=as_of, days=days, config_dir=config_dir)


def daily_view(tab_id: str, points: Sequence[DailyHistoryPoint], *, as_of: datetime, days: int, config_dir=None, asof_of: AsofOf | None = None) -> DailyHistory:
    """저장 키 순서의 점 → KST snapshot 날짜 view. 구간·비중·전환은 view 의 daily 점에서만 계산한다(장중 LIVE 는 intraday)."""
    tcfg, labels, palette = _tab_labels(tab_id, config_dir)
    rule = load_rule(config_dir)
    res = trim(resolve(list(points), storage=lambda p: p.date, source=lambda p: p.source, asof=asof_of or (lambda p: p.data_asof), rule=rule), days)

    def lab(p: DailyHistoryPoint, rd: RowDate, merged) -> DailyHistoryPoint:
        return p.model_copy(update={"date": rd.snapshot_date, "market_date": rd.market_date, "storage_date": rd.storage_date, "data_asof": rd.data_asof or p.data_asof, "merged": merged})

    pts = [lab(p, rd, m) for p, rd, m in res.rows]
    intr = lab(res.intraday[0], res.intraday[1], []) if res.intraday else None
    segs: list[DailyHistorySegment] = []
    for p in pts:
        if segs and segs[-1].state == p.state:
            segs[-1] = segs[-1].model_copy(update={"end": p.date, "days": segs[-1].days + 1})
        else:
            segs.append(DailyHistorySegment(state=p.state, label=p.label, start=p.date, end=p.date, days=1))
    cnt: dict[str, int] = {}
    for p in pts:
        cnt[p.state] = cnt.get(p.state, 0) + 1
    share = [DailyHistoryShare(state=k, label=labels.get(k, k), days=v, share=round(100.0 * v / len(pts), 0)) for k, v in sorted(cnt.items(), key=lambda kv: -kv[1])] if pts else []
    trans = [DailyHistoryTransition(date=b.start, from_state=a.state, from_label=a.label, to_state=b.state, to_label=b.label) for a, b in zip(segs, segs[1:])]
    cur = segs[-1] if segs else None; prev = segs[-2] if len(segs) >= 2 else None
    scores = [p.score for p in pts]
    chg_1w = round(scores[-1] - scores[-6], 1) if len(scores) >= 6 and scores[-1] is not None and scores[-6] is not None else None
    return DailyHistory(
        tab_id=tab_id, label=str(tcfg.get("label", tab_id)), label_ko=str(tcfg.get("label_ko", "")), as_of=as_of, window_days=days, points=pts, segments=segs, share=share,
        transitions=list(reversed(trans))[:5], current_state=cur.state if cur else None, current_label=cur.label if cur else None, current_streak=cur.days if cur else 0,
        previous_state=prev.state if prev else None, previous_label=prev.label if prev else None, changes=max(0, len(segs) - 1),
        share_pct=next((s.share for s in share if cur and s.state == cur.state), 0.0), score_label=str(tcfg.get("score_label", "")),
        score_range=[float(x) for x in (tcfg.get("score_range") or [-100, 100])], score_current=scores[-1] if scores else None, score_change_1w=chg_1w,
        palette=palette, labels=labels, recorded_days=sum(1 for p in pts if p.source == "RECORDED"), backfilled_days=sum(1 for p in pts if p.source == "BACKFILLED"),
        live_today=intr is not None, footnote=footnote(config_dir), date_basis="kst_snapshot", intraday=intr, gaps=res.gaps,
        note="날짜별 state·score·구성요소·driver 는 그 날짜의 snapshot 에서만 읽는다. 과거 snapshot 은 저장 후 고정이며 현재 모델이 과거를 다시 분류하지 않는다. 비중 % 는 기간 중 일수이지 확률이 아니다. "
             "날짜는 KST Daily Snapshot 날짜(미국 정규장 날짜는 market_date), 장중 LIVE 는 daily 띠에 넣지 않고 intraday 로 따로 둔다.",
    )
