"""
AI CHAIN VIEW (2026-10-01) — AI FUNDAMENTAL TRANSMISSION · VALUE-CHAIN LEADERSHIP · SEMICONDUCTOR CONFIRMATION 을
하나의 흐름(SNAPSHOT → FUNDAMENTAL × PRICE ALIGNMENT → TRANSMISSION → LEADERSHIP → SEMI CONFIRMATION)으로 다시 말하는 표시 층.

계산은 하나도 새로 하지 않는다. transmission.stages(펀더멘털 전파 점수·상태), value_chain.segments(1주 상대·breadth·순위·역할),
semi_confirmation.areas(화살표·상태), expectation_gap(세그먼트 펀더멘털 0~100), memory rows 를 config/ai_regime.yaml `chain_view` 의
규칙으로 정렬·결합·문장화한다. VIEW(CONFIRMED / DIVERGENCE / FUNDAMENTAL-LED / PRICE-LED / MIXED / WEAK)는 펀더멘털 상태와
가격 상태의 조합 규칙이지 새 점수가 아니다.
"""

from __future__ import annotations

from typing import Mapping

from ..models.ai_regime import AiRegime, ChainRow, ChainSemiArea, ChainSnapshot, ChainStage, ChainView
from .korean import fix_particles


def _price_status(seg, cfg: Mapping) -> str:
    if seg is None or seg.rel_5d is None:
        return "MIXED"
    if seg.role == "leading":
        return "LEADING" if seg.rank_1w == 1 and seg.rel_5d > 0 else "STRONG"
    if seg.role == "lagging":
        return "WEAK" if seg.above_ma20_pct is not None and seg.above_ma20_pct < float(cfg.get("price_weak_breadth", 50)) else "LAGGING"
    return "MIXED"


def _view(fund: str, price: str, cfg: Mapping) -> str:
    fg, fb = fund in cfg.get("fund_good", []), fund in cfg.get("fund_bad", [])
    pg, pb = price in cfg.get("price_good", []), price in cfg.get("price_bad", [])
    if fg and pg:
        return "CONFIRMED"
    if fg and pb:
        return "DIVERGENCE"
    if fg:
        return "FUNDAMENTAL-LED"
    if pg:
        return "PRICE-LED"
    if fb or pb:
        return "WEAK"
    return "MIXED"


def build_chain_view(r: AiRegime, cfg_all: Mapping) -> ChainView:
    cfg = cfg_all.get("chain_view", {}) or {}
    stage_by = {s.key: s for s in r.transmission.stages}; seg_by = {s.key: s for s in r.value_chain.segments}
    gap_by = {g.key: g for g in r.expectation_gap}; views = {k: str(v) for k, v in (cfg.get("views") or {}).items()}
    gb = cfg.get("gap_fund_bands", {}) or {}
    out = ChainView(subtitles={k: str(v) for k, v in (cfg.get("subtitles") or {}).items()}, score_tip=str(cfg.get("score_tip", "")), main_rows=int(cfg.get("main_rows", 6)), views=views,
                    semi_columns=[{"key": str(c["key"]), "label": str(c["label"])} for c in cfg.get("semi_columns", [])])
    # ── FUNDAMENTAL × PRICE ──
    for spec in cfg.get("rows", []):
        seg = seg_by.get(str(spec.get("segment"))); st = stage_by.get(str(spec.get("stage"))) if spec.get("stage") else None
        if st is not None:
            fund, fscore = st.status, st.score
        else:
            g = gap_by.get(str(spec.get("segment"))); fv = None if g is None else g.fundamental
            fund = "UNCONFIRMED" if fv is None else "POSITIVE" if fv >= float(gb.get("positive", 70)) else "DETERIORATING" if fv <= float(gb.get("deteriorating", 40)) else "STABLE"
            fscore = None
        price = _price_status(seg, cfg); view = _view(fund, price, cfg)
        out.rows.append(ChainRow(key=str(spec["key"]), label=str(spec["label"]), segment=str(spec.get("segment")), segment_label=seg.label if seg else str(spec.get("segment")), stage=str(spec["stage"]) if spec.get("stage") else None,
                                 fund_status=fund, fund_score=fscore, price_status=price, rank=seg.rank_1w if seg else None, rel_5d=seg.rel_5d if seg else None, breadth=seg.above_ma20_pct if seg else None, view=view, view_ko=views.get(view, "")))
    order = {"CONFIRMED": 0, "DIVERGENCE": 1, "FUNDAMENTAL-LED": 2, "PRICE-LED": 3, "MIXED": 4, "WEAK": 5}
    out.rows.sort(key=lambda x: (order.get(x.view, 9), x.rank or 99))
    # ── TRANSMISSION 압축 ──
    short = cfg.get("stage_short", {}) or {}
    out.stages = [ChainStage(key=s.key, label=str(short.get(s.key, s.label)), status=s.status, score=s.score, evidence=s.evidence, basis=list(s.basis)) for s in r.transmission.stages]
    rd = cfg.get("read", {}) or {}
    good = [str(short.get(s.key, s.label)) for s in r.transmission.stages if s.status in cfg.get("fund_good", [])]
    mixed = [str(short.get(s.key, s.label)) for s in r.transmission.stages if s.status not in cfg.get("fund_good", []) and s.score is not None]
    out.fundamental_read = fix_particles(str(rd.get("fundamental", "")).format(good=" · ".join(good), mixed=" · ".join(mixed))) if good else str(rd.get("fundamental_none", ""))
    # ── LEADERSHIP — 순위 중심, 상·하위 3 ──
    ranked = sorted([x for x in out.rows if x.rank is not None], key=lambda x: x.rank or 99)
    seen: set[str] = set(); uniq: list[ChainRow] = []
    for x in ranked:
        if x.segment not in seen:
            seen.add(x.segment); uniq.append(x)
    out.leaders, out.laggards = uniq[:3], list(reversed(uniq[-3:])) if len(uniq) > 3 else []
    if uniq:
        out.leadership_read = fix_particles(str(rd.get("leadership", "")).format(top=" / ".join(x.label for x in uniq[:2]), bottom=" / ".join(x.label for x in out.laggards)))
    else:
        out.leadership_read = str(rd.get("leadership_none", ""))
    # ── SEMI CONFIRMATION — 상태 행 + 의미 + HBM 핵심 증거 ──
    cols = [(str(c["key"]), str(c["label"])) for c in cfg.get("semi_columns", [])]; sm = cfg.get("semi_meaning", {}) or {}
    mem_struct = [m for m in r.semi_confirmation.memory if m.structural and m.change_1d is not None]
    for a in r.semi_confirmation.areas:
        arrows = {k: getattr(a, k) for k, _ in cols}
        goods = [lbl for k, lbl in cols if arrows[k] in ("↑↑", "↑")]; bads = [lbl for k, lbl in cols if arrows[k] in ("↓", "↓↓")]
        if all(v == "?" for v in arrows.values()):
            meaning = str(sm.get("none", ""))
        else:
            parts = []
            if goods: parts.append(str(sm.get("confirm", "")).format(good=" · ".join(goods)))
            if bads: parts.append(str(sm.get("weak", "")).format(bad=" · ".join(bads)))
            if arrows.get("eps") == "?": parts.append(str(sm.get("eps_na", "")))
            meaning = " · ".join(p for p in parts if p)
        ev = [f"{m.label} 앵커 {m.change_1d:+.0f}%" for m in mem_struct] if a.key == str(cfg.get("hbm_area", "hbm")) else []
        out.semi_areas.append(ChainSemiArea(key=a.key, label=a.label, status=a.status, meaning=meaning, key_evidence=ev, arrows=arrows))
    # ── SNAPSHOT ──
    fl = cfg.get("fundamentals_label", {}) or {}; fk = cfg.get("fundamentals_ko", {}) or {}
    lvl = r.fundamental_confirmation.level
    confirmed = [x.label for x in out.rows if x.view == "CONFIRMED"]
    semi_top = [f"{a.label} {a.status}" for a in r.semi_confirmation.areas if a.status in ("LEADING", "STRONG")]
    gap_rows = sorted([x for x in out.rows if x.view in ("DIVERGENCE", "FUNDAMENTAL-LED")], key=lambda x: -(x.fund_score if x.fund_score is not None else 0))
    snap = ChainSnapshot(fundamentals=str(fl.get(lvl, lvl)), fundamentals_ko=str(fk.get(lvl, "")), price_leadership=" / ".join(x.label for x in uniq[:2]) if uniq else "–",
                         semi_confirmation=" · ".join(semi_top) if semi_top else "확인 영역 없음",
                         key_gap=str(rd.get("key_gap", "")).format(label=gap_rows[0].label) if gap_rows else str(rd.get("key_gap_none", "")))
    snap.read = fix_particles(str(rd.get("snapshot", "")).format(fund_ko=snap.fundamentals_ko, confirmed=" / ".join(confirmed)) if confirmed else str(rd.get("snapshot_none", "")).format(fund_ko=snap.fundamentals_ko))
    out.snapshot = snap
    return out
