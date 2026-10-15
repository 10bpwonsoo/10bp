"""
LLM 구조화 출력 검증 (요구 14).

"LLM 출력은 반드시 structured output validation 을 거친다."

이 모듈의 태도
--------------
값을 조용히 고치지 않는다. sentiment 가 150 으로 오면 100 으로 자르되
**잘랐다는 사실을 ValidationReport 에 남긴다.** 모르는 테마 id 가 오면
버리되 버렸다는 사실을 남긴다. 화면과 로그에서 "이 이벤트는 LLM 이
만들었고 두 필드가 보정되었다" 를 볼 수 있어야 한다 (요구 15-11).

스키마가 형식을 보장해도 내용은 보장하지 못한다. 존재하지 않는 종목 코드,
범위를 벗어난 점수, 사전에 없는 테마는 형식상 유효한 JSON 으로 온다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

from ..models.news import (
    AssetImpact,
    Entity,
    EntityType,
    EventType,
    NewsEvent,
    RawNewsItem,
    ValidationReport,
)

TIME_HORIZONS = {"intraday", "short", "medium", "long"}
DIRECTIONS = {"up", "down", "neutral"}
MAGNITUDES = {"low", "medium", "high"}


def _clamp_int(
    value: Any, low: int, high: int, field: str, report: ValidationReport, default: int
) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        report.errors.append(f"{field}: 숫자가 아니다 ({value!r}). 기본값 {default} 사용")
        return default
    if number < low or number > high:
        report.clamped_fields.append(f"{field}: {number} → {max(low, min(high, number))}")
        return max(low, min(high, number))
    return number


def _clamp_float(
    value: Any, low: float, high: float, field: str, report: ValidationReport, default: float
) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        report.errors.append(f"{field}: 숫자가 아니다 ({value!r}). 기본값 {default} 사용")
        return default
    if number < low or number > high:
        report.clamped_fields.append(f"{field}: {number:g} → {max(low, min(high, number)):g}")
        return max(low, min(high, number))
    return number


def _enum(
    value: Any, allowed: Iterable[str], field: str, report: ValidationReport, default: str
) -> str:
    text = str(value or "").strip().lower()
    allowed_set = set(allowed)
    if text in allowed_set:
        return text
    if value not in (None, ""):
        report.errors.append(f"{field}: 허용되지 않은 값 {value!r}. 기본값 {default} 사용")
    return default


def validate_themes(
    raw: Any, known: Mapping[str, Any], report: ValidationReport
) -> list[str]:
    """
    사전에 없는 테마는 버린다.

    LLM 이 "quantum_computing" 같은 새 테마를 지어낼 수 있다. 레지스트리에
    없는 테마를 받아들이면 점수 계산이 조용히 어긋난다. 새 테마가 필요하면
    themes.yaml 에 사람이 추가하는 것이 맞다.
    """
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        key = str(item or "").strip().lower().replace(" ", "_").replace("-", "_")
        if key in known:
            if key not in out:
                out.append(key)
        elif item:
            report.errors.append(f"themes: 레지스트리에 없는 테마 '{item}' 를 버렸다")
    return out


def validate_assets(
    raw: Any,
    known_instruments: Mapping[str, Any],
    report: ValidationReport,
) -> list[AssetImpact]:
    """
    영향 자산.

    instrument_id 가 레지스트리에 없으면 id 만 비우고 label 은 남긴다.
    "Airlines" 처럼 우리 레지스트리에 없는 대상도 화면에는 보여야 하기
    때문이다 (설계서 STEP 4.2).
    """
    if not isinstance(raw, list):
        return []
    out: list[AssetImpact] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("label") or entry.get("instrument_id") or "").strip()
        if not label:
            continue
        iid = entry.get("instrument_id")
        resolved = str(iid).strip().upper() if iid else None
        if resolved and resolved not in known_instruments:
            report.errors.append(
                f"affected_assets: 레지스트리에 없는 종목 '{resolved}' 의 id 를 비웠다"
            )
            resolved = None
        out.append(
            AssetImpact(
                instrument_id=resolved,
                label=label,
                direction=_enum(
                    entry.get("direction"), DIRECTIONS, "affected_assets.direction", report, "neutral"
                ),
                magnitude=_enum(
                    entry.get("magnitude"), MAGNITUDES, "affected_assets.magnitude", report, "medium"
                ),
                confidence=_clamp_float(
                    entry.get("confidence", 0.5), 0.0, 1.0, "affected_assets.confidence", report, 0.5
                ),
                rationale=str(entry.get("rationale") or "")[:400],
            )
        )
    return out


def _validate_entities(raw: Any, report: ValidationReport) -> list[Entity]:
    if not isinstance(raw, list):
        return []
    valid = {e.value for e in EntityType}
    out: list[Entity] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        out.append(
            Entity(
                name=name[:120],
                type=EntityType(_enum(entry.get("type"), valid, "entities.type", report, "organization")),
                ticker=(str(entry.get("ticker")).strip() or None) if entry.get("ticker") else None,
            )
        )
    return out


def validate_event(
    raw: Mapping[str, Any],
    item: RawNewsItem,
    *,
    known_themes: Mapping[str, Any],
    known_instruments: Mapping[str, Any],
    theme_sentiment_fallback: Mapping[str, int] | None = None,
    theme_direction_fallback: Mapping[str, str] | None = None,
    model: str | None = None,
) -> tuple[NewsEvent | None, ValidationReport]:
    """
    LLM 응답 하나를 NewsEvent 로 바꾼다.

    돌려주는 NewsEvent 는 extractor="llm" 이고, 보정 내역이 validation 에
    담긴다. 복구 불가능한 경우(제목이 비었다든지)만 None 이다 — 그때는
    호출자가 룰 추출기로 되돌아간다.
    """
    report = ValidationReport(schema_ok=True)

    event_title = str(raw.get("event") or "").strip() or item.title.strip()
    if not event_title:
        report.schema_ok = False
        report.errors.append("event: 제목이 비어 있어 복구할 수 없다")
        return None, report

    valid_types = {e.value for e in EventType}
    themes = validate_themes(raw.get("themes"), known_themes, report)

    theme_sentiment: dict[str, int] = {}
    raw_theme_sentiment = raw.get("theme_sentiment")
    if isinstance(raw_theme_sentiment, dict):
        for key, value in raw_theme_sentiment.items():
            k = str(key).strip().lower()
            if k not in themes:
                continue
            theme_sentiment[k] = _clamp_int(
                value, -100, 100, f"theme_sentiment.{k}", report, 0
            )
    for theme_id in themes:
        if theme_id not in theme_sentiment and theme_sentiment_fallback:
            if theme_id in theme_sentiment_fallback:
                theme_sentiment[theme_id] = theme_sentiment_fallback[theme_id]

    # 방향은 감성과 다른 축이다. 모델이 비워 두면 룰 추출기가 사전으로 읽은
    # 값으로 채우고, 그것도 없으면 neutral 로 둔다 — 감성 부호로 대신하지
    # 않는다. 그것이 이 필드를 따로 둔 이유다.
    theme_direction: dict[str, str] = {}
    raw_theme_direction = raw.get("theme_direction")
    if isinstance(raw_theme_direction, dict):
        for key, value in raw_theme_direction.items():
            k = str(key)[:60]
            if k not in themes:
                continue
            theme_direction[k] = _enum(
                value, DIRECTIONS, f"theme_direction.{k}", report, "neutral"
            )
    for theme_id in themes:
        if theme_direction.get(theme_id, "neutral") == "neutral" and theme_direction_fallback:
            fallback_value = theme_direction_fallback.get(theme_id)
            if fallback_value and fallback_value != "neutral":
                theme_direction[theme_id] = fallback_value

    direction_map: dict[str, str] = {}
    if isinstance(raw.get("direction"), dict):
        for key, value in raw["direction"].items():
            direction_map[str(key)[:60]] = _enum(
                value, DIRECTIONS, f"direction.{key}", report, "neutral"
            )

    event = NewsEvent(
        id=f"llm-{item.id}",
        source_item_ids=[item.id],
        event=event_title[:300],
        event_type=EventType(
            _enum(raw.get("event_type"), valid_types, "event_type", report, "other")
        ),
        themes=themes,
        theme_sentiment=theme_sentiment,
        theme_direction=theme_direction,
        entities=_validate_entities(raw.get("entities"), report),
        sentiment=_clamp_int(raw.get("sentiment", 0), -100, 100, "sentiment", report, 0),
        impact_score=_clamp_int(raw.get("impact_score", 40), 0, 100, "impact_score", report, 40),
        novelty_score=_clamp_int(raw.get("novelty_score", 50), 0, 100, "novelty_score", report, 50),
        time_horizon=_enum(
            raw.get("time_horizon"), TIME_HORIZONS, "time_horizon", report, "short"
        ),
        affected_assets=validate_assets(
            raw.get("affected_assets"), known_instruments, report
        ),
        direction=direction_map,
        second_order=[],  # LLM 이 제안한 2차 관계는 별도 경로로 처리한다
        reason=str(raw.get("reason") or "")[:600],
        source=item.publisher or item.meta.source,
        url=item.url,
        timestamp=item.published_at,
        extractor="llm",
        extractor_model=model,
        validation=report,
        # 보정이 많았다면 그만큼 덜 믿는다.
        confidence=max(
            0.3,
            min(0.9, 0.85 - 0.05 * len(report.clamped_fields) - 0.05 * len(report.errors)),
        ),
    )
    return event, report


def summarize_reports(events: Sequence[NewsEvent]) -> dict[str, int]:
    """검증 통계. data_health 경고에 쓴다."""
    clamped = sum(len(e.validation.clamped_fields) for e in events)
    errors = sum(len(e.validation.errors) for e in events)
    return {"events": len(events), "clamped": clamped, "errors": errors}
