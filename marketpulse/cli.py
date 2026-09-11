"""
터미널 대시보드.

    python -m marketpulse.cli snapshot
    python -m marketpulse.cli snapshot --scenario baseline --json
    python -m marketpulse.cli scenarios
    python -m marketpulse.cli features SOXX

존재 이유는 두 가지다.
  1. 프론트엔드가 빌드되지 않아도 End-to-End 데모가 가능해야 한다
     (설계서 STEP 7.7 demo risk).
  2. 엔진 출력을 눈으로 확인하는 가장 빠른 경로다.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from .adapters.base import AdapterError
from .adapters.market.scenario import available_scenarios, load_scenario
from .config.registry import get_instruments
from .config.settings import Settings, get_settings
from .engines.features import compute_feature
from .engines.orchestrator import run_pipeline_detailed
from .models.common import DataMode
from .models.snapshot import IntelligenceSnapshot

RULE = "─" * 72


def _sig(value: float | None, width: int = 4) -> str:
    """신호 값 표기. None 은 0 이 아니라 빈 값으로 보인다."""
    return "-".rjust(width) if value is None else f"{value:+{width}.0f}"


def _wrap(text: str, width: int, indent: str = "") -> str:
    """한글 폭을 고려하지 않는 단순 줄바꿈. 터미널 출력용으로 충분하다."""
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return ("\n" + indent).join(lines)


def _settings(args: argparse.Namespace) -> Settings:
    s = get_settings()
    if getattr(args, "scenario", None):
        s = s.model_copy(update={"scenario": args.scenario})
    return s


def _kst(dt: datetime) -> str:
    """내부는 UTC, 표시는 KST (설계서 STEP 7.8-2)."""
    from datetime import timedelta

    return (dt.astimezone(timezone.utc) + timedelta(hours=9)).strftime(
        "%Y-%m-%d %H:%M KST"
    )


def render(snap: IntelligenceSnapshot) -> str:
    h = snap.data_health
    out: list[str] = []
    a = out.append

    a("")
    a("  MARKET PULSE AI")
    a(f"  {_kst(snap.as_of)}")
    a(RULE)

    # ── MARKET STATE ──
    ms = snap.market_state
    a("  MARKET STATE")
    label = ms.primary_label.value
    if ms.secondary_label:
        label += f" / {ms.secondary_label.value}"
    a(f"    {label}        Confidence {ms.confidence:.0f}%")
    if not ms.factors:
        a("    (factor / rule 평가는 P1 MarketStateEngine 에서 활성화된다)")
    else:
        for d in ms.main_drivers:
            a(f"    {d.label:<22s} {d.arrow:<3s} {d.z:+.2f}σ")
        a("")
        a("    발동 룰")
        top = ms.hypotheses[0] if ms.hypotheses else None
        if top and top.score > 0:
            for m in top.matched_rules:
                mark = "✓" if m.passed else ("·" if m.evaluable else "?")
                obs = f"{m.observed:+.2f}" if m.observed is not None else "  -  "
                a(f"      {mark} [{m.kind:7s}] {m.expression:<24s} 관측 {obs}")
        a("")
        if ms.narrative:
            a("    " + _wrap(ms.narrative, 66, indent="    "))
    a("")

    # ── THEME ──
    a("  THEME HEATMAP")
    if not snap.themes:
        a("    (Theme Score 는 P1 ThemeEngine 에서 활성화된다)")
    else:
        for t in snap.themes:
            # None 은 '측정되지 않음' 이다. 0 으로 찍으면 '측정했고 중립' 으로 읽힌다.
            a(
                f"    {t.name:<28s} {t.theme_score:+6.1f}   "
                f"news {_sig(t.news_sentiment)}  price {_sig(t.price_momentum)}  "
                f"flow {_sig(t.flow_momentum)}   {t.cross_asset_confirmation.value:<8s} "
                f"conf {t.confidence:3.0f}%"
            )
    a("")

    # ── WHAT'S MOVING ──
    a("  WHAT'S MOVING")
    if not snap.whats_moving:
        a("    임계 이상으로 움직인 변수가 없다")
    for m in snap.whats_moving:
        z = f"{m.z:+.2f}σ" if m.z is not None else "  -  "
        a(f"    {m.arrow:<3s} {m.label:<26s} {z:>8s}   {m.change_display:>12s}")
    a("")

    # ── DIVERGENCE / ALERT ──
    a("  DIVERGENCE")
    if not snap.divergences:
        a("    지속 조건(2틱)을 충족한 괴리 없음")
    for d in snap.divergences:
        legs = "  ".join(f"{l.name} {l.value:+.0f}" for l in d.legs)
        a(
            f"    [{d.severity_band.value:8s}] {d.severity:5.1f}  {d.type.value:22s}"
            f" {d.duration_periods}틱"
        )
        a(f"        {legs}")
        a(f"        {_wrap(d.explanation, 62, indent='        ')}")
    a("")

    a("  ALERT")
    live = [al for al in snap.alerts if al.state.value != "RESOLVED"]
    if not snap.alerts:
        a("    임계 이상으로 변한 항목 없음")
    for al in snap.alerts:
        mark = " " if al.state.value != "RESOLVED" else "~"
        t = al.trigger
        count = f" x{al.fire_count}" if al.fire_count > 1 else ""
        a(f"  {mark} [{al.severity_band.value:8s}] {al.title}{count}")
        a(
            f"        {t.metric}  {t.baseline:.1f} → {t.current:.1f}"
            f"  (Δ{t.delta:+.1f}"
            + (f", {t.delta_pct:+.0f}%" if t.delta_pct is not None else "")
            + f", 임계 {t.threshold:.1f})"
        )
    if snap.alerts:
        a(f"    진행 {len(live)}건 / 전체 {len(snap.alerts)}건 (~ 는 해소됨)")
    a("")

    # ── DATA HEALTH ──
    a(RULE)
    a(
        f"  DATA  mode={h.mode.value}"
        + (f" scenario={snap.scenario}" if snap.scenario else "")
        + f"  coverage={h.coverage:.0%} ({h.available_instruments}/{h.expected_instruments})"
        f"  news={h.news_items}  llm={h.llm_status}"
    )
    total_ms = sum(h.engine_timings_ms.values())
    timings = "  ".join(f"{k} {v:.0f}ms" for k, v in h.engine_timings_ms.items())
    a(f"  TIME  {total_ms:.0f}ms total   {timings}")
    if h.missing:
        a(f"  MISSING  {', '.join(h.missing[:8])}")
    for w in h.warnings:
        a(f"  WARN  {w}")
    a("")
    return "\n".join(out)


def cmd_snapshot(args: argparse.Namespace) -> int:
    settings = _settings(args)
    try:
        # 괴리는 최소 두 틱이 있어야 확정되고, 알림은 직전 틱과 비교해야
        # '변화' 를 말할 수 있다. 한 번만 돌리면 두 패널이 비어 있다.
        history: list = []
        pending: list = []
        for _ in range(max(1, args.warmup + 1)):
            result = run_pipeline_detailed(
                settings, history=history, pending_divergences=pending
            )
            history.append(result.snapshot)
            pending = result.pending
        snap = history[-1]
    except AdapterError as exc:
        print(f"어댑터 오류: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"시나리오 오류: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(snap.model_dump(mode="json"), ensure_ascii=False, indent=2))
    else:
        print(render(snap))
    return 0


def cmd_scenarios(args: argparse.Namespace) -> int:
    settings = get_settings()
    names = available_scenarios(settings.mock_dir)
    if not names:
        print("시나리오가 없다", file=sys.stderr)
        return 1
    for name in names:
        sc = load_scenario(settings.mock_dir, name)
        active = " (기본)" if name == settings.scenario else ""
        print(f"  {name}{active}\n      {sc.title}\n      {sc.description}\n")
    return 0


def cmd_features(args: argparse.Namespace) -> int:
    """한 instrument 의 파생 지표를 뜯어본다. 스코어 검증에 쓴다."""
    from .adapters.registry import build_market_adapter

    settings = _settings(args)
    registry = get_instruments()
    by_id = registry.by_id()
    if args.instrument not in by_id:
        print(f"알 수 없는 instrument: {args.instrument}", file=sys.stderr)
        print(f"사용 가능: {', '.join(sorted(by_id))}", file=sys.stderr)
        return 2

    ins = by_id[args.instrument]
    series = build_market_adapter(settings).fetch_series(
        [ins], bars=settings.history_bars
    )
    if ins.id not in series:
        print(f"{ins.id} 시계열을 가져오지 못했다", file=sys.stderr)
        return 1

    f = compute_feature(ins, series[ins.id], window=settings.zscore_window)
    s = series[ins.id]
    print(f"\n  {ins.id}  {ins.name}")
    print(f"  {ins.asset_class.value} / unit={ins.unit} / series_kind={ins.series_kind}")
    print(RULE)
    print(f"  value          {s.last:,.4f}   (prev {s.prev:,.4f})")
    for field, label in [
        ("ret_1d", "ret 1d"), ("ret_5d", "ret 5d"), ("ret_20d", "ret 20d"),
        ("z_1d", "z 1d"), ("z_5d", "z 5d"), ("z_20d", "z 20d"),
        ("realized_vol_20d", "realized vol"), ("rsi_14", "RSI(14)"),
        ("ma_dist_20", "MA20 이격"), ("ma_dist_60", "MA60 이격"),
        ("percentile_1y", "1Y 백분위"),
    ]:
        v = getattr(f, field)
        print(f"  {label:<14s} " + ("-" if v is None else f"{v:>12.4f}"))
    print(f"  observations   {f.observations:>12d}  (window={f.zscore_window})")
    print(f"  source         {f.meta.source}  mode={f.meta.mode.value}  "
          f"freshness={f.meta.freshness_sec}s")
    print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="marketpulse", description="Market Pulse AI 터미널 대시보드"
    )
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("snapshot", help="현재 시장 인텔리전스를 출력한다")
    sp.add_argument("--scenario", help="MOCK 시나리오 이름")
    sp.add_argument(
        "--warmup",
        type=int,
        default=1,
        help=(
            "본 출력 전에 미리 돌릴 틱 수 (기본 1). 괴리는 두 틱, 알림은 "
            "직전 틱과의 비교가 필요하다. 0 이면 첫 틱 상태를 그대로 본다."
        ),
    )
    sp.add_argument("--json", action="store_true", help="JSON 원문으로 출력")
    sp.set_defaults(func=cmd_snapshot)

    sc = sub.add_parser("scenarios", help="사용 가능한 시나리오 목록")
    sc.set_defaults(func=cmd_scenarios)

    sf = sub.add_parser("features", help="한 instrument 의 파생 지표를 뜯어본다")
    sf.add_argument("instrument", help="instrument id. 예: SOXX")
    sf.add_argument("--scenario", help="MOCK 시나리오 이름")
    sf.set_defaults(func=cmd_features)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
