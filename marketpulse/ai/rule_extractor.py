"""
룰 기반 이벤트 추출기.

이 모듈의 존재 이유는 하나다. **LLM 없이도 파이프라인이 완주해야 한다**
(요구 15-7). P3 에서 LLM 추출기가 붙어도 이것은 지워지지 않는다. LLM 이
실패하거나 꺼져 있으면 여기로 돌아온다.

키워드 매칭이라 LLM 만큼 정교하지 않다. 그래서 만들어낸 NewsEvent 에는
extractor="rule" 과 낮은 confidence 가 찍힌다. 어디서 나온 판단인지가
데이터에 남아야 한다 (요구 15-11).
"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Sequence

from ..config.registry import get_themes
from ..engines.direction import scoped_direction
from ..engines.sentiment import lexicon_sentiment, scoped_sentiment
from ..models.news import (
    EventType,
    NewsEvent,
    RawNewsItem,
    ValidationReport,
)
from ..models.theme import Theme

EXTRACTOR_VERSION = "0.1.0"

#: 키워드로 event_type 을 거칠게 가른다. 순서가 우선순위다.
_TYPE_HINTS: list[tuple[EventType, tuple[str, ...]]] = [
    (EventType.GEOPOLITICAL, ("전쟁", "분쟁", "긴장", "제재", "공습", "미사일", "봉쇄", "지정학")),
    (EventType.POLICY, ("연준", "FOMC", "금통위", "한국은행", "기준금리", "정책", "규제 완화")),
    (EventType.REGULATION, ("규제", "상법", "제도", "승인", "과징금")),
    (EventType.EARNINGS, ("실적", "영업이익", "매출", "가이던스", "어닝")),
    (EventType.SUPPLY, ("공급", "증설", "감산", "증산", "재고", "수급 차질", "양산")),
    (EventType.FLOW, ("순매수", "순매도", "수급", "자금", "유입", "유출")),
    (EventType.MACRO, ("물가", "CPI", "고용", "GDP", "경기", "인플레이션", "금리")),
]


def _match_themes(text: str, themes: Sequence[Theme]) -> list[tuple[Theme, list[str]]]:
    """본문에서 걸린 테마와 실제로 걸린 키워드를 함께 돌려준다."""
    lowered = text.lower()
    out: list[tuple[Theme, list[str]]] = []
    for theme in themes:
        hits = [k for k in theme.keywords if k.lower() in lowered]
        hits += [a for a in theme.aliases if a.lower() in lowered]
        if hits:
            out.append((theme, hits))
    return out


def _event_type(text: str) -> EventType:
    for etype, hints in _TYPE_HINTS:
        if any(h.lower() in text.lower() for h in hints):
            return etype
    return EventType.OTHER


def _impact_score(text: str, theme_count: int, sentiment: int) -> int:
    """
    영향도 추정.

    엄밀한 값이 아니다. 감성의 세기, 걸린 테마 수, 숫자 등장 여부를 섞은
    휴리스틱이다. LLM 이 붙으면 대체된다. 근거 없이 100 을 주지 않는다.
    """
    base = 25.0
    base += min(abs(sentiment), 100) * 0.35
    base += min(theme_count, 4) * 6.0
    if any(ch.isdigit() for ch in text):
        base += 6.0
    return int(max(0, min(100, round(base))))


def extract_events(
    items: Sequence[RawNewsItem],
    *,
    as_of: datetime | None = None,
    config_dir: Path | None = None,
) -> list[NewsEvent]:
    """기사 목록에서 NewsEvent 를 만든다. 네트워크도 LLM 도 쓰지 않는다."""
    themes = get_themes().themes
    events: list[NewsEvent] = []

    for item in items:
        text = f"{item.title}\n{item.body}".strip()
        matched = _match_themes(text, themes)
        sentiment, hits = lexicon_sentiment(text, config_dir=config_dir)

        theme_sentiment: dict[str, int] = {}
        theme_direction: dict[str, str] = {}
        direction_hits: list[str] = []
        for theme, keywords in matched:
            scoped = scoped_sentiment(text, keywords, config_dir=config_dir)
            value = sentiment if scoped is None else scoped
            # risk 테마는 악재가 테마를 키운다. 긴장 고조는 +다.
            if theme.sentiment_polarity == "risk":
                value = -value
            theme_sentiment[theme.id] = int(max(-100, min(100, value)))

            # 방향은 감성과 별개로 읽는다. 감성 부호를 방향으로 쓰면
            # "물가 부담 확대 우려" 가 '물가가 내린다' 로 읽힌다.
            heading, terms = scoped_direction(text, keywords, config_dir=config_dir)
            theme_direction[theme.id] = heading
            direction_hits.extend(terms)

        impact = _impact_score(text, len(matched), sentiment)

        # 키워드 매칭은 LLM 만큼 정교하지 않다. confidence 가 그것을 말해야 한다.
        confidence = 0.25 + 0.10 * min(len(matched), 3) + (0.10 if hits else 0.0)

        events.append(
            NewsEvent(
                id=f"rule-{item.id}",
                source_item_ids=[item.id],
                event=item.title,
                event_type=_event_type(text),
                themes=[t.id for t, _ in matched],
                theme_sentiment=theme_sentiment,
                theme_direction=theme_direction,
                sentiment=sentiment,
                impact_score=impact,
                # 중복 제거 기반 novelty 는 P3 다. 여기서 추정하지 않고
                # 중립값을 두되 그 사실이 confidence 에 드러나게 한다.
                novelty_score=50,
                time_horizon="short",
                reason=(
                    f"키워드 매칭으로 {len(matched)}개 테마를 식별했다"
                    + (f". 감성 표현: {', '.join(hits)}" if hits else ". 감성 표현 없음")
                    + (
                        f". 방향 표현: {', '.join(dict.fromkeys(direction_hits))}"
                        if direction_hits
                        else ". 방향 표현 없음"
                    )
                ),
                source=item.publisher or item.meta.source,
                timestamp=item.published_at,
                extractor="rule",
                extractor_model=None,
                validation=ValidationReport(schema_ok=True),
                confidence=round(min(0.6, confidence), 3),
            )
        )

    if as_of is not None:
        events.sort(key=lambda e: e.timestamp, reverse=True)
    return events
