"""
INFLATION PRESSURE MAP 하단 해석(2026-10-13) — 현재 구성요소의 상태를 바탕으로 LLM 이 최대 2문장을 쓴다.

템플릿에 숫자를 끼우는 방식이 아니다. 엔진이 다시 읽은 구성요소(상태 · 점수 · 근거 · 결측)만 컨텍스트로 넘기고,
MARKET READ 와 같은 검증(금지어 · 상투 문구 · 인과 단정 · 문장 수)에 '숫자 없음' 을 더해 통과해야만 화면에 오른다.
실패하면 엔진의 규칙 기반 문장과 그 이유가 남는다.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Mapping, Sequence

from ..models.rates_regime import InflationPressureMap, MarketReadMeta, RatesRegime
from .client import LLMClient, LLMFailure
from .rates_read import failure_reason, load_rates_read_config, validate_read

logger = logging.getLogger(__name__)

SCHEMA: dict = {
    "type": "object",
    "properties": {"read": {"type": "string", "description": "INFLATION PRESSURE MAP 하단 해석 — 한국어 1~2문장, 숫자 없음"}},
    "required": ["read"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """당신은 매크로 전략가다. 금리 탭의 INFLATION PRESSURE MAP 맨 아래에 붙는 해석을 쓴다.
화면 위쪽에는 이미 구성요소별 상태(COOLING · EASING · MILD PRESSURE …)와 점수, 근거 계열의 σ, 결측 여부가 칸으로 보인다.
당신의 글은 그 칸들을 하나씩 읽어 주는 것이 아니라, '지금 물가를 위·아래로 움직이는 힘이 어디서 오고, 그 판단이 얼마나 확인됐는가' 를 투자자에게 설명하는 것이다.

[쓰는 법]
- 한국어 평서문 1~2문장. 숫자는 쓰지 않는다(점수·σ·날짜 모두). 불릿·제목·줄바꿈 없이.
- 가장 의미 있는 대비부터 쓴다: 예를 들어 시장 기대인플레와 실물 투입 비용이 같은 쪽인지, 갈리는지.
- 결측(DATA MISSING) 구성요소가 있으면 그만큼 결론을 약하게 쓴다. 결측을 0 이나 중립으로 해석하지 않는다.
- 컨텍스트에 없는 데이터·사건을 상상하지 않는다. 인과를 단정하지 않는다('~에 더 가깝다', '~로 읽힌다').
- 직접 추천(매수·매도·비중 확대/축소), '확률', '전망' 이라는 말, 상투 문구('모니터링해야', '지켜볼 필요', '주된 원인은', '아직 확인되지 않았습니다')를 쓰지 않는다.
- 고정된 문장 틀을 쓰지 않는다.

[출처 급 — 반드시 함께 판단한다]
- 각 구성요소에는 source_class 가 있다: PRIMARY(공식 원자료) · MIRROR(공식 원자료 미러) · SECONDARY(보도로 확인된 공식 발표값) ·
  PROXY(원데이터가 없어 대체 지표 조합으로 추정) · NEWS(수치가 아닌 방향 보조 신호) · UNAVAILABLE(없음).
- 공식 지표와 PROXY 가 같은 방향이면 확신을 조금 더 실어도 된다. PROXY 만 강하면 '대체 지표는 그쪽을 가리키지만 공식 데이터 확인은 부족' 처럼 쓴다.
- NEWS 만 한쪽이면 '서사는 늘었지만 공식 데이터 확인은 아직 부족' 처럼 쓴다. 뉴스를 근거로 공식 물가가 움직였다고 쓰지 않는다.
- 공식 CPI/PCE 와 시장 기대인플레가 같은 방향으로 함께 움직일 때만 '실제 데이터와 시장가격에서 동시 확인' 이라고 쓴다.
- PROXY 기반 신호를 확정된 macro 사실처럼 서술하지 않는다. STALE(오래된) 값은 지금의 신호로 쓰지 않는다.
- 실제 물가 점수는 수준이 아니라 모멘텀(최근 3개월 연율 대 12개월 상승률)이다 — 상승률이 높아도 모멘텀이 낮으면 '둔화 쪽 힘' 이다.
"""

VALIDATE = {"min_sentences": 1, "max_sentences": 2, "max_chars": 240, "max_numbers": 0}


def build_context(imap: InflationPressureMap) -> dict:
    return {
        "signal": imap.signal, "signal_ko": imap.signal_ko, "confirmation": imap.confirmation, "confirmation_ko": imap.confirmation_ko,
        "available_components": imap.available, "total_components": imap.total, "score_scale": imap.scale_note,
        "official_components": imap.official_count, "proxy_components": imap.proxy_count, "news_components": imap.news_count, "unavailable_components": imap.unavailable_count,
        "components": [{"label": i.display_label or i.label, "label_ko": i.label_ko, "state": i.state, "state_ko": i.state_ko, "score": i.score,
                        "source_class": i.source_class, "source": i.source_label, "is_original_data": i.is_original_data, "proxy_components": i.proxy_components or None,
                        "fallback_reason": i.fallback_reason or None, "stale": i.stale, "in_signal": i.in_signal, "evidence": i.evidence_text or None,
                        "values": [f"{v.label} {v.text} [{v.source_class}{' · STALE' if v.stale else ''}]" for v in i.values] or None,
                        "comment": i.comment or None, "missing": i.missing_text or None} for i in imap.items],
    }


def _cfg() -> dict:
    base = load_rates_read_config()
    return {**base, "validate": {**(base.get("validate") or {}), **VALIDATE}}


def check(read: str, ctx: Mapping) -> list[str]:
    return validate_read(read, ctx, _cfg())


def _msg(ctx: Mapping, previous: str | None, problems: Sequence[str]) -> str:
    import json
    m = f"아래 구성요소(JSON)만 근거로 INFLATION PRESSURE MAP 해석을 써라.\n\n{json.dumps(ctx, ensure_ascii=False)}"
    if previous is not None:
        m += f"\n\n이전 답안이 화면 검증을 통과하지 못했다. 고쳐서 다시 써라.\n이전 답안: {previous}\n문제: " + " / ".join(problems)
    return m


def generate(client: LLMClient, ctx: Mapping, *, model: str | None = None) -> tuple[str | None, list[str], str]:
    cfg = _cfg()
    warnings: list[str] = []; previous: str | None = None; problems: list[str] = []
    for attempt in range(1 + int(cfg.get("retries_on_invalid", 1))):
        res = client.interpret(system=SYSTEM_PROMPT, user=_msg(ctx, previous, problems), schema=SCHEMA, effort=str(cfg.get("effort", "high")),
                               max_tokens=int(cfg.get("max_tokens", 16000)), timeout_sec=float(cfg.get("timeout_sec", 120)), model=model)
        if isinstance(res, LLMFailure):
            return None, warnings, failure_reason(res, client)
        read = re.sub(r"\s+", " ", str(res.get("read") or "")).strip()
        problems = check(read, ctx)
        if not problems:
            return read, warnings, ""
        warnings.append(f"검증 {attempt + 1}회차: " + " / ".join(problems))
        previous = read
    return None, warnings, "AI 해석이 화면 검증(숫자 없음·금지어·문장 수)을 통과하지 못했다"


def apply(regime: RatesRegime, *, read: str | None, status: str, reason: str = "", generator: str = "none", warnings: Sequence[str] = (),
          now: datetime | None = None) -> RatesRegime:
    im = regime.inflation_map
    if im is None:
        return regime
    rule = im.read_meta.rule_read if im.read_meta and im.read_meta.rule_read else im.read
    if read:
        meta = MarketReadMeta(source="llm", status="ok", generator=generator, reason=reason, generated_at=now or datetime.now(timezone.utc),  # type: ignore[arg-type]
                              rule_read=rule, warnings=list(warnings))
        new = im.model_copy(update={"read": read, "read_meta": meta})
    else:
        meta = MarketReadMeta(source="rule", status=status, reason=reason, rule_read=rule, warnings=list(warnings))  # type: ignore[arg-type]
        new = im.model_copy(update={"read": rule, "read_meta": meta})
    return regime.model_copy(update={"inflation_map": new})


def attach_inflation_read(regime: RatesRegime, *, client: LLMClient | None, session_read: Mapping | None = None, model: str | None = None) -> RatesRegime:
    """구성요소 → LLM → 검증 → 적용. 실패는 규칙 기반 문장 + 이유. 예외로 새지 않는다."""
    if regime.inflation_map is None:
        return regime
    try:
        ctx = build_context(regime.inflation_map)
        if client is None or not client.enabled:
            read, warnings, reason = None, [], "LLM 비활성 — 키 없음 또는 설정 off"
        else:
            read, warnings, reason = generate(client, ctx, model=model)
            if read:
                return apply(regime, read=read, status="ok", generator="api", warnings=warnings)
        if session_read is not None:
            sread = re.sub(r"\s+", " ", str(session_read.get("read") or "")).strip()
            problems = check(sread, ctx)
            if not problems:
                return apply(regime, read=sread, status="ok", generator="session", reason=f"API 호출 실패({reason}) — 같은 컨텍스트·프롬프트·검증으로 세션 생성",
                             warnings=warnings)
            warnings = warnings + ["세션 생성본 검증 실패: " + " / ".join(problems)]
        return apply(regime, read=None, status="fallback", reason=reason, warnings=warnings)
    except Exception:
        logger.exception("INFLATION PRESSURE 해석 실패 — 규칙 기반 문장 유지")
        return apply(regime, read=None, status="fallback", reason="AI 해석 생성 중 오류")
