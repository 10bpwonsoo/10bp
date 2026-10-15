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

SNAP = Path("/tmp/snap"); CAP = Path("/home/user/10bp/marketpulse/data/captures/2026-10-07-manual")
ins = get_instruments().instruments
# live: 9/18 캡처의 원시 시계열 + 그 스냅샷의 as_of
live = IntelligenceSnapshot.model_validate_json((CAP / "live.json").read_text(encoding="utf-8"))
series = pickle.load(open(SNAP / "series_live.pkl", "rb"))
# 뉴스 온도의 히스토리: 이번 캡처만으로는 이틀뿐이라, 이 저장소에 남아 있는 모든 캡처의 태깅 이벤트를
# 합친다 (같은 기사는 수기 > LLM > 룰 순으로 하나만). 그래도 9/14 이전은 기사가 거의 없다 — 그 날들은 결측이다.
import glob
PRIORITY = {"manual": 0, "llm": 1, "rule": 2}
merged: dict[str, object] = {}
for f in sorted(glob.glob("/home/user/10bp/marketpulse/data/captures/*/live.json")):
    snap_i = IntelligenceSnapshot.model_validate_json(Path(f).read_text(encoding="utf-8"))
    for e in snap_i.events:
        key = e.url or e.event
        cur = merged.get(key)
        if cur is None or PRIORITY.get(e.extractor, 9) < PRIORITY.get(cur.extractor, 9):
            merged[key] = e
events = sorted(merged.values(), key=lambda e: e.timestamp)
print("events merged", len(events), "manual", sum(1 for e in events if e.extractor == "manual"), "from", events[0].timestamp.date(), "to", events[-1].timestamp.date())
h = replay_market_state(ins, series, as_of=live.as_of, days=22, mode=DataMode.DELAYED, events=events)
print("news days", [(p.date.isoformat()[5:], p.news_events, p.news_temperature and round(p.news_temperature)) for p in h.points if p.news_events])
print("excluded", h.excluded_components)
(CAP / "state_history.json").write_text(h.model_dump_json(), encoding="utf-8")
print("live", len(h.points), h.summary)
VIEWS = {"inflation": "inflation_shock", "ai": "ai_sentiment", "baseline": "baseline", "oil_spike": "oil_spike", "memory_upcycle": "memory_upcycle"}
for view, scenario in VIEWS.items():
    snap = IntelligenceSnapshot.model_validate_json((SNAP / f"{view}.json").read_text(encoding="utf-8"))
    settings = Settings(data_mode="MOCK", scenario=scenario, llm_enabled=False)
    r = run_pipeline_detailed(settings, as_of=snap.as_of)
    hm = replay_market_state(ins, r.series_by_id, as_of=snap.as_of, days=22, mode=DataMode.MOCK, events=snap.events)
    same = hm.points[-1].label == snap.market_state.primary_label if hm.points else None
    (SNAP / f"hist_{view}.json").write_text(hm.model_dump_json(), encoding="utf-8")
    print(view, len(hm.points), "last==panel:", same, "|", hm.summary[:90])
