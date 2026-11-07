"""
AI VS MARKET → WHAT IS DRIVING AI? 표시 층 (2026-09-30).

두 카드는 OBSERVATION → ATTRIBUTION 관계다.
  AI VS MARKET      = AI 가 시장과 비교해 얼마나 특이하게 움직이고 있는가 (절대 방향 → 상대 방향 → 그 차이가 평소 범위를 벗어났는가)
  WHAT IS DRIVING AI = 그 특이한 움직임을 어떤 driver 가 설명하고 있는가 (DRIVER VERDICT → driver 카드)

여기서는 새 판정을 만들지 않는다. ai_vs_market 의 수치, drivers 의 evidence score·status·coverage 를 config/ai_regime.yaml
(vs_market · driver_view · driver_verdict) 의 라벨·템플릿으로 다시 말할 뿐이다. evidence score 는 확률·수익률 전망이 아니다.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from ..models.ai_regime import AiRegime, DriverRef, DriverScore, DriverVerdict, PriceCheck
from .korean import fix_particles


def _band(bands: Sequence[Mapping], score: float) -> str:
    for b in bands:
        if score >= float(b.get("min", -100)):
            return str(b.get("label", ""))
    return str(bands[-1].get("label", "")) if bands else ""


def _meaning_key(band: str) -> str:
    return {"STRONG NEGATIVE": "strong_neg", "NEGATIVE": "neg", "NEUTRAL": "neutral", "POSITIVE": "pos", "STRONG POSITIVE": "strong_pos"}.get(band, "neutral")


def _ev_text(e) -> str:
    if e.kind == "news":
        return f"{e.label} {e.value:+.0f}"
    return f"{e.label} {e.value:+.1f}σ{' · 5D' if e.window == 5 else ''}"


# ── AI VS MARKET ──────────────────────────────────────────
def annotate_vs_market(r: AiRegime, cfg: Mapping) -> None:
    vm = cfg.get("vs_market", {}) or {}
    a = r.ai_vs_market
    ab = (vm.get("absolute") or {}).get(a.abs_direction, {}); rl = (vm.get("relative") or {}).get(a.rel_verdict, {})
    a.absolute_trend, a.absolute_ko = str(ab.get("label", "–")), str(ab.get("ko", ""))
    a.absolute_text = "AI Basket 1W –" if a.basket_ret_5d is None else f"AI Basket 1W {a.basket_ret_5d:+.1f}%"
    a.relative_trend, a.relative_ko = str(rl.get("label", "–")), str(rl.get("ko", ""))
    a.relative_text = "vs Nasdaq 100 –" if a.rel_ndx_5d is None else f"vs Nasdaq 100 {a.rel_ndx_5d:+.1f}%p · 1W"
    rz_cfg = vm.get("relative_z", {}) or {}
    rz = a.rel_ndx_z_5d if a.rel_ndx_z_5d is not None else a.rel_ndx_z
    if rz is None:
        a.relative_z_text, a.relative_z_ko = "–", str(rz_cfg.get("missing_ko", ""))
    else:
        a.relative_z_text = f"{rz:+.1f}σ · {'5D' if a.rel_ndx_z_5d is not None else '1D'}"
        d = str(rz_cfg.get("weak" if rz < 0 else "strong", ""))
        key = "extreme_ko" if abs(rz) >= float(rz_cfg.get("extreme", 1.0)) else "notable_ko" if abs(rz) >= float(rz_cfg.get("notable", 0.5)) else "normal_ko"
        a.relative_z_ko = str(rz_cfg.get(key, "")).replace("{dir}", d)
    short = (vm.get("regime_short") or {}).get(r.regime, r.regime_label)
    a.market_read_label = f"{short}{(vm.get('read_add') or {}).get(a.rel_verdict, '')}"
    rd = vm.get("read", {}) or {}
    bro = next((d for d in r.drivers if d.id == "broad_risk_off"), None)
    market = str(rd.get("market_riskoff", "Risk-Off")) if bro is not None and bro.score <= -25 else str(rd.get("market_weak", "약세"))
    stress = next((d for d in r.drivers if d.id == "ai_fundamental_stress"), None)
    stress_txt = str(rd.get("stress_confirmed", "")) if stress is not None and stress.status == "CONFIRMED" else str(rd.get("stress_unconfirmed", ""))
    if a.abs_direction == "down" and a.rel_verdict == "underperform":
        a.market_read = f"{str(rd.get('down_under', '')).format(market=market)} {stress_txt}"
    elif a.abs_direction == "down":
        a.market_read = str(rd.get("down_hold", ""))
    elif a.abs_direction == "up":
        a.market_read = str(rd.get({"outperform": "up_out", "underperform": "up_under"}.get(a.rel_verdict, "up_inline"), ""))
    else:
        a.market_read = str(rd.get("flat", ""))
    rr = vm.get("relative_read", {}) or {}
    if a.rel_ndx_5d is None:
        a.relative_read = str(rr.get("missing", ""))
    else:
        first = str(rr.get("first", "")).format(gap=f"{abs(a.rel_ndx_5d):.1f}", dir="하락" if a.rel_ndx_5d < 0 else "상승")
        up = a.abs_direction == "up"
        key = {"underperform": "under_up" if up else "under_down", "inline": "inline_up" if up else "inline_down", "outperform": "out_up" if up else "out_down"}.get(a.rel_verdict, "")
        a.relative_read = f"{first} {str(rr.get(key, ''))}".strip()
    a.connector, a.connector_ko = str(vm.get("connector", "")), str(vm.get("connector_ko", ""))


# ── driver 카드 표시 층 ──────────────────────────────────
def annotate_drivers(r: AiRegime, cfg: Mapping) -> None:
    dv = cfg.get("driver_view", {}) or {}; bands = list(dv.get("bands", [])); specs = dv.get("drivers", {}) or {}
    pl = dv.get("price_labels", {}) or {}; sm = dv.get("status_meaning", {}) or {}; top_n = int(dv.get("top_evidence", 3))
    a = r.ai_vs_market
    hyper = next((g for g in r.leadership.groups if g.key == "hyperscalers"), None)
    role_ko = {"leader": "리더", "strong": "강세", "neutral": "중립", "lagging": "약세", "laggard": "후미", "unknown": "–"}
    checks = {
        "basket": PriceCheck(label="AI Basket", value=str((pl.get("basket") or {}).get(a.abs_direction, "–"))),
        "relative": PriceCheck(label="AI vs Nasdaq", value=str((pl.get("relative") or {}).get(a.rel_verdict, "–"))),
        "ndx": PriceCheck(label="Nasdaq 100", value=str((pl.get("ndx") or {}).get("down" if (a.ndx_ret_5d or 0) < -0.5 else "up" if (a.ndx_ret_5d or 0) > 0.5 else "flat" if a.ndx_ret_5d is not None else "unknown", "–"))),
    }
    for d in r.drivers:
        spec = specs.get(d.id, {}) or {}
        d.band = _band(bands, d.score)
        d.band_ko = str((spec.get("meaning") or {}).get(_meaning_key(d.band), ""))
        d.why = str(spec.get("why", ""))
        if d.band == "NEUTRAL" and spec.get("why_neutral"):
            d.why = str(spec["why_neutral"])
        elif d.status == "CONFIRMED" and spec.get("why_confirmed"):
            d.why = str(spec["why_confirmed"])
        d.transmission = [str(x) for x in spec.get("transmission", [])]
        d.price_check = [checks[k] for k in spec.get("price_check", []) if k in checks]
        for row in spec.get("extra_rows", []) or []:
            src = str(row.get("source", ""))
            if src == "group_role" and hyper is not None:
                d.price_check.append(PriceCheck(label=str(row.get("label", "")), value=f"{role_ko.get(hyper.role, hyper.role)}{'' if hyper.rel_5d is None else f' ({hyper.rel_5d:+.1f}%p)'}"))
            elif src == "narrative_tone" and r.narrative.news_tone is not None:
                t = r.narrative.news_tone
                d.price_check.append(PriceCheck(label=str(row.get("label", "")), value="일부 긍정" if t >= 5 else "일부 부정" if t <= -5 else "중립"))
            elif src == "fc_level":
                d.price_check.append(PriceCheck(label=str(row.get("label", "")), value=r.fundamental_confirmation.level))
        d.status_ko = str((spec.get("status_ko") or {}).get(d.status, ""))
        d.status_meaning = str(sm.get(d.status, ""))
        d.top_evidence = [_ev_text(e) for e in d.evidence if e.available][:top_n]
        aux = spec.get("aux") or {}
        if aux and d.id == "ai_narrative" and r.narrative.quadrant in aux:
            d.aux_label, d.aux_ko = str(aux[r.narrative.quadrant].get("label", "")), str(aux[r.narrative.quadrant].get("ko", ""))
        elif aux and d.id == "ai_narrative" and r.narrative.quadrant == "price_resilience" and "price_ahead" in aux:
            d.aux_label, d.aux_ko = str(aux["price_ahead"].get("label", "")), str(aux["price_ahead"].get("ko", ""))


# ── DRIVER VERDICT ────────────────────────────────────────
def build_verdict(r: AiRegime, cfg: Mapping) -> DriverVerdict:
    vc = cfg.get("driver_verdict", {}) or {}; dv = cfg.get("driver_view", {}) or {}
    sw = vc.get("status_weight", {}) or {}; min_abs = float(vc.get("min_abs", 10))
    a = r.ai_vs_market
    down = a.abs_direction == "down"; up = a.abs_direction == "up"
    roles = vc.get("roles_down" if not up else "roles_up", {}) or {}
    v = DriverVerdict(method=str(vc.get("method", "")), score_legend={k: str(x) for k, x in (dv.get("score_legend") or {}).items()}, status_meaning={k: str(x) for k, x in (dv.get("status_meaning") or {}).items()})
    v.gap_label = str((vc.get("gap_label") or {}).get(a.rel_verdict, ""))
    v.gap_value = "–" if a.rel_ndx_5d is None else f"{a.rel_ndx_5d:+.1f}%p vs Nasdaq · 1W"
    v.gap_question = str(vc.get("gap_question", "")).format(gap="–" if a.rel_ndx_5d is None else f"{a.rel_ndx_5d:+.1f}")
    def ref(d: DriverScore, role: str) -> DriverRef:
        return DriverRef(id=d.id, label=d.label, score=d.score, status=d.status, role=role, rank_value=round(abs(d.score) * float(sw.get(d.status, 0.5)) * d.coverage, 1))
    # 바스켓 방향과 같은 부호 = 설명 후보(압력 또는 지지), 반대 부호 = 상쇄
    sign = -1 if down else 1 if up else 0
    cands = [d for d in r.drivers if abs(d.score) >= min_abs and (sign == 0 or (d.score < 0) == (sign < 0))]
    ranked = sorted([ref(d, "") for d in cands], key=lambda x: -x.rank_value)
    confirmed = [x for x in ranked if x.status == "CONFIRMED"]
    order = confirmed + [x for x in ranked if x.status != "CONFIRMED"]  # 확인된 driver 를 먼저 — 점수만으로 primary 를 정하지 않는다
    if order and sign != 0:  # 바스켓이 방향을 찍지 않았으면 가격으로 설명력을 확인할 수 없다 — primary 를 두지 않는다
        v.primary = order[0].model_copy(update={"role": str(roles.get("primary", "PRIMARY"))})
    if v.primary is not None and len(order) > 1 and order[1].status == "CONFIRMED":
        v.secondary = order[1].model_copy(update={"role": str(roles.get("secondary", "SECONDARY"))})
    used = {x.id for x in (v.primary, v.secondary) if x}
    v.offset = [ref(d, str(roles.get("offset", "OFFSET"))) for d in r.drivers if abs(d.score) >= min_abs and d.id not in used and sign != 0 and (d.score < 0) != (sign < 0)]
    v.unconfirmed = [ref(d, str(roles.get("unconfirmed", "NOT YET CONFIRMED"))) for d in r.drivers if d.id not in used and d.id not in {x.id for x in v.offset} and d.status != "CONFIRMED" and (abs(d.score) >= min_abs or d.id == "ai_fundamental_stress")]
    # 결론
    ct = vc.get("conclusion", {}) or {}; macro_ids = set(vc.get("macro_drivers", []))
    if v.primary is None or sign == 0:
        v.conclusion = str(ct.get("flat", ""))
        return v
    sec_clause = str(ct.get("secondary_clause", "")).format(secondary=v.secondary.label) if v.secondary else ""
    if down and v.primary.id in macro_ids:
        text = str(ct.get("down_macro", "")).format(primary=v.primary.label, secondary_clause=sec_clause)
    elif down:
        text = str(ct.get("down_specific", "")).format(primary=v.primary.label)
    else:
        text = str(ct.get("up", "")).format(primary=v.primary.label, secondary_clause=sec_clause)
    if v.offset:
        text += str(ct.get("offset", "")).format(offset=" · ".join(x.label for x in v.offset), dir=str(ct.get("dir_down" if down else "dir_up", "")))
    if v.unconfirmed:
        text += str(ct.get("unconfirmed", "")).format(unconfirmed=" · ".join(x.label for x in v.unconfirmed))
    v.conclusion = fix_particles(text)
    return v


def annotate_driver_view(r: AiRegime, cfg: Mapping) -> None:
    annotate_vs_market(r, cfg)
    annotate_drivers(r, cfg)
    r.driver_verdict = build_verdict(r, cfg)
