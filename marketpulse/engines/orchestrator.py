"""
파이프라인 오케스트레이터.

핵심 성질: 이 함수는 순수 함수다.
    build_intelligence(market_snapshot, news_items, previous=None) -> IntelligenceSnapshot
전역 상태도 I/O 도 시계도 안에 없다. 같은 입력이면 언제나 같은 출력이 나오고,
과거 스냅샷을 그대로 재생할 수 있으며, 테스트에 네트워크가 필요 없다
(설계서 STEP 3.3 ①).

I/O 는 run_pipeline() 이 담당한다. 어댑터 호출과 조립을 분리해 두면
엔진 테스트가 픽스처만으로 돌아간다.

P0 범위
-------
지금 채워지는 것: MarketSnapshot, whats_moving, data_health, 뉴스 원문.
P1 에서 채울 것: market_state.factors / hypotheses, themes.
P2: divergences, alerts.  P3: impact_maps, events(LLM 추출), narrative.
비어 있는 영역은 UI 가 '해당 단계 미구현' 으로 표시한다. 거짓 숫자를 만들어
채우지 않는다.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Sequence

from ..ai.rule_extractor import extract_events
from ..config.registry import get_instruments, get_themes
from ..config.settings import Settings
from ..models.common import DataMode, arrow_for, direction_for, utcnow
from ..models.market import Instrument, MarketSnapshot
from ..models.news import RawNewsItem
from ..models.snapshot import DataHealth, IntelligenceSnapshot, MovingItem
from ..models.state import MarketState, StateLabel
from ..models.theme import ThemeState
from .market_state import compute_market_state
from .normalize import build_snapshot
from .theme import compute_theme_states

logger = logging.getLogger(__name__)

ENGINE_VERSIONS: dict[str, str] = {
    "features": "0.1.0",
    "normalize": "0.1.0",
    "factors": "0.1.0",
    "market_state": "0.1.0",
    "sentiment": "0.1.0",
    "theme": "0.1.0",
    "rule_extractor": "0.1.0",
    "orchestrator": "0.1.0-p1",
}

#: Theme Stability 계산에 쓰는 과거 틱 수 (설계서 STEP 5.7).
THEME_HISTORY_TICKS = 6

#: What's Moving 에 표시할 최대 줄 수.
WHATS_MOVING_LIMIT = 12
#: 이 |z| 미만은 '움직였다' 고 보지 않는다.
WHATS_MOVING_MIN_Z = 0.5


def _format_change(instrument: Instrument, value: float | None) -> str:
    if value is None:
        return "-"
    if instrument.series_kind == "price":
        return f"{value:+.2f}%"
    if instrument.unit == "percent":
        return f"{value:+.1f}bp"
    if instrument.unit == "bp":
        return f"{value:+.1f}bp"
    if instrument.unit == "krw_bn":
        return f"{value:+,.0f}십억"
    if instrument.unit == "ratio":
        return f"{value:+.3f}"
    return f"{value:+.2f}"


def build_whats_moving(
    snapshot: MarketSnapshot, instruments_by_id: dict[str, Instrument]
) -> list[MovingItem]:
    """|z_1d| 가 큰 순서. 요구 10 의 [WHAT'S MOVING] 패널."""
    rows: list[MovingItem] = []
    for iid, feat in snapshot.features.items():
        if feat.z_1d is None or abs(feat.z_1d) < WHATS_MOVING_MIN_Z:
            continue
        ins = instruments_by_id.get(iid)
        if ins is None:
            continue
        rows.append(
            MovingItem(
                key=iid,
                label=ins.name,
                kind="instrument",
                z=feat.z_1d,
                change=feat.ret_1d,
                change_display=_format_change(ins, feat.ret_1d),
                direction=direction_for(feat.z_1d),
                arrow=arrow_for(feat.z_1d),
            )
        )
    rows.sort(key=lambda r: abs(r.z or 0.0), reverse=True)
    return rows[:WHATS_MOVING_LIMIT]


def build_data_health(
    snapshot: MarketSnapshot,
    news_items: list[RawNewsItem],
    *,
    llm_enabled: bool,
    timings_ms: dict[str, float],
    warnings: list[str] | None = None,
) -> DataHealth:
    stale = [
        iid for iid, p in snapshot.points.items() if p.meta.is_stale
    ]
    max_fresh = max(
        (p.meta.freshness_sec for p in snapshot.points.values()), default=0
    )
    return DataHealth(
        mode=snapshot.mode,
        coverage=snapshot.coverage,
        expected_instruments=len(snapshot.expected_instruments),
        available_instruments=len(snapshot.points),
        missing=sorted(snapshot.missing),
        stale=sorted(stale),
        max_freshness_sec=max_fresh,
        news_items=len(news_items),
        llm_status="disabled" if not llm_enabled else "ok",
        engine_timings_ms={k: round(v, 2) for k, v in timings_ms.items()},
        warnings=list(warnings or []),
    )


def theme_score_history(
    history: Sequence[IntelligenceSnapshot], theme_id: str
) -> list[float]:
    """과거 스냅샷들에서 한 테마의 점수 궤적을 뽑는다. Stability 계산용."""
    out: list[float] = []
    for snap in history[-THEME_HISTORY_TICKS:]:
        for t in snap.themes:
            if t.theme_id == theme_id:
                out.append(t.theme_score)
                break
    return out


def build_theme_movers(
    themes: Sequence[ThemeState], min_change: float = 5.0
) -> list[MovingItem]:
    """직전 틱 대비 테마 점수 변화. 요구 10 의 '가장 크게 변한 ... 테마'."""
    rows: list[MovingItem] = []
    for t in themes:
        if abs(t.last_change) < min_change:
            continue
        rows.append(
            MovingItem(
                key=t.theme_id,
                label=t.name,
                kind="theme",
                z=None,
                change=t.last_change,
                change_display=f"{t.last_change:+.0f}p",
                direction=direction_for(t.last_change, deadband=min_change),
                arrow=arrow_for(t.last_change / 20.0),
            )
        )
    return rows


def build_intelligence(
    market_snapshot: MarketSnapshot,
    news_items: list[RawNewsItem],
    instruments_by_id: dict[str, Instrument],
    *,
    scenario: str | None = None,
    llm_enabled: bool = False,
    timings_ms: dict[str, float] | None = None,
    warnings: list[str] | None = None,
    history: Sequence[IntelligenceSnapshot] = (),
) -> IntelligenceSnapshot:
    """
    순수 함수. 스냅샷과 뉴스를 받아 최종 인텔리전스를 만든다.

    history 는 오래된 것부터 정렬된 과거 스냅샷이다. Persistence(상태 판정의
    지속성)와 Stability(테마 점수의 안정성) 계산에 쓴다. 비어 있으면 두 항은
    None 이 되고 confidence 가중치가 재정규화된다 — 0 으로 채우지 않는다.
    """
    timings = dict(timings_ms or {})
    previous = history[-1] if history else None

    t = time.perf_counter()
    events = extract_events(news_items, as_of=market_snapshot.as_of)
    timings["extract"] = (time.perf_counter() - t) * 1000.0

    t = time.perf_counter()
    market_state = compute_market_state(
        market_snapshot,
        instruments_by_id,
        previous_label=previous.market_state.primary_label if previous else None,
    )
    timings["market_state"] = (time.perf_counter() - t) * 1000.0

    t = time.perf_counter()
    themes = compute_theme_states(
        get_themes().themes,
        market_snapshot,
        events,
        instruments_by_id,
        previous={ts.theme_id: ts for ts in previous.themes} if previous else None,
        history={
            th.id: theme_score_history(history, th.id) for th in get_themes().themes
        },
    )
    timings["theme"] = (time.perf_counter() - t) * 1000.0

    t = time.perf_counter()
    whats_moving = build_whats_moving(market_snapshot, instruments_by_id)
    whats_moving += build_theme_movers(themes)
    whats_moving.sort(
        key=lambda r: abs(r.z if r.z is not None else (r.change or 0.0) / 20.0),
        reverse=True,
    )
    whats_moving = whats_moving[:WHATS_MOVING_LIMIT]
    timings["orchestrator"] = (time.perf_counter() - t) * 1000.0

    return IntelligenceSnapshot(
        as_of=market_snapshot.as_of,
        mode=market_snapshot.mode,
        scenario=scenario,
        market_state=market_state,
        themes=themes,
        divergences=[],
        alerts=[],
        impact_maps=[],
        events=events,
        whats_moving=whats_moving,
        data_health=build_data_health(
            market_snapshot,
            news_items,
            llm_enabled=llm_enabled,
            timings_ms=timings,
            warnings=warnings,
        ),
        engine_versions=dict(ENGINE_VERSIONS),
    )


def run_pipeline(
    settings: Settings,
    *,
    as_of: datetime | None = None,
    history: Sequence[IntelligenceSnapshot] = (),
) -> IntelligenceSnapshot:
    """I/O 를 포함한 한 tick 실행. 어댑터 -> 정규화 -> 엔진."""
    # 지연 import: 레지스트리 캐시와 순환 참조를 피한다.
    from ..adapters.registry import build_market_adapter, build_news_adapter

    registry = get_instruments()
    instruments = registry.instruments
    by_id = registry.by_id()
    timings: dict[str, float] = {}
    warnings: list[str] = []

    as_of = as_of or utcnow()

    t = time.perf_counter()
    market_adapter = build_market_adapter(settings)
    series = market_adapter.fetch_series(
        instruments, bars=settings.history_bars, as_of=as_of
    )
    timings["market_fetch"] = (time.perf_counter() - t) * 1000.0

    t = time.perf_counter()
    news_adapter = build_news_adapter(settings)
    try:
        news_items = news_adapter.fetch_news(as_of=as_of)
    except Exception as exc:  # 뉴스 실패가 정량 대시보드를 막으면 안 된다
        logger.exception("뉴스 수집 실패")
        news_items = []
        warnings.append(f"뉴스 수집 실패: {exc}")
    timings["news_fetch"] = (time.perf_counter() - t) * 1000.0

    t = time.perf_counter()
    snapshot = build_snapshot(
        instruments,
        series,
        mode=market_adapter.mode,
        zscore_window=settings.zscore_window,
    )
    timings["normalize"] = (time.perf_counter() - t) * 1000.0

    if snapshot.missing:
        warnings.append(
            f"{len(snapshot.missing)}개 instrument 미확보: "
            + ", ".join(snapshot.missing[:5])
            + ("…" if len(snapshot.missing) > 5 else "")
        )

    return build_intelligence(
        snapshot,
        news_items,
        by_id,
        scenario=settings.scenario if settings.data_mode is DataMode.MOCK else None,
        llm_enabled=settings.llm_enabled,
        timings_ms=timings,
        warnings=warnings,
        history=history,
    )
