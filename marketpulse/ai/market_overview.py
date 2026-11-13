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
- state_summary: one short line (≤ 40 chars, no period) telling an investor the market state before any number — what the official regime is doing,
  where it is trying to go and how well equities confirm it (e.g. the idea of "a policy-driven shift is being attempted, equity confirmation still limited" — your own words)
- regime_read: 1–2 short sentences (≤ 170 chars) on the official vs candidate regime, how far the transition is confirmed and what the equity/rates/cross-asset evidence says
- key_drivers: 3–5 items {name, direction: POSITIVE|NEGATIVE|MIXED, strength: STRONG|MODERATE|WEAK, read: one line}
- equity_view — synthesis and comparison, not a list of indices. `equity_terms` are the dashboard's own words for each market (trend, breadth, style, confirmation)
  and are shown next to your text: your text must agree with them, never restate them as a list. Read leadership × breadth together
  (e.g. strong leaders + weak participation = leaders strong but the rally is not broadening; strong leaders + improving breadth = leadership spreading):
  {global_read: 2–3 sentences (≤ 260 chars) on the US and Korean equity market as one picture — what leads, how broad, which style — and how to read equities overall,
   us: {headline: ≤ 28 chars, no period — what kind of market this is (e.g. leadership-driven rebound / rally not broadening, in your words),
        why: one sentence (≤ 70 chars) on why its confirmation status (`equity_terms.us.confirmation`) is what it is — the concrete reason,
        leadership: 0–2 names of what is actually leading (names only from `leadership_names`; [] if nothing leads)},
   korea: same shape as us (Korea leadership may use `korea_sector_moves`),
   divergence_label: "US > KOREA" | "KOREA > US" | "US ≈ KOREA",
   divergence: 1–2 sentences (≤ 140 chars) on what the two markets share and where they differ}
- rates_view — interpretation first, not a metric list (the 10Y level, real yield, breakeven and curve are shown next to your text; do not restate them as numbers):
  {headline: ≤ 40 chars, no period — the cause of the rates move AND what it does to equities, in your words (the idea of "Fed repricing lifts real yields, a burden on growth stocks"),
   summary: one sentence (≤ 90 chars) — what is really driving rates: weigh inflation pressure / breakevens against real yields and the front end, say which one matters,
   equity_impact: POSITIVE | NEGATIVE | MIXED | NEUTRAL — the net effect of this rates environment on equities (falling yields on growth fear are not automatically POSITIVE),
   equity_impact_read: 1–2 sentences (≤ 110 chars) — which equities are hit or helped and why}
- cross_asset_view — the relationship between assets, not a list of them. It must read as the continuation of rates_view
  (rates burden → do credit and volatility confirm stress or contain it → so is this broad risk-off or a valuation / discount-rate adjustment?):
  {headline: ≤ 40 chars, no period — the cross-asset character of the market now, in your words. Put oil / geopolitics in the headline only when it is a main driver
   (a flat oil price with an unconfirmed premium is secondary),
   summary: one sentence (≤ 80 chars) — the key relationship,
   support: 0–3 asset names that currently support equities, risk: 0–3 asset names that weigh on them — names only from `cross_asset[].asset`, no asset in both,
   2–5 names in total, the ones that best explain the market (each asset's `state` word is shown next to it),
   read: 1–2 sentences (≤ 120 chars) — what kind of pressure or support this combination is}
- ai_semiconductor_view: 1–2 sentences connecting AI price leadership with the semiconductor/memory fundamentals
- leadership_view: one line on where leadership is and how broad
- style_view: items {style: one of Growth|Value|Quality|Momentum|High Beta|Low Vol|Cyclical|Defensive, view: POSITIVE|IMPROVING|NEUTRAL|MIXED|NEGATIVE, read: one short line} — only styles the data speaks to
- sector_view: {positive: [names], watch: [names], negative: [names], read: one line} — names only from `sector_names`
- top_risks: 3–5 items {risk, level: LOW|MODERATE|ELEVATED|HIGH, read: one line on what could shake the market}
- catalysts: items {date (YYYY-MM-DD from upcoming_events), event (its name), why: one line, sensitivity: HIGH|MEDIUM|LOW}
- what_matters_next: 3–5 items {title, condition: market condition in plain words, implication: what it would mean}
- portfolio_implication: {equity_stance, style, sector, risk_control, hedge_watch} — one short line each"""

_ITEM = lambda props: {"type": "object", "properties": {k: {"type": "string"} for k in props}, "required": list(props), "additionalProperties": False}  # noqa: E731
_EQ_SIDE = {"type": "object", "properties": {"headline": {"type": "string"}, "why": {"type": "string"}, "leadership": {"type": "array", "items": {"type": "string"}}},
            "required": ["headline", "why", "leadership"], "additionalProperties": False}
SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"}, "market_view": {"type": "string"},
        "labels": _ITEM(["regime", "equity", "macro", "risk"]),
        "state_summary": {"type": "string"}, "regime_read": {"type": "string"},
        "key_drivers": {"type": "array", "items": _ITEM(["name", "direction", "strength", "read"])},
        "equity_view": {"type": "object", "properties": {"global_read": {"type": "string"}, "us": _EQ_SIDE, "korea": _EQ_SIDE,
                                                         "divergence_label": {"type": "string"}, "divergence": {"type": "string"}},
                        "required": ["global_read", "us", "korea", "divergence_label", "divergence"], "additionalProperties": False},
        "rates_view": _ITEM(["headline", "summary", "equity_impact", "equity_impact_read"]),
        "cross_asset_view": {"type": "object", "properties": {"headline": {"type": "string"}, "summary": {"type": "string"}, "support": {"type": "array", "items": {"type": "string"}},
                                                              "risk": {"type": "array", "items": {"type": "string"}}, "read": {"type": "string"}},
                             "required": ["headline", "summary", "support", "risk", "read"], "additionalProperties": False}, "ai_semiconductor_view": {"type": "string"}, "leadership_view": {"type": "string"},
        "style_view": {"type": "array", "items": _ITEM(["style", "view", "read"])},
        "sector_view": {"type": "object", "properties": {"positive": {"type": "array", "items": {"type": "string"}}, "watch": {"type": "array", "items": {"type": "string"}},
                                                         "negative": {"type": "array", "items": {"type": "string"}}, "read": {"type": "string"}},
                        "required": ["positive", "watch", "negative", "read"], "additionalProperties": False},
        "top_risks": {"type": "array", "items": _ITEM(["risk", "level", "read"])},
        "catalysts": {"type": "array", "items": _ITEM(["date", "event", "why", "sensitivity"])},
        "what_matters_next": {"type": "array", "items": _ITEM(["title", "condition", "implication"])},
        "portfolio_implication": _ITEM(["equity_stance", "style", "sector", "risk_control", "hedge_watch"]),
    },
    "required": ["headline", "market_view", "labels", "state_summary", "regime_read", "key_drivers", "equity_view", "rates_view", "cross_asset_view", "ai_semiconductor_view",
                 "leadership_view", "style_view", "sector_view", "top_risks", "catalysts", "what_matters_next", "portfolio_implication"],
    "additionalProperties": False,
}
ENUM = {"equity": {"Bullish", "Improving", "Mixed", "Weak"}, "macro": {"Tailwind", "Neutral", "Headwind"}, "risk": {"Low", "Moderate", "Elevated", "High"}}
DIRS = {"POSITIVE", "NEGATIVE", "MIXED"}; STRENGTHS = {"STRONG", "MODERATE", "WEAK"}
STYLES = {"Growth", "Value", "Quality", "Momentum", "High Beta", "Low Vol", "Cyclical", "Defensive"}
STYLE_VIEWS = {"POSITIVE", "IMPROVING", "NEUTRAL", "MIXED", "NEGATIVE"}
RISK_LEVELS = {"LOW", "MODERATE", "ELEVATED", "HIGH"}; SENS = {"HIGH", "MEDIUM", "LOW"}
DIVERGENCE = {"US > KOREA", "KOREA > US", "US ≈ KOREA"}
EQUITY_IMPACT = {"POSITIVE", "NEGATIVE", "MIXED", "NEUTRAL"}

# ── Cross-asset z → 상태 단어 (2026-11-13). 화살표와 같은 ±0.5 / ±1.5 문턱을 자산 성격에 맞는 단어로 옮긴 표시 규칙 — 프론트 caState 와 같은 표.
#    (+강, +약, 중립, −약, −강). Credit 은 스프레드(HY OAS)라 내려가면 개선이다.
CA_WORDS = {
    "EQUITY": ("STRONG", "FIRM", "FLAT", "SOFT", "WEAK"), "RATES": ("RISING", "RISING", "STABLE", "FALLING", "FALLING"),
    "CREDIT": ("STRESSED", "WIDENING", "STABLE", "IMPROVING", "IMPROVING"), "VOLATILITY": ("SPIKING", "RISING", "STABLE", "CALMING", "CALMING"),
    "USD": ("STRONG", "STRONG", "STABLE", "WEAK", "WEAK"), "OIL": ("SURGING", "RISING", "NEUTRAL", "FALLING", "SLIDING"), "GOLD": ("RISING", "RISING", "STABLE", "FALLING", "FALLING"),
}


def ca_state(key: Any, z: Any) -> str:
    w = CA_WORDS.get(str(key or "").upper()) or ("RISING", "RISING", "STABLE", "FALLING", "FALLING")
    if z is None:
        return "UNAVAILABLE"
    z = float(z)
    return w[0] if z >= 1.5 else w[1] if z >= 0.5 else w[4] if z <= -1.5 else w[3] if z <= -0.5 else w[2]


def bp_dir(bp: Any) -> str | None:
    """5일 bp 변화 → RISING · FALLING · FLAT(1bp 미만). 값이 없으면 None."""
    if bp is None:
        return None
    return "FLAT" if abs(float(bp)) < 1 else "RISING" if float(bp) > 0 else "FALLING"

# ── 주식 신호 → 화면 단어 (2026-11-13). 새 계산이 아니라 기존 neutral_equity 신호값을 읽는 표시 규칙 — 프론트 MarketOverviewView 의 eqTerms 와 같은 문턱.
#    값은 위험선호 기준 z(1D·5D 혼합) · 대표 종목 상승 비율(0~1). 문턱을 바꾸면 양쪽을 같이 바꾼다(tests/test_market_overview · marketOverview.test 가 같은 사례를 본다).
def _trend_word(z: float | None) -> str:
    if z is None:
        return "UNAVAILABLE"
    return "STRONG" if z >= 1.5 else "POSITIVE" if z >= 0.5 else "WEAK" if z <= -1.5 else "NEGATIVE" if z <= -0.5 else "NEUTRAL"


def _breadth_z_word(z: float | None) -> str:
    if z is None:
        return "UNAVAILABLE"
    return "BROAD" if z >= 1.0 else "IMPROVING" if z >= 0.5 else "WEAK" if z <= -1.0 else "NARROW" if z <= -0.5 else "MIXED"


def _breadth_ratio_word(r: float | None) -> str:
    if r is None:
        return "UNAVAILABLE"
    return "BROAD" if r >= 0.65 else "MIXED" if r >= 0.5 else "NARROW" if r >= 0.35 else "WEAK"


def _rel_word(v: float | None, a: str, b: str) -> str | None:
    if v is None:
        return None
    return f"{a} > {b}" if v >= 0.5 else f"{b} > {a}" if v <= -0.5 else f"{a} ≈ {b}"


def equity_terms(ne: Mapping[str, Any], conf: Mapping[str, Any] | None = None) -> dict:
    """neutral_equity(us · kr 신호) → {us, korea}: trend · breadth · style 단어와 그 근거값. 없는 신호는 UNAVAILABLE(0 으로 메우지 않는다)."""
    conf = conf or {}

    def val(m: str, key: str) -> float | None:
        for g in ((ne.get(m) or {}).get("signals") or []):
            if g.get("key") == key and g.get("state") != "EXCLUDED" and g.get("value") is not None:
                return float(g["value"])
        return None

    def mean(xs: list[float | None]) -> float | None:
        a = [x for x in xs if x is not None]
        return sum(a) / len(a) if a else None

    us_b = val("us", "breadth_us")
    kr_whole = val("kr", "breadth_kospi"); kr_proxy = val("kr", "breadth_kr")
    kr_b = _breadth_z_word(kr_whole) if kr_whole is not None else _breadth_ratio_word(kr_proxy)
    return {
        "us": {"trend": _trend_word(mean([val("us", "spx"), val("us", "ndx")])), "breadth": _breadth_z_word(us_b),
               "breadth_basis": "S&P 500 상승종목 비율" if us_b is not None else "상승종목 비율 데이터 없음",
               "style": [x for x in (_rel_word(val("us", "small_rel"), "SMALL", "LARGE"), _rel_word(val("us", "cyc_def"), "CYCLICAL", "DEFENSIVE")) if x],
               "confirmation": conf.get("us")},
        "korea": {"trend": _trend_word(mean([val("kr", "kospi"), val("kr", "kosdaq")])), "breadth": kr_b,
                  "breadth_basis": ("KOSPI 상승종목 비율" if kr_whole is not None else
                                    f"상승 참여율 {round(kr_proxy * 100)}% (대표 종목 기준)" if kr_proxy is not None else "상승종목 비율 데이터 없음"),
                  "participation_pct": None if kr_proxy is None else round(kr_proxy * 100),
                  "style": [x for x in (_rel_word(val("kr", "kosdaq_rel"), "KOSDAQ", "KOSPI"), _rel_word(val("kr", "cyc_kr"), "CYCLICAL", "INDEX")) if x],
                  "confirmation": conf.get("korea")},
    }


def korea_sector_moves(inv: Mapping[str, Any] | None) -> list[dict]:
    """한국 대표 종목(투자 섹션, 같은 cutoff) → 업종별 묶음: 종목 수 · 5일 평균 수익률 · 하루 상승 종목 수 · 대표 이름. 리더십 후보를 읽는 근거(판정 아님)."""
    stocks = (inv or {}).get("stocks") or {}
    groups: dict[str, list[tuple[str, float | None, float | None]]] = {}
    for s in stocks.values() if isinstance(stocks, Mapping) else []:
        meta = s.get("meta") or {}; pr = ((s.get("feature") or {}).get("price")) or {}
        if meta.get("market") not in ("KOSPI", "KOSDAQ") or not meta.get("sector"):
            continue
        groups.setdefault(str(meta["sector"]), []).append((str(meta.get("name") or meta.get("id")), pr.get("ret_5d"), pr.get("ret_1d")))
    out = []
    for sec, rows in groups.items():
        r5 = [x[1] for x in rows if x[1] is not None]
        if not r5:
            continue
        top = sorted((x for x in rows if x[1] is not None), key=lambda x: -x[1])[:2]
        out.append({"sector": sec.replace("_", " ").title(), "stocks": len(rows), "avg_ret_5d_pct": round(sum(r5) / len(r5), 1),
                    "up_1d": sum(1 for x in rows if (x[2] or 0) > 0), "top": [t[0] for t in top]})
    return sorted(out, key=lambda x: -x["avg_ret_5d_pct"])
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
    ksm = korea_sector_moves(doc.get("investment"))
    if not ksm:
        missing.append("한국 대표 종목 업종 묶음 없음")
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
        "equity_terms": equity_terms(ne, {"us": sel.get("us_equity_confirmation"), "korea": sel.get("korea_equity_confirmation")}),
        "korea_sector_moves": ksm,
        "key_variables": [{"label": k.get("label"), "z": _r(k.get("z"), 1), "change": k.get("change_display")} for k in (now.get("key_variables") or [])],
        "cross_asset": [{"asset": r.get("label"), "instrument": r.get("instrument_label"), "z": _r(r.get("z"), 1), "arrow": r.get("arrow"), "state": ca_state(r.get("key"), r.get("z"))}
                        for r in ((ck.get("cross_asset") or {}).get("rows") or [])],
        "divergences": [d.get("title") + ": " + (d.get("meaning") or "") for d in ((ck.get("cross_asset") or {}).get("divergences") or [])][:3],
        "leadership_themes": leadership,
        "rates": {"regime": rr.get("regime_label"), "headline": rr.get("headline"), "direction": (rr.get("top") or {}).get("direction_en"),
                  "primary_driver": ((rr.get("top") or {}).get("primary") or {}).get("label"), "us10y_level": (rr.get("rate_move") or {}).get("level"),
                  "us10y_5d_bp": (rr.get("rate_move") or {}).get("change_5d_bp"), "curve_shape": (rr.get("curve_move") or {}).get("shape"),
                  "us10y_5d_real_bp": t10.get("real_bp"), "us10y_5d_breakeven_bp": t10.get("breakeven_bp"),
                  "real_yield_direction": bp_dir(t10.get("real_bp")), "breakeven_direction": bp_dir(t10.get("breakeven_bp")), "decomposition_read": t10.get("line"),
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
    ctx["leadership_names"] = sorted(set(sector_names) | {k["sector"] for k in ksm})
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
    ss = str(o["state_summary"]).strip()
    if len(ss) > 40 or ss.endswith(".") or "\n" in ss:
        p.append("state_summary 는 40자 이내 한 줄, 마침표 없이")
    rr_ = str(o["regime_read"]).strip()
    if not 1 <= len(split_sentences(rr_)) <= 2 or len(rr_) > 170:
        p.append("regime_read 는 1~2문장 · 170자 이내")
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
    ev_ = o["equity_view"]
    if ev_.get("divergence_label") not in DIVERGENCE:
        p.append("equity_view.divergence_label 값")
    gr = str(ev_.get("global_read") or "").strip()
    if not 2 <= len(split_sentences(gr)) <= 3 or len(gr) > 260:
        p.append("equity_view.global_read 는 2~3문장 · 260자 이내")
    dv = str(ev_.get("divergence") or "").strip()
    if not 1 <= len(split_sentences(dv)) <= 2 or len(dv) > 140:
        p.append("equity_view.divergence 는 1~2문장 · 140자 이내")
    names = [str(x).lower() for x in ctx.get("leadership_names") or ctx.get("sector_names") or []]
    for side in ("us", "korea"):
        sd_ = ev_.get(side) or {}
        if not isinstance(sd_, Mapping):
            p.append(f"equity_view.{side} 는 headline · why · leadership 객체"); continue
        h = str(sd_.get("headline") or "").strip(); w = str(sd_.get("why") or "").strip()
        if not h or len(h) > 28 or h.endswith(".") or "\n" in h:
            p.append(f"equity_view.{side}.headline 은 28자 이내 한 줄, 마침표 없이")
        if not w or len(w) > 70 or len(split_sentences(w)) != 1:
            p.append(f"equity_view.{side}.why 는 한 문장 · 70자 이내")
        ld_ = sd_.get("leadership") or []
        if len(ld_) > 2:
            p.append(f"equity_view.{side}.leadership 는 2개 이내")
        for nm in ld_:
            if str(nm).lower() not in names:
                p.append(f"equity_view.{side}.leadership '{nm}' 는 leadership_names 에 없다")
    rv = o["rates_view"]; cv = o["cross_asset_view"]
    if not isinstance(rv, Mapping) or not isinstance(cv, Mapping):
        p.append("rates_view · cross_asset_view 는 객체(headline · summary …)")
    else:
        for nm, vv, hmax, smax in (("rates_view", rv, 40, 90), ("cross_asset_view", cv, 40, 80)):
            h = str(vv.get("headline") or "").strip(); sm = str(vv.get("summary") or "").strip()
            if not h or len(h) > hmax or h.endswith(".") or "\n" in h:
                p.append(f"{nm}.headline 은 {hmax}자 이내 한 줄, 마침표 없이")
            if not sm or len(sm) > smax or len(split_sentences(sm)) != 1:
                p.append(f"{nm}.summary 는 한 문장 · {smax}자 이내")
        if rv.get("equity_impact") not in EQUITY_IMPACT:
            p.append(f"rates_view.equity_impact 는 {sorted(EQUITY_IMPACT)} 중 하나")
        ir = str(rv.get("equity_impact_read") or "").strip()
        if not 1 <= len(split_sentences(ir)) <= 2 or len(ir) > 110:
            p.append("rates_view.equity_impact_read 는 1~2문장 · 110자 이내")
        cr = str(cv.get("read") or "").strip()
        if not 1 <= len(split_sentences(cr)) <= 2 or len(cr) > 120:
            p.append("cross_asset_view.read 는 1~2문장 · 120자 이내")
        assets = {str(r.get("asset")) for r in ctx.get("cross_asset") or [] if r.get("z") is not None}
        sup = [str(x) for x in cv.get("support") or []]; rk = [str(x) for x in cv.get("risk") or []]
        for nm in sup + rk:
            if nm not in assets:
                p.append(f"cross_asset_view '{nm}' 는 cross_asset 에 없는(또는 결측) 자산")
        if set(sup) & set(rk):
            p.append("cross_asset_view support 와 risk 에 같은 자산")
        if len(sup) > 3 or len(rk) > 3 or not 2 <= len(sup) + len(rk) <= 5 or len(set(sup + rk)) != len(sup + rk):
            p.append("cross_asset_view support · risk 는 각 0~3개, 합쳐 2~5개, 중복 없이")
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
           "semi": ((ctx.get("semiconductor_cycle") or {}) or {}).get("regime"),
           "eq": {m: [t.get("trend"), t.get("breadth"), t.get("confirmation")] for m, t in (ctx.get("equity_terms") or {}).items()},
           "ca": [(r.get("asset"), r.get("state")) for r in (ctx.get("cross_asset") or [])],
           "rt": [(ctx.get("rates") or {}).get("real_yield_direction"), (ctx.get("rates") or {}).get("breakeven_direction"), (ctx.get("rates") or {}).get("curve_shape")], "next": [(u.get("date"), u.get("event")) for u in (ctx.get("upcoming_events") or [])][:2],
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
