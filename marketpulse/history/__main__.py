"""
    python -m marketpulse.history show --tab market_regime [--dir DIR]
    python -m marketpulse.history migrate --captures marketpulse/data/captures [--dir DIR]
    python -m marketpulse.history finalize --tab market_regime --date 2026-10-07
    python -m marketpulse.history correct --tab market_regime --date 2026-09-18 --file corrected.json --reason "..." --by name
Backfill 은 데이터(시계열·기사)가 필요하므로 캡처 스크립트·API 서비스가 sync_* 로 한다.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from ..config.settings import get_settings
from ..models.daily_history import DailySnapshot
from .manager import DailySnapshotManager
from .migrate import migrate_captures
from .store import JsonDirStore


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="marketpulse.history")
    p.add_argument("cmd", choices=["show", "migrate", "finalize", "correct", "tabs"])
    p.add_argument("--dir", default=None, help="JSON 저장소 디렉터리 (기본 settings.history_dir)")
    p.add_argument("--tab"); p.add_argument("--date"); p.add_argument("--captures"); p.add_argument("--file"); p.add_argument("--reason", default=""); p.add_argument("--by", default="admin")
    a = p.parse_args(argv)
    store = JsonDirStore(Path(a.dir) if a.dir else get_settings().history_dir)
    m = DailySnapshotManager(store)
    if a.cmd == "tabs":
        print(store.tabs()); return 0
    if a.cmd == "show":
        for s in m.get_history(a.tab):
            print(s.snapshot_date, s.history_source.ljust(10), "L" if s.is_locked else " ", s.state.ljust(20), "" if s.state_score is None else f"{s.state_score:+.1f}", "" if s.confidence is None else f"{s.confidence:.0f}%",
                  s.model_version, s.logic_version, s.calculated_at.strftime("%m-%d %H:%M"), f"corr {len(s.corrections)}" if s.corrections else "")
        return 0
    if a.cmd == "migrate":
        print(json.dumps(migrate_captures(m, Path(a.captures)), ensure_ascii=False)); return 0
    if a.cmd == "finalize":
        s = m.finalize(a.tab, date.fromisoformat(a.date)); print(s and (s.history_source, s.is_locked)); return 0
    if a.cmd == "correct":
        corrected = DailySnapshot.model_validate_json(Path(a.file).read_text(encoding="utf-8"))
        s = m.correct(a.tab, date.fromisoformat(a.date), corrected, reason=a.reason, by=a.by); print(s.snapshot_date, s.state, "corrections", len(s.corrections)); return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
