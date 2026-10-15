"""실데이터 AI Trade Intelligence 캡처 — 바스켓 계열은 Yahoo(알트 어댑터)로 받아 basket_series.json 에 남긴다. 키·비밀 없음."""
import json, pickle, sys, logging
from datetime import datetime
from pathlib import Path
logging.basicConfig(level=logging.WARNING)
from marketpulse.adapters.registry import build_alt_adapter
from marketpulse.config.registry import get_instruments
from marketpulse.config.settings import Settings
from marketpulse.engines.ai_regime import basket_instruments, build_ai_regime
from marketpulse.engines.scenario_check import extra_z_from_investment
from marketpulse.models.intelligence import AltInstrument, SourceSpec
from marketpulse.models.intelligence import InvestmentIntelligence
from marketpulse.models.market import MarketSeries
from marketpulse.models.snapshot import IntelligenceSnapshot
CAP = Path(sys.argv[1]); refetch = len(sys.argv) > 2 and sys.argv[2] == "--fetch"
live = IntelligenceSnapshot.model_validate_json((CAP / "live.json").read_text(encoding="utf-8"))
inv = InvestmentIntelligence.model_validate_json((CAP / "investment.json").read_text(encoding="utf-8"))
market = pickle.load(open("/tmp/snap/market_snapshot.pkl", "rb"))
series = pickle.load(open("/tmp/snap/series_live.pkl", "rb"))
ins = get_instruments().instruments
bs_path = CAP / "ai_basket_series.json"
if bs_path.exists() and not refetch:
    basket = {k: MarketSeries.model_validate(v) for k, v in json.loads(bs_path.read_text(encoding="utf-8")).items()}
else:
    settings = Settings(data_mode="DELAYED", llm_enabled=False)
    ad = build_alt_adapter(settings, store_path=None)
    specs = [AltInstrument(id=m["id"], name=m.get("name", m["id"]), group="ai", asset_class="equity", unit="price", sources=[SourceSpec(provider="yahoo", symbol=str(m["symbol"]))], source_type="EXCHANGE") for m in basket_instruments()]
    basket = ad.fetch_series([a.as_instrument() for a in specs], {a.id: a.sources for a in specs}, bars=120, as_of=live.as_of)
    print("fetched", len(basket), "failed", [(k, o.reason) for k, o in ad.outcomes.items() if not o.ok])
    bs_path.write_text(json.dumps({k: v.model_dump(mode="json") for k, v in basket.items()}, ensure_ascii=False), encoding="utf-8")
r = build_ai_regime(market, series, basket, live.themes, live.events, {i.id: i for i in ins}, market_label=live.market_state.primary_label.value, market_confidence=live.market_state.confidence,
                    thermometer=live.thermometer.composite if live.thermometer else None, band=live.thermometer.band if live.thermometer else None,
                    extra_z=extra_z_from_investment(inv), extra_names={p.id: p.label for p in inv.alternative}, investment=inv, as_of=live.as_of)
# ── Daily snapshot history (2026-10-14): 1M 센티먼트 이력 = 저장 sequence, AI 판정 daily snapshot 기록·backfill ──
from marketpulse.config.settings import get_settings
from marketpulse.history import DailySnapshotManager, JsonDirStore
from marketpulse.history.calculators import AiInputs
from marketpulse.history.integrate import sync_ai_regime, sync_sentiment
from marketpulse.engines.ai_regime import load_ai_regime_config
_m = DailySnapshotManager(JsonDirStore(get_settings().history_dir))
_dv = r.sentiment._day_values if r.sentiment is not None else None
if _dv is not None:
    _sh = sync_sentiment(_m, r, cfg_all=load_ai_regime_config(None), dv=_dv, bench_dates=_dv.cal, as_of=live.as_of)
    print("SENT HIST", _sh.history_mode, "rec", _sh.recorded_days, "bf", _sh.backfilled_days, [(p.date[5:], p.source[0], None if p.index is None else round(p.index)) for p in _sh.points])
_ah = sync_ai_regime(_m, r, inputs=AiInputs(instruments=ins, series_by_id=series, basket_series=basket, events=live.events, mode=live.mode, zscore_window=Settings().zscore_window), as_of=live.as_of)
print("AI HIST", "rec", _ah.recorded_days, "bf", _ah.backfilled_days, _ah.current_label, _ah.current_streak, "prev", _ah.previous_label)
(CAP / "ai_regime.json").write_text(r.model_dump_json(), encoding="utf-8")
print(r.regime_label, "|", r.regime_label_ko); print(r.headline); print("missing", r.missing)
a = r.ai_vs_market; print("AVM", a.members_used, a.last_date, "abs", a.basket_ret_1d, a.basket_ret_5d, a.basket_ret_21d, "z", a.basket_z_1d, a.basket_z_5d, "| ndx", a.ndx_ret_5d, "rel", a.rel_ndx_1d, a.rel_ndx_5d, a.rel_ndx_21d, "relz", a.rel_ndx_z_1d, a.rel_ndx_z_5d, "| spx rel", a.rel_spx_5d, a.rel_spx_z_5d, a.abs_direction, a.rel_verdict)
for d in r.drivers: print("  drv", d.id, d.score, d.status, d.coverage, [(e.label, e.value) for e in d.evidence[:4]])
print("dom", r.dominant, r.runner_up, r.margin)
for g in r.leadership.groups: print("  grp", g.key, g.available, "/", g.members, g.ret_1d, g.ret_5d, g.ret_21d, "rel", g.rel_1d, g.rel_5d, g.rel_21d, "relz5", g.rel_z_5d, "ma20", g.above_ma20_pct, "down1w", g.down_1w, g.rank_1w, g.role)
print(r.leadership.sentence)
b = r.breadth; print("breadth", b.members, b.above_ma5_pct, b.above_ma20_pct, b.advancing_pct, b.above_ma20_pct_1w_ago, b.change_1w_pts, b.trend, b.narrowing_with_index_up); print(b.sentence)
n = r.narrative; print("narr", n.news_tone, n.news_count, n.news_momentum, n.price_z, n.quadrant, "|", n.sentence); print([(d.key, d.tone, d.count) for d in n.drivers])
print("macro", r.macro.verdict, r.macro.explains, r.macro.evaluated, [(m.key, m.z, m.status) for m in r.macro.rows]); print(r.macro.sentence)
print("stress", r.stress.level, r.stress.score, r.stress.max_score, [(c.key, c.display, c.points) for c in r.stress.components])
print("checks", [(c.key, c.passed) for c in r.checks])
print("triggers", [(t.metric, t.current, t.condition, t.met) for t in r.triggers]); print("release", [(t.current, t.met) for t in r.release])
print("ctx", r.context)

print("== EXT ==", r.regime_subtitle); print("strip", [(x.key, x.value) for x in r.status_strip]); print("FC", r.fundamental_confirmation.level, r.fundamental_confirmation.sentence); print("SUMMARY", r.summary)
print("TRANS", [(s.key, s.status, s.score) for s in r.transmission.stages]); print(r.transmission.sentence)
print("VC", [(s.key, s.available, s.rel_5d, s.rel_z_5d, s.above_ma20_pct, s.eps, s.arrow_1w, s.arrow_rel, s.rank_1w, s.role, s.macro_score) for s in r.value_chain.segments]); print(r.value_chain.leadership, r.value_chain.lagging, r.value_chain.sentence)
print("SEMI", [(a.key, a.status, a.detail) for a in r.semi_confirmation.areas]); print([(m.id, m.status, m.change_1d, m.change_1w, m.observations, m.freshness_days) for m in r.semi_confirmation.memory]); print(r.semi_confirmation.sentence)
print("STOCKS", len(r.stocks)); [print("  ", x.id, x.theme_exposure, [(a.key, a.arrow) for a in x.axes], x.overall, "|", x.confirmation, "|", x.interpretation[:80]) for x in r.stocks[:14]]
print("RADAR", [(b.key, [(i["name"], i["reason"][:50]) for i in b.items]) for b in r.radar])
print("NEWS", [(n.event[:40], n.drivers, n.primary, n.primary_stocks, n.confirmation) for n in r.news_impact])
print("GAP", [(g.key, g.market_pricing, g.fundamental, g.gap) for g in r.expectation_gap])
print("MATTERS", [(m.key, m.status, m.current) for m in r.what_matters])
