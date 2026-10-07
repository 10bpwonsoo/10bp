"""
Investment Intelligence 오케스트레이터 (2026-09-16 신설).

기존 build_intelligence() 는 손대지 않는다. 이 함수는 그 결과(IntelligenceSnapshot)
와 종목·대체데이터 시계열을 받아 **그 아래 계층** 을 만든다.

    MARKET(기존) → ALTERNATIVE DATA → INDUSTRY → STOCK → PRICE/FLOW → FUNDAMENTAL → ANALYST → COMMENTARY

build_investment() 는 순수 함수다. I/O 는 run_investment() 가 한다.
기존 스냅샷 경로와 분리돼 있어 기존 화면 속도에 영향이 없다 (요구 36).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence

from ..adapters.market.scenario import load_scenario
from ..config.registry import get_instruments, get_intelligence_config, get_stock_exposures, get_universe
from ..config.settings import Settings
from ..models.common import DataMode, utcnow
from ..models.intelligence import (
    SourceSpec,
    AltDataPoint, AnalystSnapshot, Commentary, DriverCard, IntelligenceHealth, InvestmentIntelligence,
    StockIntelligence, StockRow, ThemeStockRow, WatchlistRow,
)
from ..models.market import Instrument, MarketFeature, MarketSeries
from ..models.snapshot import IntelligenceSnapshot
from .alternative_data import ENGINE_VERSION as ALT_VERSION, build_alt_points
from .analyst import ENGINE_VERSION as ANALYST_VERSION, build_analyst
from .commentary import ENGINE_VERSION as COMMENTARY_VERSION, load_commentary, pick
from .commodity_impact import ENGINE_VERSION as COMMODITY_VERSION, build_commodity_impact
from .features import compute_feature
from .lead_lag import ENGINE_VERSION as LEADLAG_VERSION, compute_lead_lag
from .semiconductor import ENGINE_VERSION as SEMI_VERSION, build_semiconductor
from .stock_anomaly import ENGINE_VERSION as ANOMALY_VERSION, detect_anomalies
from .stock_divergence import ENGINE_VERSION as SDIV_VERSION, detect_stock_divergences
from .stock_explanation import ENGINE_VERSION as EXPLAIN_VERSION, explain_stock
from .stock_exposure import ENGINE_VERSION as EXPOSURE_VERSION, change_frame, compute_exposures
from .stock_features import ENGINE_VERSION as SFEAT_VERSION, build_stock_features
from .stock_impact import ENGINE_VERSION as IMPACT_VERSION, compute_impacts

logger = logging.getLogger(__name__)

ENGINE_VERSIONS: dict[str, str] = {
    "stock_features": SFEAT_VERSION, "stock_exposure": EXPOSURE_VERSION, "stock_impact": IMPACT_VERSION,
    "stock_anomaly": ANOMALY_VERSION, "stock_explanation": EXPLAIN_VERSION, "stock_divergence": SDIV_VERSION,
    "alternative_data": ALT_VERSION, "commodity_impact": COMMODITY_VERSION, "semiconductor": SEMI_VERSION,
    "analyst": ANALYST_VERSION, "lead_lag": LEADLAG_VERSION, "commentary": COMMENTARY_VERSION,
    "investment": "0.1.0",
}

COMMENTARY_DIR = Path(__file__).resolve().parent.parent / "data" / "commentary"


def _fmt(ins: Instrument | None, value: float | None) -> str:
    if value is None:
        return "–"
    if ins is None or ins.series_kind == "price":
        return f"{value:+.2f}%"
    if ins.unit == "percent":
        return f"{value:+.1f}bp"
    return f"{value:+.2f}"


def _mentions_stock(event, meta) -> bool:
    """기사가 이 종목을 직접 지목했는가. 테마 태그만으로는 True 가 아니다."""
    keys = {meta.id.lower(), meta.name.lower(), meta.symbol.lower(), meta.symbol.split(".")[0].lower()}
    keys |= {a.lower() for a in meta.aliases if a}
    # 수기·룰 태깅 기사는 entity 가 비어 있을 수 있다 — 제목·요약에 종목명이 있으면 지목으로 본다
    text = f"{event.event} {event.reason}".lower()
    if any(k in text for k in keys if len(k) >= 2 and k != meta.id.lower()):
        return True
    for ent in event.entities:
        n = (ent.name or "").lower()
        t = (ent.ticker or "").lower()
        if n in keys or t in keys or (n and any(k in n for k in keys if len(k) >= 3)):
            return True
    for a in event.affected_assets:
        if (a.instrument_id or "").lower() in keys or (a.label or "").lower() in keys:
            return True
    return False


def shared_driver_ids(config_dir=None) -> list[str]:
    """유니버스가 참조하는 기존 instruments.yaml 의 id (드라이버·peer·벤치마크)."""
    u = get_universe(config_dir)
    base = get_instruments().by_id()
    wanted = {u.benchmark_market}
    for s in u.stocks:
        wanted.update(s.drivers); wanted.update(s.peers)
    for sid, drivers in get_stock_exposures(config_dir).items():
        wanted.update(drivers.keys())
    wanted.update(get_intelligence_config(config_dir)["drivers"]["candidates"])
    wanted.update(get_intelligence_config(config_dir)["commodity_impact"]["commodities"])
    alt_ids = {a.id for a in u.alternative}
    return sorted(w for w in wanted if w in base and w not in alt_ids)


def build_investment(
    base: IntelligenceSnapshot,
    series_by_id: Mapping[str, MarketSeries],
    *,
    as_of: datetime,
    mode: DataMode,
    scenario: str | None = None,
    analyst_specs=None,
    replay_dir: Path | None = None,
    commentary: Sequence[Commentary] = (),
    previous: InvestmentIntelligence | None = None,
    outcomes: Mapping[str, object] | None = None,
    warnings: Sequence[str] = (),
    timings_ms: Mapping[str, float] | None = None,
    config_dir=None,
) -> InvestmentIntelligence:
    timings = dict(timings_ms or {})
    t0 = time.perf_counter()
    u = get_universe(config_dir)
    icfg = get_intelligence_config(config_dir)
    stocks = u.stocks
    stocks_by_id = u.stock_by_id()
    alt_by_id = u.alt_by_id()
    base_ins = get_instruments().by_id()

    # 모든 시계열의 Instrument 와 라벨
    instruments: dict[str, Instrument] = {}
    labels: dict[str, str] = {}
    for s in stocks:
        instruments[s.id] = s.as_instrument(); labels[s.id] = s.name
    for a in u.alternative:
        instruments[a.id] = a.as_instrument(); labels[a.id] = a.name
    for iid, ins in base_ins.items():
        instruments.setdefault(iid, ins); labels.setdefault(iid, ins.name)

    # 1. feature — 기존 FeatureEngine 그대로
    t = time.perf_counter()
    features: dict[str, MarketFeature] = {}
    for iid, s in series_by_id.items():
        ins = instruments.get(iid)
        if ins is None:
            continue
        try:
            features[iid] = compute_feature(ins, s, window=60)
        except Exception:
            logger.exception("%s feature 실패", iid)
    stock_features = build_stock_features(stocks, series_by_id, market_id=u.benchmark_market)
    timings["features"] = (time.perf_counter() - t) * 1000.0

    # 2. 노출
    t = time.perf_counter()
    exposures = compute_exposures(stocks, series_by_id, instruments, labels=labels, config_dir=config_dir)
    timings["exposure"] = (time.perf_counter() - t) * 1000.0

    # 3. 드라이버 카드 + Market → Stock Impact
    t = time.perf_counter()
    dcfg = icfg["drivers"]
    driver_tuples: list[tuple[str, str, float, float | None]] = []
    for did in dcfg["candidates"]:
        f = features.get(did)
        if f is None or f.z_1d is None or abs(f.z_1d) < float(dcfg["min_abs_z"]):
            continue
        driver_tuples.append((did, labels.get(did, did), f.z_1d, f.percentile_1y))
    driver_tuples.sort(key=lambda d: -abs(d[2]))
    driver_tuples = driver_tuples[: int(dcfg["limit"])]
    impacts = compute_impacts(stocks, exposures, driver_tuples, config_dir=config_dir)
    # 카드마다 노출 정의가 있는 종목 전부에 대해 점수를 매긴다 (임계 미만은 impact_for 가 거른다)
    cards: list[DriverCard] = []
    for did, label, z, pct in driver_tuples:
        s = series_by_id[did]; f = features[did]; ins = instruments.get(did)
        top = [i for i in impacts if i.driver_id == did][: int(dcfg["top_stocks"])]
        sectors: list[str] = []
        for i in top:
            sec = stocks_by_id[i.stock_id].sector
            if sec not in sectors:
                sectors.append(sec)
        fresh = int((as_of - s.as_of).total_seconds()) if s.as_of.tzinfo else 0
        cards.append(DriverCard(
            instrument_id=did, label=label, value=s.last, unit=ins.unit if ins else "price",
            change_1d_display=_fmt(ins, f.ret_1d), change_1w=f.ret_5d, change_3m=f.ret_3m, z=z,
            percentile=pct, percentile_observations=f.percentile_observations, affected_sectors=sectors,
            top_stocks=top, source=s.meta.source, freshness_sec=max(0, fresh), stale=s.meta.is_stale,
        ))
    timings["impact"] = (time.perf_counter() - t) * 1000.0

    # 4. 대체데이터
    t = time.perf_counter()
    prev_alt = {p.id: p for p in previous.alternative} if previous else None
    alt_points = build_alt_points(u.alternative, features, series_by_id, stocks_by_id, as_of, previous=prev_alt, config_dir=config_dir)
    alt_map = {p.id: p for p in alt_points}
    # 공유 드라이버도 point 로 (설명·peer 패널용)
    for did in shared_driver_ids(config_dir):
        f = features.get(did); s = series_by_id.get(did); ins = base_ins.get(did)
        if f is None or s is None or ins is None:
            continue
        alt_map[did] = AltDataPoint(
            id=did, label=ins.name, group="market", value=s.last, unit=ins.unit, change_1d=f.ret_1d, change_1w=f.ret_5d,
            change_1m=f.ret_20d, change_3m=f.ret_3m, z=f.z_1d, percentile=f.percentile_1y,
            percentile_observations=f.percentile_observations, quality="OK", source=s.meta.source, source_type="MARKET_DATA",
            why="기존 크로스에셋 드라이버", as_of=s.as_of,
        )
    timings["alternative"] = (time.perf_counter() - t) * 1000.0

    # 5. 종목 행
    rows: dict[str, StockRow] = {}
    for meta in stocks:
        sf = stock_features.get(meta.id); s = series_by_id.get(meta.id)
        if sf is None or s is None:
            continue
        rows[meta.id] = StockRow(
            stock_id=meta.id, name=meta.name, sector=meta.sector, price=s.last, change_1d=sf.price.ret_1d,
            change_1w=sf.price.ret_5d, change_1m=sf.price.ret_20d, z=sf.price.z_1d, volume_z=sf.volume_z,
            relative_z=sf.relative_z, percentile=sf.price.percentile_1y, stale=s.meta.is_stale, source=s.meta.source,
        )

    # 6. 애널리스트
    t = time.perf_counter()
    analyst_rows = build_analyst(stocks, stock_features, as_of, replay_dir=replay_dir, scenario_specs=analyst_specs,
                                 min_pct=float(icfg["stock_divergence"]["eps_min_pct"]))
    analyst_map = {a.stock_id: a for a in analyst_rows}
    timings["analyst"] = (time.perf_counter() - t) * 1000.0

    # 7. 뉴스 → 종목 (테마 경유) · 이상 거래 · 원인 · 괴리
    t = time.perf_counter()
    news_counts = {m.id: sum(1 for e in base.events if any(th in e.themes for th in m.themes)) for m in stocks}
    # 종목을 직접 지목한 기사 — entity 이름·티커 또는 affected_assets 가 종목과 일치할 때만.
    # 테마 경유 집계(news_counts)는 원인 후보용으로 남기고, 워치리스트 배지는 이쪽을 쓴다.
    stock_news_counts = {m.id: sum(1 for e in base.events if _mentions_stock(e, m)) for m in stocks}
    anomalies = detect_anomalies(stocks, stock_features, news_counts, as_of, config_dir=config_dir)
    anomaly_map = {a.stock_id: a for a in anomalies}
    market_f = features.get(u.benchmark_market)
    market_ret = market_f.ret_1d if market_f else None
    market_z = market_f.z_1d if market_f else None
    explanations = {}
    for meta in stocks:
        sf = stock_features.get(meta.id)
        if sf is None:
            continue
        explanations[meta.id] = explain_stock(
            meta, sf, as_of=as_of, market_ret=market_ret, market_z=market_z, impacts=impacts, driver_points=alt_map,
            peer_points=[alt_map[p] for p in meta.peers if p in alt_map], news=base.events,
            analyst=analyst_map.get(meta.id), commentary=pick(commentary, "stock", meta.id),
        )
    prev_div = previous.fundamental_divergences if previous else ()
    divergences = detect_stock_divergences(stocks, stock_features, features, exposures, analyst_map, labels, as_of,
                                           previous=prev_div, config_dir=config_dir)
    timings["stock_signals"] = (time.perf_counter() - t) * 1000.0

    # 8. 원자재 → 산업 → 종목, 반도체, 테마 → 종목, 선행/후행
    t = time.perf_counter()
    displays = {iid: _fmt(instruments.get(iid), f.ret_1d) for iid, f in features.items()}
    rollover = {p.id: p.rollover_suspect for p in alt_points}
    commodity = build_commodity_impact(stocks, features, stock_features, exposures, labels, displays, rollover, config_dir=config_dir)
    semi = build_semiconductor(alt_map, rows, analyst_map, config_dir=config_dir)
    theme_rows: list[ThemeStockRow] = []
    for th in sorted(base.themes, key=lambda t: -abs(t.theme_score)):
        members = [rows[m.id] for m in stocks if th.theme_id in m.themes and m.id in rows]
        if not members:
            continue
        zs = [r.z for r in members if r.z is not None]
        mean_z = sum(zs) / len(zs) if zs else None
        if mean_z is None or abs(th.theme_score) < 15:
            agreement = "unknown"
        elif abs(mean_z) < 0.4:
            agreement = "muted"
        elif (mean_z > 0) == (th.theme_score > 0):
            agreement = "confirmed"
        else:
            agreement = "mismatch"
        theme_rows.append(ThemeStockRow(theme_id=th.theme_id, theme_name=th.name, theme_score=th.theme_score,
                                        news_sentiment=th.news_sentiment, stocks=sorted(members, key=lambda r: -(abs(r.z or 0))), agreement=agreement))  # type: ignore[arg-type]
    frame = change_frame(series_by_id, {iid: ins.series_kind for iid, ins in instruments.items()})
    lead_lag = compute_lead_lag(frame, labels, config_dir=config_dir)
    timings["industry"] = (time.perf_counter() - t) * 1000.0

    # 9. 종목 상세 + 워치리스트
    t = time.perf_counter()
    theme_scores = {th.theme_id: th.theme_score for th in base.themes}
    theme_names = {th.theme_id: th.name for th in base.themes}
    stock_intel: dict[str, StockIntelligence] = {}
    for meta in stocks:
        row = rows.get(meta.id)
        if row is None:
            continue
        sf = stock_features[meta.id]
        my_impacts = [i for i in impacts if i.stock_id == meta.id]
        my_div = [d for d in divergences if d.stock_id == meta.id]
        an = anomaly_map.get(meta.id)
        ex = explanations.get(meta.id)
        c = pick(commentary, "stock", meta.id)
        a = analyst_map.get(meta.id)
        what = f"{meta.name} {row.change_1d:+.2f}%" if row.change_1d is not None else meta.name
        if row.z is not None:
            what += f" ({row.z:+.1f}σ)"
        if row.volume_z is not None:
            what += f" · 거래량 {row.volume_z:+.1f}σ"
        if sf.relative_return_1d is not None:
            what += f" · 시장 대비 {sf.relative_return_1d:+.2f}%p"
        why = ex.causes[0].text if ex and ex.causes else "원인 후보 없음"
        changed_bits = []
        if my_impacts:
            changed_bits.append(f"{my_impacts[0].driver_label} 충격 영향 {my_impacts[0].score:.0f}")
        if my_div:
            changed_bits.append(f"괴리 {len(my_div)}건 ({my_div[0].kind})")
        if an and an.label != "NONE":
            changed_bits.append(an.label)
        if a and a.available and a.eps_revision_1m is not None and abs(a.eps_revision_1m) >= 2:
            changed_bits.append(f"EPS 1M {a.eps_revision_1m:+.1f}%")
        changed = " · ".join(changed_bits) if changed_bits else "임계를 넘는 변화 없음"
        if c and c.what_next:
            nxt = " / ".join(c.what_next[:3])
        else:
            drivers_txt = ", ".join(labels.get(d, d) for d in meta.drivers[:3])
            peers_txt = ", ".join(labels.get(p, p) for p in meta.peers[:3])
            nxt = f"드라이버({drivers_txt}) 방향" + (f", 미국 세션의 {peers_txt}" if peers_txt else "") + ", 컨센서스 갱신"
        missing = ["외국인·기관 수급 (KRX 차단)"]
        if not (a and a.available):
            missing.append("컨센서스 (공개 API 없음)")
        stock_intel[meta.id] = StockIntelligence(
            meta=meta, feature=sf, row=row, headline_what=what, headline_why=why, headline_changed=changed, headline_next=nxt,
            exposure=exposures.get(meta.id), impacts=my_impacts[:6], explanation=ex, anomaly=an, divergences=my_div,
            analyst=a, peers=[alt_map[p] for p in meta.peers if p in alt_map],
            alternative=[alt_map[d] for d in meta.drivers if d in alt_map],
            theme_scores={th: theme_scores[th] for th in meta.themes if th in theme_scores},
            lead_lag=[l for l in lead_lag if l.lag_id == meta.id], commentary=c, missing=missing,
        )

    wcfg = icfg["watchlist"]
    thr = wcfg["badge_thresholds"]
    watch: list[WatchlistRow] = []
    prev_themes = {th.theme_id: th.theme_score for th in (base.themes or [])}
    for sid in wcfg["default"]:
        si = stock_intel.get(sid)
        if si is None:
            continue
        meta = si.meta; row = si.row; a = si.analyst; an = si.anomaly
        badges: list[str] = []
        top_theme = max(meta.themes, key=lambda th: abs(theme_scores.get(th, 0.0)), default=None)
        top_theme_score = theme_scores.get(top_theme) if top_theme else None
        th_state = next((t for t in base.themes if t.theme_id == top_theme), None)
        if th_state and th_state.last_change >= float(thr["theme_change"]):
            badges.append("THEME_STRENGTHENING")
        elif th_state and th_state.last_change <= -float(thr["theme_change"]):
            badges.append("THEME_WEAKENING")
        if stock_news_counts.get(sid, 0) >= int(thr.get("news_min_stock_events", 1)):
            badges.append("NEW_EVENT")
        if a and a.available and a.eps_revision_1m is not None and abs(a.eps_revision_1m) >= float(thr["eps_revision_pct"]):
            badges.append("EPS_REVISION")
        if a and a.available and a.rating_change:
            badges.append("ANALYST_CHANGE")
        alt_sig = next((p for p in si.alternative if p.z is not None and abs(p.z) >= float(thr["alt_signal_z"]) and p.group != "market"), None)
        if alt_sig:
            badges.append("ALTERNATIVE_DATA_SIGNAL")
        com = next((i for i in si.impacts if i.score >= float(thr["commodity_impact_min"]) and instruments.get(i.driver_id) and instruments[i.driver_id].asset_class.value == "commodity"), None)
        if com:
            badges.append("COMMODITY_IMPACT")
        if an and an.label != "NONE":
            badges.append("UNUSUAL_MOVE")
        watch.append(WatchlistRow(
            stock_id=sid, name=meta.name, sector=meta.sector, price=row.price, change_1d=row.change_1d, change_1w=row.change_1w,
            volume_z=row.volume_z, flow_z=None, theme=theme_names.get(top_theme) if top_theme else None, theme_score=top_theme_score,
            macro_impact=si.impacts[0].score if si.impacts else None, macro_driver=si.impacts[0].driver_label if si.impacts else None,
            alt_signal=f"{alt_sig.label} {alt_sig.z:+.1f}σ" if alt_sig else None,
            eps_revision_1m=a.eps_revision_1m if a and a.available else None,
            analyst_change=a.rating_change if a and a.available else None,
            unusual=an.label if an else "NONE", badges=badges,  # type: ignore[arg-type]
            commentary_excerpt=(si.commentary.sections.interpretation[0][:80] if si.commentary and si.commentary.sections.interpretation else None),
        ))
    timings["stocks"] = (time.perf_counter() - t) * 1000.0

    # 10. 건강
    not_available = [
        "외국인·기관 수급: KRX 데이터 포털이 세션을 거부 (LOGOUT)",
        "애널리스트 컨센서스: 공개 API 없음 (Yahoo 401, FnGuide·네이버 차단) — CSV 적재만",
    ]
    for p in alt_points:
        if p.quality == "MISSING":
            not_available.append(f"{p.label}: {p.note}")
    stale = [iid for iid, s in series_by_id.items() if s.meta.is_stale and iid in instruments]
    health = IntelligenceHealth(
        mode=mode, stocks_expected=len(stocks), stocks_available=len(rows),
        alt_expected=len(u.alternative), alt_available=sum(1 for p in alt_points if p.quality != "MISSING"),
        stale=sorted(stale), not_available=not_available, warnings=list(warnings),
        timings_ms={k: round(v, 2) for k, v in timings.items()},
    )
    timings["total"] = (time.perf_counter() - t0) * 1000.0
    health.timings_ms["total"] = round(timings["total"], 2)

    return InvestmentIntelligence(
        as_of=as_of, mode=mode, scenario=scenario, drivers=cards, alternative=alt_points, market_stock_impact=impacts[:30],
        semiconductor=semi, commodity_impact=commodity, unusual_movers=anomalies, theme_stocks=theme_rows[:8],
        analyst=analyst_rows, fundamental_divergences=divergences, stocks=stock_intel, watchlist=watch,
        lead_lag=lead_lag, commentary=list(commentary), health=health, engine_versions=dict(ENGINE_VERSIONS),
    )


def run_investment(
    settings: Settings,
    base: IntelligenceSnapshot,
    *,
    as_of: datetime | None = None,
    previous: InvestmentIntelligence | None = None,
    store_path: str | None = None,
) -> InvestmentIntelligence:
    """I/O 포함. 어댑터 → build_investment."""
    from ..adapters.registry import build_alt_adapter

    as_of = as_of or utcnow()
    u = get_universe(settings.config_dir)
    base_ins = get_instruments().by_id()
    shared = [base_ins[i] for i in shared_driver_ids(settings.config_dir)]
    adapter = build_alt_adapter(settings, store_path=store_path)
    warnings: list[str] = []
    timings: dict[str, float] = {}

    t = time.perf_counter()
    if settings.data_mode is DataMode.MOCK:
        series = adapter.fetch_series(u.stocks, u.alternative, shared, bars=settings.history_bars, as_of=as_of)
        analyst_specs = load_scenario(settings.mock_dir, settings.scenario).analyst
        scenario = settings.scenario
    else:
        sources = {a.id: a.sources for a in u.alternative}
        sources.update({s.id: [SourceSpec(provider="yahoo", symbol=s.symbol)] for s in u.stocks})
        instruments = [s.as_instrument() for s in u.stocks] + [a.as_instrument() for a in u.alternative] + shared
        series = adapter.fetch_series(instruments, sources, bars=settings.history_bars, as_of=as_of)
        analyst_specs = None
        scenario = None
        failed = [o for o in adapter.outcomes.values() if not o.ok]
        for o in failed[:6]:
            # 화면에 로컬 절대경로를 내보내지 않는다
            warnings.append(f"{o.instrument_id}: {o.reason}".replace(str(settings.replay_dir), "data/replay"))
        if len(failed) > 6:
            warnings.append(f"… 외 {len(failed) - 6}개 계열도 실패")
        for iid, (n, pct) in sorted(getattr(adapter, "revisions", {}).items(), key=lambda kv: -kv[1][1])[:8]:
            warnings.append(f"{iid}: 저장된 봉 {n}개의 값이 이번 수집에서 바뀜 (최대 {pct:.1f}%) — 확정 전 값이었거나 월물 교체. 전 화면의 급변은 이 수정을 반영하지 않았다")
    timings["fetch"] = (time.perf_counter() - t) * 1000.0

    # 수기 해설은 실데이터에 대한 것이다. MOCK 시나리오에 실제 날짜의 해설을 붙이면 거짓이 된다.
    commentary = [] if settings.data_mode is DataMode.MOCK else load_commentary(COMMENTARY_DIR, as_of, config_dir=settings.config_dir)
    inv = build_investment(
        base, series, as_of=as_of, mode=adapter.mode, scenario=scenario, analyst_specs=analyst_specs,
        replay_dir=settings.replay_dir, commentary=commentary, previous=previous,
        warnings=warnings, timings_ms=timings, config_dir=settings.config_dir,
    )
    inv._series_by_id = dict(series)
    return inv
