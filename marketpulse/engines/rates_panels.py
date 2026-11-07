"""
금리 탭 아래 세 패널(2026-10-13) — INFLATION PRESSURE MAP → TREASURY CURVE → YIELD MOVE BREAKDOWN.

새 계산은 없다. rates_regime 이 이미 만든 물가 구성요소 점수 · 테너 수준과 변화 · 명목 분해(같은 날짜로 맞춘 값)를
config/rates_panels.yaml 의 문턱과 문구로 '상태 → 방향 → 원인 → 의미' 순서로 다시 읽는다.

원칙
- 커브 모양은 실제 bp 스프레드 변화로, 움직임의 이례성은 z 로 따로 읽는다 — 같은 창(5D)으로 재고, 둘을 한 문장에 섞지 않는다.
- 결측 구성요소는 0 이 아니라 계산에서 빠지고, 실제 물가가 없으면 강한 결론(COOLING · REACCELERATING) 대신 BIAS 를 쓴다.
- MODEL REAL(명목 − 기대인플레)과 OBSERVED TIPS 는 이름을 나눠 보이고, 서로 다르면 그렇다고 적는다.
- 문장에는 숫자를 넣지 않는다(숫자는 칸에만).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Mapping, Sequence

import yaml

from ..config.settings import CONFIG_DIR
from ..models.macro_data import MacroDataPoint, MacroInflationLayer
from ..models.market import MarketSnapshot
from ..models.rates_regime import (
    BreakdownTenor, ComponentScore, CurveMoveView, CurvePoint, CurveView, InflationPressureMap, MarketReadMeta, PressureItem, PressureValue, SpreadMove,
    YieldDecomposition, YieldMoveBreakdown,
)
from .macro_fallback import load_macro_config, news_state, wage_state
from .korean import fix_particles


@lru_cache(maxsize=4)
def _load(config_dir: Path | None) -> dict:
    return yaml.safe_load(((config_dir or CONFIG_DIR) / "rates_panels.yaml").read_text(encoding="utf-8")) or {}


def load_rates_panels_config(config_dir: Path | None = None) -> dict:
    return _load(config_dir)


def _join(names: Sequence[str]) -> str:
    # 이름 안에 '·' 가 들어 있어(에너지·원자재) 목록은 쉼표로 잇는다
    return ", ".join(names)


# ── INFLATION PRESSURE MAP ─────────────────────────────────
def _state(score: float | None, states: Sequence[Mapping]) -> tuple[str, str, str]:
    if score is None:
        return "DATA MISSING", "데이터 없음", "missing"
    for s in states:
        if score >= float(s["min"]):
            return str(s["state"]), str(s.get("ko", "")), str(s.get("tone", "flat"))
    return "NEUTRAL", "중립", "flat"


def _fmt_point(p: MacroDataPoint) -> str:
    if p.value is None:
        return "–"
    sign = "+" if p.measure != "YoY" and p.value > 0 else ""
    # FRED 계절조정 지수로 계산한 YoY 는 공식 발표(비계절조정, 소수 첫째 자리)와 0.1%p 안팎 다를 수 있어 둘째 자리까지 그대로 보인다
    txt = f"{sign}{p.value:.2f}% {p.measure}" if p.source_tier in ("PRIMARY", "MIRROR") and p.measure == "YoY" else f"{sign}{p.value:.1f}% {p.measure}"
    if p.momentum_ann is not None:
        txt += f" · {'3M' if p.frequency == 'monthly' else '1Q'} 연율 {p.momentum_ann:.1f}%"
    return txt


def _pv(p: MacroDataPoint) -> PressureValue:
    return PressureValue(label=p.label, text=_fmt_point(p) if p.value is not None else "DATA UNAVAILABLE", source_class=p.source_tier, source=p.source,
                         updated=p.last_updated, freshness_days=p.freshness_days, stale=p.stale, is_original_data=p.is_original_data)


def build_inflation_map(components: Sequence[ComponentScore], cfg: Mapping, macro: MacroInflationLayer | None = None) -> InflationPressureMap:
    """
    구성요소 → 상태 · 점수 · 근거 + 출처 급. 신호는 신뢰도 가중 평균이고 NEWS · STALE · 결측은 빠진다.
    확인 정도는 개수(구성요소 n)와 품질(공식/시장 원자료 대 PROXY · NEWS)을 나눠 센다.
    """
    c = cfg.get("inflation_map") or {}
    mcfg = load_macro_config()
    tiers = mcfg.get("tiers") or {}
    proxy_note = str(mcfg.get("proxy_note", "실제 원데이터 미연결 · 대체 지표로 추정"))
    lko = c.get("label_ko") or {}; mtext = c.get("missing_text") or {}; mshort = c.get("missing_short") or {}; short = c.get("short") or {}
    mkt_conf = float((tiers.get("PRIMARY") or {}).get("confidence", 0.95))
    items: list[PressureItem] = []
    for comp in components:
        mc = macro.components.get(comp.key) if macro is not None else None
        if comp.key == "wages" and comp.score is not None and wage_state(comp.score, mcfg):
            state, sko, tone = wage_state(comp.score, mcfg)  # type: ignore[misc]
        else:
            state, sko, tone = _state(comp.score, c.get("states") or [])
        if comp.score is None:
            state, sko = "DATA UNAVAILABLE", "데이터 없음"
        ev = sorted([e for e in comp.evidence if e.available and e.value is not None and e.kind == "price"], key=lambda e: -abs(e.contribution))
        ev_txt = " · ".join(f"{short.get(e.id, e.label)} {e.value:+.1f}σ" for e in ev[: int(c.get("evidence_max", 3))])
        base = dict(key=comp.key, label=comp.label, label_ko=str(lko.get(comp.key, comp.label_ko)), state=state, state_ko=sko, tone=tone,
                    score=None if comp.score is None else round(comp.score, 1), evidence_text=ev_txt)
        if mc is not None and comp.source_class is not None:
            # macro 구성요소 — 원자료(PRIMARY · MIRROR · SECONDARY) 또는 대체 추정(PROXY)
            proxy = mc.source_class == "PROXY"
            used_vals = [_pv(p) for p in mc.series if p.source_tier != "UNAVAILABLE"]
            items.append(PressureItem(**base, display_label=mc.display_label, source_class=mc.source_class, source_label=mc.source_label,  # type: ignore[arg-type]
                                      is_original_data=mc.is_original_data, proxy_components=list(mc.proxy_components), fallback_reason=mc.fallback_reason,
                                      proxy_note=proxy_note if proxy else "", last_updated=mc.last_updated, freshness_days=mc.freshness_days, stale=mc.stale,
                                      confidence=mc.confidence, in_signal=not mc.stale, values=used_vals, comment=mc.comment))
        elif comp.score is None:
            reason = (mc.fallback_reason if mc is not None and mc.fallback_reason else str(mtext.get(comp.key, "데이터 미연결")))
            items.append(PressureItem(**base, missing_text=reason, display_label=comp.label, source_class="UNAVAILABLE", is_original_data=False,  # type: ignore[arg-type]
                                      fallback_reason=reason, confidence=0.0, in_signal=False,
                                      values=[_pv(p) for p in (mc.series if mc is not None else [])]))
        else:
            # 시장 가격 구성요소 — 기대인플레(FRED) · 원자재 · 환율(거래소 가격). 시장 원자료다
            items.append(PressureItem(**base, display_label=comp.label, source_class="PRIMARY", source_label="MARKET", is_original_data=True,  # type: ignore[arg-type]
                                      confidence=round(mkt_conf * (0.5 + 0.5 * max(0.0, min(1.0, comp.coverage))), 2), in_signal=True))
    # INFLATION NEWS PULSE — 방향 보조 신호. 신호 점수에는 넣지 않는다
    nc = mcfg.get("news") or {}
    if macro is not None and macro.news is not None:
        nw = macro.news
        nstate, nko, ntone = news_state(nw.score, mcfg)
        items.append(PressureItem(key="news", label=str(nc.get("label", "Inflation News Pulse")), label_ko="뉴스 흐름", display_label=str(nc.get("label", "Inflation News Pulse")),
                                  state=nstate, state_ko=nko, tone=ntone, score=nw.score,  # type: ignore[arg-type]
                                  evidence_text=" · ".join(f"{d.label} {d.arrow}" for d in nw.drivers if d.arrow != "–") + (f" · 기사 {nw.articles}건" if nw.articles else ""),
                                  source_class="NEWS", source_label="뉴스 톤(테마)", is_original_data=False, confidence=nw.confidence, in_signal=False, comment=nw.comment))
    sig_items = [i for i in items if i.in_signal and i.score is not None]
    core = [i for i in items if i.key != "news"]
    official = [i for i in core if i.source_class in ("PRIMARY", "MIRROR", "SECONDARY") and i.score is not None and not i.stale]
    proxies = [i for i in core if i.source_class == "PROXY" and i.score is not None]
    news_n = sum(1 for i in items if i.key == "news" and i.score is not None)
    missing = [i for i in core if i.score is None]
    sg = c.get("signal") or {}; cf = c.get("confirmation") or {}
    realized_ok = any(i.key == "realized" and i.score is not None and i.is_original_data and not i.stale for i in items)
    if official and len(official) == len(core):
        conf = "FULL"
    elif len(official) >= int(cf.get("partial_min", 3)):
        conf = "PARTIAL"
    else:
        conf = "INSUFFICIENT"
    lean, counter = float(sg.get("lean_abs", 20)), float(sg.get("counter_abs", 25))
    if not sig_items:
        key, signal, sko, tone = "none", str((sg.get("none") or {}).get("label", "NO SIGNAL")), str((sg.get("none") or {}).get("ko", "")), "missing"
    else:
        w = [(float(i.score), float(i.confidence or 0.0)) for i in sig_items]  # type: ignore[arg-type]
        if not any(x for _, x in w):
            w = [(sc, 1.0) for sc, _ in w]  # 신뢰도를 모르면 같은 가중치
        den = sum(x for _, x in w) or 1.0
        mean = sum(s * x for s, x in w) / den
        strong = conf == "FULL" and realized_ok
        if mean <= -lean and not any(float(i.score) >= counter for i in sig_items):  # type: ignore[arg-type]
            key, d = "down", sg.get("down") or {}
        elif mean >= lean and not any(float(i.score) <= -counter for i in sig_items):  # type: ignore[arg-type]
            key, d = "up", sg.get("up") or {}
        else:
            key, d = "mixed", sg.get("mixed") or {}
        signal = str(d.get("strong" if strong else "weak", d.get("label", "MIXED"))) if key != "mixed" else str(d.get("label", "MIXED"))
        sko, tone = str(d.get("ko", "")), {"down": "down", "up": "up", "mixed": "flat"}[key]
    name = lambda i: str(lko.get(i.key, i.label_ko)) + ("(대체 추정)" if i.source_class == "PROXY" else "")  # noqa: E731
    down = [i for i in sig_items if i.tone == "down"]; up = [i for i in sig_items if i.tone == "up"]
    mild = all((i.score or 0) < 25 for i in up)
    clauses = []
    if down:
        clauses.append(str(c.get("clause_down", "")).format(names=_join([name(i) for i in down])))
    if up:
        clauses.append(str(c.get("clause_up", "")).format(names=_join([name(i) for i in up]), mild="약한 " if mild else ""))
    lead = "이고 ".join(clauses) if clauses else "뚜렷한 방향의 구성요소가 없음"
    miss_names = _join([str(mshort.get(i.key, i.label_ko)) for i in missing])
    summary = fix_particles(lead + ("이지만, " + str(c.get("clause_missing", "")).format(names=miss_names) + "." if missing else "입니다."))
    rr = c.get("rule_read") or {}
    s1 = str(rr.get(key if key in ("down", "up", "mixed") else "mixed", "")).format(lead=lead)
    if missing:
        s2 = str(rr.get("missing", "")).format(names=miss_names, dir_ko=(rr.get("dir_ko") or {}).get(key, "방향"))
    elif proxies:
        s2 = str(rr.get("proxy", "")).format(names=_join([str(lko.get(i.key, i.label_ko)) for i in proxies]))
    else:
        s2 = ""
    read = fix_particles(f"{s1} {s2}".strip())
    link = str((c.get("link") or {}).get(key if key in ("down", "up") else "mixed", ""))
    return InflationPressureMap(signal=signal, signal_ko=sko, signal_tone=tone, confirmation=conf, confirmation_ko=str((cf.get("ko") or {}).get(conf, conf)),  # type: ignore[arg-type]
                                available=len([i for i in core if i.score is not None]), total=len(core), summary=summary, items=items, read=read,
                                read_meta=MarketReadMeta(source="rule", status="fallback", reason="규칙 기반 — AI 해석 전", rule_read=read),
                                scale_note=str(c.get("scale_note", "")), link=link, official_count=len(official), proxy_count=len(proxies), news_count=news_n,
                                unavailable_count=len(missing), data_sources=[_pv(p) for p in (macro.series if macro is not None else [])])


# ── TREASURY CURVE ─────────────────────────────────────────
def _shape(chg: Mapping[str, float], spread_chg: float | None, alt_spread_chg: float | None, cc: Mapping) -> tuple[str, str]:
    """(shape_key, level_key). 모양은 실제 bp 스프레드 변화, 방향은 테너 bp 변화의 부호로."""
    flat_bp, lvl_flat = float(cc.get("flat_bp", 1)), float(cc.get("level_flat_bp", 1))
    vals = [v for v in chg.values() if v is not None]
    if not vals or spread_chg is None:
        return "unknown", "flat"
    if all(abs(v) < lvl_flat for v in vals):
        level = "flat"
    elif all(v <= 0 for v in vals):
        level = "down"
    elif all(v >= 0 for v in vals):
        level = "up"
    else:
        level = "mixed"
    sp = spread_chg if abs(spread_chg) >= flat_bp else (alt_spread_chg if alt_spread_chg is not None and abs(alt_spread_chg) >= flat_bp else spread_chg)
    steep = sp >= flat_bp; flatn = sp <= -flat_bp
    if level == "flat":
        return "flat", level
    if level == "mixed":
        return ("twist_steepening" if steep else "twist_flattening" if flatn else "flat"), level
    if not steep and not flatn:
        return ("parallel_down" if level == "down" else "parallel_up"), level
    if level == "down":
        return ("bull_steepening" if steep else "bull_flattening"), level
    return ("bear_steepening" if steep else "bear_flattening"), level


def _intensity_side(z: Mapping[str, float | None], cc: Mapping) -> tuple[str, str | None, float | None]:
    zz = {k: v for k, v in z.items() if v is not None}
    if not zz:
        return "calm", None, None
    top = max(zz, key=lambda k: abs(zz[k]))
    if abs(zz[top]) < float(cc.get("unusual_z", 1.0)):
        return "calm", top, zz[top]
    front = abs(zz.get(str(cc.get("front", "2Y")), 0.0) or 0.0)
    long_ = max((abs(zz.get(t, 0.0) or 0.0) for t in cc.get("long", ["10Y", "30Y"])), default=0.0)
    m = float(cc.get("lead_margin_z", 0.3))
    side = "long" if long_ - front >= m else ("front" if front - long_ >= m else "similar")
    return side, top, zz[top]


def build_curve_move(curve: CurveView, market: MarketSnapshot, cfg: Mapping) -> CurveMoveView:
    cc = cfg.get("curve_move") or {}
    w = int(cc.get("window_days", 5)); wl = f"{w}D"
    pts: list[CurvePoint] = []; chg5: dict[str, float] = {}; chg1: dict[str, float] = {}; z5: dict[str, float | None] = {}; z1: dict[str, float | None] = {}
    end = None
    for t in curve.tenors:
        f = market.features.get(t.id)
        c5 = None if f is None or f.ret_5d is None else round(f.ret_5d, 1)
        c1 = None if f is None or f.ret_1d is None else round(f.ret_1d, 1)
        if f is not None and f.meta is not None and f.meta.as_of is not None:
            end = max(end, f.meta.as_of.date()) if end else f.meta.as_of.date()
        today = t.level
        ago = None if today is None or c5 is None else round(today - c5 / 100.0, 3)
        pts.append(CurvePoint(label=t.label, today=today, ago=ago, chg_bp=c5, z=None if t.z_5d is None else round(t.z_5d, 2), z_window=wl))
        if c5 is not None:
            chg5[t.label] = c5
        if c1 is not None:
            chg1[t.label] = c1
        z5[t.label] = t.z_5d; z1[t.label] = t.z_1d
    lvl = {p.label: p.today for p in pts}
    spreads: list[SpreadMove] = []; sp1: dict[str, float | None] = {}
    flat_bp = float(cc.get("flat_bp", 1))
    for key, (a, b) in (cc.get("spreads") or {}).items():
        if a in chg5 and b in chg5 and lvl.get(a) is not None and lvl.get(b) is not None:
            ch = round(chg5[b] - chg5[a], 1)
            spreads.append(SpreadMove(key=key, level_bp=round((lvl[b] - lvl[a]) * 100.0, 0), chg_bp=ch,  # type: ignore[operator]
                                      direction="steepening" if ch >= flat_bp else ("flattening" if ch <= -flat_bp else "flat")))
        else:
            spreads.append(SpreadMove(key=key, direction="missing"))
        sp1[key] = round(chg1[b] - chg1[a], 1) if a in chg1 and b in chg1 else None
    prim = str(cc.get("primary_spread", "2s10s"))
    sp_main = next((s.chg_bp for s in spreads if s.key == prim), None)
    sp_alt = next((s.chg_bp for s in spreads if s.key != prim), None)
    shape_key, level = _shape(chg5, sp_main, sp_alt, cc)
    labels = cc.get("shape_label") or {}
    mag = abs(sp_main or 0.0)
    word = "" if shape_key in ("flat", "unknown", "parallel_down", "parallel_up") else ("MILD " if mag < float(cc.get("mild_bp", 3)) else ("SHARP " if mag >= float(cc.get("sharp_bp", 10)) else ""))
    shape = word + str(labels.get(shape_key, shape_key.upper()))
    level_dir = {"down": "ALL YIELDS ↓", "up": "ALL YIELDS ↑", "mixed": "MIXED", "flat": "LITTLE CHANGE"}[level]
    # 1D — 상단 REGIME 칸(하루 z 기준)과 같은 날의 모양을 함께 보여, 창이 달라 생기는 차이를 읽게 한다
    sk1, _l1 = _shape(chg1, sp1.get(prim), next((v for k, v in sp1.items() if k != prim), None), cc)
    side1, top1, zt1 = _intensity_side(z1, cc)
    short = ""
    if sk1 != "unknown":
        p1 = sp1.get(prim)
        short = f"1D{'' if end is None else f' ({end.month}/{end.day})'} · {labels.get(sk1, sk1.upper())}" + ("" if p1 is None else f" · {prim} {p1:+.0f}bp") \
            + ("" if top1 is None or zt1 is None else f" · {top1} {zt1:+.1f}σ")
    side, top, zt = _intensity_side(z5, cc)
    rd = cc.get("read") or {}
    s1 = f"{(rd.get('level') or {}).get(level, '')} {str((rd.get('shape') or {}).get(shape_key, '')).format(mild='소폭 ' if word == 'MILD ' else '')}".strip()
    it = rd.get("intensity") or {}
    if side == "calm":
        sn = it.get({"long": "calm_short_long", "front": "calm_short_front"}.get(side1, "calm_short_none"), "")
        s2 = str(it.get("calm", "")).format(window=wl, short_note=sn)
    else:
        s2 = str(it.get(side, "")).format(tenor=top)
    read = fix_particles(f"{s1} {s2}".strip())
    return CurveMoveView(window_label=wl, as_of_date=end, shape_key=shape_key, shape=shape, level_dir=level_dir, points=pts, spreads=spreads, short_window=short,
                         intensity=str((cc.get("intensity_label") or {}).get(side, "")), most_unusual=top, most_unusual_z=None if zt is None else round(zt, 2),
                         read=read, link=str((cc.get("link") or {}).get(level, "")))


# ── YIELD MOVE BREAKDOWN ───────────────────────────────────
def _z5(iid: str, market: MarketSnapshot) -> float | None:
    """분해와 같은 5일 창의 z — 하루 z 와 섞지 않는다."""
    f = market.features.get(iid)
    return None if f is None else f.z_5d


def build_yield_breakdown(decomp: Sequence[YieldDecomposition], market: MarketSnapshot, cfg: Mapping) -> YieldMoveBreakdown:
    c = cfg.get("yield_breakdown") or {}
    small, flat, ratio, dv = float(c.get("small_move_bp", 3)), float(c.get("flat_bp", 1)), float(c.get("lead_ratio", 1.5)), float(c.get("divergence_bp", 2))
    pl = c.get("primary_label") or {}; ln = c.get("line") or {}
    out: list[BreakdownTenor] = []
    for d in decomp:
        nom, be, real, tips = d.nominal_bp, d.breakeven_bp, d.real_implied_bp, d.real_measured_bp
        aligned = bool(d.aligned) if d.aligned is not None else False
        if nom is None or be is None or real is None:
            out.append(BreakdownTenor(tenor=d.tenor, window_days=d.window_days, start_date=d.start_date, end_date=d.end_date, aligned=aligned, nominal_bp=nom,
                                      breakeven_bp=be, tips_bp=tips, primary="unknown", primary_label="—", line=str(ln.get("missing", "")), missing=list(d.missing)))
            continue
        dir_ko = "하락" if nom < 0 else "상승"
        arrow = lambda v: "↓" if v <= -flat else ("↑" if v >= flat else "→")  # noqa: E731
        if abs(nom) < flat:
            prim, plabel, line = "both", "—", str(ln.get("flat", ""))
        elif abs(real) >= abs(be) * ratio:
            prim = "real"; plabel = f"{pl.get('real', 'REAL YIELD')} {arrow(real)}"
            line = str(ln.get("real_with" if be * real > 0 and abs(be) >= flat else "real_alone", "")).format(dir=dir_ko)
        elif abs(be) >= abs(real) * ratio:
            prim = "breakeven"; plabel = f"{pl.get('breakeven', 'INFLATION EXPECTATION')} {arrow(be)}"
            line = str(ln.get("breakeven_with" if be * real > 0 and abs(real) >= flat else "breakeven_alone", "")).format(dir=dir_ko)
        else:
            prim = "both"; plabel = f"{pl.get('both', 'REAL + INFLATION EXP.')} {arrow(nom)}"
            line = str(ln.get("both", "")).format(dir=dir_ko)
        div, dtext = False, ""
        if tips is not None:
            if not aligned:
                dtext = str(c.get("unaligned_text", ""))
            elif abs(tips - real) >= dv or (abs(tips) >= flat and abs(real) >= flat and tips * real < 0):
                div, dtext = True, str(c.get("divergence_text", ""))
        out.append(BreakdownTenor(tenor=d.tenor, window_days=d.window_days, start_date=d.start_date, end_date=d.end_date, aligned=aligned, nominal_bp=nom, real_bp=real,
                                  breakeven_bp=be, tips_bp=tips, primary=prim, primary_label=plabel, line=fix_particles(line), small_move=abs(nom) < small,  # type: ignore[arg-type]
                                  divergence=div, divergence_text=dtext, missing=list(d.missing)))
    order = list(c.get("default_tenors", ["5Y", "10Y"]))
    out.sort(key=lambda t: (order.index(t.tenor) if t.tenor in order else len(order), t.tenor))
    head_t = str(c.get("headline_tenor", "10Y"))
    h = next((t for t in out if t.tenor == head_t), out[0] if out else None)
    ch = c.get("character") or {}
    if h is None or h.primary == "unknown" or h.nominal_bp is None:
        key, level = "unknown", "flat"
    elif abs(h.nominal_bp) < flat:
        key, level = "flat", "flat"
    else:
        level = "down" if h.nominal_bp < 0 else "up"
        ro = c.get("risk_off") or {}
        eq, cr = _z5(str(ro.get("equity", "SPX")), market), _z5(str(ro.get("credit", "US_HY_OAS")), market)
        stress = (eq is not None and eq <= float(ro.get("equity_z", -1.0))) or (cr is not None and cr >= float(ro.get("credit_z", 1.0)))
        real_down = (h.real_bp or 0) <= -flat
        if level == "down":
            if h.primary == "real" or (h.primary == "both" and real_down and (h.breakeven_bp or 0) > -flat):
                key = "growth_riskoff" if stress and real_down else "discount_easing"
            elif h.primary == "breakeven":
                key = "disinflation"
            else:
                key = "growth_riskoff" if stress and real_down else "mixed_down"
        else:
            key = "discount_tightening" if h.primary == "real" else ("inflation_repricing" if h.primary == "breakeven" else "mixed_up")
    character = str(ch.get(key, ""))
    if h is not None and h.small_move and key not in ("flat", "unknown"):
        character += str(c.get("small_suffix", ""))
    return YieldMoveBreakdown(tenors=out, default_tenors=order, headline_tenor=None if h is None else h.tenor, character_key=key, character=fix_particles(character),
                              link=str((c.get("link") or {}).get(level, "")), note=str(c.get("note", "")))


def build_panels(components: Sequence[ComponentScore], curve: CurveView, decomp: Sequence[YieldDecomposition], market: MarketSnapshot,
                 config_dir: Path | None = None, macro: MacroInflationLayer | None = None) -> tuple[InflationPressureMap, CurveMoveView, YieldMoveBreakdown]:
    cfg = load_rates_panels_config(config_dir)
    return build_inflation_map(components, cfg, macro), build_curve_move(curve, market, cfg), build_yield_breakdown(decomp, market, cfg)
