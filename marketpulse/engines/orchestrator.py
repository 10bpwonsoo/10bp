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
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping, Sequence

from ..ai.client import LLMClient, build_client
from ..ai.event_extractor import extract_events as llm_extract_events
from ..ai.rule_extractor import extract_events as rule_extract_events
from ..ai.summarizer import summarize
from ..config.registry import get_instruments, get_themes
from ..config.settings import Settings
from ..models.common import DataMode, arrow_for, direction_for, utcnow
from ..models.market import Instrument, MarketSnapshot
from ..models.news import RawNewsItem
from ..models.snapshot import DataHealth, IntelligenceSnapshot, MovingItem
from ..models.alert import Alert
from ..models.divergence import Divergence
from ..models.state import FactorScore, MarketState, StateLabel
from ..models.theme import ThemeState
from .alert import build_alerts, carry_forward
from .calendar import ENGINE_VERSION as CALENDAR_VERSION, event_window
from .correlation import ENGINE_VERSION as CORRELATION_VERSION
from .divergence import detect_divergences, pending_candidates
from .market_state import compute_market_state
from .normalize import build_snapshot
from .relationship import Observation, build_impact_maps
from .theme import compute_theme_states
from .thermometer import ENGINE_VERSION as THERMOMETER_VERSION, compute_thermometer

logger = logging.getLogger(__name__)

ENGINE_VERSIONS: dict[str, str] = {
    "features": "0.1.0",
    "normalize": "0.1.0",
    "factors": "0.1.0",
    "market_state": "0.1.0",
    "sentiment": "0.1.0",
    "theme": "0.1.0",
    "rule_extractor": "0.2.0",
    "confirmation": "0.1.0",
    "divergence": "0.1.0",
    "alert": "0.1.0",
    "relationship": "0.3.0",
    "llm_extractor": "0.1.0",
    "summarizer": "0.1.0",
    "thermometer": THERMOMETER_VERSION,
    "correlation": CORRELATION_VERSION,
    "calendar": CALENDAR_VERSION,
    "orchestrator": "0.5.0-p6",
}

#: "1주 전" 스냅샷을 찾을 때 허용하는 거리. 7일을 물었는데 이보다 더 오래된
#: 것밖에 없으면 없는 것으로 친다. 그 이상은 1주 전이 아니다.
WEEK_AGO_TARGET = timedelta(days=7)
WEEK_AGO_TOLERANCE = timedelta(days=3)

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
                z_week_ago=feat.z_1d_week_ago,
                # 60일 z 는 "최근 두 달 대비 이례적인가" 만 답한다. "역사적으로
                # 어디 있는가" 는 백분위가 답한다 — 10년물 5% 가 60일 z 로는
                # +0.9σ 지만 1년 백분위로는 98% 인 식이다.
                percentile=feat.percentile_1y,
                percentile_observations=feat.percentile_observations,
                change_3m=feat.ret_3m,
                change_3m_display=_format_change(ins, feat.ret_3m),
            )
        )
    rows.sort(key=lambda r: abs(r.z or 0.0), reverse=True)
    return rows[:WHATS_MOVING_LIMIT]


class _DisabledSettings:
    """LLM 클라이언트가 주어지지 않았을 때 쓰는 비활성 설정."""

    llm_enabled = False
    llm_timeout_sec = 8.0


#: data_health 에 싣는 공급자 실패 요약의 최대 줄 수. 47종목이 전부
#: 실패하면 경고가 화면을 덮는다 — 대표적인 것만 보이고 나머지는 개수로 낸다.
ADAPTER_WARNING_LIMIT = 4


def adapter_warnings(
    market_adapter: object, news_adapter: object, missing: Sequence[str]
) -> list[str]:
    """
    어느 종목이 왜 빠졌는지, 어느 피드가 왜 죽었는지.

    coverage 가 62% 라는 숫자만으로는 고칠 수가 없다. 무엇이 어떤 이유로
    빠졌는지 화면에 있어야 사용자가 조치한다 (요구 15-6).
    """
    notes: list[str] = []

    outcomes = getattr(market_adapter, "outcomes", None)
    if outcomes:
        failed = [o for o in outcomes.values() if not o.ok]
        for o in failed[:ADAPTER_WARNING_LIMIT]:
            notes.append(f"{o.instrument_id}: {o.reason}")
        if len(failed) > ADAPTER_WARNING_LIMIT:
            notes.append(f"… 외 {len(failed) - ADAPTER_WARNING_LIMIT}개 종목도 같은 이유로 실패")

    feed_outcomes = getattr(news_adapter, "outcomes", None)
    if feed_outcomes:
        dead = [f"{k}: {v}" for k, v in feed_outcomes.items() if not v.endswith("건")]
        for line in dead[:ADAPTER_WARNING_LIMIT]:
            notes.append(f"뉴스 피드 {line}")
        if len(dead) > ADAPTER_WARNING_LIMIT:
            notes.append(f"… 외 {len(dead) - ADAPTER_WARNING_LIMIT}개 피드도 실패")
    return notes


def freshness_warnings(snapshot: MarketSnapshot) -> list[str]:
    """
    낡은 데이터를 조용히 오늘 시장처럼 보여주지 않는다.

    화면에 신선도 숫자가 있어도 사람은 잘 안 본다. 며칠 지난 값으로
    "지금 시장" 을 읽으면 판단이 통째로 틀어지므로 문장으로 말한다.
    """
    stale = [(iid, p.meta.freshness_sec) for iid, p in snapshot.points.items() if p.meta.is_stale]
    if not stale:
        return []
    stale.sort(key=lambda x: -x[1])
    worst_id, worst_sec = stale[0]
    days = worst_sec / 86400.0
    if len(stale) == len(snapshot.points):
        who = "확보된 전 종목"
    else:
        names = ", ".join(iid for iid, _ in stale[:3])
        who = f"{len(stale)}개 종목({names}{'…' if len(stale) > 3 else ''})"
    return [
        f"{who}의 데이터가 기준 신선도를 넘었다. 가장 오래된 것은 "
        f"{worst_id} 로 {days:.1f}일 전 값이다. 지금 시장이 아니라 "
        f"그때 시장을 보고 있는 것이다."
    ]


def build_observations(
    snapshot: MarketSnapshot,
    instruments_by_id: dict[str, Instrument],
    factors: Mapping[str, FactorScore],
) -> dict[str, Observation]:
    """
    Impact Map 노드에 붙일 실측 반응.

    가격이 있는 것만 넣는다 — 종목과 매크로 factor. 테마와 업종은 제외한다.
    테마 점수는 뉴스·가격·수급을 섞은 합성값이라, 그것을 '실측 가격 반응'
    칸에 넣으면 내러티브를 내러티브로 검증하게 된다. 비워 두는 편이 정직하다.
    """
    out: dict[str, Observation] = {}
    for iid, feat in snapshot.features.items():
        if feat.z_1d is None:
            continue
        ins = instruments_by_id.get(iid)
        out[iid] = Observation(
            z=feat.z_1d,
            display=_format_change(ins, feat.ret_1d) if ins else None,
        )
    for name, fs in factors.items():
        out[name] = Observation(z=fs.score)
    return out


def build_data_health(
    snapshot: MarketSnapshot,
    news_items: list[RawNewsItem],
    *,
    llm_enabled: bool,
    timings_ms: dict[str, float],
    warnings: list[str] | None = None,
    llm_status: str | None = None,
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
        llm_status=llm_status or ("disabled" if not llm_enabled else "ok"),
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
    pending_divergences: Sequence[Divergence] = (),
    pending_out: list[Divergence] | None = None,
    llm_client: LLMClient | None = None,
    week_ago: IntelligenceSnapshot | None = None,
) -> IntelligenceSnapshot:
    """
    순수 함수. 스냅샷과 뉴스를 받아 최종 인텔리전스를 만든다.

    history 는 오래된 것부터 정렬된 과거 스냅샷이다. Persistence(상태 판정의
    지속성)와 Stability(테마 점수의 안정성) 계산에 쓴다. 비어 있으면 두 항은
    None 이 되고 confidence 가중치가 재정규화된다 — 0 으로 채우지 않는다.

    week_ago 는 약 1주 전 저장 스냅샷이다 (GOAL Kickstart 의 'Latest vs
    1-week ago' 관례). 뉴스가 섞인 값(온도계 뉴스·종합, 테마 점수)의 1주 전
    표식에만 쓴다. 가격에서 나오는 값의 1주 전은 시계열에서 직접 잰다.
    """
    timings = dict(timings_ms or {})
    previous = history[-1] if history else None
    notes = list(warnings or [])
    themes_registry = get_themes().by_id()

    # 이벤트 창. as_of 와 달력 파일만으로 결정된다 — 시계를 읽지 않는다.
    calendar = event_window(market_snapshot.as_of)

    # LLM 은 파이프라인 바깥의 enrichment 다. 꺼져 있거나 실패하면 룰
    # 추출기로 돌아가고, 아래 정량 경로는 전혀 영향을 받지 않는다.
    t = time.perf_counter()
    if llm_client is not None and llm_client.available():
        events, extract_notes = llm_extract_events(
            news_items, llm_client, themes_registry, instruments_by_id
        )
        notes.extend(extract_notes)
    else:
        events = rule_extract_events(news_items, as_of=market_snapshot.as_of)
    timings["extract"] = (time.perf_counter() - t) * 1000.0

    t = time.perf_counter()
    market_state = compute_market_state(
        market_snapshot,
        instruments_by_id,
        previous_label=previous.market_state.primary_label if previous else None,
        persistence_scale=calendar.persistence_scale,
    )
    timings["market_state"] = (time.perf_counter() - t) * 1000.0

    t = time.perf_counter()
    themes = compute_theme_states(
        list(themes_registry.values()),
        market_snapshot,
        events,
        instruments_by_id,
        previous={ts.theme_id: ts for ts in previous.themes} if previous else None,
        history={
            th_id: theme_score_history(history, th_id) for th_id in themes_registry
        },
    )
    if week_ago is not None:
        week_scores = {ts.theme_id: ts.theme_score for ts in week_ago.themes}
        themes = [
            ts.model_copy(update={"week_ago_score": week_scores.get(ts.theme_id)})
            for ts in themes
        ]
    timings["theme"] = (time.perf_counter() - t) * 1000.0

    # 직전 틱의 확정 괴리와 미확정 후보를 합쳐 지속 기간을 잇는다.
    prior_divergences = list(previous.divergences if previous else []) + list(
        pending_divergences
    )

    t = time.perf_counter()
    divergences = detect_divergences(
        themes,
        themes_registry,
        market_state,
        market_snapshot,
        instruments_by_id,
        previous=prior_divergences,
    )
    if pending_out is not None:
        pending_out.extend(
            pending_candidates(
                themes,
                themes_registry,
                market_state,
                market_snapshot,
                instruments_by_id,
                previous=prior_divergences,
            )
        )
    timings["divergence"] = (time.perf_counter() - t) * 1000.0

    t = time.perf_counter()
    impact_maps = build_impact_maps(
        events,
        themes_registry,
        instruments_by_id,
        market_snapshot.as_of,
        observed=build_observations(
            market_snapshot, instruments_by_id, market_state.factors
        ),
        correlations=market_snapshot.correlations,
    )
    timings["relationship"] = (time.perf_counter() - t) * 1000.0

    # 템플릿 문장이 먼저 있고, LLM 은 그것을 다듬는다. LLM 이 없거나 지어낸
    # 숫자를 쓰면 템플릿이 그대로 화면에 간다 (요구 15-7).
    t = time.perf_counter()
    narrative, narrative_source, summary_notes = summarize(
        market_state,
        themes,
        divergences,
        llm_client or build_client(_DisabledSettings()),
        fallback=market_state.narrative,
    )
    notes.extend(summary_notes)

    # 서킷이 영구히 열린 뒤에는 매 틱 경고가 새로 생기지 않는다. 이유가
    # 화면에서 사라지지 않도록 상태를 한 줄로 계속 남긴다.
    if llm_client is not None and llm_client.status == "failed":
        reason = llm_client.last_error or "복구 불가능한 오류"
        note = f"LLM 사용 불가: {reason} 정량 파이프라인은 정상 동작한다."
        if note not in notes:
            notes.append(note)
    elif llm_client is not None and llm_client.status == "degraded" and llm_client.last_error:
        # 키는 맞는데 계정 크레딧이 없다든지, 한도에 걸렸다든지. "degraded" 한
        # 단어로는 무엇을 고쳐야 하는지 알 수 없다.
        note = f"LLM 호출 실패 중: {llm_client.last_error} 룰 기반으로 대체했다."
        if note not in notes:
            notes.append(note)
    market_state = market_state.model_copy(
        update={"narrative": narrative, "narrative_source": narrative_source}
    )
    timings["summarize"] = (time.perf_counter() - t) * 1000.0

    # 온도계는 위에서 이미 계산된 factor 와 이벤트만 다시 읽는다. 새 데이터는
    # 없고, 그래서 여기가 맞는 자리다 — 모든 재료가 확정된 뒤.
    t = time.perf_counter()
    thermometer = compute_thermometer(
        market_state,
        events,
        market_snapshot.as_of,
        previous=previous.thermometer if previous else None,
        week_ago=week_ago.thermometer if week_ago else None,
    )
    timings["thermometer"] = (time.perf_counter() - t) * 1000.0

    health = build_data_health(
        market_snapshot,
        news_items,
        llm_enabled=llm_enabled,
        timings_ms=timings,
        warnings=notes,
        llm_status=llm_client.status if llm_client else None,
    )

    t = time.perf_counter()
    alerts: list[Alert] = build_alerts(
        market_state,
        themes,
        divergences,
        market_snapshot,
        health,
        instruments_by_id,
        previous_state=previous.market_state if previous else None,
        previous_themes=(
            {ts.theme_id: ts for ts in previous.themes} if previous else None
        ),
        previous_divergences=previous.divergences if previous else (),
        previous_alerts=previous.alerts if previous else (),
        threshold_scale=calendar.alert_threshold_scale,
    )
    # 조건이 아직 참인 대상. 괴리가 이어지는 동안 그 알림은 해소가 아니다.
    live_subjects = {d.id for d in divergences} | {
        d.subject for d in alerts
    }
    alerts += carry_forward(
        alerts,
        previous.alerts if previous else (),
        market_snapshot.as_of,
        live_subjects=live_subjects,
    )
    timings["alert"] = (time.perf_counter() - t) * 1000.0

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
        thermometer=thermometer,
        calendar=calendar,
        themes=themes,
        divergences=divergences,
        alerts=alerts,
        impact_maps=impact_maps,
        events=events,
        whats_moving=whats_moving,
        data_health=health.model_copy(
            update={"engine_timings_ms": {k: round(v, 2) for k, v in timings.items()}}
        ),
        engine_versions=dict(ENGINE_VERSIONS),
    )


@dataclass(frozen=True)
class PipelineResult:
    """
    한 틱의 산출물 전체.

    pending 은 아직 min_duration 을 못 채운 divergence 후보다. 스냅샷에는
    싣지 않지만 다음 틱에서 지속 기간을 이으려면 어딘가 남겨야 한다.
    """

    snapshot: IntelligenceSnapshot
    pending: list[Divergence]


def run_pipeline(
    settings: Settings,
    *,
    as_of: datetime | None = None,
    history: Sequence[IntelligenceSnapshot] = (),
    pending_divergences: Sequence[Divergence] = (),
    week_ago: IntelligenceSnapshot | None = None,
) -> IntelligenceSnapshot:
    """한 틱 실행. 대부분의 호출자는 스냅샷만 필요하다."""
    return run_pipeline_detailed(
        settings,
        as_of=as_of,
        history=history,
        pending_divergences=pending_divergences,
        week_ago=week_ago,
    ).snapshot


def run_pipeline_detailed(
    settings: Settings,
    *,
    as_of: datetime | None = None,
    history: Sequence[IntelligenceSnapshot] = (),
    pending_divergences: Sequence[Divergence] = (),
    week_ago: IntelligenceSnapshot | None = None,
) -> PipelineResult:
    """I/O 를 포함한 한 tick 실행. 어댑터 -> 정규화 -> 엔진."""
    # 지연 import: 레지스트리 캐시와 순환 참조를 피한다.
    from ..adapters.registry import (
        build_market_adapter,
        build_news_adapter,
        mode_warnings,
    )

    registry = get_instruments()
    instruments = registry.instruments
    by_id = registry.by_id()
    timings: dict[str, float] = {}
    warnings: list[str] = list(mode_warnings(settings))

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
        news_items = news_adapter.fetch_news(limit=settings.news_limit, as_of=as_of)
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
    warnings.extend(adapter_warnings(market_adapter, news_adapter, snapshot.missing))
    warnings.extend(freshness_warnings(snapshot))

    llm_client = build_client(settings)

    pending: list[Divergence] = []
    result = build_intelligence(
        snapshot,
        news_items,
        by_id,
        scenario=settings.scenario if settings.data_mode is DataMode.MOCK else None,
        llm_enabled=settings.llm_enabled,
        timings_ms=timings,
        warnings=warnings,
        history=history,
        pending_divergences=pending_divergences,
        pending_out=pending,
        llm_client=llm_client,
        week_ago=week_ago,
    )
    return PipelineResult(snapshot=result, pending=pending)
