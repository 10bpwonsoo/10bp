"""실데이터 금리·물가 원인 판별 캡처 — 정적 배포본용."""
import pickle, sys
from pathlib import Path
from marketpulse.config.registry import get_instruments
from marketpulse.engines.rates_regime import build_rates_regime
from marketpulse.engines.scenario_check import extra_z_from_investment
from marketpulse.models.intelligence import InvestmentIntelligence
from marketpulse.models.snapshot import IntelligenceSnapshot
CAP = Path(sys.argv[1])
live = IntelligenceSnapshot.model_validate_json((CAP / "live.json").read_text(encoding="utf-8"))
inv = InvestmentIntelligence.model_validate_json((CAP / "investment.json").read_text(encoding="utf-8"))
market = pickle.load(open("/tmp/snap/market_snapshot.pkl", "rb"))
ins = get_instruments().instruments
r = build_rates_regime(market, live.themes, {i.id: i for i in ins}, extra_z=extra_z_from_investment(inv), extra_names={p.id: p.label for p in inv.alternative})
(CAP / "rates_regime.json").write_text(r.model_dump_json(), encoding="utf-8")
print(r.regime_label, "|", r.signal_strength_label, r.margin, "| infl", r.inflation_status)
print("rate_move", r.rate_move)
for d in r.drivers: print(" ", d.id, d.score, d.status, d.coverage, [(e.label, e.value, e.available) for e in d.evidence])
print("components", [(c.key, c.score, c.status, c.note[:60]) for c in r.inflation_components])
print("curve", r.curve.shape, r.curve.lead, r.curve.spread_z, r.curve.sentence)
print("decomp", r.decomposition)
print("confirm", [(c.label, c.status, c.values) for c in r.confirmations])
print("div", [(d.label, d.severity, d.why) for d in r.divergences])
print("impl", r.market_implication.why, [(i.label, i.pressure) for i in r.market_implication.rows])
print("triggers", [(t.text, t.met) for t in r.triggers]); print("release", [t.text for t in r.release])
