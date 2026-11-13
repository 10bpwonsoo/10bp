"""실데이터 시나리오 점검 캡처 — 정적 배포본용. 시장 z 는 /tmp/snap/market_snapshot.pkl, 대체·종목 z 는 investment.json."""
import json, pickle, sys
from pathlib import Path
from marketpulse.adapters.market.scenario import available_scenarios, load_scenario
from marketpulse.config.registry import get_instruments
from marketpulse.config.settings import MOCK_DIR
from marketpulse.engines.scenario_check import check_scenarios, extra_z_from_investment
from marketpulse.models.intelligence import InvestmentIntelligence
from marketpulse.models.snapshot import IntelligenceSnapshot
CAP = Path(sys.argv[1])
live = IntelligenceSnapshot.model_validate_json((CAP / "live.json").read_text(encoding="utf-8"))
inv = InvestmentIntelligence.model_validate_json((CAP / "investment.json").read_text(encoding="utf-8"))
market = pickle.load(open("/tmp/snap/market_snapshot.pkl", "rb"))
ins = get_instruments().instruments
scs = [load_scenario(MOCK_DIR, n) for n in available_scenarios(MOCK_DIR)]
out = check_scenarios(scs, market, live.market_state, live.themes, {i.id: i for i in ins}, extra_z=extra_z_from_investment(inv))
(CAP / "scenario_check.json").write_text(json.dumps([c.model_dump(mode="json") for c in out], ensure_ascii=False), encoding="utf-8")
for c in out:
    print(c.name, c.match_score, c.match_label, "|", c.verdict[:140])
