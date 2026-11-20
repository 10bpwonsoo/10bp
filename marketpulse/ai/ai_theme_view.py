"""
AI THEME VIEW — AI 센티 탭 맨 위의 투자 관점 종합 코멘트 (2026-11-12 요청).

기존 AI 판정(AI Trade Regime · driver · breadth · narrative · 펀더멘털/반도체 확인 · 스트레스 · 센티먼트 …)은 그대로 두고,
그 값들을 모두 읽은 LLM 이 "지금 AI 테마를 어떻게 봐야 하는가" 를 직접 쓴다.
- 고정 문구 · 템플릿 · if-then 문장 선택 · 카테고리 매핑을 쓰지 않는다. 출력 필드 구조만 고정한다.
- AI REGIME READ(시스템 판정 설명)와 역할이 다르다 — 이것은 판정들의 관계를 해석한 투자 관점 종합이다.
- 컨텍스트는 그 Daily Snapshot cutoff 의 저장 데이터만(look-ahead 없음). 결측은 missing 으로 알려 주고 그것으로 결론을 만들지 않게 한다.
- 순서: API → 같은 컨텍스트 · 프롬프트 · 검증의 세션 생성본 → 없음(규칙 문장으로 채우지 않는다 — 화면은 '생성되지 않음' 을 보인다).
- 저장본에는 결과를 그대로 저장하고, 과거 날짜를 열 때 다시 생성하지 않는다. LIVE 는 판정 지문이 같으면 이전 결과를 다시 쓴다.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Mapping

from .rates_read import _phrase_hits, failure_reason, load_rates_read_config, number_check, split_sentences

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an equity portfolio manager interpreting the current AI investment theme for the top of a dashboard tab.

Read all provided AI theme, equity (US and Korea), semiconductor, memory, macro, price, breadth, fundamental, narrative, sentiment and market-regime data.
Do not choose from predefined commentary. Do not use a fixed phrase library. Identify yourself what currently drives the AI trade, what confirms it,
what contradicts it, and what matters next. Weigh the evidence yourself — there is no fixed priority (on some days the semiconductor cycle matters most,
on others hyperscaler capex, on others a price drop with credit stress).

Rules
- Use only data in the provided snapshot. Do not invent missing facts. Anything listed in `missing` (or marked unavailable / N/A / ?) must not be used to draw a conclusion.
- Interpret relationships, not a translation of labels: e.g. price strength + widening breadth + weak fundamentals = a broadening rally whose durability still needs earnings confirmation;
  weak price + strong fundamentals = a positive fundamental divergence. Always state both what supports and what contradicts the view.
- Cover US and Korea AI / semiconductor equities when data exists; say so when they diverge.
- `ai_regime_read` is the system-verdict explanation already shown on screen. Do not repeat it — your job is the investor's synthesis.
- Numbers already on screen (`displayed_elsewhere`) should not be listed again; use at most two numbers in total and only when they are the key evidence.
- Korean, short, direct, investor tone (…습니다 for summary). No generic filler ("AI 산업은 계속 발전하고 있다").
- Never use the words 확률, 매수, 매도, 전망, 목표가, and give no buy/sell recommendation.

Output JSON fields (structure fixed, content entirely yours)
- headline: one-line investment judgement of the AI theme now (Korean, ≤ 40 chars, no period)
- summary: 2–4 sentences — current direction, what leads, what is weak or unconfirmed, what would strengthen or weaken the view
- driver: what is driving the theme now (one short line)
- strength: what confirms it (one short line)
- weak_point: the most important weakness / missing confirmation (one short line)
- next_watch: what to check next and what it would mean (one short line)"""

SCHEMA = {
    "type": "object",
    "properties": {k: {"type": "string"} for k in ("headline", "summary", "driver", "strength", "weak_point", "next_watch")},
    "required": ["headline", "summary", "driver", "strength", "weak_point", "next_watch"],
    "additionalProperties": False,
}
FIELDS = ("headline", "summary", "driver", "strength", "weak_point", "next_watch")
FORBIDDEN_EXTRA = ["목표가"]
LINE_MAX = 70


def _r(v: Any, nd: int = 2) -> float | None:
    try:
        return None if v is None else round(float(v), nd)
    except (TypeError, ValueError):
        return None


def build_context(ai: Mapping[str, Any], *, semi: Mapping[str, Any] | None = None, cockpit: Mapping[str, Any] | None = None) -> dict:
    """ai = AiRegime(JSON). semi = 반도체 사이클 탭(JSON), cockpit = 실시간 탭(JSON) — 모두 같은 Daily Snapshot 의 저장 데이터."""
    a = ai.get("ai_vs_market") or {}
    lead = ai.get("leadership") or {}
    br = ai.get("breadth") or {}
    nar = ai.get("narrative") or {}
    mac = ai.get("macro") or {}
    st = ai.get("stress") or {}
    fc = ai.get("fundamental_confirmation") or {}
    sent = ai.get("sentiment") or {}
    dv = ai.get("driver_verdict") or {}
    missing: list[str] = list(ai.get("missing") or [])
    semi_areas = []
    for x in ((ai.get("semi_confirmation") or {}).get("areas") or []):
        semi_areas.append({"area": x.get("label"), "status": x.get("status"), "detail": x.get("detail")})
        if x.get("eps") in ("?", None):
            missing.append(f"EPS revision — {x.get('label')}")
    stocks = ai.get("stocks") or []
    eps_na = sum(1 for s in stocks if str(s.get("eps_revision") or "N/A") in ("N/A", "?", ""))
    if stocks and eps_na == len(stocks):
        missing.append("EPS revision / 컨센서스 — 종목 전부 없음")
    kr = [{"name": s.get("name"), "segments": s.get("segments"), "ret_5d": _r(s.get("ret_5d"), 1), "rel_5d": _r(s.get("rel_5d"), 1), "ret_21d": _r(s.get("ret_21d"), 1),
           "overall": s.get("overall")} for s in stocks if s.get("region") == "KR" and s.get("available")]
    us_top = sorted([s for s in stocks if s.get("region") != "KR" and s.get("available") and s.get("rel_5d") is not None], key=lambda s: -abs(float(s["rel_5d"])))[:8]
    sent_comp = [{"component": c.get("label"), "score": _r(c.get("score"), 0), "state": c.get("state_label") or c.get("state"), "read": c.get("read")}
                 for c in (sent.get("components") or [])]
    for c in (sent.get("components") or []):
        if c.get("score") is None:
            missing.append(f"AI Sentiment component {c.get('label')}")
    ctx: dict[str, Any] = {
        "as_of_utc": ai.get("as_of"),
        "ai_trade_regime": {"label": ai.get("regime_label"), "label_ko": ai.get("regime_label_ko"), "subtitle": ai.get("regime_subtitle"), "implication": ai.get("implication"),
                            "signal_strength": ai.get("signal_strength_label"), "dominant_driver": ai.get("dominant"), "runner_up": ai.get("runner_up")},
        "status_strip": [{"label": x.get("label"), "value": x.get("value"), "detail": x.get("detail"), "meaning": x.get("meaning")} for x in (ai.get("status_strip") or [])],
        "ai_vs_nasdaq": {"basket_ret_1d": _r(a.get("basket_ret_1d"), 1), "basket_ret_5d": _r(a.get("basket_ret_5d"), 1), "basket_ret_21d": _r(a.get("basket_ret_21d"), 1),
                         "ndx_ret_5d": _r(a.get("ndx_ret_5d"), 1), "rel_5d_pp": _r(a.get("rel_ndx_5d"), 1), "rel_z_5d": _r(a.get("rel_ndx_z_5d"), 1), "verdict": a.get("rel_verdict")},
        "drivers": [{"driver": d.get("label"), "score": _r(d.get("score"), 0), "strength": d.get("strength"), "status": d.get("status"), "why": d.get("status_reason")}
                    for d in (ai.get("drivers") or [])],
        "driver_verdict": {"gap": dv.get("gap_label"), "gap_value": dv.get("gap_value"), "primary": (dv.get("primary") or {}).get("label"), "primary_status": (dv.get("primary") or {}).get("status")},
        "leadership_groups": [{"group": g.get("label"), "ret_5d": _r(g.get("ret_5d"), 1), "rel_5d": _r(g.get("rel_5d"), 1), "ret_21d": _r(g.get("ret_21d"), 1), "role": g.get("role")}
                              for g in (lead.get("groups") or [])],
        "leadership_read": lead.get("read") or lead.get("sentence"),
        "breadth": {"above_ma20_pct": br.get("above_ma20_pct"), "change_1w_pts": br.get("change_1w_pts"), "advancing_pct": br.get("advancing_pct"), "trend": br.get("trend"),
                    "narrowing_with_index_up": br.get("narrowing_with_index_up"), "by_group": br.get("by_group"), "read": br.get("read")},
        "narrative": {"news_tone": _r(nar.get("news_tone"), 0), "news_count": nar.get("news_count"), "news_momentum": _r(nar.get("news_momentum"), 0), "quadrant": nar.get("label"),
                      "sentence": nar.get("sentence"), "topics": [{"topic": d.get("label"), "count": d.get("count"), "tone": _r(d.get("tone"), 0)} for d in (nar.get("drivers") or [])]},
        "macro": {"verdict": mac.get("verdict"), "sentence": mac.get("sentence"), "rows": [{"factor": r.get("label"), "z": _r(r.get("z"), 1), "status": r.get("status")} for r in (mac.get("rows") or [])]},
        "ai_specific_stress": {"level": st.get("level"), "score": st.get("score"), "max": st.get("max_score"),
                               "components": [{"c": c.get("label"), "value": c.get("display"), "points": c.get("points")} for c in (st.get("components") or [])]},
        "fundamental_confirmation": {"level": fc.get("level"), "confirming": fc.get("confirming"), "lagging": fc.get("lagging"), "sentence": fc.get("sentence")},
        "semiconductor_confirmation": semi_areas,
        "transmission_chain": [{"stage": x.get("label"), "status": x.get("status"), "score": _r(x.get("score"), 0), "evidence": x.get("evidence")}
                               for x in ((ai.get("transmission") or {}).get("stages") or [])],
        "value_chain_snapshot": (ai.get("chain_view") or {}).get("snapshot"),
        "expectation_gap": [{"segment": g.get("label"), "market_pricing": g.get("market_pricing"), "fundamental": g.get("fundamental"), "note": g.get("note")} for g in (ai.get("expectation_gap") or [])],
        "what_matters": [{"item": w.get("text"), "status": w.get("status"), "current": w.get("current")} for w in (ai.get("what_matters") or [])],
        "ai_sentiment_greed_fear": {"index": _r(sent.get("index"), 0), "state": sent.get("state_label") or sent.get("state"), "components": sent_comp},
        "ai_news": [{"event": n.get("event"), "tone": n.get("tone"), "primary_segments": n.get("primary")} for n in (ai.get("news_impact") or [])[:6]],
        "us_ai_stocks_largest_moves": [{"name": s.get("name"), "segments": s.get("segments"), "ret_5d": _r(s.get("ret_5d"), 1), "rel_5d": _r(s.get("rel_5d"), 1), "overall": s.get("overall")} for s in us_top],
        "korea_ai_semis_stocks": kr,
        "ai_regime_read": ai.get("regime_read"),
        "global_market_context": ai.get("context"),
    }
    if semi:
        rg = semi.get("regime") or {}
        ctx["semiconductor_cycle"] = {"state": rg.get("label") or rg.get("state"), "composite": _r(rg.get("composite"), 1),
                                      "components": [{"c": c.get("label"), "score": _r(c.get("score"), 0)} for c in (rg.get("components") or [])],
                                      "read": (semi.get("market_read") or {}).get("read")}
    if cockpit:
        now = cockpit.get("market_now") or {}
        stt = now.get("state") or {}
        ctx["market_regime"] = {"official": now.get("label_text"), "candidate": stt.get("candidate_label") or now.get("raw_text"), "market_read": now.get("read")}
    ctx["missing"] = sorted(set(missing))
    shown = [a.get("rel_ndx_5d"), a.get("rel_ndx_z_5d"), st.get("score"), br.get("above_ma20_pct"), sent.get("index")]
    for d in (ai.get("drivers") or []):
        shown.append(d.get("score"))
    ctx["displayed_elsewhere"] = {"numbers": [_r(x, 1) for x in shown if x is not None], "note": "화면에 이미 보이는 숫자 — 다시 나열하지 않는다"}
    return ctx


def context_text(ctx: Mapping) -> str:
    return json.dumps(ctx, ensure_ascii=False, indent=1)


def normalize(out: Mapping) -> dict:
    return {k: " ".join(str(out.get(k) or "").split()) for k in FIELDS}


def check(out: Mapping, ctx: Mapping) -> list[str]:
    """문제 목록 — 비면 통과. 구조 · 길이 · 금지어 · 컨텍스트 숫자 · 기존 READ 반복."""
    o = normalize(out)
    probs: list[str] = []
    for k in FIELDS:
        if not o[k]:
            probs.append(f"{k} 가 비어 있다")
    if len(o["headline"]) > 40 or o["headline"].endswith("."):
        probs.append("headline 은 40자 이내 한 줄, 마침표 없이")
    n = len(split_sentences(o["summary"]))
    if not 2 <= n <= 4:
        probs.append(f"summary 문장 수 {n} — 2~4문장")
    if len(o["summary"]) > 420:
        probs.append(f"summary 길이 {len(o['summary'])}자 — 420자 이내")
    for k in ("driver", "strength", "weak_point", "next_watch"):
        if len(o[k]) > LINE_MAX:
            probs.append(f"{k} 길이 {len(o[k])}자 — {LINE_MAX}자 이내 한 줄")
    v = dict(load_rates_read_config().get("validate") or {})
    v["forbidden"] = list(v.get("forbidden") or []) + FORBIDDEN_EXTRA
    v["filler"] = list(v.get("filler") or []) + ["계속해서 발전", "다양한 기회와 위험"]
    allt = " ".join(o.values())
    probs += _phrase_hits(allt, v)
    counted, invented, repeated = number_check(allt, ctx)
    if invented:
        probs.append(f"컨텍스트에 없는 숫자: {', '.join(invented)}")
    if counted > 2:
        probs.append(f"숫자 {counted}개 — 핵심 근거 2개 이내")
    if repeated:
        probs.append(f"화면에 이미 보이는 숫자 반복: {', '.join(repeated)}")
    rr = str(ctx.get("ai_regime_read") or "").strip()
    if rr and any(s.strip() and s.strip() in rr for s in split_sentences(o["summary"])):
        probs.append("summary 가 AI REGIME READ 문장을 그대로 반복한다")
    return probs


def _apply(o: Mapping, *, source: str, reason: str = "") -> dict:
    return {**normalize(o), "source": source, "status": "ok", "reason": reason, "generated_at": datetime.now(timezone.utc).isoformat()}


def unavailable(reason: str) -> dict:
    return {**{k: "" for k in FIELDS}, "source": "none", "status": "unavailable", "reason": reason, "generated_at": None}


def generate(client: Any, ctx: Mapping) -> tuple[dict | None, str]:
    previous: dict | None = None; probs: list[str] = []
    for _ in range(2):
        user = f"Snapshot context (JSON). Use only this.\n\n{context_text(ctx)}"
        if previous is not None:
            user += "\n\nYour previous answer failed screen validation. Fix it.\nPrevious: " + json.dumps(previous, ensure_ascii=False) + "\nProblems: " + " / ".join(probs)
        res = client.interpret(system=SYSTEM_PROMPT, user=user, schema=SCHEMA, effort="high", max_tokens=12000, timeout_sec=150)
        if not isinstance(res, Mapping):
            return None, failure_reason(res, client)
        probs = check(res, ctx)
        if not probs:
            return normalize(res), ""
        previous = normalize(res)
    return None, "AI THEME VIEW 가 검증(숫자 대조 · 금지어 · 길이 · READ 반복)을 통과하지 못했다"


def write(ctx: Mapping, *, client: Any = None, session_read: Mapping | None = None) -> dict:
    """API → 세션 생성본 → unavailable(규칙 문장으로 채우지 않는다)."""
    reason = "LLM 비활성 — 키 없음 또는 설정 off"
    if client is not None and getattr(client, "enabled", False):
        try:
            out, reason = generate(client, ctx)
        except Exception:  # noqa: BLE001
            logger.exception("AI THEME VIEW 생성 실패")
            out, reason = None, "AI THEME VIEW 생성 중 오류"
        if out is not None:
            return _apply(out, source="llm")
    if session_read is not None:
        probs = check(session_read, ctx)
        if not probs:
            return _apply(session_read, source="session", reason=f"API 호출 실패({reason}) — 같은 컨텍스트·프롬프트·검증으로 세션 생성")
        logger.warning("AI THEME VIEW 세션본 검증 실패: %s", " / ".join(probs))
        reason = "세션 생성본 검증 실패: " + " / ".join(probs)
    return unavailable(reason)


# ── LIVE 캐시 — 판정 지문이 같으면 다시 부르지 않는다 ─────────────────
_LIVE: dict[str, dict] = {}
_LOCK = threading.Lock()


def fingerprint(ai: Mapping[str, Any]) -> str:
    """의미 있는 변화만 — 판정 라벨 · 상태 줄 · 펀더멘털/반도체 확인 · 스트레스 · 센티먼트 상태 · breadth 추세."""
    key = {"regime": ai.get("regime"), "strip": [(x.get("key"), x.get("value")) for x in (ai.get("status_strip") or [])],
           "fc": (ai.get("fundamental_confirmation") or {}).get("level"), "stress": (ai.get("stress") or {}).get("level"),
           "sent": (ai.get("sentiment") or {}).get("state"), "breadth": (ai.get("breadth") or {}).get("trend"),
           "rel": (ai.get("ai_vs_market") or {}).get("rel_verdict"), "dom": ai.get("dominant")}
    return hashlib.sha256(json.dumps(key, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def live_view(ai: Mapping[str, Any], *, client: Any = None, semi: Mapping | None = None, cockpit: Mapping | None = None) -> dict:
    fp = fingerprint(ai)
    with _LOCK:
        hit = _LIVE.get(fp)
    if hit is not None:
        return hit
    view = write(build_context(ai, semi=semi, cockpit=cockpit), client=client)
    if view.get("status") == "ok":
        with _LOCK:
            _LIVE[fp] = view
    return view
