"""
SentimentEngine (설계서 STEP 5.6).

2단 구조다. 사전 기반 baseline 은 LLM 없이 항상 동작하고, LLM 이 가용하면
가중 결합한다. LLM 이 죽어도 테마 감성은 계속 나온다 (요구 15-7).

테마 단위 집계에서 단순 평균을 쓰지 않는다 (요구 5 명시). 시간 감쇠 ·
영향도 · 출처의 3중 가중이다.

    w_k = exp(-ln2 · age_hours / H) · (impact/100) · src_weight
    ThemeSentiment = Σ(w_k · S_k) / Σ(w_k)

왜 지수 감쇠인가: 뉴스의 시장 관련성은 지수적으로 줄어든다. 단순 평균은
3일 전 기사와 10분 전 기사를 같은 무게로 취급해 급변을 완전히 놓친다.
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Sequence

import yaml

from ..config.settings import CONFIG_DIR
from ..models.news import NewsEvent
from .scoring import load_scoring


@lru_cache(maxsize=4)
def load_lexicon(config_dir: Path | None = None) -> dict:
    d = config_dir or CONFIG_DIR
    with (d / "lexicon.yaml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def reset_lexicon_cache() -> None:
    load_lexicon.cache_clear()


def _negated(text: str, end: int, negation: dict) -> bool:
    window = text[end : end + int(negation["window_chars"])]
    return any(m in window for m in negation["markers"])


def lexicon_sentiment(text: str, *, config_dir: Path | None = None) -> tuple[int, list[str]]:
    """
    사전 기반 극성. -100 ~ +100 과 매칭된 표현 목록을 돌려준다.

    형태소 분석기를 쓰지 않고 부분 문자열 매칭을 쓴다. 의존성을 하나 더
    들이는 대신 사전을 보수적으로 유지하는 쪽을 택했다. 한계는 분명하다 —
    맥락 의존 표현을 다루지 못한다. 그것이 P3 LLM 레이어의 역할이다.
    """
    lex = load_lexicon(config_dir)
    cfg = load_scoring(config_dir)["sentiment"]
    lowered = text.lower()

    hits: list[tuple[int, str, int]] = []
    for polarity, terms in (("+", lex["positive"]), ("-", lex["negative"])):
        sign = 1 if polarity == "+" else -1
        for term in terms:
            idx = lowered.find(term.lower())
            if idx < 0:
                continue
            eff = -sign if _negated(text, idx + len(term), lex["negation"]) else sign
            hits.append((idx, term, eff))

    if not hits:
        return 0, []

    # 등장 위치 순으로 본다. 같은 표현이 반복돼도 한 번만 센다 — 긴 기사가
    # 무조건 극단으로 가는 것을 막는다.
    hits.sort(key=lambda h: h[0])
    limit = int(cfg["lexicon_max_terms"])
    ordered = hits[:limit]

    # 앞에 나온 표현에 더 큰 비중을 둔다. 헤드라인은 핵심을 앞에 놓기
    # 때문이고, 무엇보다 상반된 표현이 정확히 상쇄돼 0 이 되는 것을 막는다.
    # "중동 긴장 고조에 유가 급등" 이 중립으로 읽히면 안 된다.
    weighted = sum(sign / (1.0 + rank) for rank, (_, _, sign) in enumerate(ordered))
    score = weighted * float(cfg["lexicon_unit"])
    return int(max(-100.0, min(100.0, round(score)))), [t for _, t, _ in ordered]


# 문장 경계 + 한국어 대조 접속사.
# "정유주는 강세를 보인 반면 항공주는 약세" 처럼 한 문장 안에서 극성이
# 뒤집히는 자리가 바로 이 접속사들이다. 여기서 끊어야 테마별로 갈린다.
_SENTENCE_SPLIT = re.compile(
    r"(?<=[.!?。])\s+"          # 일반 문장 끝
    r"|\n+"                     # 줄바꿈
    r"|…+|\.{3,}"               # 한국어 헤드라인의 말줄임표. 두 절을 가르는 표지다.
    r"|(?<=\s)(?=반면|한편|그러나|하지만|다만)"  # 대조 접속사
)


def scoped_sentiment(
    text: str, keywords: Sequence[str], *, config_dir: Path | None = None
) -> int | None:
    """
    주어진 키워드가 등장하는 문장만 골라 감성을 낸다.

    기사 하나가 여러 테마를 건드릴 때 기사 전체 감성을 모든 테마에 그대로
    붙이면 틀린다. "정유주 강세, 항공주 약세" 는 Energy 에 +, Airlines 에
    -여야 한다. 문장 단위로 잘라 테마 키워드가 있는 문장만 채점한다.

    한 문장 안에 상반된 테마가 함께 들어 있으면 이 방법으로도 분리할 수
    없다. 그 경계가 P3 LLM 추출이 필요한 지점이다.

    키워드가 어느 문장에도 없으면 None 을 돌려주고, 호출자는 기사 전체
    감성으로 되돌아간다.
    """
    lowered_keys = [k.lower() for k in keywords]
    sentences = [s for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    matched = [
        s for s in sentences if any(k in s.lower() for k in lowered_keys)
    ]
    if not matched:
        return None
    score, _ = lexicon_sentiment(" ".join(matched), config_dir=config_dir)
    return score


def fuse_sentiment(
    lexicon_score: int,
    llm_score: int | None,
    *,
    llm_valid: bool,
    config_dir: Path | None = None,
) -> int:
    """LLM 감성이 검증을 통과했을 때만 결합한다. 아니면 사전 값 그대로."""
    if llm_score is None or not llm_valid:
        return lexicon_score
    a = float(load_scoring(config_dir)["sentiment"]["llm_weight"])
    return int(round(a * llm_score + (1.0 - a) * lexicon_score))


def decay_weight(
    event: NewsEvent, as_of: datetime, *, config_dir: Path | None = None
) -> float:
    """시간 감쇠 · 영향도 · 출처의 3중 가중."""
    cfg = load_scoring(config_dir)["sentiment"]
    half_life = float(cfg["half_life_hours"])
    age_hours = max(0.0, (as_of - event.timestamp).total_seconds() / 3600.0)
    decay = math.exp(-math.log(2.0) * age_hours / half_life)

    impact = max(event.impact_score, 1) / 100.0
    sources: dict = cfg.get("source_weights") or {}
    src = float(sources.get(event.source, sources.get("default", 1.0)))
    return decay * impact * src


def aggregate_sentiment(
    events: Sequence[NewsEvent], as_of: datetime, *, config_dir: Path | None = None
) -> tuple[float, float]:
    """
    가중 평균 감성과 가중치 합.

    Returns: (-100 ~ +100 감성, 가중치 합). 이벤트가 없으면 (0.0, 0.0).
    호출자는 가중치 합이 0 인지 보고 '중립' 과 '데이터 없음' 을 구분해야 한다.
    """
    total = 0.0
    acc = 0.0
    for e in events:
        w = decay_weight(e, as_of, config_dir=config_dir)
        acc += w * e.sentiment
        total += w
    return ((acc / total) if total > 0 else 0.0), total


def news_momentum(
    events: Sequence[NewsEvent],
    as_of: datetime,
    *,
    recent_hours: float = 3.0,
    config_dir: Path | None = None,
) -> float | None:
    """
    최근 구간과 그 이전 구간의 가중 감성 차이. -100 ~ +100.

    수준이 아니라 변화를 본다. 어느 쪽 구간이든 비어 있으면 None 이다.
    """
    recent: list[NewsEvent] = []
    prior: list[NewsEvent] = []
    for e in events:
        age = (as_of - e.timestamp).total_seconds() / 3600.0
        (recent if age <= recent_hours else prior).append(e)

    if not recent or not prior:
        return None
    r, _ = aggregate_sentiment(recent, as_of, config_dir=config_dir)
    p, _ = aggregate_sentiment(prior, as_of, config_dir=config_dir)
    return max(-100.0, min(100.0, r - p))


def count_by_theme(events: Iterable[NewsEvent]) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in events:
        for t in e.themes:
            out[t] = out.get(t, 0) + 1
    return out
