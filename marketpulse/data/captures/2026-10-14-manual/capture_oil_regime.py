"""실데이터 유가 원인 판별 캡처 — 정적 배포본용."""
import pickle, sys
from pathlib import Path
from marketpulse.config.registry import get_instruments
from marketpulse.engines.oil_regime import build_oil_regime
from marketpulse.engines.scenario_check import extra_z_from_investment
from marketpulse.models.intelligence import InvestmentIntelligence
from marketpulse.models.snapshot import IntelligenceSnapshot
CAP = Path(sys.argv[1])
live = IntelligenceSnapshot.model_validate_json((CAP / "live.json").read_text(encoding="utf-8"))
inv = InvestmentIntelligence.model_validate_json((CAP / "investment.json").read_text(encoding="utf-8"))
market = pickle.load(open("/tmp/snap/market_snapshot.pkl", "rb"))
ins = get_instruments().instruments
r = build_oil_regime(market, live.themes, live.divergences, {i.id: i for i in ins}, extra_z=extra_z_from_investment(inv), extra_names={p.id: p.label for p in inv.alternative})
(CAP / "oil_regime.json").write_text(r.model_dump_json(), encoding="utf-8")
from marketpulse.config.settings import get_settings
from marketpulse.history import DailySnapshotManager, JsonDirStore
from marketpulse.history.calculators import RegimeInputs
from marketpulse.history.integrate import sync_oil
_series = pickle.load(open("/tmp/snap/series_live.pkl", "rb"))
_h = sync_oil(DailySnapshotManager(JsonDirStore(get_settings().history_dir)), r, inputs=RegimeInputs(instruments=ins, series_by_id=_series, events=live.events, mode=live.mode), as_of=live.as_of)
print("HIST", "rec", _h.recorded_days, "bf", _h.backfilled_days, _h.current_label, _h.current_streak, "prev", _h.previous_label, [(p.date.isoformat()[5:], p.source[0], p.state) for p in _h.points[-6:]])
print(r.regime_label, r.signal_strength, r.margin)
for d in r.drivers: print(" ", d.id, d.score, d.status)
