"""
LLM 이벤트 추출 (요구 4).

뉴스에서 event / themes / entities / sentiment / impact / horizon /
affected_assets / direction 을 구조화한다.

이 모듈이 지키는 것
-------------------
1. 실패하면 룰 추출기로 되돌아간다. 예외를 밖으로 던지지 않는다 (요구 15-7).
2. 응답은 반드시 validation 을 거친다. 스키마가 형식을 보장해도 내용은
   보장하지 못한다 (요구 14).
3. 산출물에 extractor="llm" 과 보정 내역이 남는다 (요구 15-11).
4. LLM 은 **점수만 만들고 시장 판정은 하지 않는다.** Market State,
   Theme Score, Divergence 는 전부 정량 레이어에서 나온다 (요구 2).
"""

from __future__ import annotations

import json
import logging
from typing import Mapping, Sequence

from ..models.news import NewsEvent, RawNewsItem
from ..models.theme import Theme
from .client import EXTRACT_EFFORT, LLMClient, LLMFailure
from .rule_extractor import extract_events as rule_extract
from .validation import validate_event

logger = logging.getLogger(__name__)

EXTRACTOR_VERSION = "0.1.0"

#: 한 번에 보낼 기사 수. 호출 수를 줄이면서 응답 길이를 감당 가능하게 둔다.
DEFAULT_BATCH_SIZE = 10


def build_schema(theme_ids: Sequence[str]) -> dict:
    """
    응답 스키마.

    themes 를 enum 으로 고정한다. 모델이 새 테마를 지어내는 경로를 아예
    막는 것이 검증 단계에서 걸러내는 것보다 낫다. 새 테마가 필요하면
    themes.yaml 에 사람이 추가하는 것이 맞다.
    """
    return {
        "type": "object",
        "properties": {
            "events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_id": {"type": "string"},
                        "event": {"type": "string"},
                        "event_type": {
                            "type": "string",
                            "enum": [
                                "geopolitical", "macro", "policy", "earnings",
                                "supply", "regulation", "flow", "other",
                            ],
                        },
                        "themes": {
                            "type": "array",
                            "items": {"type": "string", "enum": list(theme_ids)},
                        },
                        "theme_sentiment": {
                            "type": "object",
                            "additionalProperties": {
                                "type": "integer", "minimum": -100, "maximum": 100
                            },
                        },
                        # 감성과 다른 축이다. 같은 기사가 감성 −, 방향 ↑ 일 수
                        # 있다 — "물가 부담 확대 우려" 가 그렇다.
                        "theme_direction": {
                            "type": "object",
                            "additionalProperties": {
                                "type": "string", "enum": ["up", "down", "neutral"]
                            },
                        },
                        "entities": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "type": {
                                        "type": "string",
                                        "enum": [
                                            "company", "country", "person", "organization",
                                            "commodity", "currency", "index", "sector",
                                        ],
                                    },
                                    "ticker": {"type": ["string", "null"]},
                                },
                                "required": ["name", "type", "ticker"],
                                "additionalProperties": False,
                            },
                        },
                        "sentiment": {"type": "integer", "minimum": -100, "maximum": 100},
                        "impact_score": {"type": "integer", "minimum": 0, "maximum": 100},
                        "novelty_score": {"type": "integer", "minimum": 0, "maximum": 100},
                        "time_horizon": {
                            "type": "string",
                            "enum": ["intraday", "short", "medium", "long"],
                        },
                        "affected_assets": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "instrument_id": {"type": ["string", "null"]},
                                    "label": {"type": "string"},
                                    "direction": {
                                        "type": "string", "enum": ["up", "down", "neutral"]
                                    },
                                    "magnitude": {
                                        "type": "string", "enum": ["low", "medium", "high"]
                                    },
                                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                                    "rationale": {"type": "string"},
                                },
                                "required": [
                                    "instrument_id", "label", "direction",
                                    "magnitude", "confidence", "rationale",
                                ],
                                "additionalProperties": False,
                            },
                        },
                        "reason": {"type": "string"},
                    },
                    "required": [
                        "source_id", "event", "event_type", "themes", "theme_sentiment",
                        "theme_direction",
                        "entities", "sentiment", "impact_score", "novelty_score",
                        "time_horizon", "affected_assets", "reason",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["events"],
        "additionalProperties": False,
    }


SYSTEM_PROMPT = """당신은 자산운용사의 시장 분석 데이터를 구조화하는 역할을 맡았다.
기사에서 사실만 뽑아 주어진 스키마로 정리한다.

지켜야 할 것

1. 기사에 없는 사실을 만들지 않는다. 근거가 없으면 중립값을 쓴다.
2. **감성과 방향은 다른 축이다. 절대 섞지 마라.**
   · theme_sentiment 는 호재냐 악재냐다. -100 ~ +100.
   · theme_direction 은 그 값이 오르냐 내리냐다. up / down / neutral.
   "물가 둔화 흐름 확인" → inflation 은 감성 +, 방향 down.
   "수입 물가 부담 확대 우려" → inflation 은 감성 -, 방향 up.
   방향을 이 지도가 인과 연쇄에 그대로 쓴다. 감성 부호로 대신하면 그 아래
   금리·업종·자산까지 부호가 전부 뒤집힌다.
3. 기사가 테마마다 다르게 말하면 테마마다 다르게 적는다.
   "정유주 강세, 항공주 약세" 는 energy 에 +/up, 항공 관련 테마에 -/down.
   기사에서 방향을 읽을 수 없으면 neutral 로 둔다. 짐작해서 채우지 마라.
4. impact_score 는 시장 전체에 미칠 파급의 크기다. 기사의 흥미도가 아니다.
   개별 기업 소식은 낮게, 통화정책·지정학·원자재 공급은 높게 본다.
5. affected_assets 의 instrument_id 는 아래 목록에 있는 것만 쓴다.
   목록에 없는 대상은 instrument_id 를 null 로 두고 label 만 적는다.
6. 시장 상태를 판정하지 않는다. Risk-On/Risk-Off 같은 판단은 별도의 정량
   엔진이 가격 데이터로 계산한다. 당신은 기사의 내용만 구조화한다.
7. reason 은 왜 그렇게 분류했는지 한 문장으로 적는다. 한국어로 쓴다.

사용 가능한 instrument_id 목록:
{instruments}
"""


def _render_batch(items: Sequence[RawNewsItem]) -> str:
    lines: list[str] = []
    for item in items:
        body = (item.body or "").strip()
        lines.append(
            f"[source_id: {item.id}]\n"
            f"제목: {item.title.strip()}\n"
            f"본문: {body[:1500] if body else '(없음)'}\n"
            f"출처: {item.publisher or '(미상)'}\n"
            f"시각: {item.published_at.isoformat()}"
        )
    return "\n\n---\n\n".join(lines)


def extract_events(
    items: Sequence[RawNewsItem],
    client: LLMClient,
    themes_by_id: Mapping[str, Theme],
    instruments_by_id: Mapping[str, object],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> tuple[list[NewsEvent], list[str]]:
    """
    LLM 으로 추출하고, 실패한 기사는 룰 추출기로 채운다.

    Returns: (이벤트 목록, 경고 문자열 목록)

    부분 실패를 허용한다. 10건 중 7건만 LLM 이 처리했으면 나머지 3건은
    룰로 만들고 둘을 섞어 돌려준다. extractor 필드로 구분되므로 화면에서
    어느 쪽인지 알 수 있다.
    """
    if not items:
        return [], []

    if not client.available():
        events = rule_extract(items)
        return events, []

    schema = build_schema(sorted(themes_by_id))
    instrument_list = ", ".join(sorted(instruments_by_id))
    system = SYSTEM_PROMPT.format(instruments=instrument_list)

    by_source: dict[str, NewsEvent] = {}
    warnings: list[str] = []

    for start in range(0, len(items), batch_size):
        batch = list(items[start : start + batch_size])
        result = client.structured(
            system=system,
            user=_render_batch(batch),
            schema=schema,
            effort=EXTRACT_EFFORT,
        )
        if isinstance(result, LLMFailure):
            logger.warning("LLM 추출 실패 (%s): %s", result.kind, result.reason)
            warnings.append(f"LLM 추출 실패({result.kind}). 룰 추출기로 대체했다.")
            continue

        payloads = result.get("events")
        if not isinstance(payloads, list):
            warnings.append("LLM 응답에 events 배열이 없다. 룰 추출기로 대체했다.")
            continue

        index = {item.id: item for item in batch}
        # 룰 추출 결과를 theme_sentiment 의 보조 근거로 쓴다. LLM 이 특정
        # 테마의 감성을 빠뜨렸을 때 사전 기반 값으로 메운다.
        rule_by_source = {
            e.source_item_ids[0]: e for e in rule_extract(batch) if e.source_item_ids
        }

        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            item = index.get(str(payload.get("source_id") or ""))
            if item is None:
                warnings.append("LLM 응답의 source_id 가 요청과 맞지 않아 버렸다.")
                continue
            fallback = rule_by_source.get(item.id)
            event, report = validate_event(
                payload,
                item,
                known_themes=themes_by_id,
                known_instruments=instruments_by_id,
                theme_sentiment_fallback=fallback.theme_sentiment if fallback else None,
                theme_direction_fallback=fallback.theme_direction if fallback else None,
                model=client.model,
            )
            if event is None:
                warnings.append(f"'{item.title[:24]}…' 검증 실패: {'; '.join(report.errors[:2])}")
                continue
            by_source[item.id] = event

    # LLM 이 처리하지 못한 기사는 룰로 채운다. 기사가 사라지면 안 된다.
    missing = [item for item in items if item.id not in by_source]
    events = list(by_source.values()) + (rule_extract(missing) if missing else [])
    events.sort(key=lambda e: e.timestamp, reverse=True)

    if missing and by_source:
        warnings.append(
            f"{len(missing)}건은 룰 추출기로 처리했다 (LLM {len(by_source)}건)."
        )
    return events, warnings
