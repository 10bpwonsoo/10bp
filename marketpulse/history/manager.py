"""
DailySnapshotManager — 모든 탭의 History 가 같은 lifecycle 을 쓴다.

  ① 과거 + snapshot 있음      → 읽는다 (LOCKED)
  ② 과거 + snapshot 없음      → calculator 로 그 날짜를 1회 계산 → BACKFILLED 저장 → LOCKED
  ③ 오늘                      → LIVE (finalize_time 전) / RECORDED (finalize_time 이후, 저장 즉시 LOCKED)
  ④ 날이 바뀌면 어제의 LIVE   → 그날 마지막 관측을 RECORDED(last_observation) 로 승격·LOCKED (그날 당시 시스템 판단이므로 backfill 로 대체하지 않는다)
locked snapshot 은 일반 갱신이 건드리지 못한다. correct() 만 audit trail 과 함께 바꾼다.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Sequence
from zoneinfo import ZoneInfo

from ..models.common import utcnow
from ..models.daily_history import Correction, DailySnapshot
from .store import DailySnapshotStore, LockedSnapshotError
from .versions import load_history_config

logger = logging.getLogger(__name__)

Calculator = Callable[[date, DailySnapshot | None], DailySnapshot | None]


class DailySnapshotManager:
    def __init__(self, store: DailySnapshotStore, *, finalize_time: str | None = None, tz: str | None = None, clock: Callable[[], datetime] = utcnow, config_dir=None,
                 namespace: str = "") -> None:
        cfg = load_history_config(config_dir)
        self.store = store
        #: 저장 키 접두 — MOCK 시나리오는 'mock-{scenario}-' 로 분리해 실데이터 기록과 섞이지 않게 한다
        self.namespace = namespace
        self.clock = clock
        hh, mm = str(finalize_time or cfg.get("finalize_time", "16:10")).split(":")
        self.finalize_at = time(int(hh), int(mm))
        self.tz = ZoneInfo(str(tz or cfg.get("timezone", "Asia/Seoul")))
        self.window_days = int(cfg.get("window_days", 22))
        self.backfill_days = int(cfg.get("backfill_days", self.window_days))
        self.cfg = cfg

    def weekend(self, d: date) -> bool:
        """history.yaml 의 weekdays_only 면 토·일 snapshot 을 새로 만들지 않는다(이미 있는 것은 그대로 둔다)."""
        return bool(self.cfg.get("weekdays_only", False)) and d.weekday() >= 5

    # ── 읽기 ──────────────────────────────────────────────
    def key(self, tab_id: str) -> str:
        return f"{self.namespace}{tab_id}"

    def _put(self, snapshot: DailySnapshot, *, replace_locked: bool = False) -> None:
        self.store.put(self.key(snapshot.tab_id), snapshot, replace_locked=replace_locked)

    def get_snapshot(self, tab_id: str, snapshot_date: date) -> DailySnapshot | None:
        return self.store.get(self.key(tab_id), snapshot_date)

    def get_history(self, tab_id: str, start: date | None = None, end: date | None = None) -> list[DailySnapshot]:
        return self.store.list(self.key(tab_id), start, end)

    # ── 날짜·시각 규칙 ─────────────────────────────────────
    @staticmethod
    def snapshot_date_of(as_of: datetime) -> date:
        """스냅샷의 날짜는 as_of 의 UTC 날짜다 — 시계열 봉 날짜(trading_dates)와 같은 잣대."""
        return as_of.astimezone(timezone.utc).date() if as_of.tzinfo else as_of.date()

    def finalize_datetime(self, d: date) -> datetime:
        """그 날짜의 Daily Finalization 시각(설정의 KST 시각)을 UTC 로."""
        return datetime.combine(d, self.finalize_at, tzinfo=self.tz).astimezone(timezone.utc)

    def is_final_time(self, as_of: datetime) -> bool:
        return as_of >= self.finalize_datetime(self.snapshot_date_of(as_of))

    def today(self) -> date:
        return self.snapshot_date_of(self.clock())

    # ── 쓰기 ──────────────────────────────────────────────
    def save_snapshot(self, snapshot: DailySnapshot) -> DailySnapshot:
        """append-only 저장. locked 가 있으면 LockedSnapshotError (silent overwrite 금지)."""
        self._put(snapshot)
        return snapshot

    def lock_snapshot(self, tab_id: str, snapshot_date: date) -> DailySnapshot | None:
        s = self.get_snapshot(tab_id, snapshot_date)
        if s is None or s.is_locked:
            return s
        s2 = s.model_copy(update={"is_locked": True, "is_final": True})
        self._put(s2)
        return s2

    def record(self, snapshot: DailySnapshot, *, as_of: datetime | None = None) -> DailySnapshot:
        """
        오늘(또는 as_of 날짜)의 계산 결과를 넣는다.
          - 그 날짜에 locked snapshot 이 있으면 그것을 돌려준다 (갱신하지 않는다).
          - finalize_time 이후면 RECORDED + LOCKED (Daily Finalization), 아니면 LIVE (교체 가능).
        """
        as_of = as_of or snapshot.data_asof or snapshot.calculated_at
        existing = self.get_snapshot(snapshot.tab_id, snapshot.snapshot_date)
        if existing is not None and existing.is_locked:
            return existing
        if self.weekend(snapshot.snapshot_date):
            # 토·일 날짜(한국 월요일 아침 = UTC 일요일)는 새로 만들지 않는다 — 금요일 장은 다음 계산의 backfill 이 채운다
            return existing or snapshot
        if self.is_final_time(as_of):
            s = snapshot.model_copy(update={"history_source": "RECORDED", "is_final": True, "is_locked": True, "is_backfilled": False, "finalization": "daily_close"})
        else:
            s = snapshot.model_copy(update={"history_source": "LIVE", "is_final": False, "is_locked": False, "is_backfilled": False, "finalization": "live"})
        self._put(s)
        return s

    def finalize(self, tab_id: str, snapshot_date: date, *, finalization: str = "daily_close") -> DailySnapshot | None:
        """그 날짜의 LIVE 를 RECORDED 로 확정·잠근다. 이미 locked 면 그대로."""
        s = self.get_snapshot(tab_id, snapshot_date)
        if s is None or s.is_locked:
            return s
        s2 = s.model_copy(update={"history_source": "RECORDED", "is_final": True, "is_locked": True, "is_backfilled": False, "finalization": finalization})
        self._put(s2)
        return s2

    def promote_stale_live(self, tab_id: str, *, today: date | None = None) -> list[DailySnapshot]:
        """날이 바뀌었는데 LIVE 로 남은 과거 날짜 — 그날 마지막 관측이 그날의 기록이다. RECORDED(last_observation) 로 승격·LOCK."""
        today = today or self.today()
        out = []
        for s in self.get_history(tab_id, None, today - timedelta(days=1)):
            if s.history_source == "LIVE" and not s.is_locked:
                out.append(self.finalize(tab_id, s.snapshot_date, finalization="last_observation"))  # type: ignore[arg-type]
        return out

    # ── Backfill ─────────────────────────────────────────
    def backfill_missing(self, tab_id: str, dates: Sequence[date], calculator: Calculator, *, previous_hint: DailySnapshot | None = None) -> list[DailySnapshot]:
        """
        snapshot 이 없는 날짜만 calculator(date, previous_snapshot) 로 1회 계산해 BACKFILLED 로 저장·LOCK.
        같은 날짜는 두 번 계산하지 않는다. calculator 가 None 을 주면 INSUFFICIENT_DATA snapshot 을 저장한다(빈칸으로 두지 않되 state 를 지어내지 않는다).
        calculator 는 날짜 D 이하의 데이터만 써야 한다(look-ahead 금지). previous 는 저장된 직전 날짜 snapshot — 지속성 항은 저장된 sequence 로 잇는다.
        """
        created: list[DailySnapshot] = []
        prev = previous_hint
        for d in sorted(x for x in dates if not self.weekend(x)):
            existing = self.get_snapshot(tab_id, d)
            if existing is not None:
                prev = existing
                continue
            try:
                snap = calculator(d, prev)
            except Exception:
                logger.exception("%s %s backfill 실패 — 그날은 INSUFFICIENT_DATA 로 남긴다", tab_id, d)
                snap = None
            if snap is None:
                snap = self.insufficient(tab_id, d)
            snap = snap.model_copy(update={"history_source": "BACKFILLED", "is_backfilled": True, "is_final": True, "is_locked": True, "finalization": "backfill",
                                           "calculated_at": self.clock()})
            try:
                self._put(snap)
            except LockedSnapshotError:
                snap = self.get_snapshot(tab_id, d) or snap
            created.append(snap)
            prev = snap
        return created

    def insufficient(self, tab_id: str, d: date) -> DailySnapshot:
        ins = self.cfg.get("insufficient") or {}
        return DailySnapshot(snapshot_date=d, tab_id=tab_id, state=str(ins.get("state", "INSUFFICIENT_DATA")), state_label=str(ins.get("label", "Insufficient data")),
                             state_label_ko=str(ins.get("label_ko", "데이터 부족")), history_source="BACKFILLED", calculated_at=self.clock(), is_backfilled=True, is_final=True,
                             is_locked=True, finalization="backfill", summary="그날까지의 데이터로는 판정할 수 없다 — 값을 지어내지 않았다")

    # ── 예외적 수정 ───────────────────────────────────────
    def correct(self, tab_id: str, snapshot_date: date, corrected: DailySnapshot, *, reason: str, by: str) -> DailySnapshot:
        """명시적 admin correction 만 locked snapshot 을 바꾼다. original / corrected / reason / when / who 를 남긴다."""
        cur = self.get_snapshot(tab_id, snapshot_date)
        if cur is None:
            raise KeyError(f"{tab_id} {snapshot_date} 에 snapshot 이 없다")
        if not reason.strip():
            raise ValueError("correction_reason 이 비어 있다 — silent overwrite 는 허용하지 않는다")
        c = Correction(original_value=cur.model_dump(mode="json", exclude={"corrections"}), corrected_value=corrected.model_dump(mode="json", exclude={"corrections"}),
                       correction_reason=reason, corrected_at=self.clock(), corrected_by=by)
        s = corrected.model_copy(update={"tab_id": tab_id, "snapshot_date": snapshot_date, "is_locked": True, "is_final": True, "corrections": list(cur.corrections) + [c]})
        self._put(s, replace_locked=True)
        return s
