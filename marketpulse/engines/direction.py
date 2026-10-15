"""
DirectionEngine — 뉴스가 말하는 '방향'.

감성과 다른 축이다. 감성은 "호재냐 악재냐" 를 보고, 방향은 "그 값이
오르냐 내리냐" 만 본다.

    "물가 둔화 흐름 확인"       감성 +  /  물가 방향 ↓
    "수입 물가 부담 확대 우려"   감성 −  /  물가 방향 ↑

둘을 한 필드로 합치면 Impact Map 의 연쇄 전체가 틀어진다. 감성 부호를
방향으로 쓰면 "물가 부담 확대 우려" 가 '물가가 내린다' 로 읽히고, 그
아래 금리·성장주까지 부호가 뒤집힌다.

lexicon.yaml 의 감성 사전이 맥락 의존이라며 일부러 뺀 표현(둔화 · 확대)이
방향으로는 전혀 모호하지 않다. 두 축이 독립이라는 증거다.

읽을 수 없으면 "neutral" 이다. 추측하지 않는다 (요구 15-11).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

from ..models.news import Direction
from .scoring import load_scoring
from .sentiment import SENTENCE_SPLIT, load_lexicon

ENGINE_VERSION = "0.1.0"

#: 방향은 감성보다 한 칸 더 잘게 끊는다. 한국어 헤드라인은 쉼표로 대조를
#: 만든다 — "정유·에너지주 강세, 항공주는 약세". 감성 채점에서는 문장
#: 단위가 맞지만, 방향은 어느 대상이 오르고 내리는지를 가려야 하므로
#: 쉼표까지 경계로 본다. 자릿수 쉼표(1,380원)는 건드리지 않는다.
CLAUSE_SPLIT = re.compile(f"(?:{SENTENCE_SPLIT.pattern})|(?<!\\d),(?!\\d)")


def _negated(text: str, end: int, negation: dict) -> bool:
    """한국어 부정은 표현 뒤에 온다 — "상승하지 않았다"."""
    window = text[end : end + int(negation["window_chars"])]
    return any(m in window for m in negation["markers"])


def _hits(text: str, lex: dict) -> list[tuple[int, str, int]]:
    """(위치, 표현, 부호). 부정어가 뒤따르면 부호를 뒤집는다."""
    lowered = text.lower()
    terms = lex.get("direction") or {}
    out: list[tuple[int, str, int]] = []
    for key, sign in (("up", 1), ("down", -1)):
        for raw in terms.get(key, []):
            term = str(raw)
            idx = lowered.find(term.lower())
            if idx < 0:
                continue
            eff = -sign if _negated(text, idx + len(term), lex["negation"]) else sign
            out.append((idx, term, eff))
    return out


def _vote(ordered: list[tuple[str, int]]) -> tuple[Direction, list[str]]:
    """
    앞선 것에 큰 비중을 둔 가중 투표.

    상반된 표현이 정확히 상쇄돼 중립이 되는 것을 막는다. 그러고도 0 이면
    한쪽으로 단정하지 않는다.
    """
    if not ordered:
        return "neutral", []
    weighted = sum(sign / (1.0 + rank) for rank, (_, sign) in enumerate(ordered))
    matched = list(dict.fromkeys(t for t, _ in ordered))
    if weighted > 0:
        return "up", matched
    if weighted < 0:
        return "down", matched
    return "neutral", matched


def lexicon_direction(
    text: str, *, config_dir: Path | None = None
) -> tuple[Direction, list[str]]:
    """
    문서 전체의 방향. 등장 순서가 곧 비중이다 — 헤드라인은 핵심을 앞에 둔다.

    테마가 정해져 있다면 scoped_direction 을 쓴다. 이쪽은 테마를 특정할 수
    없을 때의 기준선이다.
    """
    lex = load_lexicon(config_dir)
    limit = int(load_scoring(config_dir)["sentiment"]["lexicon_max_terms"])
    hits = sorted(_hits(text, lex), key=lambda h: h[0])
    return _vote([(t, s) for _, t, s in hits[:limit]])


def _keyword_positions(clause: str, keywords: Sequence[str]) -> list[int]:
    lowered = clause.lower()
    out: list[int] = []
    for k in keywords:
        key = k.lower()
        start = 0
        while True:
            idx = lowered.find(key, start)
            if idx < 0:
                break
            out.append(idx)
            start = idx + max(1, len(key))
    return out


def scoped_direction(
    text: str, keywords: Sequence[str], *, config_dir: Path | None = None
) -> tuple[Direction, list[str]]:
    """
    테마 키워드에 **가장 가까운** 방향 표현이 그 테마의 방향이다.

    두 단계로 좁힌다.

    1. 테마 키워드가 있는 절만 본다. 한 헤드라인이 두 테마를 반대 방향으로
       건드리는 일이 흔하다.
    2. 그 안에서 키워드와의 거리 순으로 본다. 절만 보고 등장 순서로 재면
       틀린다 —

           연준 위원 "물가 둔화 흐름 확인"… 국채 금리 소폭 상승

       rates 테마는 '연준'(1절)과 '금리'(2절) 양쪽에 걸린다. 등장 순서로는
       1절의 '둔화'가 이기지만 그 '둔화'는 물가를 말한 것이다. 거리로 재면
       '금리↔상승'(2절)이 이겨 rates ↑ 가 된다. 맞는 답이다.

    키워드가 어느 절에도 없으면 ("neutral", []) 이다. 기사 전체 방향으로
    되돌아가지 않는다 — 무관한 절의 방향어를 그 테마에 붙이는 것이 바로
    이 버그의 원인이었다.
    """
    lex = load_lexicon(config_dir)
    limit = int(load_scoring(config_dir)["sentiment"]["lexicon_max_terms"])

    scored: list[tuple[int, str, int]] = []
    for clause in CLAUSE_SPLIT.split(text):
        if not clause.strip():
            continue
        positions = _keyword_positions(clause, keywords)
        if not positions:
            continue
        for idx, term, sign in _hits(clause, lex):
            distance = min(abs(idx - p) for p in positions)
            scored.append((distance, term, sign))

    if not scored:
        return "neutral", []
    scored.sort(key=lambda h: (h[0], h[1]))
    return _vote([(t, s) for _, t, s in scored[:limit]])
