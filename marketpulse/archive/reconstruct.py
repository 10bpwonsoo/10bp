"""
누락 평일 재구성 · 오늘 최신 저장 — 하나의 캡처 파이프라인.

    fetch_inputs(dir)        지금 한 번: 시장 계열 · 종목/대체 계열 · AI 바스켓 · RSS 기사를 받아 둔다(키 값은 출력·저장하지 않는다)
    reconstruct(day, …)      cutoff(기본 그 한국 날짜 07:30 KST) 에 이미 공개된 봉·기사·발표만으로 화면 전체를 계산해
                             data/captures/<day>-backfill/ 에 남긴다(오늘 최신 저장은 cutoff = 지금, <day>-latest/)

순서가 정합성이다(capture 스크립트와 같다): 시장 스냅샷 → Investment → AI → 금리(거시 vintage · 정책 이벤트 · 해석) → 유가 →
시나리오 점검 → Market State History → cockpit → Analyst View → Daily History. 하위 계산은 모두 같은 cutoff·같은 계열을 쓴다.
과거 날짜는 반드시 오름차순으로 — Daily History 의 지속성·전환·전일 비교가 바로 앞 날짜의 저장값을 잇는다.

지금 값으로 과거를 채우지 않는다: 남는 봉이 없는 계열은 결측, 그 시점 기사가 없으면 뉴스가 적은 그대로, 그날 확인된 코멘트가 없으면 비운다.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from ..models.market import MarketSeries
from .pit import cut_series, last_bars

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")
PKG = Path(__file__).resolve().parent.parent


def cutoff_for(day: date, hhmm: str = "07:30") -> datetime:
    hh, mm = (int(x) for x in hhmm.split(":"))
    return datetime.combine(day, time(hh, mm), tzinfo=KST)


# ── 입력 받기 ─────────────────────────────────────────────
def _dump_series(path: Path, series: Mapping[str, MarketSeries]) -> None:
    path.write_text(json.dumps({k: v.model_dump(mode="json") for k, v in series.items()}, ensure_ascii=False), encoding="utf-8")


def _load_series(path: Path) -> dict[str, MarketSeries]:
    return {k: MarketSeries.model_validate(v) for k, v in json.loads(path.read_text(encoding="utf-8")).items()}


def fetch_inputs(out: Path, *, as_of: datetime | None = None, news_limit: int = 500) -> dict[str, Any]:
    """지금 받을 수 있는 전체 이력을 한 번 받는다. 날짜별 절단은 reconstruct 가 한다."""
    from ..adapters.registry import build_alt_adapter, build_market_adapter, build_news_adapter
    from ..config.registry import get_instruments, get_universe
    from ..config.settings import Settings
    from ..engines.ai_regime import basket_instruments
    from ..engines.investment import shared_driver_ids
    from ..models.common import utcnow
    from ..models.intelligence import AltInstrument, SourceSpec

    out.mkdir(parents=True, exist_ok=True)
    as_of = as_of or utcnow()
    settings = Settings(data_mode="DELAYED", llm_enabled=False, news_search="off")
    report: dict[str, Any] = {"fetched_at": as_of.isoformat()}

    ins = get_instruments().instruments
    ad = build_market_adapter(settings)
    base = ad.fetch_series(ins, bars=settings.history_bars, as_of=as_of)
    report["base"] = {"got": len(base), "of": len(ins), "failed": [(k, o.reason) for k, o in getattr(ad, "outcomes", {}).items() if not o.ok]}
    _dump_series(out / "series_base.json", base)

    u = get_universe(settings.config_dir)
    base_ins = get_instruments().by_id()
    shared = [base_ins[i] for i in shared_driver_ids(settings.config_dir)]
    alt = build_alt_adapter(settings, store_path=None)
    sources = {a.id: a.sources for a in u.alternative}
    sources.update({s.id: [SourceSpec(provider="yahoo", symbol=s.symbol)] for s in u.stocks})
    instruments = [s.as_instrument() for s in u.stocks] + [a.as_instrument() for a in u.alternative] + shared
    uni = alt.fetch_series(instruments, sources, bars=settings.history_bars, as_of=as_of)
    report["universe"] = {"got": len(uni), "of": len(instruments), "failed": [(k, o.reason) for k, o in alt.outcomes.items() if not o.ok]}
    _dump_series(out / "series_universe.json", uni)

    specs = [AltInstrument(id=m["id"], name=m.get("name", m["id"]), group="ai", asset_class="equity", unit="price",
                           sources=[SourceSpec(provider="yahoo", symbol=str(m["symbol"]))], source_type="EXCHANGE") for m in basket_instruments()]
    ad2 = build_alt_adapter(settings, store_path=None)
    basket = ad2.fetch_series([a.as_instrument() for a in specs], {a.id: a.sources for a in specs}, bars=120, as_of=as_of)
    report["basket"] = {"got": len(basket), "of": len(specs), "failed": [(k, o.reason) for k, o in ad2.outcomes.items() if not o.ok]}
    _dump_series(out / "series_basket.json", basket)

    try:
        items = build_news_adapter(settings).fetch_news(limit=news_limit, as_of=as_of)
    except Exception as exc:  # 기사는 없어도 계산은 된다
        report["news_error"] = str(exc)
        items = []
    (out / "news_rss.json").write_text(json.dumps([i.model_dump(mode="json") for i in items], ensure_ascii=False), encoding="utf-8")
    report["news"] = len(items)
    (out / "fetch_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


def fetch_macro_vintage(out: Path, cutoff: datetime) -> dict[str, Any]:
    """거시 지표(CPI·PCE·임금 등)를 그 cutoff 시점의 FRED vintage 로 받는다 — 나중 개정치로 과거 판단을 바꾸지 않는다."""
    import os

    from ..adapters.macro_fred import fetch_macro_raw
    from ..engines.macro_fallback import load_macro_config

    cfg = load_macro_config()
    raw = fetch_macro_raw(cfg, api_key=os.environ.get("FRED_API_KEY") or None, as_of=cutoff)
    doc = {"as_of": cutoff.isoformat(), "realtime": "FRED realtime_start=realtime_end=cutoff 의 미국 중부시간 날짜", "series": raw}
    out.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return doc


# ── 재구성 ───────────────────────────────────────────────
@dataclass
class ReconstructResult:
    day: date
    cutoff: datetime
    out: Path
    summary: dict[str, Any] = field(default_factory=dict)


def _news_items_until(items: list[dict], cutoff: datetime, *, since: datetime | None) -> list[dict]:
    keep = []
    for it in items:
        try:
            t = datetime.fromisoformat(str(it["published_at"]).replace("Z", "+00:00"))
        except Exception:
            continue
        if t <= cutoff and (since is None or t > since):
            keep.append(it)
    return keep


def build_events(raw_items: list[dict], tags: Mapping[str, Mapping[str, Any]], extra: list[dict], cutoff: datetime):
    """수기 태깅(extractor=manual)을 NewsEvent 로. 발행 시각이 cutoff 뒤인 것은 넣지 않는다."""
    import hashlib

    from ..models.common import DataMeta, DataMode, DataQuality, utcnow
    from ..models.news import NewsEvent, RawNewsItem, ValidationReport

    by_id = {i["id"]: dict(i) for i in raw_items}
    retrieved = utcnow()
    for f in extra:  # 시각이 확인된 웹 기사 — RSS 에 이미 없는 그 시점 기사
        host = f["url"].split("/")[2]
        host = host[4:] if host.startswith("www.") else host
        published = datetime.fromisoformat(f["published_at"])
        if published > cutoff:
            continue
        item = RawNewsItem(id=hashlib.sha256(f["url"].encode()).hexdigest()[:16], title=f["title"], body="", url=f["url"], publisher=f.get("publisher") or host,
                           published_at=published, language=f.get("language", "en"),
                           meta=DataMeta(source=f"web:{host}", mode=DataMode.DELAYED, retrieved_at=retrieved, as_of=published,
                                         quality=DataQuality.PARTIAL if f.get("timestamp_quality") != "EXACT" else DataQuality.OK))
        by_id[item.id] = item.model_dump(mode="json")
        by_id[item.id]["timestamp_quality"] = f.get("timestamp_quality", "EXACT")
        tags = dict(tags)
        tags[item.id] = {k: f[k] for k in ("themes", "theme_sentiment", "theme_direction", "sentiment", "impact", "novelty", "horizon", "event_type", "reason")}
    events = []
    for item_id, tag in tags.items():
        item = by_id.get(item_id)
        if item is None:
            continue
        ts = datetime.fromisoformat(str(item["published_at"]).replace("Z", "+00:00"))
        if ts > cutoff:
            continue
        events.append(NewsEvent(
            id=f"manual-{item_id}", source_item_ids=[item_id], event=item["title"], event_type=tag["event_type"], themes=tag["themes"],
            theme_sentiment=tag["theme_sentiment"], theme_direction=tag["theme_direction"], sentiment=tag["sentiment"], impact_score=tag["impact"],
            novelty_score=tag["novelty"], time_horizon=tag["horizon"], reason=tag["reason"], source=item["publisher"], url=item.get("url"),
            timestamp=item["published_at"], extractor="manual", validation=ValidationReport(schema_ok=True), confidence=0.55,
        ))
    events.sort(key=lambda e: e.timestamp, reverse=True)
    return events, list(by_id.values())


class _AnalystDir:
    """그 날짜 이전에 확인·저장된 수기 코멘트 파일만 보이는 임시 디렉터리 — 나중에 확인한 코멘트를 과거 화면에 넣지 않는다."""

    def __init__(self, day: date) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="analyst-pit-"))
        src = PKG / "data" / "analyst_views" / "manual"
        for p in sorted(src.glob("*.json")) if src.exists() else []:
            if p.stem <= day.isoformat():
                shutil.copy(p, self.tmp / p.name)

    def close(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


def reconstruct(day: date, *, inputs: Path, out: Path, cutoff: datetime, tags: Mapping[str, Mapping[str, Any]], extra_news: list[dict],
                previous_investment: Mapping[str, Any] | None, news_since: datetime | None, origin: str, session_reads: Mapping[str, Any] | None = None,
                manager=None) -> ReconstructResult:
    """한 날짜의 화면 전체를 cutoff 기준으로 계산해 out/ 에 캡처 파일로 남긴다."""
    from ..adapters.analyst_view import AnalystViewStore
    from ..adapters.market.scenario import available_scenarios, load_scenario
    from ..ai.client import build_client
    from ..ai.inflation_read import attach_inflation_read, build_context as inflation_context
    from ..ai.rates_read import attach_market_read
    from ..config.registry import get_instruments, get_themes, get_universe
    from ..config.settings import MOCK_DIR, Settings, get_settings
    from ..engines.ai_regime import build_ai_regime, load_ai_regime_config
    from ..engines.cockpit import build_cockpit
    from ..engines.commentary import load_commentary
    from ..engines.investment import COMMENTARY_DIR, build_investment
    from ..engines.macro_fallback import build_layer
    from ..engines.normalize import build_snapshot
    from ..engines.oil_regime import build_oil_regime
    from ..engines.policy_events import build_policy_events, load_events_file
    from ..engines.rates_regime import build_rates_regime
    from ..engines.scenario_check import check_scenarios, extra_z_from_investment
    from ..history import DailySnapshotManager, JsonDirStore
    from ..history.calculators import AiInputs, MarketInputs, MemoryInputs, RegimeInputs
    from ..history.integrate import history_of, sync_ai_regime, sync_market, sync_memory, sync_oil, sync_rates, sync_sentiment
    from ..models.analyst_view import AnalystViews
    from ..models.common import DataMode
    from ..models.intelligence import InvestmentIntelligence
    from .tick import run_tick

    out.mkdir(parents=True, exist_ok=True)
    settings = Settings(data_mode="DELAYED", llm_enabled=False, news_search="off")
    manager = manager or DailySnapshotManager(JsonDirStore(get_settings().history_dir))
    ins = get_instruments().instruments
    by_iid = {i.id: i for i in ins}
    summary: dict[str, Any] = {"day": day.isoformat(), "cutoff": cutoff.isoformat(), "origin": origin}

    # 1) 시계열 절단 — cutoff 에 이미 끝나 공개된 봉만
    base = cut_series(_load_series(inputs / "series_base.json"), cutoff)
    uni = cut_series(_load_series(inputs / "series_universe.json"), cutoff)
    basket = cut_series(_load_series(inputs / "series_basket.json"), cutoff)
    summary["series"] = {"base": len(base), "universe": len(uni), "basket": len(basket)}
    (out / "series_last_bars.json").write_text(json.dumps({"base": last_bars(base), "universe": last_bars(uni), "basket": last_bars(basket)}, ensure_ascii=False, indent=1), encoding="utf-8")

    # 2) 기사 — 발행 시각이 cutoff 이하이고 직전 저장 이후인 것만 · 수기 태깅
    rss = json.loads((inputs / "news_rss.json").read_text(encoding="utf-8"))
    raw = _news_items_until(rss, cutoff, since=news_since)
    events, all_raw = build_events(raw, tags, extra_news, cutoff)
    (out / "news_live.json").write_text(json.dumps(sorted(all_raw, key=lambda r: r["published_at"], reverse=True), ensure_ascii=False), encoding="utf-8")
    summary["news"] = {"rss_in_window": len(raw), "web_extra": sum(1 for f in extra_news if datetime.fromisoformat(f["published_at"]) <= cutoff), "tagged_events": len(events)}

    # 3) 시장 스냅샷(판정·테마·괴리·온도계)
    market = build_snapshot(ins, base, mode=DataMode.DELAYED, as_of=cutoff.astimezone(timezone.utc), zscore_window=settings.zscore_window)
    themes_registry = get_themes().by_id()
    t1, p1 = run_tick(market, events, by_iid, themes_registry, previous=None, pending_in=[])
    live, _ = run_tick(market, events, by_iid, themes_registry, previous=t1, pending_in=p1)
    (out / "live.json").write_text(live.model_dump_json(), encoding="utf-8")
    summary["market"] = {"state": live.market_state.primary_label.value, "confidence": round(live.market_state.confidence, 1),
                         "coverage": f"{live.data_health.available_instruments}/{live.data_health.expected_instruments}",
                         "thermo": None if live.thermometer is None else round(live.thermometer.composite)}

    # 4) Investment — 직전 저장일의 Investment 를 previous 로(변화량은 저장된 앞 화면과 비교)
    prev_inv = InvestmentIntelligence.model_validate(previous_investment) if previous_investment else None
    commentary = load_commentary(COMMENTARY_DIR, live.as_of, config_dir=settings.config_dir)
    _tz = lambda t: t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    commentary = [c for c in commentary if _tz(c.as_of) <= live.as_of and _tz(c.created_at) <= live.as_of]  # 그 뒤에 쓴 해설은 넣지 않는다
    inv = build_investment(live, uni, as_of=live.as_of, mode=DataMode.DELAYED, scenario=None, analyst_specs=None, replay_dir=settings.replay_dir,
                           commentary=commentary, previous=prev_inv, warnings=[], timings_ms={}, config_dir=settings.config_dir)
    inv._series_by_id = dict(uni)
    (out / "investment.json").write_text(inv.model_dump_json(), encoding="utf-8")
    u = get_universe(settings.config_dir)
    by_all = {s.id: s.as_instrument() for s in u.stocks}
    by_all.update({a.id: a.as_instrument() for a in u.alternative})
    by_all.update(get_instruments().by_id())
    sync_memory(manager, inv, inputs=MemoryInputs(series_by_id=dict(uni), instruments_by_id=by_all, zscore_window=settings.zscore_window), as_of=live.as_of)
    xz, xn = extra_z_from_investment(inv), {p.id: p.label for p in inv.alternative}

    # 5) AI
    ai = build_ai_regime(market, base, basket, live.themes, live.events, by_iid, market_label=live.market_state.primary_label.value,
                         market_confidence=live.market_state.confidence, thermometer=live.thermometer.composite if live.thermometer else None,
                         band=live.thermometer.band if live.thermometer else None, extra_z=xz, extra_names=xn, investment=inv, as_of=live.as_of)
    dv = ai.sentiment._day_values if ai.sentiment is not None else None
    if dv is not None:
        sync_sentiment(manager, ai, cfg_all=load_ai_regime_config(None), dv=dv, bench_dates=dv.cal, as_of=live.as_of)
    sync_ai_regime(manager, ai, inputs=AiInputs(instruments=ins, series_by_id=base, basket_series=basket, events=live.events, mode=live.mode,
                                                zscore_window=settings.zscore_window), as_of=live.as_of)
    (out / "ai_regime.json").write_text(ai.model_dump_json(), encoding="utf-8")
    summary["ai"] = {"regime": ai.regime_label, "sentiment": None if ai.sentiment is None or ai.sentiment.index is None else round(ai.sentiment.index)}

    # 6) 금리 — 거시는 그날 vintage, 정책 이벤트는 그날까지 확인된 수기 파일, 해석은 API → 같은 검증을 통과한 세션 생성본 → 규칙 문장
    macro_doc = json.loads((out / "macro_raw.json").read_text(encoding="utf-8")) if (out / "macro_raw.json").exists() else None
    macro = build_layer(macro_doc["series"] if macro_doc else None, as_of=live.as_of, curated=load_events_file(live.as_of), themes=live.themes, events=live.events)
    (out / "macro_data.json").write_text(macro.model_dump_json(indent=1), encoding="utf-8")
    rr = build_rates_regime(market, live.themes, by_iid, extra_z=xz, extra_names=xn, series=base, macro=macro)
    ev = build_policy_events(load_events_file(live.as_of), base, rr, as_of=live.as_of)
    if ev is not None:
        rr = rr.model_copy(update={"events": ev})
    reads = dict(session_reads or {})
    client = build_client(get_settings())
    rr, ctx = attach_market_read(rr, client=client, market=market, series=base, news=live.events, instrument_kinds={i.id: i.series_kind for i in ins},
                                 as_of=live.as_of, session_read=reads.get("rates_read"))
    rr = attach_inflation_read(rr, client=client, session_read=reads.get("inflation_read"))
    ctx["inflation_map"] = inflation_context(rr.inflation_map)
    (out / "rates_read_context.json").write_text(json.dumps(ctx, ensure_ascii=False, indent=1), encoding="utf-8")
    sync_rates(manager, rr, inputs=RegimeInputs(instruments=ins, series_by_id=base, events=live.events, mode=live.mode), as_of=live.as_of)
    (out / "rates_regime.json").write_text(rr.model_dump_json(), encoding="utf-8")
    summary["rates"] = {"regime": rr.regime_label, "market_read": [rr.top.market_read_meta.source, rr.top.market_read_meta.generator, rr.top.market_read_meta.reason],
                        "inflation_read": [rr.inflation_map.read_meta.source, rr.inflation_map.read_meta.generator, rr.inflation_map.read_meta.reason]}

    # 7) 유가
    oil = build_oil_regime(market, live.themes, live.divergences, by_iid, extra_z=xz, extra_names=xn)
    sync_oil(manager, oil, inputs=RegimeInputs(instruments=ins, series_by_id=base, events=live.events, mode=live.mode), as_of=live.as_of)
    (out / "oil_regime.json").write_text(oil.model_dump_json(), encoding="utf-8")
    summary["oil"] = {"regime": oil.regime_label}

    # 8) 시나리오 점검
    scs = [load_scenario(MOCK_DIR, n) for n in available_scenarios(MOCK_DIR)]
    checks = check_scenarios(scs, market, live.market_state, live.themes, by_iid, extra_z=xz)
    (out / "scenario_check.json").write_text(json.dumps([c.model_dump(mode="json") for c in checks], ensure_ascii=False), encoding="utf-8")

    # 9) Market State History — 그날까지 태깅된 기사만(앞 캡처들의 수기 이벤트 포함, cutoff 뒤 제외)
    merged: dict[str, Any] = {}
    PRIORITY = {"manual": 0, "llm": 1, "rule": 2}
    from ..models.snapshot import IntelligenceSnapshot as _IS
    for f in sorted((PKG / "data" / "captures").glob("*/live.json")):
        if f.parent == out:
            continue
        try:
            snap_i = _IS.model_validate_json(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for e in snap_i.events:
            if e.timestamp > live.as_of:
                continue
            key = e.url or e.event
            cur = merged.get(key)
            if cur is None or PRIORITY.get(e.extractor, 9) < PRIORITY.get(cur.extractor, 9):
                merged[key] = e
    for e in live.events:
        merged[e.url or e.event] = e
    hist_events = sorted(merged.values(), key=lambda e: e.timestamp)
    sh = sync_market(manager, inputs=MarketInputs(instruments=ins, series_by_id=base, events=hist_events, mode=live.mode, zscore_window=settings.zscore_window),
                     snapshot=live, as_of=live.as_of)
    (out / "state_history.json").write_text(sh.model_dump_json(), encoding="utf-8")

    # 10) cockpit
    ck = build_cockpit(live, market, by_iid, history=sh, investment=inv, ai_regime=ai, rates_regime=rr, oil_regime=oil, extra_z=xz, extra_names=xn)
    (out / "cockpit.json").write_text(ck.model_dump_json(), encoding="utf-8")
    summary["cockpit"] = {"now": ck.market_now.label_text}

    # 11) Analyst View — 그 날짜까지 확인된 수기 코멘트만
    adir = _AnalystDir(day)
    try:
        store = AnalystViewStore(adir.tmp / "_nocache.json", adir.tmp)
        ids = [r.id for r in ck.radar]
        best = store.best(ids, as_of=ck.as_of, max_age_days=30)
        av = AnalystViews(as_of=ck.as_of, views=[best[i] for i in ids if i in best], requested=ids, pending=[], missing=[i for i in ids if i not in best],
                          provider="unavailable", note=f"{day.isoformat()} 이전에 이름·증권사·날짜·URL·맥락이 확인된 수기 코멘트만. 그 뒤에 확인한 코멘트는 넣지 않는다.")
    finally:
        adir.close()
    (out / "analyst_views.json").write_text(av.model_dump_json(), encoding="utf-8")

    # 12) Daily History — 저장된 sequence 만(cutoff 날짜까지)
    dh = {tab: json.loads(history_of(manager, tab, as_of=live.as_of).model_dump_json())
          for tab in ("market_regime", "ai_sentiment", "ai_regime", "rates_regime", "oil_regime", "memory_cycle")}
    (out / "daily_history.json").write_text(json.dumps(dh, ensure_ascii=False), encoding="utf-8")

    summary["vintage"] = {
        "market_series": {"data_vintage": "CURRENT_SERIES", "vintage_guaranteed": False,
                          "note": "Yahoo 일봉(수정종가)·FRED 시장금리를 지금 받아 cutoff 에 이미 끝난 봉만 남겼다 — 사후 수정은 드물지만 vintage 가 보장되지는 않는다"},
        "macro_releases": {"data_vintage": "FRED_REALTIME_AT_CUTOFF" if macro_doc else "UNAVAILABLE", "vintage_guaranteed": bool(macro_doc),
                           "note": "CPI·PCE·임금 등은 FRED realtime(그날 vintage)으로 받았다 — 나중 개정치를 쓰지 않는다"},
        "news": {"timestamp_rule": "published_at <= cutoff", "rss_window_since": news_since.isoformat() if news_since else None},
        "analyst_views": {"rule": "수기 확인 파일 날짜 <= 그 날짜"},
    }
    (out / "manifest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return ReconstructResult(day, cutoff, out, summary)
