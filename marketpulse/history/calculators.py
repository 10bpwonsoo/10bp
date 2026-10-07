"""
탭별 daily snapshot 계산기.

두 종류:
  *_snapshot(...)    — 오늘의 live 결과(엔진 출력)를 DailySnapshot 으로 옮긴다 (LIVE / RECORDED 저장용, 캡처 migration 에도 쓴다)
  *_calculator(...)  — 과거 날짜 D 를 **D 이하의 데이터만으로** 1회 계산하는 closure (BACKFILLED 저장용). 미래 봉·기사는 자르고 들어간다.
오늘 값을 과거에 복사하지 않는다 — 날짜마다 독립 계산이다. 결측 입력은 0 이 아니라 결측으로 남고 coverage·missing_components 에 적힌다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Mapping, Sequence

from ..engines.state_history import replay_point, slice_series
from ..models.common import DataMode, utcnow
from ..models.daily_history import DailySnapshot
from ..models.market import Instrument, MarketSeries
from ..models.news import NewsEvent
from ..models.snapshot import IntelligenceSnapshot
from ..models.state import StateLabel
from ..models.state_history import StateHistoryPoint
from .manager import Calculator
from .versions import load_history_config, logic_version, model_version

logger = logging.getLogger(__name__)


def _end_of(d: date) -> datetime:
    return datetime.combine(d, time(23, 59, 59), tzinfo=timezone.utc)


def _sliced(series_by_id: Mapping[str, MarketSeries], cutoff: datetime) -> dict[str, MarketSeries]:
    out = {}
    for iid, s in series_by_id.items():
        cut = slice_series(s, cutoff)
        if cut is not None:
            out[iid] = cut
    return out


def _labels(tab_id: str, config_dir=None) -> dict:
    return (load_history_config(config_dir).get("tabs") or {}).get(tab_id, {}).get("states") or {}


def _label_of(tab_id: str, state: str, config_dir=None) -> str:
    st = _labels(tab_id, config_dir).get(state) or {}
    return str(st.get("label", state))


def _base(tab_id: str, d: date, as_of: datetime, *, config_dir=None, **kw) -> DailySnapshot:
    return DailySnapshot(snapshot_date=d, tab_id=tab_id, history_source="LIVE", calculated_at=utcnow(), data_asof=as_of,
                         model_version=model_version(tab_id), logic_version=logic_version(tab_id, config_dir), **kw)


# ── 1. MARKET REGIME ───────────────────────────────────────
def market_snapshot_from_point(point: StateHistoryPoint, *, config_dir=None) -> DailySnapshot:
    return _base("market_regime", point.date, point.as_of, config_dir=config_dir, state=point.label.value, state_label=_label_of("market_regime", point.label.value, config_dir),
                 state_score=point.composite if point.composite is not None else point.price_temperature, confidence=point.confidence,
                 component_scores={**{k: v for k, v in point.components.items()}, **{f"factor:{k}": v for k, v in point.factors.items()}},
                 key_drivers=list(point.drivers), data_coverage=point.coverage,
                 missing_components=[k for k, v in point.components.items() if v is None],
                 summary=f"{point.label.value} {point.confidence:.0f}% · 온도 {point.composite:+.0f}" if point.composite is not None else f"{point.label.value} {point.confidence:.0f}%",
                 payload=point.model_dump(mode="json", exclude={"source", "calculated_at", "model_version", "logic_version", "locked"}))


def market_snapshot_from_intelligence(snap: IntelligenceSnapshot, *, config_dir=None) -> DailySnapshot:
    """파이프라인 스냅샷(오늘 화면 판정)을 그대로 daily snapshot 으로 — 화면이 보여준 판정과 같은 값이다."""
    ms, th, dh = snap.market_state, snap.thermometer, snap.data_health
    comps = {c.key: c.value for c in (th.components if th else [])}
    point = StateHistoryPoint(
        date=snap.as_of.astimezone(timezone.utc).date(), as_of=snap.as_of, label=ms.primary_label, secondary_label=ms.secondary_label, confidence=ms.confidence,
        price_temperature=th.price if th else None, news_temperature=th.news if th else None, composite=th.composite if th else None,
        news_events=int(getattr(th, "news_events", 0) or 0) if th else 0, thermo_confidence=float(getattr(th, "confidence", 0.0) or 0.0) if th else 0.0,
        components=comps, band=th.band if th else "unknown", band_label=th.band_label if th else "측정 불가",
        coverage=(dh.available_instruments / dh.expected_instruments) if dh.expected_instruments else 0.0,
        factors={k: round(v.score, 3) for k, v in ms.factors.items()}, hypotheses={h.label.value: round(h.score, 3) for h in ms.hypotheses if h.score > 0},
        drivers=[f"{dr.label} {dr.z:+.1f}σ" for dr in ms.main_drivers[:3]],
    )
    s = market_snapshot_from_point(point, config_dir=config_dir)
    ev = snap.engine_versions.get("market_state") if getattr(snap, "engine_versions", None) else None
    if ev:
        s = s.model_copy(update={"model_version": f"market_regime_v{ev}"})
    return s


@dataclass
class MarketInputs:
    instruments: Sequence[Instrument]
    series_by_id: Mapping[str, MarketSeries]
    events: Sequence[NewsEvent] = ()
    mode: DataMode = DataMode.DELAYED
    zscore_window: int = 60
    config_dir: Path | None = None


def market_calculator(inp: MarketInputs, *, as_of: datetime) -> Calculator:
    def calc(d: date, prev: DailySnapshot | None) -> DailySnapshot | None:
        prev_label = None
        if prev is not None and prev.tab_id == "market_regime" and prev.state in StateLabel.__members__:
            prev_label = StateLabel(prev.state)  # 지속성 항은 저장된 sequence 의 직전 판정으로 잇는다
        got = replay_point(inp.instruments, inp.series_by_id, d, as_of=min(as_of, _end_of(d)), mode=inp.mode, events=inp.events,
                           zscore_window=inp.zscore_window, config_dir=inp.config_dir, prev_label=prev_label)
        if got is None:
            return None
        point, _labels_ = got
        if point.coverage <= 0.0:
            return None
        return market_snapshot_from_point(point, config_dir=inp.config_dir)
    return calc


# ── 공통: 날짜 D 의 테마 상태 (rates·oil·AI backfill 입력) ─────
def _themes_for(instruments: Sequence[Instrument], market, events: Sequence[NewsEvent], cutoff: datetime, config_dir=None):
    from ..config.registry import get_themes
    from ..engines.theme import compute_theme_states
    past = [e for e in events if e.timestamp <= cutoff]
    return compute_theme_states(list(get_themes(config_dir).themes), market, past, {i.id: i for i in instruments}, config_dir=config_dir)


def _market_for(instruments: Sequence[Instrument], series_by_id: Mapping[str, MarketSeries], cutoff: datetime, mode: DataMode, zwin: int):
    from ..engines.normalize import build_snapshot
    sliced = _sliced(series_by_id, cutoff)
    if not sliced:
        return None, {}
    return build_snapshot(instruments, sliced, mode=mode, as_of=cutoff, zscore_window=zwin, correlations=False), sliced


# ── 2. AI SENTIMENT ───────────────────────────────────────
def sentiment_snapshot(sent, *, as_of: datetime, d: date | None = None, config_dir=None) -> DailySnapshot:
    """AiSentiment(오늘) → daily snapshot. 구성요소 · KEY TENSION · support/pressure 를 같이 저장한다 — 과거를 오늘 데이터로 다시 설명하지 않기 위해."""
    d = d or as_of.astimezone(timezone.utc).date()
    comps = {c.key: c.score for c in sent.components}
    return _base("ai_sentiment", d, as_of, config_dir=config_dir, state=str(sent.state), state_label=str(sent.state_label), state_label_ko=str(sent.state_ko),
                 state_score=sent.index, confidence=round(100.0 * float(sent.coverage), 1), component_scores=comps, data_coverage=float(sent.coverage),
                 key_drivers=[f.label for f in sent.support[:3]] + [f"−{f.label}" for f in sent.pressure[:3]],
                 missing_components=[c.key for c in sent.components if c.score is None],
                 summary=f"{sent.state_label} {sent.index:.0f}" if sent.index is not None else sent.state_label,
                 payload={"components": comps, "component_states": {c.key: c.state for c in sent.components}, "key_tension": sent.gap_read, "read": sent.read,
                          "secondary": sent.secondary_label, "support": [f.model_dump(mode="json") for f in sent.support], "pressure": [f.model_dump(mode="json") for f in sent.pressure],
                          "basis": [c.key for c in sent.components if c.score is not None]})


def sentiment_calculator(cfg: Mapping, dv, *, config_dir=None) -> Calculator:
    """날짜 D 의 센티먼트 — DayValues(D 이하 봉·기사) 로 구성요소를 다시 재고, 확보된 구성요소 가중을 재정규화해 지수를 만든다."""
    from ..engines.ai_sentiment import _band, index_of, score_components
    min_cov = float(cfg.get("min_coverage", 0.5))

    def calc(d: date, prev: DailySnapshot | None) -> DailySnapshot | None:
        vals = dv.values(d)
        if not vals:
            return None
        comps = score_components(cfg, vals)
        index, cov = index_of(cfg, comps)
        if index is not None and cov < min_cov:
            index = None
        band = _band(cfg, index)
        comp_scores = {c.key: c.score for c in comps}
        if all(v is None for v in comp_scores.values()):
            return None
        return _base("ai_sentiment", d, min(_end_of(d), dv.as_of), config_dir=config_dir, state=str(band.get("key", "UNKNOWN")), state_label=str(band.get("label", "–")),
                     state_label_ko=str(band.get("ko", "")), state_score=index, confidence=round(100.0 * cov, 1), component_scores=comp_scores, data_coverage=cov,
                     missing_components=[c.key for c in comps if c.score is None],
                     summary=f"{band.get('label', '–')} {index:.0f}" if index is not None else "지수 없음(확보 부족)",
                     payload={"components": comp_scores, "component_states": {c.key: c.state for c in comps}, "basis": [c.key for c in comps if c.score is not None],
                              "key_tension": "", "read": ""})
    return calc


# ── 3. AI TRADE REGIME ────────────────────────────────────
def ai_regime_snapshot(r, *, as_of: datetime, d: date | None = None, config_dir=None) -> DailySnapshot:
    d = d or as_of.astimezone(timezone.utc).date()
    avm, br, vc = r.ai_vs_market, r.breadth, r.value_chain
    strip = {s.key: s.value for s in r.status_strip}
    comps = {"basket_z_5d": avm.basket_z_5d, "rel_ndx_5d": avm.rel_ndx_5d, "rel_ndx_z_5d": avm.rel_ndx_z_5d, "breadth_ma20": br.above_ma20_pct, "news_tone": r.narrative.news_tone,
             **{f"driver:{x.id}": x.score for x in r.drivers}}
    return _base("ai_regime", d, as_of, config_dir=config_dir, state=str(r.regime), state_label=str(r.regime_label), state_label_ko=str(r.regime_label_ko),
                 state_score=float(r.signal_strength), confidence=float(r.signal_strength), component_scores=comps, data_coverage=(avm.members_used / avm.members_total) if avm.members_total else None,
                 key_drivers=[f"{x.label} {x.score:+.0f} {x.status}" for x in sorted(r.drivers, key=lambda x: -abs(x.score))[:3]],
                 missing_components=list(r.missing), summary=r.headline,
                 payload={"leadership": list(vc.leadership), "lagging": list(vc.lagging), "leader_1w": next((g.key for g in r.leadership.groups if g.role == "leader"), None),
                          "breadth_trend": br.trend, "breadth_ma20": br.above_ma20_pct, "price_confirmation": strip.get("price", ""), "fundamental_confirmation": r.fundamental_confirmation.level,
                          "narrative": r.narrative.quadrant, "ai_vs_market": avm.rel_verdict, "abs_direction": avm.abs_direction, "dominant": r.dominant, "status_strip": strip,
                          "subtitle": r.regime_subtitle, "stress": r.stress.level})


@dataclass
class AiInputs:
    instruments: Sequence[Instrument]
    series_by_id: Mapping[str, MarketSeries]
    basket_series: Mapping[str, MarketSeries]
    events: Sequence[NewsEvent] = ()
    mode: DataMode = DataMode.DELAYED
    zscore_window: int = 60
    config_dir: Path | None = None
    market_context: Mapping[date, tuple[str, float]] = field(default_factory=dict)  # 저장된 시장 판정(sequence) — 맥락 입력


def ai_regime_calculator(inp: AiInputs, *, as_of: datetime) -> Calculator:
    from ..engines.ai_regime import build_ai_regime

    def calc(d: date, prev: DailySnapshot | None) -> DailySnapshot | None:
        cutoff = min(as_of, _end_of(d))
        market, sliced = _market_for(inp.instruments, inp.series_by_id, cutoff, inp.mode, inp.zscore_window)
        basket = _sliced(inp.basket_series, cutoff)
        if market is None or not basket:
            return None
        themes = _themes_for(inp.instruments, market, inp.events, cutoff, inp.config_dir)
        label, conf = inp.market_context.get(d, ("NEUTRAL", 0.0))
        r = build_ai_regime(market, sliced, basket, themes, [e for e in inp.events if e.timestamp <= cutoff], {i.id: i for i in inp.instruments},
                            market_label=label, market_confidence=conf, extra_z={}, extra_names={}, investment=None, as_of=cutoff, config_dir=inp.config_dir)
        if r.ai_vs_market.members_used == 0:
            return None
        s = ai_regime_snapshot(r, as_of=cutoff, d=d, config_dir=inp.config_dir)
        return s.model_copy(update={"missing_components": sorted(set(s.missing_components) | {"investment(memory·HBM·consensus)"})})
    return calc


# ── 4 · 5. RATES / OIL REGIME ─────────────────────────────
def _regime_snapshot(tab_id: str, r, *, as_of: datetime, d: date | None, config_dir=None, move: dict) -> DailySnapshot:
    d = d or as_of.astimezone(timezone.utc).date()
    dom = str(r.dominant or "none")
    dom_score = next((x.score for x in r.drivers if x.id == dom), None)
    comps = {f"driver:{x.id}": x.score for x in r.drivers}
    comps.update(move)
    return _base(tab_id, d, as_of, config_dir=config_dir, state=dom, state_label=str(r.regime_label), state_score=dom_score, confidence=float(r.signal_strength),
                 component_scores=comps, data_coverage=(sum(x.coverage for x in r.drivers) / len(r.drivers)) if r.drivers else None,
                 key_drivers=[f"{x.label} {x.score:+.0f} {x.status}" for x in sorted(r.drivers, key=lambda x: -abs(x.score))[:3]],
                 missing_components=[x.id for x in r.drivers if x.coverage == 0], summary=r.headline,
                 payload={"regime_label": r.regime_label, "dominant": dom, "runner_up": r.runner_up, "margin": r.margin, "signal_strength_label": r.signal_strength_label,
                          "drivers": {x.id: {"label": x.label, "score": x.score, "status": x.status, "coverage": x.coverage} for x in r.drivers},
                          "confirmations": {c.label: c.status for c in r.confirmations}, "implication": r.implication})


def rates_snapshot(r, *, as_of: datetime, d: date | None = None, config_dir=None) -> DailySnapshot:
    s = _regime_snapshot("rates_regime", r, as_of=as_of, d=d, config_dir=config_dir, move={"rate_move_z": r.rate_move.z, "rate_change_5d_bp": r.rate_move.change_5d_bp,
                         **{f"inflation:{c.key}": c.score for c in r.inflation_components}})
    s.payload.update({"inflation_status": str(r.inflation_status), "rate_direction": r.rate_move.direction, "curve": r.curve.shape, "inflation_components": {c.key: c.status for c in r.inflation_components}})
    return s


def oil_snapshot(r, *, as_of: datetime, d: date | None = None, config_dir=None) -> DailySnapshot:
    s = _regime_snapshot("oil_regime", r, as_of=as_of, d=d, config_dir=config_dir, move={"brent_z": r.oil_move.brent_z, "wti_z": r.oil_move.wti_z, "oil_z": r.oil_move.oil_z})
    s.payload.update({"oil_direction": r.oil_move.direction, "suspect": r.oil_move.suspect})
    return s


@dataclass
class RegimeInputs:
    instruments: Sequence[Instrument]
    series_by_id: Mapping[str, MarketSeries]
    events: Sequence[NewsEvent] = ()
    mode: DataMode = DataMode.DELAYED
    zscore_window: int = 60
    config_dir: Path | None = None


def rates_calculator(inp: RegimeInputs, *, as_of: datetime) -> Calculator:
    from ..engines.rates_regime import build_rates_regime

    def calc(d: date, prev: DailySnapshot | None) -> DailySnapshot | None:
        cutoff = min(as_of, _end_of(d))
        market, _ = _market_for(inp.instruments, inp.series_by_id, cutoff, inp.mode, inp.zscore_window)
        if market is None:
            return None
        themes = _themes_for(inp.instruments, market, inp.events, cutoff, inp.config_dir)
        r = build_rates_regime(market, themes, {i.id: i for i in inp.instruments}, extra_z={}, extra_names={}, config_dir=inp.config_dir)
        if all(x.coverage == 0 for x in r.drivers):
            return None
        return rates_snapshot(r, as_of=cutoff, d=d, config_dir=inp.config_dir)
    return calc


def oil_calculator(inp: RegimeInputs, *, as_of: datetime) -> Calculator:
    from ..engines.oil_regime import build_oil_regime

    def calc(d: date, prev: DailySnapshot | None) -> DailySnapshot | None:
        cutoff = min(as_of, _end_of(d))
        market, _ = _market_for(inp.instruments, inp.series_by_id, cutoff, inp.mode, inp.zscore_window)
        if market is None:
            return None
        themes = _themes_for(inp.instruments, market, inp.events, cutoff, inp.config_dir)
        r = build_oil_regime(market, themes, [], {i.id: i for i in inp.instruments}, extra_z={}, extra_names={}, config_dir=inp.config_dir)
        if all(x.coverage == 0 for x in r.drivers):
            return None
        return oil_snapshot(r, as_of=cutoff, d=d, config_dir=inp.config_dir)
    return calc


# ── 6. MEMORY CYCLE ───────────────────────────────────────
def _memory_state(semi) -> tuple[str, float | None, dict[str, float | None]]:
    dirs = {"memory": semi.memory_direction, "peers": semi.peer_direction, "korea": semi.korea_direction, "eps": semi.eps_direction}
    known = [v for v in dirs.values() if v is not None]
    if not known:
        return "INSUFFICIENT_DATA", None, dirs
    up = sum(1 for v in known if v >= 0.5); down = sum(1 for v in known if v <= -0.5)
    state = "UPCYCLE" if up == len(known) else "DOWNCYCLE" if down == len(known) else "MIXED"
    return state, round(100.0 * sum(known) / len(known), 1), dirs


def memory_snapshot(semi, *, as_of: datetime, d: date | None = None, config_dir=None) -> DailySnapshot:
    d = d or as_of.astimezone(timezone.utc).date()
    state, score, dirs = _memory_state(semi)
    comps: dict[str, float | None] = dict(dirs)
    comps.update({f"memory:{p.id}": p.z for p in semi.memory}); comps.update({f"peer:{p.id}": p.z for p in semi.peers}); comps.update({f"korea:{r.stock_id}": r.z for r in semi.korea})
    known = sum(1 for v in dirs.values() if v is not None)
    return _base("memory_cycle", d, as_of, config_dir=config_dir, state=state, state_label=_label_of("memory_cycle", state, config_dir), state_score=score,
                 confidence=round(100.0 * known / 4, 1), component_scores=comps, data_coverage=known / 4, key_drivers=[p.label for p in semi.memory if p.z is not None][:3],
                 missing_components=[k for k, v in dirs.items() if v is None] + list(semi.missing), summary=semi.interpretation[:160],
                 payload={"directions": dirs, "memory": {p.id: {"label": p.label, "z": p.z, "quality": p.quality, "change_1w": p.change_1w} for p in semi.memory},
                          "peers": {p.id: p.z for p in semi.peers}, "korea": {r.stock_id: r.z for r in semi.korea}, "interpretation": semi.interpretation})


@dataclass
class MemoryInputs:
    series_by_id: Mapping[str, MarketSeries]   # 종목·대체데이터·공유 드라이버 계열 (Investment 어댑터가 받은 것)
    instruments_by_id: Mapping[str, Instrument]
    zscore_window: int = 60
    config_dir: Path | None = None


def memory_calculator(inp: MemoryInputs, *, as_of: datetime) -> Calculator:
    from ..config.registry import get_intelligence_config
    from ..engines.features import compute_feature
    from ..engines.semiconductor import build_semiconductor
    from ..models.intelligence import AltDataPoint, StockRow
    cfg = get_intelligence_config(inp.config_dir)["semiconductor"]

    def calc(d: date, prev: DailySnapshot | None) -> DailySnapshot | None:
        cutoff = min(as_of, _end_of(d))
        sliced = _sliced(inp.series_by_id, cutoff)
        alt: dict[str, AltDataPoint] = {}; rows: dict[str, StockRow] = {}
        for iid in list(cfg["memory"]) + list(cfg["peers"]):
            s = sliced.get(iid); ins = inp.instruments_by_id.get(iid)
            if s is None or ins is None:
                continue
            try:
                f = compute_feature(ins, s, window=inp.zscore_window)
            except Exception:
                continue
            alt[iid] = AltDataPoint(id=iid, label=ins.name, group="semi", value=s.last, z=f.z_1d, quality="OK" if f.z_1d is not None else "PARTIAL",
                                    change_1w=f.ret_5d, observations=len(s.values), source=s.meta.source, as_of=s.as_of)
        for iid in cfg["korea"]:
            s = sliced.get(iid); ins = inp.instruments_by_id.get(iid)
            if s is None or ins is None:
                continue
            try:
                f = compute_feature(ins, s, window=inp.zscore_window)
            except Exception:
                continue
            rows[iid] = StockRow(stock_id=iid, name=ins.name, sector="semiconductor", price=s.last, z=f.z_1d, change_1w=f.ret_5d)
        if not alt and not rows:
            return None
        semi = build_semiconductor(alt, rows, {}, config_dir=inp.config_dir)  # EPS 컨센서스는 날짜별 계열이 없어 결측으로 둔다
        s = memory_snapshot(semi, as_of=cutoff, d=d, config_dir=inp.config_dir)
        return s.model_copy(update={"missing_components": sorted(set(s.missing_components) | {"eps"})})
    return calc
