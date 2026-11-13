"""
Daily snapshot 저장소 — append-only.

두 구현:
  JsonDirStore   디렉터리에 탭별 JSON 파일 하나(`{tab_id}.json`). 저장소를 커밋해 두면 세션·프로세스가 바뀌어도 기록이 남는다. 정적 배포본·캡처 파이프라인의 기본.
  SqliteDailyStore  기존 스냅샷 DB(SQLite) 안의 `daily_snapshots` 테이블. API 서버가 DB 를 쓰면 이쪽.
둘 다 locked snapshot 을 일반 put 으로 덮어쓰지 못한다 — LockedSnapshotError. correction 경로만 교체하고 audit trail 을 남긴다.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path

from ..models.daily_history import DailySnapshot


class LockedSnapshotError(RuntimeError):
    """잠긴 과거 snapshot 을 일반 갱신이 바꾸려 했다. 자동 update 는 이것을 reject 한다."""


class DailySnapshotStore(ABC):
    @abstractmethod
    def get(self, key: str, snapshot_date: date) -> DailySnapshot | None: ...

    @abstractmethod
    def list(self, key: str, start: date | None = None, end: date | None = None) -> list[DailySnapshot]: ...

    @abstractmethod
    def put(self, key: str, snapshot: DailySnapshot, *, replace_locked: bool = False) -> None:
        """저장. key 는 저장 키(보통 tab_id, MOCK 은 'mock-{scenario}-{tab_id}'). 같은 (key, date) 가 locked 이면 replace_locked 없이는 LockedSnapshotError."""

    @abstractmethod
    def tabs(self) -> list[str]: ...

    def close(self) -> None:  # pragma: no cover - 기본은 할 일 없음
        return None


class JsonDirStore(DailySnapshotStore):
    def __init__(self, directory: Path | str) -> None:
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._cache: dict[str, dict[date, DailySnapshot]] = {}

    def _path(self, tab_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in tab_id)
        return self.dir / f"{safe}.json"

    def _load(self, tab_id: str) -> dict[date, DailySnapshot]:
        with self._lock:
            if tab_id in self._cache:
                return self._cache[tab_id]
            p = self._path(tab_id)
            out: dict[date, DailySnapshot] = {}
            if p.exists():
                raw = json.loads(p.read_text(encoding="utf-8"))
                for row in raw.get("snapshots", []):
                    s = DailySnapshot.model_validate(row)
                    out[s.snapshot_date] = s
            self._cache[tab_id] = out
            return out

    def _flush(self, key: str) -> None:
        with self._lock:
            rows = [s.model_dump(mode="json") for _, s in sorted(self._load(key).items())]
            p = self._path(key)
            tmp = p.with_suffix(".json.tmp")
            tmp.write_text(json.dumps({"tab_id": key, "note": "append-only daily snapshots — locked rows are never rewritten by routine updates", "snapshots": rows},
                                      ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, p)

    def get(self, key: str, snapshot_date: date) -> DailySnapshot | None:
        return self._load(key).get(snapshot_date)

    def list(self, key: str, start: date | None = None, end: date | None = None) -> list[DailySnapshot]:
        rows = self._load(key)
        return [s for d, s in sorted(rows.items()) if (start is None or d >= start) and (end is None or d <= end)]

    def put(self, key: str, snapshot: DailySnapshot, *, replace_locked: bool = False) -> None:
        with self._lock:
            rows = self._load(key)
            cur = rows.get(snapshot.snapshot_date)
            if cur is not None and cur.is_locked and not replace_locked:
                raise LockedSnapshotError(f"{key} {snapshot.snapshot_date} 는 {cur.history_source} · locked — 일반 갱신으로 바꿀 수 없다")
            rows[snapshot.snapshot_date] = snapshot
            self._flush(key)

    def tabs(self) -> list[str]:
        return sorted(p.stem for p in self.dir.glob("*.json"))


_DDL = """
CREATE TABLE IF NOT EXISTS daily_snapshots (
    tab_id         TEXT NOT NULL,
    snapshot_date  TEXT NOT NULL,
    history_source TEXT NOT NULL,
    is_locked      INTEGER NOT NULL DEFAULT 0,
    calculated_at  TEXT NOT NULL,
    payload        TEXT NOT NULL,
    PRIMARY KEY (tab_id, snapshot_date)
);
CREATE TABLE IF NOT EXISTS daily_snapshot_corrections (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    tab_id         TEXT NOT NULL,
    snapshot_date  TEXT NOT NULL,
    corrected_at   TEXT NOT NULL,
    corrected_by   TEXT NOT NULL,
    reason         TEXT NOT NULL,
    original_value TEXT NOT NULL,
    corrected_value TEXT NOT NULL
);
"""


class SqliteDailyStore(DailySnapshotStore):
    def __init__(self, path: Path | str = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_DDL)
        self._lock = threading.RLock()

    def get(self, key: str, snapshot_date: date) -> DailySnapshot | None:
        with self._lock:
            row = self._conn.execute("SELECT payload FROM daily_snapshots WHERE tab_id=? AND snapshot_date=?", (key, snapshot_date.isoformat())).fetchone()
        return DailySnapshot.model_validate_json(row["payload"]) if row else None

    def list(self, key: str, start: date | None = None, end: date | None = None) -> list[DailySnapshot]:
        q = "SELECT payload FROM daily_snapshots WHERE tab_id=?"; args: list[object] = [key]
        if start is not None:
            q += " AND snapshot_date>=?"; args.append(start.isoformat())
        if end is not None:
            q += " AND snapshot_date<=?"; args.append(end.isoformat())
        with self._lock:
            rows = self._conn.execute(q + " ORDER BY snapshot_date", args).fetchall()
        return [DailySnapshot.model_validate_json(r["payload"]) for r in rows]

    def put(self, key: str, snapshot: DailySnapshot, *, replace_locked: bool = False) -> None:
        with self._lock:
            cur = self._conn.execute("SELECT is_locked, history_source FROM daily_snapshots WHERE tab_id=? AND snapshot_date=?",
                                     (key, snapshot.snapshot_date.isoformat())).fetchone()
            if cur is not None and int(cur["is_locked"]) and not replace_locked:
                raise LockedSnapshotError(f"{key} {snapshot.snapshot_date} 는 {cur['history_source']} · locked — 일반 갱신으로 바꿀 수 없다")
            if replace_locked and snapshot.corrections:
                c = snapshot.corrections[-1]
                self._conn.execute("INSERT INTO daily_snapshot_corrections (tab_id, snapshot_date, corrected_at, corrected_by, reason, original_value, corrected_value) VALUES (?,?,?,?,?,?,?)",
                                   (key, snapshot.snapshot_date.isoformat(), c.corrected_at.isoformat(), c.corrected_by, c.correction_reason,
                                    json.dumps(c.original_value, ensure_ascii=False, default=str), json.dumps(c.corrected_value, ensure_ascii=False, default=str)))
            self._conn.execute("INSERT OR REPLACE INTO daily_snapshots (tab_id, snapshot_date, history_source, is_locked, calculated_at, payload) VALUES (?,?,?,?,?,?)",
                               (key, snapshot.snapshot_date.isoformat(), snapshot.history_source, int(snapshot.is_locked), snapshot.calculated_at.isoformat(), snapshot.model_dump_json()))

    def tabs(self) -> list[str]:
        with self._lock:
            return [r["tab_id"] for r in self._conn.execute("SELECT DISTINCT tab_id FROM daily_snapshots ORDER BY tab_id").fetchall()]

    def close(self) -> None:
        self._conn.close()
