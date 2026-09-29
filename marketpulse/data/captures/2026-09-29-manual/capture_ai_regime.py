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
                    extra_z=extra_z_from_investment(inv), extra_names={p.id: p.label for p in inv.alternative}, as_of=live.as_of)
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
