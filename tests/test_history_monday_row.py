"""월요일 07:30 KST 저장(= UTC 일요일) — 그 화면 판정(REGIME v2 선택 포함)이 금요일 행으로 기록된다(2026-11-09)."""
import json
from pathlib import Path

from marketpulse.history import DailySnapshotManager, JsonDirStore
from marketpulse.history.calculators import MarketInputs
from marketpulse.history.integrate import sync_market
from marketpulse.models.snapshot import IntelligenceSnapshot

CAP = Path(__file__).resolve().parents[1] / "marketpulse" / "data" / "captures" / "2026-11-09-backfill" / "live.json"


def test_monday_screen_is_recorded_as_friday_row(tmp_path):
    live = IntelligenceSnapshot.model_validate_json(CAP.read_text(encoding="utf-8"))
    assert live.as_of.weekday() == 6  # UTC 일요일 22:30
    sel = live.market_state.selection
    assert sel is not None and live.market_state.primary_label.value == sel.selected_regime
    mgr = DailySnapshotManager(JsonDirStore(tmp_path))
    sync_market(mgr, inputs=MarketInputs(instruments=[], series_by_id={}), snapshot=live, as_of=live.as_of)
    rows = mgr.get_history("market_regime")
    assert [r.snapshot_date.isoformat() for r in rows] == ["2026-11-06"]  # 주말 행은 만들지 않는다
    r = rows[0]
    assert r.state == sel.selected_regime and round(r.confidence) == sel.regime_confidence  # 화면 판정 그대로
    assert r.history_source == "RECORDED" and r.is_locked and r.payload["date"] == "2026-11-06"
    # 이미 있으면 다시 쓰지 않는다
    sync_market(mgr, inputs=MarketInputs(instruments=[], series_by_id={}), snapshot=live, as_of=live.as_of)
    assert len(mgr.get_history("market_regime")) == 1
