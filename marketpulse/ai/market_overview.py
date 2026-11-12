"""
MARKET OVERVIEW (시장 종합) — 기존 탭 엔진 결과를 읽어 전체 시장을 하나의 투자 관점으로 연결하는 LLM 종합 (2026-11-12 요청).

새 판정 · 새 점수를 만들지 않는다. SOURCE OF TRUTH 는 기존 엔진(실시간 cockpit · 금리 · 유가 · AI 센티 · 반도체 사이클)이고,
여기는 READ → SYNTHESIZE 만 한다. 화면의 숫자 칸은 프론트가 같은 저장본 섹션에서 직접 그린다(이 모듈은 해석만 만든다).

- 컨텍스트 = 그 Daily Snapshot 저장본의 섹션들(같은 cutoff)만. 결측은 missing 으로 알려 주고 그것으로 결론을 만들지 않게 한다.
- 고정 문구 · 템플릿 · 코멘트 버킷 · 결론 강제(Risk-On 이면 Bullish 같은) 없음. 출력 필드 구조만 고정.
- 검증: 구조 · 길이 · 금지어(직접 매매 지시 · 확률 · 전망) · 컨텍스트에 없는 숫자 · 허용된 이름(섹터 · 스타일) · 지난 날짜 이벤트를 catalyst 로 쓰지 않기.
- 순서: API → 같은 컨텍스트 · 프롬프트 · 검증의 세션 생성본 → unavailable(규칙 문장으로 채우지 않는다).
- 저장: capture/market_overview.json → 저장본 섹션 market_overview. 과거 날짜는 저장값 그대로. LIVE 는 판정 지문이 같으면 이전 결과 재사용.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping

from .rates_read import _phrase_hits, failure_reason, number_check, split_sentences

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))

SYSTEM_PROMPT = """You are the head of multi-asset equity strategy writing the MARKET OVERVIEW tab of a market dashboard for a Korean portfolio manager.

You receive one snapshot (JSON) assembled from the dashboard's existing engines: market regime (official / candidate / transition / equity confirmation),
market drivers, US and Korea equity signals, leadership themes, rates & inflation, oil, cross-asset, AI theme, semiconductor/memory cycle, news and upcoming events.
These engines are the source of truth — do not recompute or contradict their measured values; interpret them.

Your job: connect the pieces into one investment view — what is happening, why, whether equities confirm it, where leadership is, what the risks are,
what would change the view, and what it means for a portfolio.

Rules
- Use only the snapshot. Do not invent facts, numbers, companies, sectors or events. Anything in `missing` (or marked unavailable / EXCLUDED / NO DATA / N/A / ?) must not support a conclusion.
- No predefined commentary, no phrase library, no forced conclusions (an official Risk-On does not automatically mean bullish). State what confirms and what conflicts.
- Choose drivers, risks and next-checks yourself by market impact, recent change, link to equities, persistence and events — not by absolute score order.
- Catalysts: only events in `upcoming_events` dated on/after the snapshot date. Past events only as context.
- What-matters-next: plain market conditions a PM understands; no raw rule thresholds like "z < -1" or "score > 75" in the main text.
- Portfolio implication: views like Overweight bias / Neutral / Underweight bias / Watch / Risk — never direct trade orders.
- Do not repeat numbers already displayed elsewhere; at most two numbers in market_view. Korean, concise, professional (…습니다 for prose fields).
- Never use the words 확률, 매수, 매도, 전망, 목표가, BUY, SELL.

Field guide (structure fixed, content yours)
- headline: one-line market call (≤ 50 chars, no period)
- market_view: 3–5 sentences linking regime, equities (US/Korea), rates, credit, oil, AI/semis, leadership, events — the core investment logic now
- labels: regime (short regime name as the engines state it), equity (Bullish|Improving|Mixed|Weak), macro (Tailwind|Neutral|Headwind), risk (Low|Moderate|Elevated|High)
- regime_read: 1–2 sentences on the official vs candidate regime and transition
- key_drivers: 3–5 items {name, direction: POSITIVE|NEGATIVE|MIXED, strength: STRONG|MODERATE|WEAK, read: one line}
- equity_view: {us, korea: one line each, divergence_label: "US > KOREA" | "KOREA > US" | "US + KOREA CONFIRMED" | "US + KOREA WEAK" | "MIXED", divergence: one line}
- rates_view: one line — what the rates move means for equities
- cross_asset_view: 1–2 sentences
- ai_semiconductor_view: 1–2 sentences connecting AI price leadership with the semiconductor/memory fundamentals
- leadership_view: one line on where leadership is and how broad
- style_view: items {style: one of Growth|Value|Quality|Momentum|High Beta|Low Vol|Cyclical|Defensive, view: POSITIVE|IMPROVING|NEUTRAL|MIXED|NEGATIVE, read: one short line} — only styles the data speaks to
- sector_view: {positive: [names], watch: [names], negative: [names], read: one line} — names only from `sector_names`
- top_risks: 3–5 items {risk, level: LOW|MODERATE|ELEVATED|HIGH, read: one line on what could shake the market}
- catalysts: items {date (YYYY-MM-DD from upcoming_events), event (its name), why: one line, sensitivity: HIGH|MEDIUM|LOW}
- what_matters_next: 3–5 items {title, condition: market condition in plain words, implication: what it would mean}
- portfolio_implication: {equity_stance, style, sector, risk_control, hedge_watch} — one short line each"""

_ITEM = lambda props: {"type": "object", "properties": {k: {"type": "string"} for k in props}, "required": list(props), "additionalProperties": False}  # noqa: E731
SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"}, "market_view": {"type": "string"},
        "labels": _ITEM(["regime", "equity", "macro", "risk"]),
        "regime_read": {"type": "string"},
        "key_drivers": {"type": "array", "items": _ITEM(["name", "direction", "strength", "read"])},
        "equity_view": _ITEM(["us", "korea", "divergence_label", "divergence"]),
        "rates_view": {"type": "string"}, "cross_asset_view": {"type": "string"}, "ai_semiconductor_view": {"type": "string"}, "leadership_view": {"type": "string"},
        "style_view": {"type": "array", "items": _ITEM(["style", "view", "read"])},
        "sector_view": {"type": "object", "properties": {"positive": {"type": "array", "items": {"type": "string"}}, "watch": {"type": "array", "items": {"type": "string"}},
                                                         "negative": {"type": "array", "items": {"type": "string"}}, "read": {"type": "string"}},
                        "required": ["positive", "watch", "negative", "read"], "additionalProperties": False},
        "top_risks": {"type": "array", "items": _ITEM(["risk", "level", "read"])},
        "catalysts": {"type": "array", "items": _ITEM(["date", "event", "why", "sensitivity"])},
        "what_matters_next": {"type": "array", "items": _ITEM(["title", "condition", "implication"])},
        "portfolio_implication": _ITEM(["equity_stance", "style", "sector", "risk_control", "hedge_watch"]),
    },
    "required": ["headline", "market_view", "labels", "regime_read", "key_drivers", "equity_view", "rates_view", "cross_asset_view", "ai_semiconductor_view",
                 "leadership_view", "style_view", "sector_view", "top_risks", "catalysts", "what_matters_next", "portfolio_implication"],
    "additionalProperties": False,
}
ENUM = {"equity": {"Bullish", "Improving", "Mixed", "Weak"}, "macro": {"Tailwind", "Neutral", "Headwind"}, "risk": {"Low", "Moderate", "Elevated", "High"}}
DIRS = {"POSITIVE", "NEGATIVE", "MIXED"}; STRENGTHS = {"STRONG", "MODERATE", "WEAK"}
STYLES = {"Growth", "Value", "Quality", "Momentum", "High Beta", "Low Vol", "Cyclical", "Defensive"}
STYLE_VIEWS = {"POSITIVE", "IMPROVING", "NEUTRAL", "MIXED", "NEGATIVE"}
RISK_LEVELS = {"LOW", "MODERATE", "ELEVATED", "HIGH"}; SENS = {"HIGH", "MEDIUM", "LOW"}
DIVERGENCE = {"US > KOREA", "KOREA > US", "US + KOREA CONFIRMED", "US + KOREA WEAK", "MIXED"}
FORBIDDEN = ["확률", "매수", "매도", "전망", "목표가", "BUY", "SELL", "사야", "팔아야"]


def _r(v: Any, nd: int = 2) -> float | None:
    try:
        return None if v is None else round(float(v), nd)
    except (TypeError, ValueError):
        return None


def snapshot_date_of(doc: Mapping[str, Any]) -> str:
    a = str(((doc.get("snapshot") or {}).get("as_of")) or "")
    if not a:
        return ""
    return datetime.fromisoformat(a.replace("Z", "+00:00")).astimezone(KST).date().isoformat()


def build_context(doc: Mapping[str, Any]) -> dict:
    """doc = 저장본 형식(snapshot · cockpit · rates_regime · oil_regime · ai_regime · semiconductor_cycle). 없는 섹션은 missing 으로."""
    snap = doc.get("snapshot") or {}
    ck = doc.get("cockpit") or {}
    rr = doc.get("rates_regime") or {}
    oil = doc.get("oil_regime") or {}
    ai = doc.get("ai_regime") or {}
    semi = doc.get("semiconductor_cycle") or {}
    missing: list[str] = [f"{k} 섹션 없음" for k in ("cockpit", "rates_regime", "oil_regime", "ai_regime", "semiconductor_cycle") if not doc.get(k)]
    sd = snapshot_date_of(doc)
    now = ck.get("market_now") or {}
    st = now.get("state") or {}
    sel = now.get("selection") or {}
    hist = ck.get("history") or {}
    days = hist.get("days") or []
    ne = sel.get("neutral_equity") or {}

    def sigs(m: str) -> list[dict]:
        out = []
        for g in ((ne.get(m) or {}).get("signals") or []):
            if g.get("state") == "EXCLUDED":
                missing.append(f"{g.get('label')} ({m.upper()}) 데이터 없음")
                continue
            out.append({"signal": g.get("label"), "value_riskon_basis": _r(g.get("value"), 2), "note": g.get("note") or ""})
        return out

    for x in sel.get("excluded") or []:
        missing.append(f"{x} — EXCLUDED")
    ld = ck.get("leadership") or {}
    lead_rows = ld.get("all_rows") or []
    detailed = {str(r.get("key")): (role, r) for role, rows in (("leader", ld.get("leaders") or []), ("laggard", ld.get("laggards") or [])) for r in rows}
    leadership = []
    for r in lead_rows:
        role, full = detailed.get(str(r.get("key")), ("", r))
        det = full.get("detail") or {}
        leadership.append({"theme": r.get("label"), "role": role, "arrow": r.get("arrow"), "z_1d": _r(r.get("z_1d"), 1), "rel_1w": _r(r.get("rel_1w"), 1), "breadth": r.get("breadth"),
                           "why": ((det.get("why") or [""])[0]) or full.get("system_view") or "", "quality": det.get("quality_ko"), "risk": det.get("risk"),
                           "key_stocks": [k.get("name") for k in (det.get("key_stocks") or []) if isinstance(k, Mapping)]})
    ai_groups = (ai.get("leadership") or {}).get("groups") or []
    sector_names = sorted({str(r.get("label")) for r in lead_rows if r.get("label")} | {str(g.get("label")) for g in ai_groups if g.get("label")}
                          | {str(r.get("label")) for r in ((rr.get("market_implication") or {}).get("rows") or []) if r.get("label")})
    ev = rr.get("events") or {}
    upcoming = [{"date": u.get("date"), "event": u.get("name"), "importance": u.get("importance"), "note": u.get("note"), "days_ahead": u.get("days_ahead")}
                for u in (ev.get("upcoming") or []) if str(u.get("date") or "") >= sd]
    yb = {t.get("tenor"): t for t in ((rr.get("yield_breakdown") or {}).get("tenors") or [])}
    t10 = yb.get("10Y") or {}
    imap = rr.get("inflation_map") or {}
    rg = semi.get("regime") or {}
    if semi:
        for c in rg.get("components") or []:
            if c.get("score") is None:
                missing.append(f"반도체 사이클 {c.get('label')} 데이터 없음")
    ctx: dict[str, Any] = {
        "snapshot_date": sd, "as_of_utc": snap.get("as_of"),
        "market_regime": {
            "official": now.get("label_text"), "candidate": st.get("candidate_label"), "official_support": st.get("support"),
            "exit": f"{st.get('exit_streak', 0)}/{st.get('exit_required', 2)}" if st else None, "entry": (f"{st.get('entry_label')} {st.get('entry_streak')}/{st.get('entry_required')}" if st.get("entry_regime") else None),
            "released_previous_official": st.get("released_label"), "raw_signal": st.get("raw_signal"), "transition_status": now.get("transition_status"),
            "selection_confidence": sel.get("regime_confidence"), "equity_confirmation": {"us": sel.get("us_equity_confirmation"), "korea": sel.get("korea_equity_confirmation"), "global": sel.get("global_equity_confirmation")},
            "selection_commentary": sel.get("commentary"), "market_read": now.get("read"),
            "factors_today": (days[-1].get("factors") if days else {}),
            "recent_official_vs_candidate": [{"date": d.get("date"), "official": d.get("display_label"), "candidate": ((d.get("state") or {}).get("candidate_label") or d.get("raw_state"))} for d in days[-8:]],
        },
        "market_drivers": [{"driver": d.get("label"), "direction": d.get("direction"), "strength": _r(d.get("strength"), 2), "why": d.get("why"),
                            "evidence": [f"{e.get('label')} {e.get('display') or ''}".strip() for e in (d.get("evidence") or []) if e.get("available", True)][:3]} for d in (ck.get("drivers") or [])],
        "market_tone": {"state": (ck.get("tone") or {}).get("state"), "read": (ck.get("tone") or {}).get("read")},
        "us_equity_signals": sigs("us"), "korea_equity_signals": sigs("kr"),
        "key_variables": [{"label": k.get("label"), "z": _r(k.get("z"), 1), "change": k.get("change_display")} for k in (now.get("key_variables") or [])],
        "cross_asset": [{"asset": r.get("label"), "instrument": r.get("instrument_label"), "z": _r(r.get("z"), 1), "arrow": r.get("arrow")} for r in ((ck.get("cross_asset") or {}).get("rows") or [])],
        "divergences": [d.get("title") + ": " + (d.get("meaning") or "") for d in ((ck.get("cross_asset") or {}).get("divergences") or [])][:3],
        "leadership_themes": leadership,
        "rates": {"regime": rr.get("regime_label"), "headline": rr.get("headline"), "direction": (rr.get("top") or {}).get("direction_en"),
                  "primary_driver": ((rr.get("top") or {}).get("primary") or {}).get("label"), "us10y_level": (rr.get("rate_move") or {}).get("level"),
                  "us10y_5d_bp": (rr.get("rate_move") or {}).get("change_5d_bp"), "curve_shape": (rr.get("curve_move") or {}).get("shape"),
                  "us10y_5d_real_bp": t10.get("real_bp"), "us10y_5d_breakeven_bp": t10.get("breakeven_bp"), "decomposition_read": t10.get("line"),
                  "inflation_pressure": imap.get("signal_ko") or imap.get("signal"), "inflation_read": (imap.get("read_meta") or {}).get("read") or imap.get("read"),
                  "market_read": (rr.get("top") or {}).get("market_read"), "equity_implication": (rr.get("market_implication") or {}).get("why")},
        "recent_releases_and_policy": [{"date": r.get("date"), "release": r.get("title"), "result": r.get("label")} for r in (ev.get("recent") or [])][:4]
                                      + [{"date": p.get("date"), "bank": p.get("bank"), "decision": p.get("decision"), "tone": p.get("tone")} for p in (ev.get("policy") or [])][:4],
        "upcoming_events": upcoming,
        "oil": {"regime": oil.get("regime_label"), "headline": oil.get("headline"), "implication": oil.get("implication"),
                "brent_z": _r((oil.get("oil_move") or {}).get("brent_z"), 1), "wti_z": _r((oil.get("oil_move") or {}).get("wti_z"), 1)},
        "ai_theme": {"regime": ai.get("regime_label"), "subtitle": ai.get("regime_subtitle"), "status": [f"{x.get('label')}: {x.get('value')}" for x in (ai.get("status_strip") or [])],
                     "rel_vs_nasdaq_5d_pp": _r((ai.get("ai_vs_market") or {}).get("rel_ndx_5d"), 1), "fundamental_confirmation": (ai.get("fundamental_confirmation") or {}).get("level"),
                     "theme_view_headline": (ai.get("theme_view") or {}).get("headline"), "theme_view_summary": (ai.get("theme_view") or {}).get("summary"),
                     "groups": [{"group": g.get("label"), "rel_5d": _r(g.get("rel_5d"), 1), "ret_21d": _r(g.get("ret_21d"), 1)} for g in ai_groups]},
        "semiconductor_cycle": {"regime": rg.get("label"), "composite": _r(rg.get("composite"), 1),
                                "components": [{"component": c.get("label"), "score": _r(c.get("score"), 0)} for c in (rg.get("components") or [])],
                                "read": (semi.get("market_read") or {}).get("read")} if semi else None,
        "news": [{"headline": c.get("headline"), "tag": c.get("tag"), "impact": c.get("impact"), "why": c.get("why")} for c in (ck.get("catalysts") or [])[:8]],
        "sector_names": sector_names,
    }
    ctx["missing"] = sorted(set(missing))
    ctx["displayed_elsewhere"] = {"numbers": [x for x in [ctx["rates"]["us10y_level"], ctx["ai_theme"]["rel_vs_nasdaq_5d_pp"], sel.get("regime_confidence"),
                                                          ctx["semiconductor_cycle"]["composite"] if ctx["semiconductor_cycle"] else None] if x is not None],
                                  "note": "다른 칸에 이미 보이는 숫자 — 다시 나열하지 않는다"}
    return ctx


def context_text(ctx: Mapping) -> str:
    return json.dumps(ctx, ensure_ascii=False, indent=1)


def _texts(o: Mapping) -> list[str]:
    out: list[str] = []
    for k, v in o.items():
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, Mapping):
            out += _texts(v)
        elif isinstance(v, list):
            for x in v:
                out += _texts(x) if isinstance(x, Mapping) else [str(x)]
    return out


def check(o: Mapping, ctx: Mapping) -> list[str]:
    """문제 목록 — 비면 통과."""
    p: list[str] = []
    req = SCHEMA["required"]
    for k in req:
        if k not in o or o[k] in (None, "", [], {}):
            p.append(f"{k} 가 비어 있다")
    if p:
        return p
    hl = str(o["headline"]).strip()
    if len(hl) > 50 or hl.endswith("."):
        p.append("headline 은 50자 이내 한 줄, 마침표 없이")
    n = len(split_sentences(str(o["market_view"])))
    if not 3 <= n <= 5:
        p.append(f"market_view 문장 수 {n} — 3~5문장")
    if len(str(o["market_view"])) > 650:
        p.append("market_view 650자 이내")
    lab = o["labels"]
    for k, allowed in ENUM.items():
        if lab.get(k) not in allowed:
            p.append(f"labels.{k} 는 {sorted(allowed)} 중 하나")
    for name, lo, hi in (("key_drivers", 3, 5), ("top_risks", 3, 5), ("what_matters_next", 3, 5)):
        if not lo <= len(o[name]) <= hi:
            p.append(f"{name} 는 {lo}~{hi}개")
    for d in o["key_drivers"]:
        if d.get("direction") not in DIRS or d.get("strength") not in STRENGTHS:
            p.append(f"key_drivers '{d.get('name')}' direction/strength 값")
    for s in o["style_view"]:
        if s.get("style") not in STYLES or s.get("view") not in STYLE_VIEWS:
            p.append(f"style_view '{s.get('style')}' 스타일/판정 값")
    for r in o["top_risks"]:
        if r.get("level") not in RISK_LEVELS:
            p.append(f"top_risks '{r.get('risk')}' level 값")
    if o["equity_view"].get("divergence_label") not in DIVERGENCE:
        p.append("equity_view.divergence_label 값")
    allowed = [str(x).lower() for x in ctx.get("sector_names") or []]
    for bucket in ("positive", "watch", "negative"):
        for nm in o["sector_view"].get(bucket) or []:
            if not any(str(nm).lower() in a or a in str(nm).lower() for a in allowed):
                p.append(f"sector_view.{bucket} '{nm}' 는 sector_names 에 없다")
    up = {(str(u.get("date")), str(u.get("event"))) for u in ctx.get("upcoming_events") or []}
    for c in o["catalysts"]:
        if (str(c.get("date")), str(c.get("event"))) not in up:
            p.append(f"catalysts '{c.get('date')} {c.get('event')}' 는 upcoming_events 에 없다(지난 이벤트 · 없는 일정 금지)")
        if c.get("sensitivity") not in SENS:
            p.append(f"catalysts '{c.get('event')}' sensitivity 값")
    allt = " ".join(_texts(o))
    hits = [w for w in FORBIDDEN if w.lower() in allt.lower()]
    if hits:
        p.append(f"금지어: {', '.join(hits)}")
    p += [x for x in _phrase_hits(allt, {"filler": ["다양한 기회와 위험", "계속해서 발전"]})]
    _n, invented, _rep = number_check(allt, ctx)
    if invented:
        p.append(f"컨텍스트에 없는 숫자: {', '.join(invented)}")
    cnt, _inv, rep = number_check(str(o["market_view"]), ctx)
    if cnt > 2:
        p.append(f"market_view 숫자 {cnt}개 — 2개 이내")
    if rep:
        p.append(f"market_view 가 화면에 이미 보이는 숫자를 반복: {', '.join(rep)}")
    return p


def unavailable(reason: str, ctx: Mapping | None = None) -> dict:
    return {"status": "unavailable", "source": "none", "reason": reason, "generated_at": None, "view": None,
            "snapshot_date": (ctx or {}).get("snapshot_date"), "as_of": (ctx or {}).get("as_of_utc")}


def _ok(view: Mapping, ctx: Mapping, *, source: str, reason: str = "") -> dict:
    return {"status": "ok", "source": source, "reason": reason, "generated_at": datetime.now(timezone.utc).isoformat(), "view": dict(view),
            "snapshot_date": ctx.get("snapshot_date"), "as_of": ctx.get("as_of_utc")}


def generate(client: Any, ctx: Mapping) -> tuple[dict | None, str]:
    previous: Any = None; probs: list[str] = []
    for _ in range(2):
        user = f"Snapshot (JSON). Use only this.\n\n{context_text(ctx)}"
        if previous is not None:
            user += "\n\nYour previous answer failed validation. Fix it.\nProblems: " + " / ".join(probs)
        res = client.interpret(system=SYSTEM_PROMPT, user=user, schema=SCHEMA, effort="high", max_tokens=20000, timeout_sec=240)
        if not isinstance(res, Mapping):
            return None, failure_reason(res, client)
        probs = check(res, ctx)
        if not probs:
            return dict(res), ""
        previous = res
    return None, "MARKET OVERVIEW 가 검증(구조 · 금지어 · 숫자 대조 · 이름 · 일정)을 통과하지 못했다"


def write(ctx: Mapping, *, client: Any = None, session_read: Mapping | None = None) -> dict:
    reason = "LLM 비활성 — 키 없음 또는 설정 off"
    if client is not None and getattr(client, "enabled", False):
        try:
            out, reason = generate(client, ctx)
        except Exception:  # noqa: BLE001
            logger.exception("MARKET OVERVIEW 생성 실패")
            out, reason = None, "MARKET OVERVIEW 생성 중 오류"
        if out is not None:
            return _ok(out, ctx, source="llm")
    if session_read is not None:
        view = {k: v for k, v in session_read.items() if not str(k).startswith("_")}
        probs = check(view, ctx)
        if not probs:
            return _ok(view, ctx, source="session", reason=f"API 호출 실패({reason}) — 같은 컨텍스트·프롬프트·검증으로 세션 생성")
        logger.warning("MARKET OVERVIEW 세션본 검증 실패: %s", " / ".join(probs))
        reason = "세션 생성본 검증 실패: " + " / ".join(probs[:5])
    return unavailable(reason, ctx)


# ── LIVE — 의미 있는 변화에서만 다시 만든다 ─────────────────
_LIVE: dict[str, dict] = {}
_LOCK = threading.Lock()


def fingerprint(ctx: Mapping) -> str:
    """후보 regime · 공식 · 전환 · driver 구성 · AI/금리/유가/반도체 regime · 다음 이벤트 · 큰 가격 변화(핵심 변수 방향)."""
    mr = ctx.get("market_regime") or {}
    key = {"off": mr.get("official"), "cand": mr.get("candidate"), "ts": mr.get("transition_status"),
           "drv": [(d.get("driver"), d.get("direction")) for d in (ctx.get("market_drivers") or [])][:4],
           "ai": (ctx.get("ai_theme") or {}).get("regime"), "rates": (ctx.get("rates") or {}).get("regime"), "oil": (ctx.get("oil") or {}).get("regime"),
           "semi": ((ctx.get("semiconductor_cycle") or {}) or {}).get("regime"), "next": [(u.get("date"), u.get("event")) for u in (ctx.get("upcoming_events") or [])][:2],
           "big": sorted((k.get("label"), 1 if (k.get("z") or 0) > 0 else -1) for k in (ctx.get("key_variables") or []) if abs(k.get("z") or 0) >= 2)}
    return hashlib.sha256(json.dumps(key, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def live_overview(doc: Mapping[str, Any], *, client: Any = None) -> dict:
    ctx = build_context(doc)
    fp = fingerprint(ctx)
    with _LOCK:
        hit = _LIVE.get(fp)
    if hit is not None:
        return {**hit, "as_of": ctx.get("as_of_utc"), "snapshot_date": ctx.get("snapshot_date")}
    res = write(ctx, client=client)
    if res.get("status") == "ok":
        with _LOCK:
            _LIVE[fp] = res
    return res


def today_kst() -> date:
    return datetime.now(KST).date()
