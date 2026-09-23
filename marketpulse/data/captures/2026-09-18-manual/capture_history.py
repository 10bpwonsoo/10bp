"""정적 배포본용 Market State 히스토리 캡처 — 뷰별로 같은 as_of 에서 재생."""
import json, pickle
from datetime import datetime
from pathlib import Path
from marketpulse.config.registry import get_instruments
from marketpulse.config.settings import Settings
from marketpulse.engines.orchestrator import run_pipeline_detailed
from marketpulse.engines.state_history import replay_market_state
from marketpulse.models.common import DataMode
from marketpulse.models.snapshot import IntelligenceSnapshot

SNAP = Path("/tmp/snap"); CAP = Path("/home/user/10bp/marketpulse/data/captures/2026-09-18-manual")
ins = get_instruments().instruments
# live: 9/18 캡처의 원시 시계열 + 그 스냅샷의 as_of
live = IntelligenceSnapshot.model_validate_json((CAP / "live.json").read_text(encoding="utf-8"))
series = pickle.load(open(SNAP / "series_live.pkl", "rb"))
h = replay_market_state(ins, series, as_of=live.as_of, days=22, mode=DataMode.DELAYED)
(CAP / "state_history.json").write_text(h.model_dump_json(), encoding="utf-8")
print("live", len(h.points), h.summary)
VIEWS = {"inflation": "inflation_shock", "ai": "ai_sentiment", "baseline": "baseline", "oil_spike": "oil_spike", "memory_upcycle": "memory_upcycle"}
for view, scenario in VIEWS.items():
    snap = IntelligenceSnapshot.model_validate_json((SNAP / f"{view}.json").read_text(encoding="utf-8"))
    settings = Settings(data_mode="MOCK", scenario=scenario, llm_enabled=False)
    r = run_pipeline_detailed(settings, as_of=snap.as_of)
    hm = replay_market_state(ins, r.series_by_id, as_of=snap.as_of, days=22, mode=DataMode.MOCK)
    same = hm.points[-1].label == snap.market_state.primary_label if hm.points else None
    (SNAP / f"hist_{view}.json").write_text(hm.model_dump_json(), encoding="utf-8")
    print(view, len(hm.points), "last==panel:", same, "|", hm.summary[:90])
