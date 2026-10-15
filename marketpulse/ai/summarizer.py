"""
AI Market Summary (요구 6, 설계서 STEP 7.3).

LLM 의 역할은 **판정이 아니라 설명**이다. 상태 라벨, 신뢰도, factor, 괴리는
전부 정량 엔진이 이미 계산했다. 여기서는 그 결과를 자연어로 다듬기만 한다.

숫자 검증
---------
생성된 문장에 등장하는 모든 수치가 입력 사실에 실제로 존재해야 한다.
하나라도 없으면 문장을 버리고 템플릿으로 되돌아간다. 지어낸 숫자가 화면에
오르는 것보다 덜 매끄러운 문장이 낫다.

이 검증이 없으면 "VIX 가 18.4 까지 올랐다" 같은 그럴듯한 거짓이 통과한다.
운용자는 그 숫자를 믿고 판단한다.
"""

from __future__ import annotations

import logging
import re
from typing import Sequence

from ..models.divergence import Divergence
from ..models.state import MarketState
from ..models.theme import ThemeState
from .client import SUMMARY_EFFORT, LLMClient, LLMFailure

logger = logging.getLogger(__name__)

SUMMARIZER_VERSION = "0.1.0"

#: 수치로 볼 토큰. 부호와 천단위 구분 기호를 포함해 잡는다.
_NUMBER = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "watch": {"type": "string"},
    },
    "required": ["summary", "watch"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """당신은 자산운용사 운용역에게 아침 브리핑을 쓰는 애널리스트다.

아래 '확정된 사실'은 정량 엔진이 가격·수급 데이터로 이미 계산한 결과다.
당신의 일은 판단이 아니라 **설명**이다.

절대 규칙

1. 확정된 사실에 없는 수치를 쓰지 않는다. 숫자를 새로 만들거나 추정하지
   않는다. 사실에 적힌 수치만 그대로 인용한다.
2. 상태 판정을 뒤집거나 다시 하지 않는다. 엔진이 Inflation Shock 이라고
   했으면 그것을 설명하는 것이지 재평가하는 것이 아니다.
3. 사실에 없는 인과를 단정하지 않는다. 추정이면 "가능성", "여지" 같은 말로
   불확실성을 드러낸다.
4. 확인되지 않은 신호가 있으면 반드시 언급한다. 그것이 이 시스템의 존재
   이유다.

형식

- summary: 3~4문장. 무엇이 움직였고, 그것이 무엇을 뜻하며, 어디가 아직
  확인되지 않았는지. 한국어 평서문.
- watch: 1~2문장. 다음에 확인할 지점. 한국어 평서문.
- 불릿, 제목, 마크다운을 쓰지 않는다. 문장으로만 쓴다.
"""


def _fmt(value: float, digits: int = 1) -> str:
    return f"{value:+.{digits}f}"


def build_facts(
    state: MarketState,
    themes: Sequence[ThemeState],
    divergences: Sequence[Divergence],
    *,
    theme_limit: int = 5,
    divergence_limit: int = 3,
) -> str:
    """LLM 에 넘길 확정 사실. 여기 없는 숫자는 문장에 나올 수 없다."""
    lines: list[str] = ["[시장 상태]"]
    label = state.primary_label.value
    if state.secondary_label:
        label += f" / {state.secondary_label.value}"
    lines.append(f"판정: {label}")
    lines.append(f"신뢰도: {state.confidence:.0f}%")

    if state.main_drivers:
        lines.append("주도 변수:")
        for d in state.main_drivers:
            lines.append(f"  - {d.label} {_fmt(d.z, 2)}σ")

    if state.factors:
        ranked = sorted(state.factors.values(), key=lambda f: -abs(f.score))[:5]
        lines.append("주요 factor:")
        for f in ranked:
            lines.append(f"  - {f.factor} {_fmt(f.score, 2)}")

    c = state.cross_asset_confirmation
    if c.expected:
        lines.append("[Cross-asset 확인]")
        lines.append(f"판정: {c.verdict}")
        if c.confirmed:
            lines.append(f"기대대로 움직인 자산: {', '.join(c.confirmed)}")
        if c.unconfirmed:
            lines.append(f"반응이 제한적인 자산: {', '.join(c.unconfirmed)}")
        if c.conflicting:
            lines.append(f"기대와 반대로 움직인 자산: {', '.join(c.conflicting)}")

    ranked_themes = sorted(themes, key=lambda t: -abs(t.theme_score))[:theme_limit]
    if ranked_themes:
        lines.append("[테마]")
        for t in ranked_themes:
            parts = [f"점수 {_fmt(t.theme_score, 0)}"]
            if t.news_sentiment is not None:
                parts.append(f"뉴스 {_fmt(t.news_sentiment, 0)}")
            if t.price_momentum is not None:
                parts.append(f"가격 {_fmt(t.price_momentum, 0)}")
            if t.flow_momentum is not None:
                parts.append(f"수급 {_fmt(t.flow_momentum, 0)}")
            lines.append(f"  - {t.name}: {', '.join(parts)}")

    if divergences:
        lines.append("[괴리]")
        for d in divergences[:divergence_limit]:
            legs = ", ".join(f"{l.name} {_fmt(l.value, 0)}" for l in d.legs)
            lines.append(f"  - {d.explanation} ({legs})")

    return "\n".join(lines)


def extract_numbers(text: str) -> set[str]:
    """비교용으로 정규화한 수치 토큰. 부호와 천단위 구분은 무시한다."""
    out: set[str] = set()
    for match in _NUMBER.findall(text):
        cleaned = match.lstrip("+-").replace(",", "")
        if not cleaned:
            continue
        # 12.0 과 12 를 같은 것으로 본다
        if "." in cleaned:
            cleaned = cleaned.rstrip("0").rstrip(".") or "0"
        out.add(cleaned)
    return out


def verify_numbers(generated: str, facts: str) -> list[str]:
    """
    문장에 등장하는 수치 중 사실에 없는 것을 돌려준다.

    비어 있으면 통과다. 하나라도 있으면 그 문장은 쓰지 않는다.
    """
    allowed = extract_numbers(facts)
    return sorted(extract_numbers(generated) - allowed)


def summarize(
    state: MarketState,
    themes: Sequence[ThemeState],
    divergences: Sequence[Divergence],
    client: LLMClient,
    *,
    fallback: str | None,
) -> tuple[str | None, str, list[str]]:
    """
    시장 요약을 만든다.

    Returns: (문장, 출처("llm"|"template"|"none"), 경고 목록)

    LLM 이 꺼져 있거나 실패하거나 지어낸 숫자를 쓰면 fallback(템플릿)을
    그대로 돌려준다. 화면은 어느 쪽이든 동작한다.
    """
    warnings: list[str] = []

    if not client.available():
        return fallback, ("template" if fallback else "none"), warnings

    facts = build_facts(state, themes, divergences)
    result = client.structured(
        system=SYSTEM_PROMPT,
        user=f"확정된 사실:\n\n{facts}",
        schema=SCHEMA,
        effort=SUMMARY_EFFORT,
        max_tokens=4000,
    )

    if isinstance(result, LLMFailure):
        logger.warning("AI 요약 실패 (%s): %s", result.kind, result.reason)
        warnings.append(f"AI 요약 실패({result.kind}). 템플릿 문장을 사용했다.")
        return fallback, ("template" if fallback else "none"), warnings

    summary = str(result.get("summary") or "").strip()
    watch = str(result.get("watch") or "").strip()
    if not summary:
        warnings.append("AI 요약이 비어 있다. 템플릿 문장을 사용했다.")
        return fallback, ("template" if fallback else "none"), warnings

    text = summary if not watch else f"{summary} {watch}"
    invented = verify_numbers(text, facts)
    if invented:
        # 지어낸 숫자가 화면에 오르는 것보다 덜 매끄러운 문장이 낫다.
        logger.warning("AI 요약에 근거 없는 수치 %s. 템플릿으로 되돌린다.", invented)
        warnings.append(
            f"AI 요약이 확정 사실에 없는 수치({', '.join(invented[:3])})를 써서 "
            "템플릿 문장으로 되돌렸다."
        )
        return fallback, ("template" if fallback else "none"), warnings

    return text, "llm", warnings
