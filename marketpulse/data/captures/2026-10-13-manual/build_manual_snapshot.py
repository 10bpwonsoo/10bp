"""run_tick — 9/15 수기 캡처(marketpulse/data/captures/2026-09-15-manual/build_manual_snapshot.py)의 함수를 그대로 옮긴 scratchpad 헬퍼.
컨테이너 재시작으로 scratchpad 가 지워져 커밋된 원본에서 복원했다(2026-10-13). 엔진 로직은 새로 짜지 않는다."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


from marketpulse.adapters.registry import build_market_adapter
from marketpulse.ai.client import build_client
from marketpulse.ai.summarizer import summarize
from marketpulse.config.registry import get_instruments, get_themes
from marketpulse.config.settings import Settings
from marketpulse.engines.alert import build_alerts, carry_forward
from marketpulse.engines.calendar import event_window
from marketpulse.engines.divergence import detect_divergences, pending_candidates
from marketpulse.engines.market_state import compute_market_state
from marketpulse.engines.normalize import build_snapshot
from marketpulse.engines.orchestrator import (
    ENGINE_VERSIONS,
    WHATS_MOVING_LIMIT,
    adapter_warnings,
    build_data_health,
    build_observations,
    build_theme_movers,
    build_whats_moving,
    freshness_warnings,
)
from marketpulse.engines.relationship import build_impact_maps
from marketpulse.engines.theme import compute_theme_states
from marketpulse.engines.thermometer import compute_thermometer
from marketpulse.models.common import utcnow
from marketpulse.models.news import NewsEvent, ValidationReport
from marketpulse.models.snapshot import IntelligenceSnapshot


def run_tick(
    market_snapshot, events, instruments_by_id, themes_registry, *, previous, pending_in
) -> tuple[IntelligenceSnapshot, list]:
    """build_intelligence() 의 추출 이후 단계를 그대로 재현한다."""
    calendar = event_window(market_snapshot.as_of)
    market_state = compute_market_state(
        market_snapshot,
        instruments_by_id,
        previous_label=previous.market_state.primary_label if previous else None,
        persistence_scale=calendar.persistence_scale,
    )
    themes = compute_theme_states(
        list(themes_registry.values()),
        market_snapshot,
        events,
        instruments_by_id,
        previous={ts.theme_id: ts for ts in previous.themes} if previous else None,
        history={},
    )
    # 직전 틱의 확정 괴리 + 미확정 후보(pending)를 합쳐야 지속기간(2틱)이 이어진다.
    prior_divergences = list(previous.divergences if previous else []) + list(pending_in)
    divergences = detect_divergences(
        themes, themes_registry, market_state, market_snapshot, instruments_by_id,
        previous=prior_divergences,
    )
    pending_out = pending_candidates(
        themes, themes_registry, market_state, market_snapshot, instruments_by_id,
        previous=prior_divergences,
    )
    impact_maps = build_impact_maps(
        events, themes_registry, instruments_by_id, market_snapshot.as_of,
        observed=build_observations(market_snapshot, instruments_by_id, market_state.factors),
        correlations=market_snapshot.correlations,
    )
    # 요약은 비활성 클라이언트로 — market_state 가 이미 들고 있는 템플릿
    # 문장을 그대로 쓴다. API 호출 0건.
    narrative, narrative_source, summary_notes = summarize(
        market_state, themes, divergences,
        build_client(Settings(llm_enabled=False)), fallback=market_state.narrative,
    )
    market_state = market_state.model_copy(
        update={"narrative": narrative, "narrative_source": narrative_source}
    )
    notes = list(summary_notes)
    notes.append(
        f"이 스냅샷의 뉴스 이벤트 {len(events)}건은 전부 Claude(이 세션)가 API 없이 직접 읽고 "
        "태깅했다 — extractor='manual'. 자동화된 Anthropic API 추출이 아니며 저절로 갱신되지 않는다."
    )
    health = build_data_health(
        market_snapshot, [], llm_enabled=False,
        timings_ms={}, warnings=notes, llm_status="disabled", events=events,
    )
    alerts = build_alerts(
        market_state, themes, divergences, market_snapshot, health, instruments_by_id,
        previous_state=previous.market_state if previous else None,
        previous_themes={ts.theme_id: ts for ts in previous.themes} if previous else None,
        previous_divergences=previous.divergences if previous else (),
        previous_alerts=previous.alerts if previous else (),
        threshold_scale=calendar.alert_threshold_scale,
    )
    live_subjects = {d.id for d in divergences} | {a.subject for a in alerts}
    alerts += carry_forward(
        alerts, previous.alerts if previous else (), market_snapshot.as_of,
        live_subjects=live_subjects,
    )
    whats_moving = build_whats_moving(market_snapshot, instruments_by_id)
    whats_moving += build_theme_movers(themes)
    whats_moving.sort(key=lambda r: abs(r.z if r.z is not None else (r.change or 0.0) / 20.0), reverse=True)
    whats_moving = whats_moving[:WHATS_MOVING_LIMIT]
    thermometer = compute_thermometer(
        market_state, events, market_snapshot.as_of,
        previous=previous.thermometer if previous else None,
    )
    snap = IntelligenceSnapshot(
        as_of=market_snapshot.as_of,
        mode=market_snapshot.mode,
        scenario=None,
        market_state=market_state,
        thermometer=thermometer,
        calendar=calendar,
        themes=themes,
        divergences=divergences,
        alerts=alerts,
        impact_maps=impact_maps,
        events=events,
        whats_moving=whats_moving,
        data_health=health,
        engine_versions=dict(ENGINE_VERSIONS),
    )
    return snap, pending_out
