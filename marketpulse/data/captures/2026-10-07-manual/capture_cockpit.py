"""실데이터 cockpit 캡처 — 기존 캡처(live·investment·state_history·ai_regime·rates_regime·oil_regime)를 모아 고른다."""
import json, pickle, sys
from pathlib import Path
from marketpulse.config.registry import get_instruments
from marketpulse.engines.cockpit import build_cockpit
from marketpulse.engines.scenario_check import extra_z_from_investment
from marketpulse.models.ai_regime import AiRegime
from marketpulse.models.intelligence import InvestmentIntelligence
from marketpulse.models.oil_regime import OilRegime
from marketpulse.models.rates_regime import RatesRegime
from marketpulse.models.snapshot import IntelligenceSnapshot
from marketpulse.models.state_history import MarketStateHistory
CAP = Path(sys.argv[1])
rd = lambda n: (CAP / n).read_text(encoding="utf-8")
live = IntelligenceSnapshot.model_validate_json(rd("live.json")); inv = InvestmentIntelligence.model_validate_json(rd("investment.json"))
hist = MarketStateHistory.model_validate_json(rd("state_history.json")); ai = AiRegime.model_validate_json(rd("ai_regime.json"))
rr = RatesRegime.model_validate_json(rd("rates_regime.json")); orr = OilRegime.model_validate_json(rd("oil_regime.json"))
market = pickle.load(open("/tmp/snap/market_snapshot.pkl", "rb")); ins = get_instruments().instruments
c = build_cockpit(live, market, {i.id: i for i in ins}, history=hist, investment=inv, ai_regime=ai, rates_regime=rr, oil_regime=orr, extra_z=extra_z_from_investment(inv), extra_names={p.id: p.label for p in inv.alternative})
(CAP / "cockpit.json").write_text(c.model_dump_json(), encoding="utf-8")
n = c.market_now; print("NOW", n.label_text, n.conviction, n.confidence, "persist", n.persistence_days, n.change_text, [(k.id, k.z, k.arrow) for k in n.key_variables]); print("  ", n.sentence); print("  interp:", n.interpretation[:120]); print("  spark", len(n.spark), n.coverage, n.latency)
for d in c.drivers: print("DRV", d.key, d.label, d.arrow, d.strength, d.importance, d.coverage, d.confirmed_by_regime, d.persistent, d.news_tone, [(e.id, e.z, e.display, e.context) for e in d.evidence if e.available], "|", d.why)
print("CA", c.cross_asset.confirm, c.cross_asset.evaluated, [(r.key, r.arrow, r.status, r.z) for r in c.cross_asset.rows]); print("  ", c.cross_asset.sentence); print("  DIV", [(d.title, d.severity, d.source, d.meaning[:70]) for d in c.cross_asset.divergences], c.cross_asset.total_divergences)
print("LEAD", [(r.label, r.z_1d, r.rel_1w, r.breadth, r.arrow) for r in c.leadership.leaders]); print("LAG", [(r.label, r.rel_1w, r.breadth) for r in c.leadership.laggards]); print("  ", c.leadership.sentence)
print("PULSE", [(p.name, p.price, p.news, p.rel, p.why) for p in c.leadership.pulse])
for t in c.transmission: print("TRANS", t.driver_label, "→", t.mechanism, t.industries, [(s.name, s.status, s.z) for s in t.stocks], t.confirmed)
print("RADAR", [(r.name, r.change_1d, r.tag, r.kind, r.score, r.signals, r.why[:50]) for r in c.radar])
for i in c.catalysts: print("CAT", i.level, i.time, i.tag, i.kind, i.cluster_size, i.headline[:50], "|", i.impact, "|", i.confidence, "|", i.price_confirmation[:20], i.related_stocks)
print("EARN", c.earnings); print("NEXT", [(x.text, x.status, x.current) for x in c.what_matters_next], c.upcoming)
print("WATCH", [(w.name, w.change_1d, w.watch, w.indicators) for w in c.watchlist]); print("DATA", c.data_status.line, c.data_status.warnings)
# ANALYST VIEW — 수기 확인 파일을 같은 검증(validate_view)으로 걸러 radar 종목만 싣는다. provider 없음.
from marketpulse.adapters.analyst_view import AnalystViewStore
from marketpulse.models.analyst_view import AnalystViews
_root = Path(__file__).resolve().parents[3]
_store = AnalystViewStore(_root / "data/analyst_views/cache.json", _root / "data/analyst_views/manual")
_ids = [r.id for r in c.radar]
_best = _store.best(_ids, as_of=c.as_of, max_age_days=30)
av = AnalystViews(as_of=c.as_of, views=[_best[i] for i in _ids if i in _best], requested=_ids, pending=[], missing=[i for i in _ids if i not in _best], provider="unavailable",
                  note="웹에서 이름·증권사·날짜·URL·맥락이 모두 확인된 코멘트만(수기 확인). 없는 종목은 줄을 숨긴다. 시스템 판단과 섞지 않는다. 검색 provider 없음 — 저장된 코멘트만.")
(CAP / "analyst_views.json").write_text(av.model_dump_json(), encoding="utf-8")
print("ANALYST", [(v.stock_id, v.analyst, v.broker, str(v.published_date), v.freshness, v.stance) for v in av.views], "missing", av.missing)
