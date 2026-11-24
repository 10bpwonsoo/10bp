"""
반도체 사이클 탭 CYCLE READ (2026-11-24) — '왜 지금 이 국면으로 판정됐는가' 의 짧은 해설.

MARKET READ(semi_read)와 역할이 다르다:
  CYCLE READ   = 판정의 설명 — 어떤 증거가 국면을 지지하고 어떤 증거가 막는지, 신뢰도가 왜 그 수준인지 (2~3문장 + 지지 · 제약 메모)
  MARKET READ  = 업황의 성격과 시장 해석 (아래 패널, 그대로)

국면 · composite · 신뢰도 · 증거 점수 · 가중치는 정량 엔진(engines/semiconductor_cycle)이 이미 계산했다. 여기서는 아무것도 다시 계산하지 않고
`cycle_read` 필드 하나만 붙인다. 고정 문장 사전은 없다 — API → 세션 생성본(같은 컨텍스트 · 프롬프트 · 검증) → 비움. 어떤 실패도 예외로 새지 않는다.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .rates_read import _phrase_hits, split_sentences
from .semi_read import _NAMES, _r, number_check

logger = logging.getLogger(__name__)

SIDE_MIN = 10.0  # |점수| 가 이 이상이어야 지지 · 제약으로 센다(엔진의 good / bad tone 기준과 같다)

#: 각 증거 점수가 무엇을 재는가 — 엔진 계산식을 그대로 옮긴 설명(컨텍스트로만 쓴다. 화면 문구는 프론트 semiExplain.ts)
FACTOR_WHAT = {
    "memory_pricing": "표준 등급 현물 가격의 1주 · 1개월 · 3개월 변화율을 합친 모멘텀",
    "spot_premium": "현물이 계약가보다 얼마나 높은가(프리미엄 수준). 칩의 EXPANDING / STABLE / COMPRESSING 은 그 방향이다",
    "contract": "최근 공개 계약가의 직전 대비 변화. 공개된 지 오래되면(STALE) 점수를 절반만 반영한다",
    "premium_breadth": "표준 등급 제품 가운데 가격 모멘텀이 플러스인 제품의 비중(절반이면 0)",
    "hbm": "HBM 계약가 앵커(비정기 · 추정)의 직전 대비 변화",
    "export": "한국 반도체 수출 나우캐스트의 전년 대비 증가율과 지난달 대비 가속 · 둔화",
    "eps_revision": "실적 컨센서스 변화 — 공급원이 없어 NO DATA(계산에서 빠진다)",
    "equity": "메모리 3사(SK hynix · Samsung Electronics · Micron) 1개월 주가 수익률의 평균 — 주가의 방향과 크기",
    "supply_news": "감산 · 재고 · 가격 · 증설 기사 감성의 평균",
}
EQUITY_CONFIRM_WHAT = ("Equity Confirm 칩은 주가가 오르는지가 아니라, 메모리 3사의 1개월 주가 방향이 현물 가격 모멘텀(Memory Pricing)의 방향과 같은지를 본다. "
                       "현물과 주가가 함께 내려도 BROAD CONFIRMATION 이다. 주가의 방향과 크기 자체는 Equity 증거 점수다.")
TURNING_WHAT = ("Turning Point 는 현재 국면이 아니라 국면이 바뀔 조짐이다 — 현물 1개월 모멘텀의 부호 전환 · 프리미엄의 1년 평균 통과 · "
                "가격 breadth 변화 가운데 둘 이상이 같은 방향일 때만 켜진다(EARLY TIGHTENING / EARLY SOFTENING).")
CONFIDENCE_WHAT = "신뢰도 = 증거 확보 비율 × 증거 방향의 일치 정도 × 현물 이력 깊이. 증거 확보 비율이 높아도 지지 · 제약 증거가 엇갈리면 신뢰도는 낮다."

_ITEM = {"type": "object", "properties": {"key": {"type": "string"}, "note": {"type": "string"}}, "required": ["key", "note"], "additionalProperties": False}
SCHEMA: dict = {
    "type": "object",
    "properties": {
        "read": {"type": "string", "description": "CYCLE READ — 한국어 2~3문장(…습니다)"},
        "verdict": {"type": "string", "description": "지지와 제약을 합친 결론 한 줄"},
        "support": {"type": "array", "items": _ITEM},
        "constraint": {"type": "array", "items": _ITEM},
    },
    "required": ["read", "verdict", "support", "constraint"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """당신은 메모리 반도체 업황을 보는 섹터 애널리스트다. 반도체 사이클 탭 맨 위, 국면 이름 바로 아래에 놓이는 CYCLE READ 를 쓴다.
목적은 하나다 — 처음 보는 사용자가 '왜 지금 이 국면으로 판정됐는가' 를 30초 안에 이해하게 하는 것.
국면 · composite · 신뢰도 · 증거 점수는 정량 엔진이 이미 계산했다. 당신은 그것을 바꾸지 않고 숫자 사이의 관계를 설명한다.

[쓸 것]
- read: 2~3문장. 어떤 증거가 이 국면을 가장 강하게 지지하는지, 어떤 증거가 반박하거나 막고 있는지, 그래서 왜 더 강한(또는 더 약한) 국면이 아닌지.
  신뢰도와 증거 확보 비율의 차이가 설명에 도움이 되면 그 관계를 한 문장으로 넣는다(데이터는 충분한데 신호가 엇갈린다 / 데이터가 비어 있다 등).
  HBM 은 강한데 범용 메모리 가격은 약한 것처럼 서로 다른 방향의 증거가 함께 있으면 그 조합이 무엇을 뜻하는지 말한다.
- verdict: 지지와 제약을 합친 결론 한 줄(숫자 없이).
- support / constraint: factors 가운데 side 가 support 인 것 · constraint 인 것에서 각각 2~4개(해당 증거가 그보다 적으면 있는 만큼)를 고르고,
  그 증거가 지금 어떤 상태인지 짧은 메모(명사구, 숫자 없이)를 붙인다. key 는 factors 의 key 그대로. side 가 맞지 않는 증거는 넣지 않는다.

[지킬 것]
- path 가 있으면 이 국면에 아래에서 올라왔는지 위에서 내려왔는지를 구분해 쓴다(국면 이름만 보고 '회복' 이라고 단정하지 않는다).
- 컨텍스트의 정의를 따른다. 특히 Equity Confirm 은 '주가가 현물 가격과 같은 방향인가' 이지 주가 강세가 아니다 — 현물과 주가가 함께 내리면
  BROAD CONFIRMATION 이면서 Equity 점수는 낮다. 이것을 긍정 신호로 쓰지 않는다. Turning Point 는 현재 국면이 아니라 변화 조짐이다.
- 이 칸은 판정의 설명이다. 시장 의미 · 투자 해석 · 앞으로의 시나리오는 아래 MARKET READ 의 몫이라 쓰지 않는다.
- 한국어 '…습니다' 평서문. 불릿 · 제목 · 마크다운 · 줄바꿈 없이.
- 숫자는 read 에 많아야 2개, 컨텍스트 값 그대로. 점수를 줄줄이 나열하지 않는다 — 관계를 말한다.
- 매수 · 매도 · 비중 같은 직접 추천, '확률', '전망', 목표가, 미래 가격 예측을 쓰지 않는다. 인과를 단정하지 않는다.
- '모니터링해야', '지켜볼 필요', '향후 추이' 같은 상투 문구를 쓰지 않는다."""


def _side(score: Any) -> str:
    if score is None:
        return "no_data"
    return "support" if float(score) >= SIDE_MIN else "constraint" if float(score) <= -SIDE_MIN else "neutral"


def build_context(cyc: Mapping[str, Any], cfg_regime: Mapping | None = None) -> dict:
    """LLM 에 넘길 사실 전부. 여기 없는 숫자는 CYCLE READ 에 나올 수 없다."""
    reg = cyc.get("regime") or {}
    comps = reg.get("components") or []
    factors = [{"key": c["key"], "label": c["label"], "score": _r(c.get("score"), 0), "weight": c.get("weight"), "side": _side(c.get("score")),
                "what": FACTOR_WHAT.get(c["key"], "")} for c in comps]
    signs = [1 if c["score"] > 5 else -1 if c["score"] < -5 else 0 for c in comps if c.get("score") is not None]
    mem = next((c.get("score") for c in comps if c["key"] == "memory_pricing"), None)
    eq = cyc.get("equity_confirmation") or {}
    tp = cyc.get("turning") or {}
    con = cyc.get("contract") or {}
    hbm = cyc.get("hbm_supply") or {}
    ex = cyc.get("export_nowcast") or {}
    now = ex.get("nowcast") or {}
    ctx = {
        "as_of_utc": str(cyc.get("as_of", ""))[:16],
        "regime": {"state": reg.get("label"), "composite": _r(reg.get("composite"), 0), "confidence": _r(reg.get("confidence"), 0),
                   "evidence_coverage_pct": None if reg.get("coverage") is None else round(float(reg["coverage"]) * 100),
                   "composite_note": "증거 점수(−100~+100)의 가중 평균. 없는 증거는 분모에서 뺀다"},
        "confidence": {"definition": CONFIDENCE_WHAT, "evidence_up": sum(1 for s in signs if s > 0), "evidence_down": sum(1 for s in signs if s < 0),
                       "evidence_flat": sum(1 for s in signs if s == 0), "evidence_missing": [c["label"] for c in comps if c.get("score") is None]},
        "factors": factors,
        "indicators": {c["label"]: c["value"] for c in reg.get("chips") or []},
        "equity_confirm": {"definition": EQUITY_CONFIRM_WHAT, "status": eq.get("status"),
                           "memory_price_direction": None if mem is None else "up" if mem > 0 else "down" if mem < 0 else "flat",
                           "stocks": [{"name": s["label"], "ret_1m_pct": _r(s.get("ret_1m"), 1), "confirmation": s.get("confirmation")} for s in eq.get("stocks") or []]},
        "turning_point": {"definition": TURNING_WHAT, "signal": tp.get("signal"), "softening_evidence": list(tp.get("softening") or []),
                          "tightening_evidence": list(tp.get("tightening") or [])},
        "memory_pricing": [{"product": p["label"], "momentum_state": p.get("momentum_state") or "NO DATA", "chg_1m_pct": _r(p.get("change_1m"))}
                           for p in cyc.get("memory_prices") or [] if p.get("available") and p.get("tier") == "main"],
        "spot_premium": [{"spot": x["spot_label"], "premium_pct": _r(x.get("current")), "direction": x.get("direction"), "proxy": x.get("proxy", False)}
                         for x in cyc.get("spot_premium") or [] if x.get("available")],
        "breadth": {k: (cyc.get("breadth") or {}).get(k) for k in ("state", "positive_momentum")},
        "contract": {"trend": con.get("trend"), "stale": con.get("stale"), "period": next((r["period"][:7] for r in con.get("rows") or []), None),
                     "stale_rule": "공개된 지 오래된 계약가는 점수를 절반만 반영한다 — RISING 판정 자체는 그대로"},
        "hbm": {"pricing": hbm.get("pricing"), "anchors": [{"item": a["label"], "date": a.get("date"), "chg_pct": _r(a.get("change_pct"), 1)} for a in hbm.get("anchors") or [] if a.get("available")]},
        "export": {"latest": ex.get("latest_scope_label"), "latest_yoy_pct": _r(ex.get("latest_yoy"), 1), "nowcast_yoy_mid_pct": _r(now.get("yoy_mid"), 0),
                   "prev_month_yoy_pct": _r(ex.get("prev_month_yoy"), 0), "momentum": ex.get("momentum")},
        "data_quality": [{"item": d["item"], "status": d.get("status"), "last": (d.get("last") or "")[:10]} for d in cyc.get("data_quality") or []
                         if d.get("status") in ("STALE", "UNAVAILABLE")],
    }
    hist = cyc.get("memory_history") or {}
    if hist.get("points"):
        ctx["path"] = {"note": "국면은 composite 구간으로 정한다 — 같은 EARLY RECOVERY 라도 아래에서 올라온 것과 위에서 내려온 것은 다르다",
                       "previous_state": hist.get("previous_label"), "days_in_current_state": hist.get("current_streak"),
                       "composite_change_1w": _r(hist.get("score_change_1w"), 1),
                       "recent": [{"date": p.get("date"), "state": p.get("label"), "composite": _r(p.get("score"), 0)} for p in (hist.get("points") or [])[-5:]]}
    states = (cfg_regime or {}).get("states") or []
    if states:
        ctx["regime"]["thresholds"] = [{"state": s["label"], "composite_min": s["min"]} for s in states if s["min"] > -1000]
    return ctx


def context_text(ctx: Mapping) -> str:
    return json.dumps(ctx, ensure_ascii=False, separators=(",", ":"))


_HAS_NUM = re.compile(r"\d")


def normalize_output(data: Mapping) -> dict:
    clean = lambda s: re.sub(r"\s+", " ", str(s or "")).strip()  # noqa: E731
    items = lambda xs: [{"key": clean((x or {}).get("key")), "note": clean((x or {}).get("note"))} for x in (xs or []) if isinstance(x, Mapping)]  # noqa: E731
    return {"read": clean(data.get("read")), "verdict": clean(data.get("verdict")), "support": items(data.get("support")), "constraint": items(data.get("constraint"))}


def check_output(out: Mapping, ctx: Mapping, cfg: Mapping) -> list[str]:
    v = cfg.get("validate") or {}
    problems: list[str] = []
    text = str(out.get("read") or "")
    if not text:
        return ["read 가 비어 있다"]
    if "\n" in text or re.search(r"^\s*[-*•#]", text):
        problems.append("줄바꿈·불릿·제목 없이 문장으로만 써야 한다")
    n = len(split_sentences(text))
    lo, hi = int(v.get("min_sentences", 2)), int(v.get("max_sentences", 3))
    if not lo <= n <= hi:
        problems.append(f"read 문장 수 {n} — {lo}~{hi}문장이어야 한다")
    if len(text) > int(v.get("max_chars", 280)):
        problems.append(f"read 길이 {len(text)}자 — {v.get('max_chars', 280)}자 이내로")
    problems += _phrase_hits(text, v)
    counted, invented, _rep = number_check(text, ctx)
    if counted > int(v.get("max_numbers", 2)):
        problems.append(f"read 숫자 {counted}개 — {v.get('max_numbers', 2)}개 이내로")
    if invented:
        problems.append(f"컨텍스트에 없는 숫자: {', '.join(invented)}")

    verdict = str(out.get("verdict") or "")
    if not verdict:
        problems.append("verdict 가 비어 있다")
    else:
        if len(split_sentences(verdict)) > 1 or len(verdict) > int(v.get("verdict_max_chars", 60)):
            problems.append(f"verdict 는 한 줄({v.get('verdict_max_chars', 60)}자 이내)")
        if _HAS_NUM.search(_NAMES.sub("§", verdict)):
            problems.append("verdict 에는 숫자를 쓰지 않는다")
        problems += [f"verdict: {p}" for p in _phrase_hits(verdict, v)]

    by_side: dict[str, list[str]] = {"support": [], "constraint": []}
    for f in ctx.get("factors") or []:
        if f.get("side") in by_side:
            by_side[f["side"]].append(f["key"])
    cap = int(v.get("max_items", 4)); floor = int(v.get("min_items", 2)); note_max = int(v.get("note_max_chars", 24))
    for side in ("support", "constraint"):
        rows = list(out.get(side) or [])
        keys = [r.get("key") for r in rows]
        need = min(floor, len(by_side[side]))
        if not need <= len(rows) <= cap:
            problems.append(f"{side} {len(rows)}개 — {need}~{min(cap, max(need, len(by_side[side])))}개여야 한다")
        if len(set(keys)) != len(keys):
            problems.append(f"{side} 에 같은 증거가 두 번 있다")
        for r in rows:
            if r.get("key") not in by_side[side]:
                problems.append(f"{side} 에 넣을 수 없는 증거: {r.get('key')} (가능: {by_side[side]})")
            note = str(r.get("note") or "")
            if not note or len(note) > note_max:
                problems.append(f"{side}.{r.get('key')} 메모는 1~{note_max}자")
            if _HAS_NUM.search(_NAMES.sub("§", note)):
                problems.append(f"{side}.{r.get('key')} 메모에는 숫자를 쓰지 않는다")
            problems += [f"{side}.{r.get('key')}: {p}" for p in _phrase_hits(note, v)]
    return problems


def empty(status: str = "unavailable", reason: str = "", warnings: Sequence[str] = ()) -> dict:
    return {"status": status, "source": "none", "generator": "none", "reason": reason, "read": "", "verdict": "", "support": [], "constraint": [],
            "warnings": list(warnings), "generated_at": None}


def _result(out: Mapping, ctx: Mapping, *, generator: str, reason: str, warnings: Sequence[str]) -> dict:
    label = {f["key"]: f["label"] for f in ctx.get("factors") or []}
    rows = lambda xs: [{"key": x["key"], "label": label.get(x["key"], x["key"]), "note": x["note"]} for x in xs]  # noqa: E731
    return {"status": "ok", "source": "llm", "generator": generator, "reason": reason, "read": out["read"], "verdict": out["verdict"],
            "support": rows(out["support"]), "constraint": rows(out["constraint"]), "warnings": list(warnings),
            "generated_at": datetime.now(timezone.utc).isoformat() if generator == "api" else None}


def _user_message(ctx: Mapping, *, previous: str | None = None, problems: Sequence[str] = ()) -> str:
    msg = f"아래는 지금 시점의 컨텍스트(JSON)다. 이것만 근거로 CYCLE READ 를 써라.\n\n{context_text(ctx)}"
    if previous is not None:
        msg += f"\n\n이전 답안이 화면 검증을 통과하지 못했다. 문제를 고쳐 다시 써라.\n이전 답안: {previous}\n문제: " + " / ".join(problems)
    return msg


def generate(client, ctx: Mapping, cfg: Mapping) -> tuple[dict | None, list[str], str]:
    from .client import LLMFailure
    from .rates_read import failure_reason
    warnings: list[str] = []
    previous: str | None = None
    problems: list[str] = []
    for attempt in range(1 + int(cfg.get("retries_on_invalid", 1))):
        res = client.interpret(system=SYSTEM_PROMPT, user=_user_message(ctx, previous=previous, problems=problems), schema=SCHEMA,
                               effort=str(cfg.get("effort", "high")), max_tokens=int(cfg.get("max_tokens", 16000)), timeout_sec=float(cfg.get("timeout_sec", 120)))
        if isinstance(res, LLMFailure):
            return None, warnings, failure_reason(res, client)
        out = normalize_output(res)
        problems = check_output(out, ctx, cfg)
        if not problems:
            return out, warnings, ""
        warnings.append(f"검증 {attempt + 1}회차: " + " / ".join(problems))
        previous = json.dumps(out, ensure_ascii=False)
    return None, warnings, "AI 해설이 화면 검증(숫자 대조·금지어·문장 수·증거 방향)을 통과하지 못했다"


def attach_cycle_read(cyc: dict, session_read: Mapping | None = None, *, client=None, cfg: Mapping | None = None, cfg_regime: Mapping | None = None) -> dict:
    """cyc['cycle_read'] 하나만 붙인다. API → 세션 생성본 → 비움. 어떤 실패도 예외로 새지 않는다(정량 화면은 그대로)."""
    if cfg is None or cfg_regime is None:
        from ..engines.semiconductor_cycle import load_config
        full = load_config()
        cfg = full.get("cycle_read") or {} if cfg is None else cfg
        cfg_regime = full.get("regime") or {} if cfg_regime is None else cfg_regime
    try:
        ctx = build_context(cyc, cfg_regime)
    except Exception:
        logger.exception("반도체 CYCLE READ 컨텍스트 구성 실패 — 비워 둔다")
        cyc["cycle_read"] = empty(reason="컨텍스트 구성 실패")
        return cyc
    if (cyc.get("regime") or {}).get("composite") is None:
        cyc["cycle_read"] = empty(reason="국면을 정할 증거가 없어 해설을 만들지 않는다")
        return cyc
    warnings: list[str] = []
    reason = "LLM 비활성 — 키 없음 또는 설정 off"
    if client is not None and getattr(client, "enabled", False):
        try:
            out, warnings, reason = generate(client, ctx, cfg)
        except Exception:
            logger.exception("반도체 CYCLE READ 생성 실패")
            out, reason = None, "AI 해설 생성 중 오류"
        if out is not None:
            cyc["cycle_read"] = _result(out, ctx, generator="api", reason="", warnings=warnings)
            return cyc
    if session_read is not None:
        out = normalize_output(session_read)
        problems = check_output(out, ctx, cfg)
        if not problems:
            cyc["cycle_read"] = _result(out, ctx, generator="session", reason=f"API 호출 실패({reason}) — 같은 컨텍스트·프롬프트·검증으로 세션 생성", warnings=warnings)
            return cyc
        warnings = warnings + ["세션 생성본 검증 실패: " + " / ".join(problems)]
    cyc["cycle_read"] = empty(reason=reason, warnings=warnings)
    return cyc
