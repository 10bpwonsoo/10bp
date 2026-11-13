"""
Daily snapshot history 캡처 (2026-10-12).
  --market   : 기존 캡처를 RECORDED 로 migration(한 번만 들어간다) → 시장 판정 backfill·오늘 기록 → state_history.json (저장 sequence)
  --assemble : 모든 탭의 저장 sequence 를 daily_history.json 으로 (정적 배포본의 /api/v1/history/{tab})
저장소는 marketpulse/data/history/ (JSON, 커밋). 과거 snapshot 은 절대 다시 계산하지 않는다.
"""
import glob, json, pickle, sys
from pathlib import Path
from marketpulse.config.registry import get_instruments
from marketpulse.config.settings import Settings, get_settings
from marketpulse.history import DailySnapshotManager, JsonDirStore
from marketpulse.history.calculators import MarketInputs
from marketpulse.history.integrate import history_of, sync_market
from marketpulse.history.migrate import migrate_captures
from marketpulse.models.snapshot import IntelligenceSnapshot

CAP = Path(sys.argv[1]); mode = sys.argv[2] if len(sys.argv) > 2 else "--market"
ROOT = Path("/home/user/10bp/marketpulse")
manager = DailySnapshotManager(JsonDirStore(get_settings().history_dir))
live = IntelligenceSnapshot.model_validate_json((CAP / "live.json").read_text(encoding="utf-8"))
if mode == "--market":
    print("migrate", migrate_captures(manager, ROOT / "data/captures"))
    series = pickle.load(open("/tmp/snap/series_live.pkl", "rb"))
    PRIORITY = {"manual": 0, "llm": 1, "rule": 2}; merged = {}
    for f in sorted(glob.glob(str(ROOT / "data/captures/*/live.json"))):
        for e in IntelligenceSnapshot.model_validate_json(Path(f).read_text(encoding="utf-8")).events:
            key = e.url or e.event; cur = merged.get(key)
            if cur is None or PRIORITY.get(e.extractor, 9) < PRIORITY.get(cur.extractor, 9): merged[key] = e
    events = sorted(merged.values(), key=lambda e: e.timestamp)
    h = sync_market(manager, inputs=MarketInputs(instruments=get_instruments().instruments, series_by_id=series, events=events, mode=live.mode, zscore_window=Settings().zscore_window),
                    snapshot=live, as_of=live.as_of)
    (CAP / "state_history.json").write_text(h.model_dump_json(), encoding="utf-8")
    print("market", h.history_mode, "rec", h.recorded_days, "bf", h.backfilled_days, "live", h.live_today, len(h.points)); print(h.summary)
    for p in h.points: print(" ", p.date, p.source.ljust(10), p.label.value.ljust(17), f"{p.confidence:5.1f}", None if p.composite is None else f"{p.composite:+.0f}")
else:
    out = {}
    for tab in ("market_regime", "ai_sentiment", "ai_regime", "rates_regime", "oil_regime", "memory_cycle"):
        h = history_of(manager, tab, as_of=live.as_of)
        out[tab] = json.loads(h.model_dump_json())
        print(tab.ljust(14), "pts", len(h.points), "rec", h.recorded_days, "bf", h.backfilled_days, "live", h.live_today, "|", h.current_label, h.current_streak, "d · prev", h.previous_label, "· chg", h.changes)
    (CAP / "daily_history.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
