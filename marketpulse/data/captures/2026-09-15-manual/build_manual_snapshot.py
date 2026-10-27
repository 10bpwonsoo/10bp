"""
API 크레딧 없이 '뉴스가 구조화됐을 때' 를 보여주는 수기 캡처.

build_intelligence() 를 그대로 쓰지 않는다 — 그 함수는 내부에서 자동으로
LLM/룰 추출기를 부른다. 여기서는 추출 단계만 손으로 만든 NewsEvent 로
바꿔치기하고, 나머지(시장 판정·테마·괴리·영향경로·알림·온도계)는 전부
같은 순수 함수를 그대로 재사용한다 — 엔진 로직은 한 줄도 새로 안 짠다.

extractor="manual" 로 정직하게 남긴다. 이것은 Anthropic API 호출이 아니라
이 세션(Claude)이 기사를 읽고 직접 분류한 것이다.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/tmp/claude-0/-home-user-10bp/d1217ff9-9e47-595a-ade2-530a334c6aba/scratchpad")
from manual_tags import TAGS

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

CAPTURE_DIR = Path("marketpulse/data/captures/2026-09-15-llm-3")
OUT_DIR = Path("marketpulse/data/captures/2026-09-15-manual")


def build_manual_events(raw_items: list[dict]) -> list[NewsEvent]:
    """캡처된 RawNewsItem 60건 중 TAGS 에 있는 것만 NewsEvent 로. 나머지는 버린다
    (테마와 무관한 사내공시·프로모션 기사라 애초에 룰 추출기도 태그를 못 단다)."""
    by_id = {i["id"]: i for i in raw_items}
    out: list[NewsEvent] = []
    for item_id, tag in TAGS.items():
        item = by_id[item_id]
        out.append(
            NewsEvent(
                id=f"manual-{item_id}",
                source_item_ids=[item_id],
                event=item["title"],
                event_type=tag["event_type"],
                themes=tag["themes"],
                theme_sentiment=tag["theme_sentiment"],
                theme_direction=tag["theme_direction"],
                sentiment=tag["sentiment"],
                impact_score=tag["impact"],
                novelty_score=tag["novelty"],
                time_horizon=tag["horizon"],
                reason=tag["reason"],
                source=item["publisher"],
                timestamp=item["published_at"],
                extractor="manual",
                extractor_model=None,
                validation=ValidationReport(schema_ok=True),
                # 사람이 한 번 읽고 판단한 값. 다중 검증을 거친 LLM 출력보다는
                # 보수적으로 잡는다.
                confidence=0.55,
            )
        )
    out.sort(key=lambda e: e.timestamp, reverse=True)
    return out


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


def main() -> None:
    settings = Settings(data_mode="DELAYED", llm_enabled=False)  # 시장데이터만. API 0건.
    registry = get_instruments()
    instruments = registry.instruments
    by_id = registry.by_id()
    themes_registry = get_themes().by_id()

    print("시장데이터 재수집 중 (무료 공급자, API 아님)...")
    market_adapter = build_market_adapter(settings)
    as_of = utcnow()
    series = market_adapter.fetch_series(instruments, bars=settings.history_bars, as_of=as_of)
    snapshot = build_snapshot(instruments, series, mode=market_adapter.mode, zscore_window=settings.zscore_window)
    print(f"  coverage {len(snapshot.points)}/{len(instruments)}")

    raw_items = json.loads((CAPTURE_DIR / "news_live.json").read_text(encoding="utf-8"))
    events = build_manual_events(raw_items)
    print(f"수기 태깅 이벤트 {len(events)}건 (원본 기사 {len(raw_items)}건 중)")

    tick1, pending1 = run_tick(snapshot, events, by_id, themes_registry, previous=None, pending_in=[])
    tick2, _ = run_tick(snapshot, events, by_id, themes_registry, previous=tick1, pending_in=pending1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "live.json").write_text(tick2.model_dump_json(), encoding="utf-8")
    (OUT_DIR / "news_live.json").write_text(
        json.dumps(raw_items, ensure_ascii=False), encoding="utf-8"
    )

    ms, th, h = tick2.market_state, tick2.thermometer, tick2.data_health
    print(f"\nas_of={tick2.as_of}  state={ms.primary_label.value} conf={ms.confidence:.0f}%")
    print("drivers:", ", ".join(f"{d.label} {d.z:+.1f}σ" for d in ms.main_drivers))
    print(f"thermo: comp={th.composite:+.0f} price={th.price:+.0f} news={th.news:+.0f} gap={th.gap_flag} conf={th.confidence:.0f}")
    print("themes(top6):", [(t.name, round(t.theme_score), t.news_sentiment and round(t.news_sentiment)) for t in sorted(tick2.themes, key=lambda x: -abs(x.theme_score))[:6]])
    print("divergences:", [(d.type.value, d.related_theme, round(d.severity)) for d in tick2.divergences])
    print("alerts:", len(tick2.alerts), "| maps:", [(m.max_depth, len(m.nodes)) for m in tick2.impact_maps])
    print("extractors:", sorted({e.extractor for e in tick2.events}))


if __name__ == "__main__":
    main()
