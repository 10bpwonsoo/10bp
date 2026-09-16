"""SQLite 스냅샷 저장소."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
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

    def at_or_before(
        self, stream_key: str, target: datetime, *, max_distance: timedelta
    ) -> IntelligenceSnapshot | None:
        # as_of 는 UTC isoformat 문자열이라 사전순이 곧 시간순이다.
        with self._lock:
            row = self._conn.execute(
                """
                SELECT payload, as_of FROM snapshots
                WHERE stream_key = ? AND as_of <= ?
                ORDER BY as_of DESC
                LIMIT 1
                """,
                (stream_key, target.isoformat()),
            ).fetchone()
        if row is None:
            return None
        found = datetime.fromisoformat(row["as_of"])
        if target - found > max_distance:
            return None
        return IntelligenceSnapshot.model_validate(json.loads(row["payload"]))

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

    # ── Investment Intelligence (2026-09-16 신설, 전부 추가) ─────────
    def upsert_daily(
        self, series_id: str, rows: Sequence[tuple[str, float, float | None]], source: str
    ) -> int:
        """(date, value, volume) 행을 upsert 한다. 거래량 None 은 NULL 이다."""
        if not rows:
            return 0
        with self._cursor() as cur:
            cur.executemany(
                """
                INSERT INTO alt_daily (series_id, date, value, volume, source)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (series_id, date) DO UPDATE SET
                    value = excluded.value, volume = excluded.volume, source = excluded.source
                """,
                [(series_id, d, v, vol, source) for d, v, vol in rows],
            )
            cur.execute(
                """
                INSERT INTO alt_fetch_log (series_id, fetched_date, last_bar, source, points)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (series_id) DO UPDATE SET
                    fetched_date = excluded.fetched_date, last_bar = excluded.last_bar,
                    source = excluded.source, points = excluded.points
                """,
                (series_id, utcnow().date().isoformat(), max(r[0] for r in rows), source, len(rows)),
            )
        return len(rows)

    def load_daily(
        self, series_id: str, *, limit: int = 400
    ) -> list[tuple[str, float, float | None, str]]:
        """오래된 것부터 (date, value, volume, source)."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT date, value, volume, source FROM alt_daily
                WHERE series_id = ? ORDER BY date DESC LIMIT ?
                """,
                (series_id, limit),
            ).fetchall()
        return [(r["date"], r["value"], r["volume"], r["source"]) for r in reversed(rows)]

    def fetch_log(self, series_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM alt_fetch_log WHERE series_id = ?", (series_id,)
            ).fetchone()
        return dict(row) if row else None

    def save_investment(self, stream_key: str, as_of: datetime, payload: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO investment_snapshots (stream_key, as_of, created_at, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (stream_key, as_of) DO UPDATE SET
                    payload = excluded.payload, created_at = excluded.created_at
                """,
                (stream_key, as_of.isoformat(), utcnow().isoformat(), payload),
            )

    def latest_investment(self, stream_key: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT payload FROM investment_snapshots
                WHERE stream_key = ? ORDER BY as_of DESC LIMIT 1
                """,
                (stream_key,),
            ).fetchone()
        return row["payload"] if row else None

    def upsert_analyst(
        self, rows: Sequence[tuple[str, str, str, str | None, float | None, float | None]], source: str
    ) -> int:
        """(stock_id, date, broker, rating, target_price, eps_fy1)."""
        if not rows:
            return 0
        with self._cursor() as cur:
            cur.executemany(
                """
                INSERT INTO analyst_revision (stock_id, date, broker, rating, target_price, eps_fy1, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (stock_id, date, broker) DO UPDATE SET
                    rating = excluded.rating, target_price = excluded.target_price,
                    eps_fy1 = excluded.eps_fy1, source = excluded.source
                """,
                [(*r, source) for r in rows],
            )
        return len(rows)

    def load_analyst(self, stock_id: str, *, limit: int = 200) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM analyst_revision WHERE stock_id = ?
                ORDER BY date DESC LIMIT ?
                """,
                (stock_id, limit),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def save_commentary(
        self, *, kind: str, entity: str, as_of: datetime, source_mode: str, confidence: str, payload: str
    ) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO commentary (kind, entity, as_of, created_at, source_mode, confidence, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (kind, entity, as_of.isoformat(), utcnow().isoformat(), source_mode, confidence, payload),
            )

    def load_commentary(self, entity: str | None = None, *, limit: int = 50) -> list[dict]:
        with self._lock:
            if entity is None:
                rows = self._conn.execute(
                    "SELECT * FROM commentary ORDER BY as_of DESC LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM commentary WHERE entity = ? ORDER BY as_of DESC LIMIT ?",
                    (entity, limit),
                ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
