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
    if getattr(args, "mode", None):
        # model_copy 는 검증을 건너뛴다. 문자열이 그대로 들어가면 뒤에서
        # .value 가 터진다. 여기서 enum 으로 바꿔 둔다.
        s = s.model_copy(update={"data_mode": DataMode(args.mode)})
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

    # ── THERMOMETER ──
    th = snap.thermometer
    if th is not None:
        a("  SENTIMENT THERMOMETER")
        a(f"    종합 {_sig(th.composite)}  {th.trend_arrow}  {th.band_label:<6s}"
          f"  가격 {_sig(th.price)}  뉴스 {_sig(th.news)}  신뢰도 {th.confidence:3.0f}%"
          f"  기사 {th.news_events}건")
        a("    " + _wrap(th.note, 66, indent="    "))
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


def cmd_probe(args: argparse.Namespace) -> int:
    """
    공급자 연결 상태와 종목별 커버리지를 표로 낸다.

    막힌 네트워크에서 개발했기 때문에 이 명령이 필요하다. 사용자가 자기
    네트워크에서 한 번 돌리면 무엇이 되고 무엇이 안 되는지, 안 되면
    왜인지가 한 화면에 나온다. "안 된다" 와 "왜 안 되는지" 는 다르다.
    """
    from .adapters.registry import build_market_adapter, build_news_adapter

    settings = _settings(args)
    out: list[str] = [f"DATA PROBE  ·  모드 {settings.data_mode.value}", RULE]

    market = build_market_adapter(settings)
    news = build_news_adapter(settings)

    # ── 1. 공급자 사용 가능 여부. 네트워크를 쓰지 않는다 ──
    out.append("공급자")
    probe = getattr(market, "probe", None)
    if probe is None:
        out.append("  MOCK 어댑터에는 외부 공급자가 없다")
    else:
        for name, (ok, why) in probe().items():
            out.append(f"  {'OK ' if ok else '불가'}  {name:<7} {why}")
    out.append("")

    # ── 1b. LLM. 네트워크를 쓰지 않는다 — 키가 있는지, 서킷이 열렸는지만 ──
    from .ai.client import build_client

    llm = build_client(settings)
    out.append("LLM")
    if not settings.llm_enabled:
        out.append("  꺼짐   MARKETPULSE_LLM_ENABLED=true 로 켠다. 키는 ANTHROPIC_API_KEY 환경변수")
    else:
        out.append(f"  {llm.status:<7s} 모델 {llm.model}  뉴스 검색 정책 {settings.news_search}")
        if llm.last_error:
            out.append(f"         {llm.last_error}")
    out.append("")

    if args.offline:
        out.append("--offline: 실제 수집은 건너뛴다")
        print("\n".join(out))
        return 0

    if args.llm_search:
        # 검색 한 번을 실제로 돌려 본다. 키가 맞는지, 결과가 오는지, 무엇이
        # 왜 버려지는지가 한 화면에 나온다.
        from .adapters.news.llm_search import LlmSearchNewsAdapter

        search = LlmSearchNewsAdapter(llm, config_dir=settings.config_dir)
        found = search.fetch_news(limit=settings.news_limit)
        out.append(f"LLM 검색  {len(found)}건")
        for name, result in sorted(search.probe().items()):
            out.append(f"  {name:<12} {result}")
        for item in found[:8]:
            out.append(f"     {item.published_at:%m-%d %H:%M}  {item.publisher:<20} {item.title[:70]}")
        out.append("")
        print("\n".join(out))
        return 0 if found else 1

    # ── 2. 실제 수집 ──
    instruments = get_instruments().instruments
    if args.only:
        wanted = {x.strip().upper() for x in args.only.split(",")}
        instruments = [i for i in instruments if i.id.upper() in wanted]
        if not instruments:
            print(f"일치하는 instrument 가 없다: {args.only}")
            return 2

    out.append(f"종목 {len(instruments)}개 수집 시도…")
    series = market.fetch_series(instruments, bars=settings.history_bars)
    outcomes = getattr(market, "outcomes", {}) or {}

    ok_rows = [o for o in outcomes.values() if o.ok]
    bad_rows = [o for o in outcomes.values() if not o.ok]
    total = len(outcomes) or len(instruments)
    got = len(ok_rows) or len(series)
    out.append("")
    out.append(f"커버리지  {got}/{total} ({got / total * 100 if total else 0:.0f}%)")
    out.append("")

    if bad_rows:
        out.append("실패")
        for o in sorted(bad_rows, key=lambda x: x.instrument_id):
            out.append(f"  x  {o.instrument_id:<18} {o.reason}")
        out.append("")

    if args.verbose and ok_rows:
        out.append("성공")
        for o in sorted(ok_rows, key=lambda x: x.instrument_id):
            out.append(f"  o  {o.instrument_id:<18} {o.reason}")
        out.append("")

    host_status = getattr(market, "host_status", None)
    if host_status:
        status = host_status()
        if status:
            out.append("호스트")
            for host, state in sorted(status.items()):
                out.append(f"  {state:<28} {host}")
            out.append("")

    # ── 3. 뉴스 ──
    items = news.fetch_news(limit=settings.news_limit)
    out.append(f"뉴스  {len(items)}건")
    for name, result in sorted((getattr(news, "outcomes", {}) or {}).items()):
        mark = "o" if result.endswith("건") else "x"
        out.append(f"  {mark}  {name:<18} {result}")
    if items and args.verbose:
        out.append("")
        for item in items[:5]:
            out.append(f"     {item.title[:86]}")

    print("\n".join(out))
    # 하나도 못 가져왔으면 실패로 끝낸다. 스크립트와 CI 가 알아채야 한다.
    return 0 if series else 1


def _pct(value: float | None) -> str:
    """None 은 0 이 아니라 빈 값으로 보인다."""
    return "  -  " if value is None else f"{value:+.2f}%"


def cmd_backtest(args: argparse.Namespace) -> int:
    """
    저장된 스냅샷으로 신호 성적을 낸다.

    매매 전략이 아니라 **신호**를 채점한다. 이 시스템은 주문을 내지 않고,
    검증할 것은 "판정과 괴리가 실제로 무언가를 앞섰는가" 다.

    수익률의 기준 자산을 인자로 받는 이유는 그것이 분석가의 선택이기
    때문이다. 엔진이 몰래 정할 일이 아니다.
    """
    from .adapters.registry import build_market_adapter
    from .analysis.backtest import forward_returns, run_backtest
    from .storage.sqlite_repo import SqliteSnapshotRepository

    settings = _settings(args)
    repo = SqliteSnapshotRepository(args.db)
    try:
        history = repo.recent(args.stream, limit=args.limit)
    finally:
        repo.close()

    if not history:
        print(
            f"{args.db} 에 '{args.stream}' 스냅샷이 없다.\n"
            "스케줄러를 먼저 돌려 히스토리를 쌓아야 한다:\n"
            "  python -m marketpulse.scheduler.runner "
            f"--scenario {settings.scenario} --interval 60 --db {args.db}"
        )
        return 1

    by_id = get_instruments().by_id()
    instrument = by_id.get(args.benchmark)
    if instrument is None:
        print(f"알 수 없는 instrument: {args.benchmark}")
        return 2

    adapter = build_market_adapter(settings)
    series = adapter.fetch_series([instrument], bars=settings.history_bars)
    if args.benchmark not in series:
        reason = getattr(adapter, "outcomes", {}).get(args.benchmark)
        print(
            f"{args.benchmark} 시세를 가져오지 못했다"
            + (f": {reason.reason}" if reason else "")
            + "\n채점할 기준이 없으면 성적을 낼 수 없다."
        )
        return 1

    returns = forward_returns(
        series[args.benchmark],
        [s.as_of for s in history],
        horizon_bars=args.horizon,
    )
    report = run_backtest(history, returns, horizon_bars=args.horizon)

    out = [
        f"SIGNAL BACKTEST  ·  {args.stream}",
        RULE,
        f"스냅샷 {len(history)}개  ·  기준 {instrument.name}({args.benchmark})"
        f"  ·  지평 {args.horizon}봉",
    ]
    if report.baseline_return is not None:
        out.append(f"같은 기간 평균 {report.baseline_return * 100:+.2f}%")
    out.append("")

    if report.by_signal:
        out.append(
            f"{'신호':<32}{'표본':>5}{'적중':>8}{'평균':>10}{'초과':>10}{'MDD':>9}"
        )
        for key, m in report.by_signal.items():
            hit = "  -  " if m.hit_rate is None else f"{m.hit_rate:>5.0f}%"
            out.append(
                f"{key[:31]:<32}{m.samples:>5}{hit:>8}"
                f"{_pct(m.mean_return):>10}{_pct(m.edge):>10}{_pct(m.max_drawdown):>9}"
            )
            if m.note:
                out.append(f"{'':<32}{m.note}")
    else:
        out.append("채점할 신호가 없다.")

    if report.warnings:
        out.append("")
        for w in report.warnings:
            out.append(f"! {w}")
    out.append("")
    out.append(
        "적중률만 보지 마라. 작게 자주 맞고 크게 한 번 틀리는 신호가 "
        "적중률로는 우수해 보인다."
    )
    print("\n".join(out))
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

    pr = sub.add_parser(
        "probe",
        help="공급자 연결과 종목별 커버리지를 점검한다",
        description=(
            "네트워크가 막힌 환경에서 개발했다. 자기 네트워크에서 이것을 "
            "돌리면 무엇이 되고 무엇이 왜 안 되는지 한 화면에 나온다."
        ),
    )
    pr.add_argument(
        "--mode",
        choices=["MOCK", "DELAYED", "LIVE"],
        default="DELAYED",
        help="점검할 데이터 모드 (기본 DELAYED)",
    )
    pr.add_argument("--only", help="쉼표로 구분한 instrument id. 예: SPX,US10Y")
    pr.add_argument(
        "--offline", action="store_true", help="실제 수집 없이 설정만 점검한다"
    )
    pr.add_argument("-v", "--verbose", action="store_true", help="성공한 것도 전부 출력")
    pr.add_argument(
        "--llm-search",
        action="store_true",
        help="LLM 웹검색을 실제로 한 번 돌려 결과와 제외 사유를 보인다 (ANTHROPIC_API_KEY 필요)",
    )
    pr.set_defaults(func=cmd_probe)

    bt = sub.add_parser(
        "backtest",
        help="저장된 스냅샷으로 신호 성적을 낸다",
        description=(
            "매매 전략이 아니라 신호를 채점한다. Market State 판정과 괴리가 "
            "실제로 무언가를 앞섰는지 본다."
        ),
    )
    bt.add_argument("--db", default="data/snapshots.db", help="스냅샷 SQLite 경로")
    bt.add_argument(
        "--stream", default="MOCK:baseline", help="스트림 키. 예: MOCK:inflation_shock"
    )
    bt.add_argument("--benchmark", default="SPX", help="수익률 기준 instrument")
    bt.add_argument("--horizon", type=int, default=5, help="신호 이후 몇 봉을 볼지")
    bt.add_argument("--limit", type=int, default=500, help="읽어올 스냅샷 수")
    bt.add_argument("--scenario", help="MOCK 시나리오 이름")
    bt.add_argument(
        "--mode", choices=["MOCK", "DELAYED", "LIVE"], help="기준 시세를 받을 모드"
    )
    bt.set_defaults(func=cmd_backtest)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
