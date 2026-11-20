"""
RECENT TRANSITIONS — 공식 regime 전환 이유를 LLM 이 그날 데이터로 직접 쓴다 (2026-11-12 요청, exit_entry_v2 전환부터).

고정 코멘트 목록 · 템플릿 선택 · 문구 사전을 쓰지 않는다. 그 전환이 확정된 Daily Snapshot 의 cutoff 에 이미 있던 데이터
(공식 상태 변화 · factor 전날 대비 · 그날 주도 변수 · 주식 확인 · 신용 · 변동성 · 금리 · 유가 · 환율 · 지표/정책 이벤트 · 태깅된 뉴스 ·
그날 REGIME 선택 해설)만 컨텍스트로 준다 — 뒤에 알게 된 사실은 넣지 않는다(look-ahead 없음).

순서: API → 같은 컨텍스트 · 프롬프트 · 검증을 통과한 세션 생성본(capture 의 transition_read_session.json) → 없음(화면이 저장 데이터로 고른 문장).
검증: 1~3문장 · 직접 추천 · 확률 · 전망 표현 금지 · 컨텍스트에 없는 숫자 금지.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .rates_read import _phrase_hits, failure_reason, load_rates_read_config, number_check, split_sentences

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """당신은 주식 · 매크로 운용역이다. 대시보드의 RECENT TRANSITIONS 칸에 '이 날짜에 왜 공식 시장 레짐이 바뀌었는지' 를 쓴다.

규칙
- 컨텍스트(JSON)에 있는 사실만 쓴다. 컨텍스트에 없는 숫자 · 사건 · 기업을 만들지 않는다.
- 고정된 이벤트 우선순위를 쓰지 않는다. 이벤트 · 뉴스 · 주식(미국 · 한국) · 신용 · 변동성 · 금리 · 유가 · 환율 · 업종 움직임 중 그날 실제로 크게 움직였고
  전환 방향과 이어지는 것을 2~3개 골라, '무슨 일이 있었고 → 시장이 어떻게 반응했고 → 그래서 레짐이 어떻게 됐는지' 를 이어 쓴다.
- 전환 종류를 정확히 쓴다. kind=exit 이면 '이전 레짐의 근거가 연속으로 지지되지 않아 해제됐고, 새 레짐은 아직 확정되지 않아 Neutral / Mixed' 라는 뜻이다
  (새 레짐이 왔다고 쓰지 않는다). kind=entry 이면 같은 후보가 서로 다른 거래일 연속 선택돼 새 레짐이 확정된 것이다.
- 'Nasdaq ↑ VIX ↓' 같은 신호 나열이 아니라 사람이 바로 이해하는 문장으로. 뚜렷한 단일 사건이 없으면 그렇게 말하고 누적된 시장 움직임으로 설명한다.
- '특별한 사건 없이', '최근 며칠간' 같은 정보 없는 문구만으로 채우지 않는다.
- 1~3문장, 한국어, 존댓말 서술형(…습니다). 숫자는 꼭 필요한 것만 2개 이내.
- '확률', '매수', '매도', '전망', '목표가' 라는 말을 쓰지 않는다. 투자 권유를 하지 않는다.

출력: {"why": "문장"}"""

SCHEMA = {"type": "object", "properties": {"why": {"type": "string"}}, "required": ["why"], "additionalProperties": False}
FORBIDDEN_EXTRA = ["목표가"]


def _num(v: Any, nd: int = 2) -> float | None:
    try:
        return None if v is None else round(float(v), nd)
    except (TypeError, ValueError):
        return None


def build_context(doc: Mapping[str, Any], state: Mapping[str, Any], days: Sequence[Mapping[str, Any]]) -> dict:
    """doc = 그 Daily Snapshot 의 저장본 형식(cockpit · snapshot · rates_regime), state = 그날 공식 상태(RegimeStateView), days = 그날까지의 history 행(최근 몇 개)."""
    ck = doc.get("cockpit") or {}
    now = ck.get("market_now") or {}
    sel = now.get("selection") or {}
    d_today = days[-1] if days else {}
    d_prev = days[-2] if len(days) >= 2 else {}
    fac = {k: {"prev": _num((d_prev.get("factors") or {}).get(k)), "today": _num((d_today.get("factors") or {}).get(k))}
           for k in (d_today.get("factors") or {}).keys()}
    drivers = [{"label": d.get("label"), "direction": d.get("direction"), "strength": _num(d.get("strength")), "why": d.get("why"),
                "evidence": [{"label": e.get("label"), "z": _num(e.get("z"), 1), "display": e.get("display")} for e in (d.get("evidence") or []) if e.get("available", True)][:4]}
               for d in (ck.get("drivers") or [])[:5]]
    cross = [{"asset": r.get("label"), "instrument": r.get("instrument_label"), "z": _num(r.get("z"), 1), "arrow": r.get("arrow")} for r in ((ck.get("cross_asset") or {}).get("rows") or [])]
    keyvars = [{"label": k.get("label"), "z": _num(k.get("z"), 1), "change": k.get("change_display")} for k in (now.get("key_variables") or [])]
    ev = (doc.get("rates_regime") or {}).get("events") or {}
    events = [{"date": r.get("date"), "title": r.get("title"), "result": r.get("label")} for r in (ev.get("recent") or [])][:4] + \
             [{"date": p.get("date"), "bank": p.get("bank"), "decision": p.get("decision"), "tone": p.get("tone")} for p in (ev.get("policy") or [])][:4]
    cutoff = str(doc.get("cutoff") or (doc.get("snapshot") or {}).get("as_of") or "")
    news = []
    for e in sorted((doc.get("snapshot") or {}).get("events") or [], key=lambda x: -(x.get("impact_score") or 0)):
        if (e.get("impact_score") or 0) < 40:
            continue
        news.append({"title": e.get("event"), "themes": e.get("themes"), "sentiment": e.get("sentiment"), "summary": e.get("reason")})
        if len(news) >= 8:
            break
    neq = sel.get("neutral_equity") or {}
    return {
        "snapshot_date": state.get("snapshot_date"), "market_date": state.get("date"), "cutoff": cutoff,
        "transition": {"kind": state.get("change_kind"), "from": state.get("exited_label") or state.get("previous_official_label"), "to": state.get("official_label"),
                       "exit_streak": state.get("exit_streak"), "exit_required": state.get("exit_required"), "entry_streak": state.get("entry_streak"),
                       "entry_required": state.get("entry_required"), "support_today": state.get("support"), "support_reasons": state.get("support_reasons")},
        "recent_daily_states": [{"date": d.get("date"), "candidate": ((d.get("state") or {}).get("candidate_label")), "official": d.get("display_label"),
                                 "support": ((d.get("state") or {}).get("support"))} for d in days[-5:]],
        "factors_prev_vs_today": fac,
        "today_drivers": drivers, "key_variables": keyvars, "cross_asset_z": cross,
        "equity_broad_risk_on_basis": {m: {"status": (neq.get(m) or {}).get("status"), "score": _num((neq.get(m) or {}).get("score"))} for m in ("us", "kr")},
        "selection_today": {"selected": sel.get("selected_regime"), "commentary": sel.get("commentary"), "primary_reason": sel.get("primary_reason")},
        "events": events, "news": news,
    }


def context_text(ctx: Mapping) -> str:
    return json.dumps(ctx, ensure_ascii=False, indent=1)


def check(text: str, ctx: Mapping) -> list[str]:
    """문제 목록 — 비면 통과."""
    t = (text or "").strip()
    if not t:
        return ["문장이 비어 있다"]
    problems: list[str] = []
    n = len(split_sentences(t))
    if not 1 <= n <= 3:
        problems.append(f"문장 수 {n} — 1~3문장이어야 한다")
    if len(t) > 360:
        problems.append(f"길이 {len(t)}자 — 360자 이내")
    v = dict((load_rates_read_config().get("validate") or {}))
    v["forbidden"] = list(v.get("forbidden") or []) + FORBIDDEN_EXTRA
    v["filler"] = list(v.get("filler") or []) + ["특별한 사건 없이"]
    problems += _phrase_hits(t, v)
    _n, invented, _rep = number_check(t, {**ctx, "displayed_elsewhere": {"numbers": []}})
    if invented:
        problems.append(f"컨텍스트에 없는 숫자: {', '.join(invented)}")
    if ctx.get("transition", {}).get("kind") == "exit" and ("Neutral" not in t and "중립" not in t):
        problems.append("공식 해제(exit) 전환은 Neutral / Mixed 로 간 것을 적어야 한다")
    return problems


def generate(client: Any, ctx: Mapping) -> tuple[dict | None, str]:
    """(출력, 실패 사유)."""
    previous: str | None = None; problems: list[str] = []
    for _ in range(2):
        user = f"아래 컨텍스트만 근거로 쓴다.\n\n{context_text(ctx)}"
        if previous is not None:
            user += f"\n\n이전 답안이 검증을 통과하지 못했다. 고쳐 다시 써라.\n이전 답안: {previous}\n문제: " + " / ".join(problems)
        res = client.interpret(system=SYSTEM_PROMPT, user=user, schema=SCHEMA, effort="high", max_tokens=8000, timeout_sec=120)
        if not isinstance(res, Mapping):
            return None, failure_reason(res, client)
        why = str(res.get("why") or "").strip()
        problems = check(why, ctx)
        if not problems:
            return {"why": why}, ""
        previous = why
    return None, "전환 해설이 검증(숫자 대조 · 금지어 · 문장 수)을 통과하지 못했다"


def write(ctx: Mapping, *, client: Any = None, session_read: Mapping | None = None) -> dict | None:
    """API → 세션 생성본 → None. 반환 = 상태 로그의 transition_comment."""
    reason = "LLM 비활성 — 키 없음 또는 설정 off"
    if client is not None and getattr(client, "enabled", False):
        try:
            out, reason = generate(client, ctx)
        except Exception:  # noqa: BLE001
            logger.exception("전환 해설 생성 실패")
            out, reason = None, "전환 해설 생성 중 오류"
        if out is not None:
            return {"text": out["why"], "source": "llm", "generated_at": datetime.now(timezone.utc).isoformat(), "reason": ""}
    if session_read is not None:
        why = str(session_read.get("why") or "").strip()
        problems = check(why, ctx)
        if not problems:
            return {"text": why, "source": "session", "generated_at": datetime.now(timezone.utc).isoformat(),
                    "reason": f"API 호출 실패({reason}) — 같은 컨텍스트·프롬프트·검증으로 세션 생성"}
        logger.warning("전환 해설 세션본 검증 실패: %s", " / ".join(problems))
    return None
