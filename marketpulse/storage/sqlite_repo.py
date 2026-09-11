"""SQLite 스냅샷 저장소."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence

from ..models.common import utcnow
from ..models.divergence import Divergence
from ..models.snapshot import IntelligenceSnapshot
from .repository import SnapshotRepository

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


class SqliteSnapshotRepository(SnapshotRepository):
    """
    파일 기반 저장소.

    ':memory:' 를 주면 인메모리로 동작한다 — 테스트가 디스크를 건드리지
    않는다. 인메모리에서는 연결을 공유해야 하므로 하나만 열고 락으로 감싼다.
    """

    def __init__(self, path: Path | str = ":memory:") -> None:
        self.path = str(path)
        self._lock = threading.Lock()
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            self.path, check_same_thread=False, isolation_level=None
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute("BEGIN")
                yield cur
                cur.execute("COMMIT")
            except Exception:
                cur.execute("ROLLBACK")
                raise
            finally:
                cur.close()

    def save(
        self,
        stream_key: str,
        snapshot: IntelligenceSnapshot,
        pending: Sequence[Divergence] = (),
    ) -> None:
        payload = json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False)
        pending_json = json.dumps(
            [d.model_dump(mode="json") for d in pending], ensure_ascii=False
        )
        with self._cursor() as cur:
            # 같은 시각의 재실행은 덮어쓴다. 중복 행을 만들지 않는다.
            cur.execute(
                """
                INSERT INTO snapshots (stream_key, as_of, created_at, payload, pending)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (stream_key, as_of)
                DO UPDATE SET payload = excluded.payload,
                              pending = excluded.pending,
                              created_at = excluded.created_at
                """,
                (
                    stream_key,
                    snapshot.as_of.isoformat(),
                    utcnow().isoformat(),
                    payload,
                    pending_json,
                ),
            )

    def recent(self, stream_key: str, limit: int = 12) -> list[IntelligenceSnapshot]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT payload FROM snapshots
                WHERE stream_key = ?
                ORDER BY as_of DESC
                LIMIT ?
                """,
                (stream_key, limit),
            ).fetchall()
        # 최신순으로 읽어 오래된 순으로 뒤집는다. 엔진은 시간순을 기대한다.
        return [
            IntelligenceSnapshot.model_validate(json.loads(r["payload"]))
            for r in reversed(rows)
        ]

    def latest_pending(self, stream_key: str) -> list[Divergence]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT pending FROM snapshots
                WHERE stream_key = ?
                ORDER BY as_of DESC
                LIMIT 1
                """,
                (stream_key,),
            ).fetchone()
        if row is None:
            return []
        return [Divergence.model_validate(d) for d in json.loads(row["pending"])]

    def prune(self, stream_key: str, keep: int) -> int:
        with self._cursor() as cur:
            cur.execute(
                """
                DELETE FROM snapshots
                WHERE stream_key = ?
                  AND id NOT IN (
                      SELECT id FROM snapshots
                      WHERE stream_key = ?
                      ORDER BY as_of DESC
                      LIMIT ?
                  )
                """,
                (stream_key, stream_key, keep),
            )
            return cur.rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()
