"""
AI 탭 확장 층 (2026-09-29 (6)) — AI 뉴스·수요·하이퍼스케일러 Capex·반도체·HBM/메모리·네트워킹·데이터센터·전력·소프트웨어·EPS·가격·
상대강도·breadth·금리·달러·위험선호를 하나의 연결된 판단 체계로 묶는다.

  무슨 일이 일어나고 있는가 → 밸류체인 어디에 영향을 주는가 → 시장이 확인하는가 → 펀더멘털이 확인하는가 → 어떤 종목에 연결되는가 → 무엇이 뒤집는가

여기서 만드는 것: 상태 띠·펀더멘털 확인·요약 / 전파 체인 / 밸류체인 리더십 / 반도체 펀더멘털 확인(메모리 데이터는 업사이클 판정이 아니라
확인 데이터) / 종목 영향도(네 축, 단일 점수 없음) / 레이더 / 뉴스 → driver → 밸류체인 → 종목 / 기대 vs 펀더멘털 / What Matters Now.
반도체 데이터는 'Fundamental Confirmation Layer' 다 — 업사이클 확률·신호 n/4·서명 일치도는 쓰지 않는다.
임의 값은 만들지 않는다: 계열·컨센서스·기사가 없으면 None/'?'/N/A 로 남기고 분모에서 뺀다. 확률이 아니라 증거 크기. 추천이 아니다.
"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence

from ..models.ai_regime import (
    AiRegime, FundamentalConfirmation, GapRow, MattersItem, MemoryRow, NewsImpact, RadarBucket, SegmentRow, SemiArea, SemiConfirmation,
    StatusItem, StockAxis, StockImpactRow, Transmission, TransmissionStage, ValueChain,
)
from ..models.market import Instrument, MarketSnapshot
from ..models.news import NewsEvent
from ..models.theme import ThemeState
from .ai_regime import _clip, _equal_weight_index, _feature, _member_stats, _pct, _r, _ratio, _z_of
from .korean import fix_particles
from .sentiment import decay_weight

ARROWS = ("↑↑", "↑", "→", "↓", "↓↓")


def _arrow(v: float | None, hi: float, lo: float) -> str:
    if v is None:
        return "?"
    return "↑↑" if v >= hi else "↑" if v >= lo else "↓↓" if v <= -hi else "↓" if v <= -lo else "→"


def _arrow_val(a: str) -> float | None:
    return {"↑↑": 2.0, "↑": 1.0, "→": 0.0, "↓": -1.0, "↓↓": -2.0}.get(a)


def _mean(xs: Sequence[float | None]) -> float | None:
    v = [x for x in xs if x is not None]
    return (sum(v) / len(v)) if v else None


def _stage_status(score: float | None, bands: dict, parts: Sequence[float | None] = ()) -> str:
    if score is None:
        return "UNCONFIRMED"
    p = [x for x in parts if x is not None]
    if p and max(p) >= 15 and min(p) <= -15:
        return "MIXED"
    if score >= float(bands.get("strong", 40)):
        return "STRONG"
    if score >= float(bands.get("positive", 15)):
        return "POSITIVE"
    if score >= float(bands.get("stable", -15)):
        return "STABLE"
    if score >= float(bands.get("deteriorating", -40)):
        return "MIXED"
    return "DETERIORATING"


def extend_with_value_chain(result: AiRegime, cfg: dict, *, market: MarketSnapshot, extra: dict, names: dict, closes: dict, stats: dict, bench_closes: dict,
                            ai_events: Sequence[NewsEvent], narr: Mapping[str, object], themes: Mapping[str, ThemeState], investment: object | None,
                            inst_names: Mapping[str, str], instruments_by_id: Mapping[str, Instrument], as_of: datetime, zwin: int, config_dir: Path | None) -> None:
    vc = cfg.get("value_chain", {}); si = cfg.get("stock_impact", {}); eg = cfg.get("expectation_gap", {}); tr = cfg.get("transmission", {})
    sc = cfg.get("semi_confirmation", {}); ni = cfg.get("news_impact", {}); wm = cfg.get("what_matters", {})
    news_ref = float(cfg.get("news_ref", 40.0)); window = str(cfg.get("window", "max"))
    ma_s = int(cfg.get("breadth", {}).get("ma_short", 5)); ma_l = int(cfg.get("breadth", {}).get("ma_long", 20))
    a_hi, a_lo = [float(x) for x in vc.get("arrow_pct", [3.0, 1.0])]
    inst_cfg = {str(m["id"]): m for m in cfg.get("instruments", [])}
    region = {k: str(v.get("region", "US")) for k, v in inst_cfg.items()}
    avm = result.ai_vs_market
    for mid, rows in closes.items():  # 그룹 밖 종목(장비·파운드리 …)의 통계
        if mid not in stats:
            stats[mid] = _member_stats(rows, ma_s, ma_l) if len(rows) >= 2 else {}

    # ── 메모리·HBM 데이터 (Investment 층의 대체데이터 점) ──────────────
    alt_by_id = {p.id: p for p in (getattr(investment, "alternative", None) or [])}
    improving = float(sc.get("improving_pct", 1.0))
    memory_rows: list[MemoryRow] = []; data_score: dict[str, float] = {}
    for spec in sc.get("memory_rows", []):
        pid = str(spec["id"]); p = alt_by_id.get(pid); structural = bool(spec.get("structural", False))
        if p is None or p.value is None:
            memory_rows.append(MemoryRow(id=pid, label=str(spec["label"]), structural=structural, note="계열 없음")); continue
        fresh = None if p.as_of is None else max(0, (as_of.date() - p.as_of.date()).days)
        chg = p.change_1d if structural else (p.change_1w if p.change_1w is not None else p.change_1m)
        if chg is None:
            status, note = "N/A", f"봉 {p.observations}개 — 변화율을 낼 이력이 아직 없다. 방향은 이력이 쌓이면 나온다"
        elif structural:
            status, note = ("STRONG" if chg >= 5 else "IMPROVING" if chg > 0 else "DETERIORATING" if chg <= -improving else "NEUTRAL"), "앵커 간 변화(분기·비정기) — 일간 점수에 넣지 않는 구조적 증거"
        else:
            status, note = ("IMPROVING" if chg >= improving else "DETERIORATING" if chg <= -improving else "NEUTRAL"), ""
        if status != "N/A":
            data_score[pid] = {"STRONG": 60.0, "IMPROVING": 30.0, "NEUTRAL": 0.0, "DETERIORATING": -30.0}[status]
        memory_rows.append(MemoryRow(id=pid, label=str(spec["label"]), structural=structural, value=p.value, unit=p.unit, change_1d=_r(p.change_1d), change_1w=_r(p.change_1w), change_1m=_r(p.change_1m),
                                     z=_r(p.z), observations=p.observations, frequency=p.frequency, freshness_days=fresh, quality=str(p.quality), status=status, note=note or p.note))  # type: ignore[arg-type]

    # ── EPS revision (컨센서스가 있는 종목만) ────────────────────────
    eps_map: dict[str, float] = {}
    for a in (getattr(investment, "analyst", None) or []):
        v = getattr(a, "eps_revision_1m", None) if getattr(a, "eps_revision_1m", None) is not None else getattr(a, "eps_revision_1w", None)
        if getattr(a, "available", False) and v is not None:
            eps_map[str(a.stock_id)] = float(v)

    # ── 내러티브 driver 톤 ─────────────────────────────────────────
    tone_of = {k: (getattr(v, "tone", None), getattr(v, "count", 0)) for k, v in narr.items()}
    def _drivers_tone(keys: Sequence[str]) -> float | None:
        return _mean([tone_of[k][0] for k in keys if k in tone_of and tone_of[k][1] > 0])

    # ── 밸류체인 세그먼트 ──────────────────────────────────────────
    bench = str(vc.get("benchmark", "NDX")); bc = bench_closes.get(bench); kbc = bench_closes.get("KOSPI")
    mi = si.get("macro_inputs", {}); z_ref = float(si.get("macro", {}).get("z_ref", 2.0))
    macro_z = {k: _z_of(str(iid), market, extra, window)[0] for k, iid in mi.items()}
    seg_rows: list[SegmentRow] = []; seg_cfg: dict[str, dict] = {}; seg_fund: dict[str, float | None] = {}; seg_mkt_ev: dict[str, float | None] = {}
    eg_m = eg.get("market", {}); eg_f = eg.get("fundamental", {})
    for s in vc.get("segments", []):
        key = str(s["key"]); ids = [str(m) for m in s.get("members", [])]; seg_cfg[key] = s
        avail = [i for i in ids if stats.get(i)]
        row = SegmentRow(key=key, label=str(s["label"]), label_ko=str(s.get("label_ko", s["label"])), exposure=str(s.get("exposure", "MEDIUM")).replace("_", " "), members=len(ids), available=len(avail))
        if bc and avail:
            cal = [d for d, _ in bc]; bv = [v for _, v in bc]
            gd, gv, _u = _equal_weight_index({i: closes.get(i, []) for i in avail}, cal)
            row.ret_1d, row.ret_5d, row.ret_21d = _r(_pct(gv, 1)), _r(_pct(gv, 5)), _r(_pct(gv, 21))
            b1, b5, b21 = _pct(bv, 1), _pct(bv, 5), _pct(bv, 21)
            row.rel_1d = _r(None if row.ret_1d is None or b1 is None else row.ret_1d - b1)
            row.rel_5d = _r(None if row.ret_5d is None or b5 is None else row.ret_5d - b5)
            row.rel_21d = _r(None if row.ret_21d is None or b21 is None else row.ret_21d - b21)
            rd, rv = _ratio(gd, gv, cal, bv); rf = _feature(f"VC_{key.upper()}_REL", rd, rv, as_of, zwin)
            row.rel_z_5d = _r(rf.z_5d) if rf else None
        flags = [stats[i]["above_ma20"] for i in avail if stats[i].get("above_ma20") is not None]
        row.above_ma20_pct = _r(100.0 * sum(1 for f in flags if f) / len(flags), 0) if flags else None
        eps_vals = [eps_map[i] for i in ids if i in eps_map]
        row.eps = _r(_mean(eps_vals)) if eps_vals else None
        row.eps_note = f"컨센서스 {len(eps_vals)}/{len(ids)} 종목" if eps_vals else "컨센서스 없음 — EPS revision 을 잴 수 없다"
        row.arrow_1w, row.arrow_rel, row.arrow_eps = _arrow(row.ret_5d, a_hi, a_lo), _arrow(row.rel_5d, a_hi, a_lo), _arrow(row.eps, 5.0, 1.0)  # type: ignore[assignment]
        sens = s.get("macro", {}) or {}
        contrib = [float(sens[k]) * (macro_z[k] / z_ref) for k in sens if k in macro_z and macro_z[k] is not None]
        row.macro_score = _r(max(-2.0, min(2.0, sum(contrib) / max(1.0, len(contrib)) * 2.0))) if contrib else None
        # 기대(시장 가격) vs 펀더멘털
        mkt = None
        if row.rel_z_5d is not None or row.ret_21d is not None or row.above_ma20_pct is not None:
            mkt = 50.0
            if row.rel_z_5d is not None: mkt += float(eg_m.get("rel_z_w", 25)) * _clip(row.rel_z_5d / 2.0)
            if row.ret_21d is not None: mkt += float(eg_m.get("ret21_w", 15)) * _clip(row.ret_21d / float(eg_m.get("ret21_ref", 10)))
            if row.above_ma20_pct is not None: mkt += float(eg_m.get("breadth_w", 10)) * (row.above_ma20_pct - 50.0) / 50.0
            mkt = max(0.0, min(100.0, mkt))
        seg_mkt_ev[key] = None if row.rel_z_5d is None else _clip(row.rel_z_5d / 2.0) * 100.0
        tone = _drivers_tone([str(d) for d in s.get("drivers", [])]); fund_ids = [str(x) for x in s.get("fundamentals", [])]
        dsc = _mean([data_score[i] for i in fund_ids if i in data_score]) if fund_ids else None
        parts = []
        if tone is not None: parts.append(float(eg_f.get("tone_w", 30)) * _clip(tone / news_ref))
        if dsc is not None: parts.append(float(eg_f.get("data_w", 20)) * _clip(dsc / 60.0))
        if row.eps is not None: parts.append(float(eg_f.get("eps_w", 20)) * _clip(row.eps / 5.0))
        fund = max(0.0, min(100.0, 50.0 + sum(parts))) if parts else None
        seg_fund[key] = None if fund is None else (fund - 50.0) * 2.0
        seg_rows.append(row); row_gap = (mkt, fund)
        s["_gap"] = row_gap  # noqa — 아래 gap 표에서 쓴다
    ranked = sorted([r for r in seg_rows if r.rel_5d is not None], key=lambda r: -(r.rel_5d or 0))
    top_n = int(vc.get("leadership_top", 4)); lag_max = float(vc.get("lag_max_rel_pct", -1.0))
    for i, r in enumerate(ranked):
        r.rank_1w = i + 1; r.role = "leading" if i < top_n and (r.rel_5d or 0) > 0 else "lagging" if (r.rel_5d or 0) <= lag_max else "neutral"
    lab = {r.key: r.label for r in seg_rows}
    leadership = [r.key for r in ranked[:top_n]]
    lag_n = int(vc.get("lagging_bottom", 3))
    lagging = [r.key for r in ranked[::-1] if r.role == "lagging" and r.key not in leadership][:lag_n]
    if ranked:
        top_txt = " · ".join(f"{lab[k]}({next(r.rel_5d for r in ranked if r.key == k):+.1f}%p)" for k in leadership)
        vc_sent = f"1주 상대 모멘텀 상위: {top_txt}. " + (f"후미: {', '.join(lab[k] for k in lagging)}. " if lagging else "") + ("상위도 Nasdaq 에 뒤진다 — 상대적 순위일 뿐 절대 리더십은 없다." if all((r.rel_5d or 0) <= 0 for r in ranked[:top_n]) else "")
    else:
        vc_sent = "세그먼트 상대 모멘텀을 낼 계열이 없다."
    result.value_chain = ValueChain(segments=seg_rows, leadership=leadership, lagging=lagging, sentence=vc_sent)
    seg_by = {r.key: r for r in seg_rows}

    # ── 전파 체인 ──────────────────────────────────────────────────
    bands = tr.get("bands", {}); stages: list[TransmissionStage] = []
    news_tone = result.narrative.news_tone
    # 세그먼트 '펀더멘털' 점수(seg_fund)가 무엇으로 만들어졌는지 — 근거 유형 태그용. 기사 톤이면 NEWS, 메모리 데이터·EPS 면 DATA
    seg_fund_basis: dict[str, set[str]] = {}
    for s in vc.get("segments", []):
        k = str(s["key"]); b: set[str] = set()
        if _drivers_tone([str(d) for d in s.get("drivers", [])]) is not None: b.add("NEWS")
        if any(i in data_score for i in s.get("fundamentals", [])): b.add("DATA")
        if seg_by.get(k) is not None and seg_by[k].eps is not None: b.add("DATA")
        seg_fund_basis[k] = b
    for st in tr.get("stages", []):
        src = str(st.get("source")); parts: list[float | None] = []; ev = []; basis: list[str] = []
        def _tag(t: str) -> None:
            if t not in basis: basis.append(t)
        if src == "news_tone":
            parts = [None if news_tone is None else _clip(news_tone / news_ref) * 100]; ev.append(f"AI 뉴스 톤 {'–' if news_tone is None else f'{news_tone:+.0f}'} ({result.narrative.news_count}건)")
            if news_tone is not None: _tag("NEWS")
        elif src == "drivers":
            t = _drivers_tone([str(d) for d in st.get("drivers", [])]); parts.append(None if t is None else _clip(t / news_ref) * 100); ev.append(f"driver 톤 {'–' if t is None else f'{t:+.0f}'}")
            if t is not None: _tag("NEWS")
            sg = seg_by.get(str(st.get("segment", ""))); parts.append(seg_mkt_ev.get(sg.key) if sg else None)
            if sg: ev.append(f"{sg.label} 상대 z {'–' if sg.rel_z_5d is None else f'{sg.rel_z_5d:+.1f}σ'}")
            if sg and seg_mkt_ev.get(sg.key) is not None: _tag("PRICE")
        elif src == "segment":
            for k in (st.get("segment"), st.get("segment2")):
                if k and k in seg_by:
                    parts += [seg_mkt_ev.get(k), seg_fund.get(k)]
                    ev.append(f"{seg_by[k].label} 상대 z {'–' if seg_by[k].rel_z_5d is None else f'{seg_by[k].rel_z_5d:+.1f}σ'} · 펀더멘털 {'–' if seg_fund.get(k) is None else f'{seg_fund[k]:+.0f}'}")
                    if seg_mkt_ev.get(k) is not None: _tag("PRICE")
                    if seg_fund.get(k) is not None:
                        for b in sorted(seg_fund_basis.get(k, set())): _tag(b)
        elif src == "fundamentals":
            ds = [data_score[i] for i in st.get("ids", []) if i in data_score]; parts.append(_mean(ds) if ds else None)
            ev.append("메모리 데이터 " + (", ".join(f"{i} {next(r.status for r in memory_rows if r.id == i)}" for i in st.get("ids", []) if any(r.id == i for r in memory_rows)) or "없음"))
            if ds: _tag("DATA")
            if st.get("drivers"):
                t = _drivers_tone([str(d) for d in st["drivers"]]); parts.append(None if t is None else _clip(t / news_ref) * 100); ev.append(f"driver 톤 {'–' if t is None else f'{t:+.0f}'}")
                if t is not None: _tag("NEWS")
        elif src == "eps":
            vals = list(eps_map.values()); parts.append(None if not vals else _clip(_mean(vals) / 5.0) * 100)  # type: ignore[arg-type]
            ev.append(f"컨센서스 {len(vals)}종목" if vals else "컨센서스 없음 — EPS revision 은 아직 못 잰다")
            if vals: _tag("DATA")
        score = _mean(parts); status = _stage_status(score, bands, parts)
        if status == "STRONG" and st.get("accelerating_label"): status = "ACCELERATING"
        if src == "eps" and status in ("POSITIVE", "STRONG"): status = "IMPROVING"
        stages.append(TransmissionStage(key=str(st["key"]), label=str(st["label"]), status=status, score=_r(score), evidence=" · ".join(ev), basis=basis))  # type: ignore[arg-type]
    good = [s.label for s in stages if s.status in ("ACCELERATING", "POSITIVE", "STRONG", "IMPROVING")]
    limited = [s.label for s in stages if s.status in ("MIXED", "UNCONFIRMED", "DETERIORATING", "STABLE")]
    tr_sent = (f"AI 투자 수요는 {' · '.join(good)} 까지 확인된다" if good else "AI 투자 수요가 확인되는 단계가 없다") + (f" — {' · '.join(limited)} 로의 전파는 아직 제한적이거나 미확인이다." if limited else ".")
    result.transmission = Transmission(stages=stages, sentence=tr_sent)

    # ── 반도체 펀더멘털 확인 ───────────────────────────────────────
    areas: list[SemiArea] = []
    for a in sc.get("areas", []):
        sg = seg_by.get(str(a.get("segment", ""))); fids = [str(x) for x in a.get("fundamentals", [])]
        area = SemiArea(key=str(a["key"]), label=str(a["label"]), status="UNCONFIRMED")
        if not a.get("fundamentals_only") and sg is not None:
            area.price_momentum = _arrow(sg.ret_5d, a_hi, a_lo); area.relative_strength = _arrow(sg.rel_5d, a_hi, a_lo)  # type: ignore[assignment]
            area.breadth = "?" if sg.above_ma20_pct is None else ("↑↑" if sg.above_ma20_pct >= 70 else "↑" if sg.above_ma20_pct >= 55 else "→" if sg.above_ma20_pct >= 45 else "↓" if sg.above_ma20_pct >= 30 else "↓↓")  # type: ignore[assignment]
            t = _drivers_tone([str(d) for d in seg_cfg.get(sg.key, {}).get("drivers", [])]); area.news_evidence = _arrow(t, 20, 5)  # type: ignore[assignment]
            area.eps = sg.arrow_eps
        if fids:
            ds = [data_score[i] for i in fids if i in data_score]
            if ds:
                area.news_evidence = _arrow(_mean(ds), 40, 10) if a.get("fundamentals_only") else area.news_evidence  # type: ignore[assignment]
                if a.get("fundamentals_only"):
                    area.price_momentum = _arrow(_mean(ds), 40, 10)  # type: ignore[assignment]
        vals = [v for v in (_arrow_val(area.price_momentum), _arrow_val(area.relative_strength), _arrow_val(area.breadth), _arrow_val(area.news_evidence), _arrow_val(area.eps)) if v is not None]
        if not vals:
            area.status, area.detail = "UNCONFIRMED", "잴 계열이 없다"
        elif a.get("fundamentals_only"):
            m = _mean(vals) or 0.0; area.status = "IMPROVING" if m >= 0.5 else "WEAK" if m <= -0.5 else "NEUTRAL"  # type: ignore[assignment]
            area.detail = "메모리 현물·지수 데이터만으로 본다(주가 아님)"
        else:
            pos = sum(1 for v in vals if v >= 1); neg = sum(1 for v in vals if v <= -1)
            if pos and neg: area.status = "MIXED"
            elif pos >= 2 and _arrow_val(area.relative_strength) == 2: area.status = "LEADING"
            elif pos >= 2 and neg == 0: area.status = "STRONG"
            elif neg >= 2: area.status = "WEAK"
            else: area.status = "NEUTRAL"
            area.detail = f"가격 {area.price_momentum} · 상대 {area.relative_strength} · breadth {area.breadth} · 뉴스 {area.news_evidence} · EPS {area.eps}"
        areas.append(area)
    strong_a = [x.label for x in areas if x.status in ("STRONG", "LEADING", "IMPROVING")]; weak_a = [x.label for x in areas if x.status in ("WEAK", "MIXED", "NEUTRAL")]
    unc_a = [x.label for x in areas if x.status == "UNCONFIRMED"]
    semi_sent = (f"AI 수요는 {' · '.join(strong_a)} 에서 확인되고 있으나" if strong_a else "AI 수요가 반도체 데이터에서 확인되는 영역이 없고") + (f" {' · '.join(weak_a)} 까지의 확산은 제한적이다." if weak_a else " 나머지는 확인된다.") + (f" ({' · '.join(unc_a)} 는 계열 없음)" if unc_a else "")
    result.semi_confirmation = SemiConfirmation(areas=areas, memory=memory_rows, sentence=semi_sent)
    n_strong = len(strong_a); n_weak = len([x for x in areas if x.status in ("WEAK", "MIXED")])
    level = "STRONG" if n_strong >= 4 and n_weak == 0 else "PARTIAL" if n_strong >= 1 else "WEAK" if n_weak >= 1 else "UNCONFIRMED"
    fc_sent = {"STRONG": "실제 AI 인프라·반도체 데이터가 넓게 개선을 확인한다.", "PARTIAL": f"AI 관련 가격은 {'매크로 위험회피의 영향을 받고 있지만' if avm.abs_direction == 'down' else '움직이고 있고'} {' · '.join(strong_a)} 등 실제 AI 인프라 데이터는 부분적으로 개선을 확인한다.",
               "WEAK": "반도체·인프라 데이터가 AI 내러티브를 확인하지 못한다.", "UNCONFIRMED": "확인할 반도체·인프라 데이터가 없다."}[level]
    result.fundamental_confirmation = FundamentalConfirmation(level=level, confirming=strong_a, lagging=weak_a, sentence=fc_sent)  # type: ignore[arg-type]

    # ── 종목 영향도 (네 축) ────────────────────────────────────────
    th = si.get("theme", {}); mk = si.get("market", {}); ab = [float(x) for x in si.get("axis_bands", [1.5, 0.5])]
    seg_of: dict[str, list[str]] = {}
    for s in vc.get("segments", []):
        for m in s.get("members", []):
            seg_of.setdefault(str(m), []).append(str(s["key"]))
    ev_sorted = sorted(ai_events, key=lambda e: -decay_weight(e, as_of, config_dir=config_dir))
    def _mentions(iid: str) -> list[NewsEvent]:
        al = [str(inst_names.get(iid, iid))] + [str(x) for x in inst_cfg.get(iid, {}).get("aliases", [])]
        return [e for e in ev_sorted if any(a.lower() in e.event.lower() for a in al if len(a) >= 2)]
    def _ax(v: float | None) -> str:
        return "?" if v is None else "↑↑" if v >= ab[0] else "↑" if v >= ab[1] else "↓↓" if v <= -ab[0] else "↓" if v <= -ab[1] else "→"
    stocks: list[StockImpactRow] = []
    exp_rank = {"VERY HIGH": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    for iid, segs in seg_of.items():
        name = inst_names.get(iid, iid); st = stats.get(iid) or {}
        exp = min((str(seg_cfg[k].get("exposure", "MEDIUM")).replace("_", " ") for k in segs), key=lambda e: exp_rank.get(e, 9))
        row = StockImpactRow(id=iid, name=name, segments=segs, region=region.get(iid, "US"), theme_exposure=exp, available=bool(st))
        # THEME — 세그먼트 driver 톤 + 직접 언급
        drv = sorted({d for k in segs for d in seg_cfg[k].get("drivers", [])}); t = _drivers_tone([str(d) for d in drv]); ments = _mentions(iid)
        theme_v = None if t is None else max(-2.0, min(2.0, t / news_ref * 2.0))
        if ments:
            mt = _mean([float(e.theme_sentiment.get("ai", e.sentiment)) for e in ments]) or 0.0
            theme_v = max(-2.0, min(2.0, (theme_v or 0.0) + float(th.get("mention_bonus", 0.5)) * (1 if mt > 0 else -1 if mt < 0 else 0)))
        # FUNDAMENTAL — 세그먼트 펀더멘털 증거 + EPS
        fparts = [seg_fund[k] / 50.0 for k in segs if seg_fund.get(k) is not None]
        if iid in eps_map: fparts.append(_clip(eps_map[iid] / 5.0) * 2.0)
        fund_v = None if not fparts else max(-2.0, min(2.0, _mean(fparts) or 0.0))
        # MARKET — 자기 가격: 1주 상대(벤치마크는 지역), 1개월 수익, 20일선
        bref = kbc if region.get(iid) == "KR" else bc
        rel5 = None
        if st and bref:
            b5 = _pct([v for _, v in bref], 5); rel5 = None if st.get("ret_5d") is None or b5 is None else st["ret_5d"] - b5
        mparts = []
        if rel5 is not None: mparts.append(max(-2.0, min(2.0, rel5 / float(mk.get("rel_pct_ref", 4.0)) * 2.0)))
        if st.get("ret_21d") is not None: mparts.append(max(-2.0, min(2.0, st["ret_21d"] / float(mk.get("ret21_ref", 10.0)) * 2.0)))
        if st.get("above_ma20") is not None: mparts.append(0.5 if st["above_ma20"] else -0.5)
        mkt_v = None if not mparts else max(-2.0, min(2.0, _mean(mparts) or 0.0))
        # MACRO — 세그먼트 민감도 × 현재 매크로 z
        macro_v = _mean([seg_by[k].macro_score for k in segs if k in seg_by])
        r5 = st.get("ret_5d"); r21 = st.get("ret_21d")
        mkt_detail = ("계열 없음" if not st else
                      f"1주 {'–' if r5 is None else f'{r5:+.1f}%'} (상대 {'–' if rel5 is None else f'{rel5:+.1f}%p'}) · 1개월 {'–' if r21 is None else f'{r21:+.1f}%'} · 20일선 {'위' if st.get('above_ma20') else '아래'}")
        row.axes = [StockAxis(key="theme", value=_r(theme_v), arrow=_ax(theme_v), detail=f"driver {', '.join(drv) or '없음'} 톤 {'–' if t is None else f'{t:+.0f}'} · 직접 언급 {len(ments)}건"),  # type: ignore[arg-type]
                    StockAxis(key="fundamental", value=_r(fund_v), arrow=_ax(fund_v), detail=("세그먼트 펀더멘털 " + " · ".join(f"{seg_by[k].label} {'–' if seg_fund.get(k) is None else f'{seg_fund[k]:+.0f}'}" for k in segs)) + (f" · EPS {eps_map[iid]:+.1f}%" if iid in eps_map else " · EPS 컨센서스 없음")),  # type: ignore[arg-type]
                    StockAxis(key="market", value=_r(mkt_v), arrow=_ax(mkt_v), detail=mkt_detail),  # type: ignore[arg-type]
                    StockAxis(key="macro", value=_r(macro_v), arrow=_ax(macro_v), detail="세그먼트 민감도 × 금리·실질금리·HY OAS·달러 z — 음수는 역풍")]  # type: ignore[arg-type]
        row.ret_5d, row.rel_5d, row.ret_21d, row.mentions = _r(st.get("ret_5d")), _r(rel5), _r(st.get("ret_21d")), len(ments)
        row.ai_demand = "POSITIVE" if (theme_v or 0) >= 0.5 else "NEGATIVE" if (theme_v or 0) <= -0.5 else ("NEUTRAL" if theme_v is not None else "NO NEWS")
        row.semiconductor = "N/A" if fund_v is None else "CONFIRMED" if fund_v >= 0.5 else "WEAK" if fund_v <= -0.5 else "MIXED"
        row.relative_strength = "N/A" if rel5 is None else "STRONG" if rel5 >= a_lo else "WEAK" if rel5 <= -a_lo else "NEUTRAL"
        row.news_flow = f"{len(ments)}건 · {'+' if ments and (_mean([float(e.theme_sentiment.get('ai', e.sentiment)) for e in ments]) or 0) > 0 else '−' if ments else '–'}" if ments else "언급 없음"
        row.eps_revision = f"{eps_map[iid]:+.1f}%" if iid in eps_map else "N/A"
        row.rates_sensitivity = "N/A" if macro_v is None else "NEGATIVE" if macro_v <= -0.5 else "POSITIVE" if macro_v >= 0.5 else "NEUTRAL"
        tv, fv, mv, cv = theme_v, fund_v, mkt_v, macro_v
        if not st:
            row.overall, row.confirmation = "NO DATA", "NO DATA"
        elif (fv or 0) >= 0.5 and (mv or 0) >= 0.5 and (tv or 0) >= 0.5:
            row.overall, row.confirmation = "STRONG", "CONFIRMED"
        elif (fv or 0) >= 0.5 and (mv or 0) >= 0.5:
            row.overall, row.confirmation = "CONFIRMED", "FUNDAMENTALS / PRICE LEADING NARRATIVE" if (tv is None or tv < 0.5) else "CONFIRMED"
        elif (mv or 0) <= -0.5 and (cv or 0) <= -0.5 and (fv is None or fv <= 0.5):
            row.overall, row.confirmation = "NEGATIVE PRESSURE", "NEGATIVE"
        elif (tv or 0) >= 0.5 and (mv is None or mv < 0.5):
            row.overall, row.confirmation = "UNCONFIRMED", "NEWS POSITIVE / MARKET UNCONFIRMED"
        elif (fv or 0) >= 0.5 and (mv or 0) < 0.5:
            row.overall, row.confirmation = "UNCONFIRMED", "FUNDAMENTALS / PRICE LEADING NARRATIVE" if (tv or 0) < 0.5 else "MIXED"
        else:
            row.overall, row.confirmation = "MIXED", "MIXED"
        segl = " · ".join(seg_by[k].label for k in segs if k in seg_by)
        parts_i = []
        parts_i.append(f"{segl} 노출({exp})")
        parts_i.append("AI 수요·펀더멘털 확인은 강하다" if (fv or 0) >= 1 and (tv or 0) >= 0.5 else "펀더멘털 확인이 부분적이다" if (fv or 0) >= 0.5 else "펀더멘털 확인이 없다" if fv is None else "펀더멘털이 약하다")
        parts_i.append("가격도 상대 강세로 확인한다" if (mv or 0) >= 0.5 else "가격 확인은 아직 부분적이다" if mv is not None and mv > -0.5 else "가격은 상대 약세다" if mv is not None else "가격 계열이 없다")
        parts_i.append("금리·위험회피 환경이 밸류에이션에 부담이다" if (cv or 0) <= -0.5 else "매크로는 중립이다" if cv is not None else "")
        row.interpretation = ", ".join(p for p in parts_i if p) + "."
        stocks.append(row)
    ov_rank = {"STRONG": 0, "CONFIRMED": 1, "MIXED": 2, "UNCONFIRMED": 3, "NEGATIVE PRESSURE": 4, "NO DATA": 5}
    stocks.sort(key=lambda r: (exp_rank.get(r.theme_exposure, 9), ov_rank.get(r.overall, 9), -(r.rel_5d or -99)))
    result.stocks = stocks
    ax = lambda r, k: next((a.value for a in r.axes if a.key == k), None)  # noqa: E731

    # ── 레이더 ────────────────────────────────────────────────────
    nmax = int(si.get("radar_max_per_bucket", 4)); buckets: list[RadarBucket] = []
    def _reason(r: StockImpactRow, kind: str) -> str:
        segl = "/".join(seg_by[k].label_ko for k in r.segments[:2] if k in seg_by)
        if kind == "strongest": return f"{segl} + 펀더멘털 {_ax(ax(r, 'fundamental'))} + 상대강도 {'–' if r.rel_5d is None else f'{r.rel_5d:+.1f}%p'}"
        if kind == "improving": return f"{segl} 1주 {'–' if r.ret_5d is None else f'{r.ret_5d:+.1f}%'} · 상대 {'–' if r.rel_5d is None else f'{r.rel_5d:+.1f}%p'} · 펀더멘털 {_ax(ax(r, 'fundamental'))}"
        if kind == "narrative_ahead": return f"AI 뉴스 {_ax(ax(r, 'theme'))}({r.mentions}건 언급) 인데 상대 가격 {'–' if r.rel_5d is None else f'{r.rel_5d:+.1f}%p'}"
        if kind == "fundamentals_ahead": return f"펀더멘털 {_ax(ax(r, 'fundamental'))} 인데 가격 {_ax(ax(r, 'market'))} — 가격 반영이 제한적"
        return f"{segl} · 매크로 {_ax(ax(r, 'macro'))}(금리·위험회피 민감) · 상대 {'–' if r.rel_5d is None else f'{r.rel_5d:+.1f}%p'}"
    avail_st = [r for r in stocks if r.available]
    b_strong = [r for r in avail_st if r.overall == "STRONG"]
    b_impr = [r for r in avail_st if r.overall != "STRONG" and (r.rel_5d or 0) > 0 and (r.ret_5d or 0) > 0 and (ax(r, "fundamental") or 0) >= 0]
    b_narr = [r for r in avail_st if (ax(r, "theme") or 0) >= 0.5 and (ax(r, "market") is None or (ax(r, "market") or 0) <= 0) and (r.mentions > 0 or (ax(r, "theme") or 0) >= 1.0)]
    b_fund = [r for r in avail_st if (ax(r, "fundamental") or 0) >= 0.5 and (ax(r, "market") or 0) <= 0]
    b_macro = [r for r in avail_st if (ax(r, "macro") or 0) <= -0.5 and (ax(r, "market") or 0) <= 0]
    for key, label, lst, sort_key in (("strongest", "STRONGEST CONFIRMATION", b_strong, lambda r: -(r.rel_5d or 0)), ("improving", "IMPROVING", b_impr, lambda r: -(r.rel_5d or 0)),
                                      ("narrative_ahead", "NARRATIVE > FUNDAMENTALS", b_narr, lambda r: -(ax(r, "theme") or 0)), ("fundamentals_ahead", "FUNDAMENTALS > PRICE", b_fund, lambda r: (ax(r, "market") or 0)),
                                      ("macro_pressure", "MACRO PRESSURE", b_macro, lambda r: (ax(r, "macro") or 0))):
        items = [{"id": r.id, "name": r.name, "reason": _reason(r, key)} for r in sorted(lst, key=sort_key)[:nmax]]
        buckets.append(RadarBucket(key=key, label=label, items=items))  # type: ignore[arg-type]
    result.radar = buckets

    # ── 뉴스 → driver → 밸류체인 → 종목 ───────────────────────────
    kw = {str(d["key"]): [str(k).lower() for k in d.get("keywords", [])] for d in cfg.get("narrative_drivers", [])}
    chains = ni.get("chains", {}); news: list[NewsImpact] = []
    st_by = {r.id: r for r in stocks}
    def _top_stocks(seg_keys: Sequence[str], n: int = 3, first: Sequence[str] = ()) -> list[str]:
        """세그먼트 구성원 중 시장 축이 높은 순. 기사에 직접 언급된 종목(first)이 있으면 그것부터."""
        ids = []
        for k in seg_keys:
            for m in seg_cfg.get(k, {}).get("members", []):
                if str(m) not in ids: ids.append(str(m))
        ids.sort(key=lambda i: (0 if i in first else 1, -((ax(st_by[i], "market") or 0) if i in st_by else -9)))
        return [st_by[i].name if i in st_by else i for i in ids[:n]]
    def _mentioned(e: NewsEvent) -> list[str]:
        out = []
        for iid in seg_of:
            al = [str(inst_names.get(iid, iid))] + [str(x) for x in inst_cfg.get(iid, {}).get("aliases", [])]
            if any(a.lower() in e.event.lower() for a in al if len(a) >= 2): out.append(iid)
        return out
    for e in ev_sorted[: int(ni.get("top_n", 5))]:
        drv = [k for k, ks in kw.items() if any(x in e.event.lower() for x in ks)]
        prim = []; sec = []; infra = []
        for d in drv:
            c = chains.get(d, {}); prim += [x for x in c.get("primary", []) if x not in prim]; sec += [x for x in c.get("secondary", []) if x not in sec and x not in prim]; infra += [x for x in c.get("infrastructure", []) if x not in infra]
        tone = float(e.theme_sentiment.get("ai", e.sentiment)); first = _mentioned(e)
        pm = _mean([ax(st_by[i], "market") for k in prim for i in [str(m) for m in seg_cfg.get(k, {}).get("members", [])] if i in st_by]) if prim else None
        if not drv: conf = "driver 미분류 — 밸류체인 연결 없음" + (f" (직접 언급: {', '.join(st_by[i].name for i in first if i in st_by)})" if first else "")
        elif pm is None: conf = "1차 노출 종목 가격 없음"
        elif tone > 0 and pm >= 0.5: conf = "CONFIRMED — 뉴스 + 1차 노출 가격 ↑"
        elif tone > 0: conf = "NEWS POSITIVE / MARKET UNCONFIRMED"
        elif tone < 0 and pm <= -0.5: conf = "CONFIRMED NEGATIVE — 뉴스 − 1차 노출 가격 ↓"
        elif tone < 0: conf = "NEWS NEGATIVE / PRICE RESILIENT"
        else: conf = "NEUTRAL"
        news.append(NewsImpact(event=e.event[:120], source=e.source, url=e.url, tone=round(tone, 0), drivers=drv, primary=[lab.get(k, k) for k in prim], secondary=[lab.get(k, k) for k in sec], infrastructure=[lab.get(k, k) for k in infra],
                               primary_stocks=_top_stocks(prim, first=first) if prim else [st_by[i].name for i in first if i in st_by][:3], secondary_stocks=_top_stocks(sec, first=first), infrastructure_stocks=_top_stocks(infra, first=first), confirmation=conf))
    result.news_impact = news

    # ── 기대 vs 펀더멘털 ──────────────────────────────────────────
    gaps: list[GapRow] = []; gnote = float(eg.get("gap_note", 15))
    for s in vc.get("segments", []):
        mkt, fund = s.get("_gap", (None, None)); key = str(s["key"])
        gap = None if mkt is None or fund is None else round(mkt - fund, 0)
        note = ("펀더멘털 근거 없음 — 기대만 있다" if fund is None else "가격 계열 없음" if mkt is None else
                "기대가 펀더멘털보다 앞서 있다" if gap >= gnote else "펀더멘털 대비 가격 반영이 제한적이다" if gap <= -gnote else "비교적 확인된 움직임")
        gaps.append(GapRow(key=key, label=lab.get(key, key), market_pricing=_r(mkt, 0), fundamental=_r(fund, 0), gap=gap, note=note))
        s.pop("_gap", None)
    result.expectation_gap = gaps

    # ── WHAT MATTERS NOW ──────────────────────────────────────────
    stage_score = {s.key: s.score for s in stages}
    hyper_g = next((g for g in result.leadership.groups if g.key == "hyperscalers"), None)
    metrics: dict[str, float | None] = {f"TRANS_{k}": v for k, v in stage_score.items()}
    metrics["BROADEN"] = _mean([seg_by[k].rel_z_5d for k in ("software", "dc_infra") if k in seg_by])
    metrics["AI_REL_NDX_Z5"] = avm.rel_ndx_z_5d; metrics["BREADTH_CHANGE"] = result.breadth.change_1w_pts
    metrics["HYPER_DOWN_1W_NEG"] = None if hyper_g is None or not hyper_g.available else -float(hyper_g.down_1w)
    items: list[MattersItem] = []
    for q in wm.get("questions", []):
        v = metrics.get(str(q["metric"]))
        if v is None:
            continue
        stt = "CONFIRMING" if v >= float(q["confirming"]) else "DETERIORATING" if v <= float(q["deteriorating"]) else "WATCH"
        items.append(MattersItem(key=str(q["key"]), text=str(q["text"]), status=stt, metric=str(q["metric"]), current=f"{v:+.1f}", detail=f"확인 ≥ {float(q['confirming']):g} · 악화 ≤ {float(q['deteriorating']):g}"))  # type: ignore[arg-type]
        if len(items) >= int(wm.get("max", 5)):
            break
    result.what_matters = items

    # ── 상태 띠 · 부제 · 요약 ─────────────────────────────────────
    nt = news_tone
    narr_lbl = "–" if nt is None else "POSITIVE" if nt >= 20 else "NEUTRAL+" if nt >= 5 else "NEUTRAL" if nt >= -5 else "NEUTRAL−" if nt >= -20 else "NEGATIVE"
    rz = avm.rel_ndx_z_5d
    rel_lbl = "–" if rz is None else "STRONG" if rz >= 0.5 else ("RESILIENT" if avm.abs_direction == "down" else "NEUTRAL") if rz >= -0.5 else "SOFT" if rz >= -1 else "WEAK"
    bz = avm.basket_z; price_lbl = "–" if bz is None else "STRONG" if bz >= 0.5 else "FLAT" if bz >= -0.5 else "WEAK"
    infra_keys = ("dc_infra", "power", "networking"); infra_st = [seg_by[k] for k in infra_keys if k in seg_by and seg_by[k].rel_5d is not None]
    infra_lbl = "–" if not infra_st else "STRONG" if sum(1 for s in infra_st if (s.rel_5d or 0) >= a_lo) >= 2 else "WEAK" if sum(1 for s in infra_st if (s.rel_5d or 0) <= -a_lo) >= 2 else "MIXED"
    sw = seg_by.get("software"); sw_lbl = "–" if sw is None or sw.rel_5d is None else "STRONG" if sw.rel_5d >= a_lo else "WEAK" if sw.rel_5d <= -a_lo else "NEUTRAL"
    br_lbl = {"widening": "WIDENING", "narrowing": "NARROWING", "stable": "STABLE", "unknown": "–"}[result.breadth.trend]
    mv = result.macro.verdict; macro_lbl = "HEADWIND" if mv in ("macro_driven", "ai_specific") else "TAILWIND" if (mv == "not_weak" and result.macro.explains >= 2 and avm.abs_direction == "up") else "NEUTRAL" if mv != "unknown" else "–"
    good_t = lambda lbl, goods, bads: "good" if lbl in goods else "bad" if lbl in bads else "warn" if lbl != "–" else "muted"  # noqa: E731
    result.status_strip = [
        StatusItem(key="narrative", label="Narrative", value=narr_lbl, tone=good_t(narr_lbl, ("POSITIVE", "NEUTRAL+"), ("NEGATIVE", "NEUTRAL−")), detail=f"AI 뉴스 톤 {'–' if nt is None else f'{nt:+.0f}'}"),
        StatusItem(key="relative", label="AI Relative Strength", value=rel_lbl, tone=good_t(rel_lbl, ("STRONG", "RESILIENT"), ("WEAK",)), detail=f"Nasdaq 대비 5일 상대 z {'–' if rz is None else f'{rz:+.1f}σ'}"),
        StatusItem(key="price", label="Price", value=price_lbl, tone=good_t(price_lbl, ("STRONG",), ("WEAK",)), detail=f"바스켓 {'–' if bz is None else f'{bz:+.1f}σ'}"),
        StatusItem(key="semi", label="Semiconductor Confirm.", value=level, tone=good_t(level, ("STRONG",), ("WEAK",)), detail=fc_sent),
        StatusItem(key="infra", label="AI Infra", value=infra_lbl, tone=good_t(infra_lbl, ("STRONG",), ("WEAK",)), detail="데이터센터 인프라·전력·네트워킹 세그먼트의 1주 상대 %p"),
        StatusItem(key="software", label="Software", value=sw_lbl, tone=good_t(sw_lbl, ("STRONG",), ("WEAK",)), detail=f"소프트웨어 1주 상대 {'–' if sw is None or sw.rel_5d is None else f'{sw.rel_5d:+.1f}%p'}"),
        StatusItem(key="breadth", label="Breadth", value=br_lbl, tone=good_t(br_lbl, ("WIDENING",), ("NARROWING",)), detail=result.breadth.sentence),
        StatusItem(key="macro", label="Macro", value=macro_lbl, tone=good_t(macro_lbl, ("TAILWIND",), ("HEADWIND",)), detail=result.macro.sentence),
        StatusItem(key="fundamental", label="Fundamental Confirmation", value=level, tone=good_t(level, ("STRONG",), ("WEAK",)), detail=fc_sent),
    ]
    # 상태값 아래 한 줄 의미 (config status_meaning) — 번역이 아니라 '지금 이 상태가 뜻하는 것'
    sm = cfg.get("status_meaning", {}) or {}
    conf_txt = " · ".join(strong_a[:2]) if strong_a else "일부 영역"
    for item in result.status_strip:
        m = (sm.get(item.key) or {}).get(item.value)
        item.meaning = fix_particles(str(m).replace("{confirming}", conf_txt)) if m else str(sm.get("missing", "데이터 없음")) if item.value == "–" else ""
    sub_map = {"STRONG": "FUNDAMENTALS CONFIRMED", "PARTIAL": "FUNDAMENTALS RESILIENT", "WEAK": "FUNDAMENTALS WEAK", "UNCONFIRMED": "FUNDAMENTALS UNCONFIRMED"}
    result.regime_subtitle = f"{result.regime_label} / {sub_map[level]}"
    lead_txt = " · ".join(lab[k] for k in leadership) if leadership else "없음"
    lag_txt = " · ".join(lab[k] for k in lagging) if lagging else "없음"
    result.summary = ((f"AI 수요와 인프라 펀더멘털은 {'유지되고 있으나' if level in ('STRONG', 'PARTIAL') else '확인되지 않고'} "
                       + ("금리·위험회피 환경이 가격을 압박하고 있다. " if macro_lbl == "HEADWIND" else "가격은 " + {"STRONG": "이를 확인한다. ", "FLAT": "아직 확인하지 않는다. ", "WEAK": "약하다. ", "–": "계열이 없다. "}[price_lbl]))
                      + f"현재 리더십(1주 상대)은 {lead_txt} 에 있고, {lag_txt} 는 뒤처진다. "
                      + (f"Software 와 범용 메모리로의 확산은 {'확인된다' if sw_lbl == 'STRONG' and any(r.status == 'IMPROVING' for r in memory_rows if not r.structural) else '아직 제한적이다'}."))
    # AI REGIME READ — 2~3문장 (config regime_read). 상태 띠의 값만 조합한다
    rr = cfg.get("regime_read", {}) or {}
    mk = "strong" if price_lbl == "STRONG" and br_lbl != "NARROWING" else "weak" if price_lbl == "WEAK" or br_lbl == "NARROWING" else "mixed"
    s1 = str((rr.get("fund") or {}).get(level, "")) + str((rr.get("market") or {}).get(mk, ""))
    lead2 = [lab[k] for k in leadership[:2]]
    s2 = (str(rr.get("leaders", "")).format(leaders=" · ".join(lead2)) if lead2 else str(rr.get("no_leaders", ""))) + str((rr.get("macro") or {}).get(macro_lbl, ""))
    result.regime_read = fix_particles(" ".join(x for x in (s1, s2) if x).strip())
