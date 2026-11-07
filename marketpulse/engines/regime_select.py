"""
MARKET REGIME v2 — 주식 투자자 관점의 regime 선택 (2026-11-04).

    RAW DATA → FACTORS(market_state) → REGIME CANDIDATES(require = 자격) → US / KOREA EQUITY CONFIRMATION
    → CROSS-ASSET · HISTORY · DATA QUALITY → LLM 선택(자격 있는 후보 또는 NEUTRAL 중에서) → 2거래일 persistence(history) → OFFICIAL

이 모듈은 factor · 원천 데이터를 바꾸지 않는다. market_state 가 이미 계산한 factor 와 require/support 판정을 그대로 읽고,
(1) 자격 있는 후보를 모두 모으고 (2) 후보마다 미국 · 한국 · Global 주식 확인을 계산하고 (3) 데이터 없음은 EXCLUDED 로 분모에서 빼고
(4) LLM 이 고를 수 있게 컨텍스트를 만들고 출력을 검증한다. LLM 이 없거나 검증을 통과하지 못하면 같은 증거로 정량 선택을 한다 —
고정 우선순위가 아니라 후보별 정량 confidence 비교다. 어떤 실패도 예외로 새지 않는다(정량 화면은 그대로).
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

import yaml

from ..config.settings import CONFIG_DIR
from ..models.regime_select import (AlternativeCandidate, EquityConfirmation, EquitySignalRead, MarketConfirmation, RegimeCandidate,
                                    RegimeSelection, SupportRead)

logger = logging.getLogger(__name__)

LABELS = ("RISK_ON", "RISK_OFF", "LIQUIDITY_STRESS", "INFLATION_SHOCK", "GROWTH_SHOCK", "GEOPOLITICAL_RISK", "POLICY_DRIVEN")
STATUS_ORDER = {"CONTRADICTED": 0, "MIXED": 1, "PARTIAL": 1, "CONFIRMED": 2, "STRONG": 3, "UNAVAILABLE": -1}
BANNED = ("확률", "매수", "매도", "전망")


@lru_cache(maxsize=4)
def _load(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def load_config(config_dir: Path | None = None) -> dict:
    return _load(str((config_dir or CONFIG_DIR) / "regime_select.yaml"))


def display(label: str, cfg: Mapping | None = None) -> str:
    d = (cfg or load_config()).get("display", {}).get(label) or {}
    return str(d.get("en") or label)


# ── 주식 입력 ────────────────────────────────────────────
def kr_stock_features(investment: Any, universe: Any | None = None) -> dict[str, dict]:
    """Investment 의 한국 대표 종목(.KS/.KQ) → {id: {z_1d, z_5d, ret_1d, sector}}. 값이 없는 종목은 넣지 않는다(EXCLUDED)."""
    if investment is None:
        return {}
    raw = investment.model_dump(mode="json") if hasattr(investment, "model_dump") else dict(investment)
    if universe is None:
        from ..config.registry import get_universe
        universe = get_universe()
    meta = {s.id: s for s in getattr(universe, "stocks", [])}
    out: dict[str, dict] = {}
    for sid, st in (raw.get("stocks") or {}).items():
        m = meta.get(sid)
        if m is None or not str(getattr(m, "symbol", "")).upper().endswith((".KS", ".KQ")):
            continue
        p = ((st or {}).get("feature") or {}).get("price") or {}
        if p.get("z_1d") is None or p.get("ret_1d") is None:
            continue
        out[sid] = {"z_1d": float(p["z_1d"]), "z_5d": None if p.get("z_5d") is None else float(p["z_5d"]), "ret_1d": float(p["ret_1d"]), "sector": str(getattr(m, "sector", ""))}
    return out


class EquityInputs:
    """주식 확인에 쓰는 값 — market.z(id, '1d'/'5d') 와 한국 대표 종목 특징. 테스트는 dict 로 바로 넣는다."""

    def __init__(self, z1: Mapping[str, float | None], z5: Mapping[str, float | None] | None = None, kr_stocks: Mapping[str, Mapping] | None = None,
                 levels: Mapping[str, float | None] | None = None):
        self.z1 = dict(z1); self.z5 = dict(z5 or {}); self.kr = dict(kr_stocks or {}); self.levels = dict(levels or {})

    @classmethod
    def from_market(cls, market: Any, kr_stocks: Mapping[str, Mapping] | None = None) -> "EquityInputs":
        ids = list(getattr(market, "features", {}).keys())
        return cls({i: market.z(i, "1d") for i in ids}, {i: market.z(i, "5d") for i in ids}, kr_stocks)


def _blend(inp: EquityInputs, iid: str, b: float) -> float | None:
    z1 = inp.z1.get(iid)
    if z1 is None:
        return None
    z5 = inp.z5.get(iid)
    return z1 if z5 is None else (1 - b) * z1 + b * z5


def _basket_members(name: str, cfg: Mapping, kr: Mapping[str, Mapping]) -> list[str]:
    secs = (cfg.get("kr_baskets") or {}).get(name) or []
    fixed = cfg.get("kr_basket_members") or {}
    ids: list[str] = []
    for s in secs:
        if s in fixed:
            ids += [i for i in fixed[s] if i in kr]
        else:
            ids += [i for i, v in kr.items() if v.get("sector") == s]
    return ids


def _signal_value(spec: Mapping, inp: EquityInputs, cfg: Mapping) -> tuple[float | None, str, str]:
    """(값, state, note). 값 None = EXCLUDED."""
    b = float(cfg.get("blend_5d", 0.3)); kind = spec["kind"]
    if kind == "abs":
        v = _blend(inp, spec["id"], b)
        return v, "AVAILABLE" if v is not None else "EXCLUDED", "" if v is not None else f"{spec['id']} 데이터 없음"
    if kind == "rel":
        a, c = _blend(inp, spec["id"], b), _blend(inp, spec["base"], b)
        if a is None or c is None:
            return None, "EXCLUDED", f"{spec['id'] if a is None else spec['base']} 데이터 없음"
        return a - c, "AVAILABLE", ""
    kospi = inp.z1.get("KOSPI")
    if kind == "basket_rel":
        mem = [i for n in spec["baskets"] for i in _basket_members(n, cfg, inp.kr)]
        if not mem or kospi is None:
            return None, "EXCLUDED", "대표 종목 · KOSPI 데이터 없음"
        z = sum(inp.kr[i]["z_1d"] for i in mem) / len(mem)
        return z - kospi, "PARTIAL", f"대표 종목 {len(mem)}개 평균(업종 지수 아님)"
    if kind == "breadth":
        rs = [v["ret_1d"] for v in inp.kr.values()]
        if len(rs) < 10:
            return None, "EXCLUDED", "대표 종목이 10개 미만"
        return sum(1 for r in rs if r > 0) / len(rs), "PARTIAL", f"대표 종목 {len(rs)}개 중 상승 비율(시장 전체 breadth 아님)"
    if kind == "broad":
        zs = [v["z_1d"] for v in inp.kr.values()]
        if len(zs) < 10 or kospi is None:
            return None, "EXCLUDED", "대표 종목 · KOSPI 데이터 없음"
        return median(zs) - kospi, "PARTIAL", "대표 종목 중앙값 − KOSPI(− 면 일부 대형주 쏠림)"
    return None, "EXCLUDED", f"알 수 없는 신호 {kind}"


def _status(score: float | None, cfg: Mapping) -> str:
    s = cfg.get("status") or {}
    if score is None:
        return "UNAVAILABLE"
    if score >= float(s.get("strong", 0.6)):
        return "STRONG"
    if score >= float(s.get("confirmed", 0.25)):
        return "CONFIRMED"
    if score <= float(s.get("contradicted", -0.25)):
        return "CONTRADICTED"
    return "PARTIAL"


def _market(label: str, market: str, inp: EquityInputs, cfg: Mapping, flip: int = 1) -> MarketConfirmation:
    specs = (((cfg.get("equity_signals") or {}).get(label) or {}).get(market)) or []
    scale = float(cfg.get("signal_scale", 1.5)); bscale = float(cfg.get("breadth_scale", 0.25))
    reads: list[EquitySignalRead] = []; wsum = wall = 0.0; acc = 0.0
    for sp in specs:
        w = float(sp.get("weight", 1.0)); wall += w
        sign = int(sp["sign"]) * flip
        v, state, note = _signal_value(sp, inp, cfg)
        sc = None
        if v is not None:
            x = (v - 0.5) / bscale if sp["kind"] == "breadth" else v / scale
            sc = max(-1.0, min(1.0, sign * x)); wsum += w; acc += w * sc
        reads.append(EquitySignalRead(key=sp["key"], label=sp["label"], market=market, value=None if v is None else round(v, 3), expected=sign,  # type: ignore[arg-type]
                                      score=None if sc is None else round(sc, 3), state=state, note=note))  # type: ignore[arg-type]
    cov = wsum / wall if wall else 0.0
    score = acc / wsum if wsum else None
    if cov < float(cfg.get("min_market_coverage", 0.4)):
        score = None
    return MarketConfirmation(status=_status(score, cfg), score=None if score is None else round(score, 3),  # type: ignore[arg-type]
                              available=sum(1 for r in reads if r.score is not None), total=len(reads), coverage=round(cov, 3), signals=reads)


def _global(us: MarketConfirmation, kr: MarketConfirmation, cfg: Mapping) -> MarketConfirmation:
    have = [m for m in (us, kr) if m.score is not None]
    cov = round((us.coverage + kr.coverage) / 2, 3)
    if not have:
        return MarketConfirmation(status="UNAVAILABLE", coverage=cov)
    score = sum(m.score for m in have) / len(have)  # type: ignore[misc]
    st = _status(score, cfg)
    if len(have) == 2:
        hi = {us.status, kr.status}
        if ({"STRONG", "CONFIRMED"} & hi) and "CONTRADICTED" in hi:
            st = "MIXED"
    elif st == "STRONG":
        st = "CONFIRMED"  # 한 시장만으로 Global 을 STRONG 이라 하지 않는다
    return MarketConfirmation(status=st, score=round(score, 3), available=us.available + kr.available, total=us.total + kr.total, coverage=cov)  # type: ignore[arg-type]


def equity_confirmation(label: str, inp: EquityInputs, cfg: Mapping | None = None, *, rates_sign: int = 1) -> EquityConfirmation:
    cfg = cfg or load_config()
    flip = (1 if rates_sign >= 0 else -1) if label == "POLICY_DRIVEN" else 1
    us, kr = _market(label, "us", inp, cfg, flip), _market(label, "kr", inp, cfg, flip)
    return EquityConfirmation(us=us, kr=kr, **{"global": _global(us, kr, cfg)})


# ── 후보 ────────────────────────────────────────────────
_THR = re.compile(r"(>=|<=)\s*([+-]?\d+(?:\.\d+)?)")


def _trigger(rule: Any) -> tuple[str, float | None, float | None, float | None]:
    expr = str(rule.expression); obs = rule.observed
    m = _THR.search(expr)
    if not m or obs is None:
        return expr, obs, None, None
    thr = float(m.group(2)); op = m.group(1)
    margin = (obs - thr) if op == ">=" else (thr - obs)
    return expr, float(obs), thr, float(margin)


def build_candidates(ms: Any, market: Any, instruments_by_id: Mapping[str, Any], inp: EquityInputs, cfg: Mapping | None = None) -> tuple[list[RegimeCandidate], list[dict]]:
    """require 를 모두 통과한 가설 = 후보. 둘째 값은 후보가 아닌 regime 의 trigger 근접도(NEUTRAL 판단용)."""
    from .confirmation import evaluate_confirmation
    from .market_state import _parsed_rules
    cfg = cfg or load_config()
    rules = _parsed_rules()
    rates = ms.factors.get("Rates").score if ms.factors.get("Rates") is not None else 0.0
    qc = cfg.get("quant_confidence") or {}
    cands: list[RegimeCandidate] = []; near: list[dict] = []
    for h in ms.hypotheses:
        lab = h.label.value if hasattr(h.label, "value") else str(h.label)
        if lab not in LABELS:
            continue
        req = [r for r in h.matched_rules if r.kind == "require"]
        sup = [r for r in h.matched_rules if r.kind == "support"]
        ok = bool(req) and all(r.passed and r.evaluable for r in req)
        expr, obs, thr, margin = _trigger(req[0]) if req else ("", None, None, None)
        if not ok:
            if thr is not None and obs is not None:
                prox = max(0.0, 1.0 - max(0.0, -(margin or 0.0)) / max(abs(thr), 1e-6))
                near.append({"label": lab, "trigger": expr, "value": round(obs, 3), "threshold": thr, "proximity": round(prox, 3)})
            continue
        supports = [SupportRead(id=r.rule_id, expr=r.expression, passed=(r.passed if r.evaluable else None), observed=r.observed) for r in sup]
        ev = [(r, float(r.weight or 1.0)) for r in sup if r.evaluable]
        ratio = (sum(w for r, w in ev if r.passed) / sum(w for _, w in ev)) if ev else None
        expected = rules.get(lab, {}).get("expected_response") or {}
        ca = evaluate_confirmation(expected, market, instruments_by_id).score if expected else None
        eq = equity_confirmation(lab, inp, cfg, rates_sign=1 if rates >= 0 else -1)
        cands.append(RegimeCandidate(label=lab, display=display(lab, cfg), trigger_expr=expr, trigger_value=None if obs is None else round(obs, 3), trigger_threshold=thr,
                                     trigger_margin=None if margin is None else round(margin, 3), support=supports, support_ratio=None if ratio is None else round(ratio, 3),
                                     cross_asset=None if ca is None else round(float(ca), 3), equity=eq, quant_confidence=0.0,
                                     interpretation=str((cfg.get("interpretation") or {}).get(lab, ""))))
    # 정량 confidence — coverage 는 넣지 않는다(따로 보인다). 없는 항목은 가중치 재정규화
    w = dict(qc.get("weights") or {}); full = float(qc.get("trigger_full_margin", 1.0))
    def base(c: RegimeCandidate) -> dict[str, float | None]:
        g = c.equity.global_.score
        return {"trigger": None if c.trigger_margin is None else max(0.0, min(1.0, c.trigger_margin / full)), "support": c.support_ratio,
                "equity": None if g is None else (g + 1) / 2, "cross_asset": None if c.cross_asset is None else (c.cross_asset + 1) / 2}
    def avg(parts: Mapping[str, float | None]) -> float:
        have = {k: v for k, v in parts.items() if v is not None and k in w}
        tw = sum(w[k] for k in have)
        return 100.0 * sum(w[k] * v for k, v in have.items()) / tw if tw else 0.0
    pre = [avg(base(c)) for c in cands]
    for i, c in enumerate(cands):
        others = [p for j, p in enumerate(pre) if j != i]
        parts = base(c)
        parts["separation"] = None if not others else max(0.0, min(1.0, (pre[i] - max(others)) / 30.0))
        cands[i] = c.model_copy(update={"quant_confidence": round(avg(parts), 1)})
    cands.sort(key=lambda c: -c.quant_confidence)
    return cands, sorted(near, key=lambda x: -x["proximity"])


# ── 선택 · 검증 ─────────────────────────────────────────
def _norm_label(x: Any) -> str:
    s = str(x or "").strip().upper().replace("-", "_").replace(" ", "_").replace("/", "_")
    s = re.sub(r"_+", "_", s).strip("_")
    if s in ("NEUTRAL", "NEUTRAL_MIXED", "NO_REGIME", "MIXED"):
        return "NEUTRAL"
    return s


def quant_select(ctx: Mapping) -> dict:
    """LLM 이 없을 때 — 후보별 정량 confidence 비교(고정 우선순위 없음). 약하거나 주식이 반박하면 NEUTRAL / MIXED."""
    cfg = load_config(); qc = cfg.get("quant_confidence") or {}
    cands = ctx["candidates"]
    floor = float(qc.get("neutral_floor", 40))
    if not cands:
        near = max([n["proximity"] for n in ctx.get("near_triggers") or []] or [0.0])
        conf = int(round(max(floor, 100 * (1 - near))))
        return {"selected_regime": "NEUTRAL", "regime_confidence": conf, "selection_status": "NO_ELIGIBLE",
                "primary_reason": "어느 regime 도 주요 Trigger 를 넘지 않았다.", "alternative_candidates": []}
    top = cands[0]
    weak = top["quant_confidence"] < float(qc.get("min_select", 45)) or top["equity"]["global"]["status"] == "CONTRADICTED"
    alts = [{"regime": c["label"], "reason": f"정량 confidence {c['quant_confidence']:.0f} 로 1등보다 낮다"} for c in cands[1:]]
    if weak:
        return {"selected_regime": "NEUTRAL", "regime_confidence": int(round(max(floor, 100 - top["quant_confidence"]))), "selection_status": "LOW_CONFIDENCE",
                "primary_reason": f"{top['display']} 가 자격은 있지만 주식 확인이 약해 하나의 환경으로 정하기 어렵다.",
                "alternative_candidates": [{"regime": top["label"], "reason": "자격은 있지만 확인이 약하다"}] + alts}
    return {"selected_regime": top["label"], "regime_confidence": int(round(top["quant_confidence"])), "selection_status": "CONFIRMED" if top["quant_confidence"] >= 65 else "TENTATIVE",
            "primary_reason": f"{top['display']} 의 주요 Trigger 와 주식 확인이 후보 중 가장 강하다.", "alternative_candidates": alts}


def check_output(out: Mapping, ctx: Mapping) -> list[str]:
    """LLM(또는 세션) 출력 검증 — 자격 없는 regime 금지 · 필드 · 범위 · 금지어 · 문장 수."""
    probs: list[str] = []
    eligible = {c["label"] for c in ctx["candidates"]} | {"NEUTRAL"}
    for k in ("selected_regime", "regime_confidence", "selection_status", "primary_reason", "alternative_candidates", "us_equity_confirmation",
              "korea_equity_confirmation", "global_equity_confirmation", "persistence_assessment", "data_coverage", "selection_rationale", "commentary"):
        if k not in out:
            probs.append(f"필드 없음: {k}")
    if probs:
        return probs
    sel = _norm_label(out["selected_regime"])
    if sel not in eligible:
        probs.append(f"자격 없는 regime 선택: {out['selected_regime']} (가능: {sorted(eligible)})")
    try:
        c = int(out["regime_confidence"])
        if not 0 <= c <= 100:
            probs.append("regime_confidence 범위 밖")
    except Exception:
        probs.append("regime_confidence 가 정수가 아님")
    if out["selection_status"] not in ("CONFIRMED", "TENTATIVE", "LOW_CONFIDENCE", "NO_ELIGIBLE"):
        probs.append("selection_status 값")
    for a in out.get("alternative_candidates") or []:
        r = _norm_label((a or {}).get("regime"))
        if r not in eligible or r == sel:
            probs.append(f"대안 후보가 자격 목록 밖이거나 선택과 같다: {(a or {}).get('regime')}")
    text = " ".join(str(out.get(k) or "") for k in ("primary_reason", "selection_rationale", "commentary", "persistence_assessment"))
    for b in BANNED:
        if b in text:
            probs.append(f"금지어: {b}")
    n = len([s for s in re.split(r"(?<=[.다요])\s+", str(out.get("commentary") or "").strip()) if s])
    if not 2 <= n <= 4:
        probs.append(f"commentary 는 2~4문장(지금 {n})")
    return probs


def _ctx_status(ctx: Mapping, sel: str) -> tuple[str, str, str]:
    if sel == "NEUTRAL":
        eq = ctx.get("neutral_reference_equity") or {}
    else:
        eq = next((c["equity"] for c in ctx["candidates"] if c["label"] == sel), {})
    g = lambda k: str(((eq.get(k) or {}).get("status")) or "UNAVAILABLE")
    return g("us"), g("kr"), g("global")


def finalize(out: Mapping, ctx: Mapping, *, source: str, status: str = "ok", reason: str = "", warnings: Sequence[str] = ()) -> RegimeSelection:
    """출력 → RegimeSelection. 주식 확인 상태 · coverage 는 엔진 값으로 맞춘다(LLM 이 다르게 쓰면 경고로 남기고 엔진 값)."""
    sel = _norm_label(out["selected_regime"])
    us, kr, gl = _ctx_status(ctx, sel)
    warns = list(warnings)
    for k, v in (("us_equity_confirmation", us), ("korea_equity_confirmation", kr), ("global_equity_confirmation", gl)):
        if out.get(k) and str(out[k]).upper() != v:
            warns.append(f"{k}: 출력 {out[k]} → 엔진 계산 {v}")
    cand_models = [RegimeCandidate.model_validate(c) for c in ctx["candidates"]]
    neutral_eq = EquityConfirmation.model_validate(ctx["neutral_reference_equity"]) if ctx.get("neutral_reference_equity") else None
    return RegimeSelection(
        selected_regime=sel, regime_confidence=int(out["regime_confidence"]), selection_status=out.get("selection_status") or "TENTATIVE",
        primary_reason=str(out.get("primary_reason") or ""), alternative_candidates=[AlternativeCandidate(regime=_norm_label(a["regime"]), reason=str(a.get("reason") or "")) for a in out.get("alternative_candidates") or []],
        us_equity_confirmation=us, korea_equity_confirmation=kr, global_equity_confirmation=gl,  # type: ignore[arg-type]
        persistence_assessment=str(out.get("persistence_assessment") or ctx.get("persistence_hint") or ""), data_coverage=int(ctx["data_coverage"]),
        selection_rationale=str(out.get("selection_rationale") or ""), commentary=str(out.get("commentary") or ""), source=source, status=status, reason=reason,  # type: ignore[arg-type]
        quant_label=str(ctx.get("quant_label") or "NEUTRAL"), candidates=cand_models, neutral_equity=neutral_eq, primary_signal=str(ctx.get("primary_signal") or ""),
        coverage_detail=dict(ctx.get("coverage") or {}), excluded=list(ctx.get("excluded") or []), warnings=warns)


def quant_commentary(sel: Mapping, ctx: Mapping) -> str:
    """LLM 이 없을 때의 WHY — 고정 목록이 아니라 그날 값으로 만든 2문장(출처: 정량)."""
    lab = sel["selected_regime"]
    if lab == "NEUTRAL":
        n = (ctx.get("near_triggers") or [{}])[0] if ctx.get("near_triggers") else {}
        first = "어느 regime 도 주요 Trigger 를 넘지 않았다" + (f" — 가장 가까운 것은 {display(n['label'])}({n['trigger']}, 지금 {n['value']:+.2f})" if n else "") + "."
    else:
        c = next(x for x in ctx["candidates"] if x["label"] == lab)
        first = f"{c['display']} 의 주요 Trigger({c['trigger_expr']}, 지금 {c['trigger_value']:+.2f})를 넘었다."
    us, kr, gl = _ctx_status(ctx, lab)
    return f"{first} 주식 확인은 미국 {us} · 한국 {kr} · Global {gl} 이다."


# ── 컨텍스트 · 전체 흐름 ─────────────────────────────────
def build_context(ms: Any, market: Any, instruments_by_id: Mapping[str, Any], inp: EquityInputs, *, history_rows: Sequence[Mapping] = (),
                  official: str | None = None, events: Sequence[Mapping] = (), news: Sequence[Mapping] = (), as_of: str = "") -> dict:
    cfg = load_config()
    cands, near = build_candidates(ms, market, instruments_by_id, inp, cfg)
    neutral_eq = equity_confirmation("RISK_ON", inp, cfg)
    fac = {k: round(v.score, 2) for k, v in ms.factors.items() if v is not None and v.score is not None}
    excluded = sorted({s.label for c in cands for m in (c.equity.us, c.equity.kr) for s in m.signals if s.state == "EXCLUDED"}
                      | {s.label for m in (neutral_eq.us, neutral_eq.kr) for s in m.signals if s.state == "EXCLUDED"})
    fcov = getattr(market, "coverage", 1.0)
    ref = cands[0].equity if cands else neutral_eq
    coverage = {"factor": round(float(fcov), 3), "us": ref.us.coverage, "kr": ref.kr.coverage, "global": ref.global_.coverage}
    data_cov = int(round(100 * (0.5 * coverage["factor"] + 0.5 * coverage["global"])))
    keys = ["SPX", "NDX", "RUT", "SOXX", "KOSPI", "KOSDAQ", "VIX", "MOVE", "US_HY_OAS", "US10Y", "US2Y", "BE10Y", "BRENT", "GOLD", "DXY", "USDKRW", "XLF", "XLU", "XLE", "ITA", "JETS"]
    moves = {k: (None if inp.z1.get(k) is None else round(inp.z1[k], 2)) for k in keys}
    top = cands[0] if cands else None
    prim = (f"{top.trigger_expr.split(' ')[0]} {top.trigger_value:+.2f}" if top and top.trigger_value is not None
            else (f"{near[0]['trigger'].split(' ')[0]} {near[0]['value']:+.2f}" if near else ""))
    hist = list(history_rows)[-10:]
    last_raw = [r.get("raw_state") for r in hist]
    persistence_hint = (f"공식 {official} · 직전 raw {last_raw[-1] if last_raw else '없음'} · 공식 전환은 같은 raw 가 서로 다른 거래일 2일 연속(또는 확신 80 이상)일 때")
    ql = ms.primary_label.value if hasattr(ms.primary_label, "value") else str(ms.primary_label)
    return {
        "as_of": as_of, "purpose": "현재 미국과 한국을 포함한 주식시장이 어떤 환경에 놓여 있는가",
        "factors": fac, "candidates": [c.model_dump(mode="json", by_alias=True) for c in cands], "near_triggers": near,
        "neutral_reference_equity": neutral_eq.model_dump(mode="json", by_alias=True), "market_moves_z1d": moves,
        "kr_breadth_proxy": next((s.model_dump(mode="json") for s in neutral_eq.kr.signals if s.key == "breadth_kr"), None),
        "history": hist, "official_regime": official, "persistence_hint": persistence_hint,
        "events": list(events)[:8], "news": list(news)[:10], "coverage": coverage, "data_coverage": data_cov, "excluded": excluded,
        "quant_label": ql, "primary_signal": prim,
        "rules": {"eligibility": "state_rules.yaml require — LLM 은 candidates 의 label 또는 NEUTRAL 만 고른다",
                  "missing": "EXCLUDED 신호는 증거가 아니다(부정 · 중립 · 미확인 아님) — coverage 로만"},
    }


SCHEMA: dict = {
    "type": "object",
    "properties": {
        "selected_regime": {"type": "string", "description": "candidates 의 label 중 하나 또는 NEUTRAL"},
        "regime_confidence": {"type": "integer", "minimum": 0, "maximum": 100},
        "selection_status": {"type": "string", "enum": ["CONFIRMED", "TENTATIVE", "LOW_CONFIDENCE", "NO_ELIGIBLE"]},
        "primary_reason": {"type": "string"},
        "alternative_candidates": {"type": "array", "items": {"type": "object", "properties": {"regime": {"type": "string"}, "reason": {"type": "string"}}, "required": ["regime", "reason"], "additionalProperties": False}},
        "us_equity_confirmation": {"type": "string"}, "korea_equity_confirmation": {"type": "string"}, "global_equity_confirmation": {"type": "string"},
        "persistence_assessment": {"type": "string"}, "data_coverage": {"type": "integer"},
        "selection_rationale": {"type": "string"},
        "commentary": {"type": "string", "description": "화면 WHY — 한국어 2~4문장, 선택과 모순되지 않게, 미국 · 한국 차이가 있으면 말한다"},
    },
    "required": ["selected_regime", "regime_confidence", "selection_status", "primary_reason", "alternative_candidates", "us_equity_confirmation",
                 "korea_equity_confirmation", "global_equity_confirmation", "persistence_assessment", "data_coverage", "selection_rationale", "commentary"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """당신은 미국과 한국 주식을 함께 운용하는 포트폴리오 매니저다. 대시보드의 MARKET REGIME 을 고른다.
목적은 '거시 변수 자체의 상태' 가 아니라 '지금 주식시장이 어떤 환경에 놓여 있는가' 다.

[선택 규칙]
1. candidates 에 있는 label(주요 Trigger 를 넘은 regime) 또는 NEUTRAL 중에서만 고른다. 없는 regime 을 만들지 않는다.
2. 후보가 여럿이면 고정 우선순위를 쓰지 않는다 — Trigger 강도, 보조 확인, 미국 · 한국 · Global 주식 확인, cross-asset, history 를 함께 읽고
   지금 주식시장을 가장 잘 설명하는 것을 고른다.
3. 한 시장(미국 또는 한국)만으로 Global 상태를 단정하지 않는다. 미국과 한국이 엇갈리면 그 차이를 confidence 와 설명에 반영한다.
4. Macro 와 주식이 충돌하면(예: 물가 Trigger 인데 성장주 · breadth 가 강함) confidence 를 낮추고 그 충돌을 말한다.
5. EXCLUDED(데이터 없음) 신호는 증거로 쓰지 않는다 — 부정 · 중립 · 미확인으로 보지 않는다. 데이터 부족은 data_coverage 로만.
6. Trigger 가 간신히 넘었고 주식 확인 · cross-asset 이 약하고 후보 간 차이가 작으면 NEUTRAL 을 고를 수 있다.
7. 공식 regime 은 2거래일 persistence 로 history 가 정한다. 당신은 오늘의 후보를 고른다 — 공식과 다르면 persistence_assessment 에 '전환 후보' 로 쓴다.
8. regime_confidence 는 '그 선택이 얼마나 확실한가' 다. Trigger 를 넘었다는 이유만으로 높이지 않는다.
9. 주어진 컨텍스트만 근거로 쓴다. 매수 · 매도 · 확률 · 전망 같은 말을 쓰지 않는다.

[출력]
- us/korea/global_equity_confirmation 은 고른 후보의 equity 상태를 그대로(후보가 NEUTRAL 이면 neutral_reference_equity).
- data_coverage 는 컨텍스트 data_coverage 를 그대로.
- commentary: 한국어 2~4문장. 왜 이 regime 이 지금 미국과 한국을 포함한 주식시장을 가장 잘 설명하는지. 숫자는 1~3개만, 컨텍스트 값 그대로."""


def _user(ctx: Mapping, previous: str | None = None, problems: Sequence[str] = ()) -> str:
    msg = "아래는 지금 시점의 컨텍스트(JSON)다. 이것만 근거로 regime 을 고르고 설명하라.\n\n" + json.dumps(ctx, ensure_ascii=False)
    if previous is not None:
        msg += "\n\n이전 답안이 검증을 통과하지 못했다. 고쳐서 다시 답하라.\n이전 답안: " + previous + "\n문제: " + " / ".join(problems)
    return msg


def select_regime(ctx: Mapping, *, client: Any = None, session_read: Mapping | None = None) -> RegimeSelection:
    """API → 세션 생성본(같은 컨텍스트 · 프롬프트 · 검증) → 정량 선택. 어떤 실패도 예외로 새지 않는다."""
    cfg = (load_config().get("llm") or {})
    warnings: list[str] = []
    reason = "LLM 비활성 — 키 없음 또는 설정 off"
    if client is not None and getattr(client, "enabled", False):
        try:
            from ..ai.client import LLMFailure
            previous: str | None = None; problems: list[str] = []
            for attempt in range(1 + int(cfg.get("retries_on_invalid", 1))):
                res = client.interpret(system=SYSTEM_PROMPT, user=_user(ctx, previous, problems), schema=SCHEMA, effort=str(cfg.get("effort", "high")),
                                       max_tokens=int(cfg.get("max_tokens", 16000)), timeout_sec=float(cfg.get("timeout_sec", 150)))
                if isinstance(res, LLMFailure):
                    reason = f"LLM 호출 실패({getattr(res, 'kind', 'error')})"
                    break
                problems = check_output(res, ctx)
                if not problems:
                    return finalize(res, ctx, source="llm", warnings=warnings)
                warnings.append(f"검증 {attempt + 1}회차: " + " / ".join(problems)); previous = json.dumps(res, ensure_ascii=False)
                reason = "LLM 출력이 검증을 통과하지 못했다"
        except Exception as e:  # noqa: BLE001
            logger.exception("regime 선택 LLM 실패")
            reason = f"LLM 오류: {type(e).__name__}"
    if session_read:
        try:
            problems = check_output(session_read, ctx)
            if not problems:
                return finalize(session_read, ctx, source="session", reason=reason, warnings=warnings)
            warnings.append("세션 생성본 검증 실패: " + " / ".join(problems))
        except Exception as e:  # noqa: BLE001
            warnings.append(f"세션 생성본 오류: {type(e).__name__}")
    q = quant_select(ctx)
    us, kr, gl = _ctx_status(ctx, q["selected_regime"])
    out = {**q, "us_equity_confirmation": us, "korea_equity_confirmation": kr, "global_equity_confirmation": gl,
           "persistence_assessment": ctx.get("persistence_hint", ""), "data_coverage": ctx["data_coverage"],
           "selection_rationale": q["primary_reason"], "commentary": quant_commentary(q, ctx)}
    return finalize(out, ctx, source="quant", status="fallback", reason=reason, warnings=warnings)


def apply_selection(ms: Any, sel: RegimeSelection) -> Any:
    """market_state 에 선택을 반영 — primary_label = 선택(history 의 raw 가 된다), confidence = regime_confidence. 정량 1등은 sel.quant_label 에 남는다."""
    from ..models.state import StateLabel
    return ms.model_copy(update={"primary_label": StateLabel(sel.selected_regime), "confidence": float(sel.regime_confidence), "selection": sel,
                                 "secondary_label": None if sel.selected_regime == "NEUTRAL" else ms.secondary_label})
