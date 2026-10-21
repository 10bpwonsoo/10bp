"""
History 날짜 기준 (2026-10-21) — snapshot 날짜와 market 날짜를 분리한다.

저장소 키(DailySnapshot.snapshot_date)는 지금까지처럼 as_of 의 UTC 날짜다. 저장 데이터는 바꾸지 않고, 화면용 view 에서만 날짜를 다시 붙인다.

    market_date   = data_asof 시점에 이미 끝난 미국 정규장 날짜 (16:00 ET, 주말 제외)
    snapshot_date = market_date 다음 평일 = 그 종가를 처음 반영하는 KST 07:30 Daily Snapshot 날짜

예) 2026-10-21 07:30 KST = 2026-10-20 18:30 EDT → market_date 10/20 → snapshot_date 10/21.
    2026-10-21 16:00 KST(장중) = 10/21 03:00 EDT → market_date 10/20 → snapshot_date 10/21 (같은 날짜의 장중 값)

같은 snapshot 날짜에 저장 행이 둘 이상일 때(UTC 키로는 서로 다른 날이었다):
  · 맨 끝의 LIVE(장중, 미확정) 는 daily 에서 빼 intraday 로 따로 둔다 — daily 값을 덮지 않는다
  · 그 밖은 RECORDED > BACKFILLED(당시 기록이 없을 때만 복원한 값), 같으면 snapshot_time 에 가까운 것 하나
  · 빠진 행은 merged 에 남긴다(숨긴 것이 아니라 왜 빠졌는지 적는다)
미국 휴장일 달력은 아직 없다 — 평일이면 장이 열린 것으로 본다(archive.yaml holidays 와 같은 한계).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Generic, Sequence, TypeVar
from zoneinfo import ZoneInfo

from ..models.daily_history import MergedRow
from .versions import load_history_config

T = TypeVar("T")

PRIORITY = {"RECORDED": 0, "BACKFILLED": 1}


@dataclass(frozen=True)
class DateRule:
    snapshot_tz: ZoneInfo
    snapshot_time: time
    market_tz: ZoneInfo
    market_close: time

    @property
    def label(self) -> str:
        return f"{self.snapshot_time.strftime('%H:%M')} {'KST' if str(self.snapshot_tz) == 'Asia/Seoul' else str(self.snapshot_tz)}"


def _hm(s: str) -> time:
    hh, mm = str(s).split(":")
    return time(int(hh), int(mm))


def load_rule(config_dir=None) -> DateRule:
    c = (load_history_config(config_dir).get("date_view") or {})
    return DateRule(snapshot_tz=ZoneInfo(str(c.get("snapshot_tz", "Asia/Seoul"))), snapshot_time=_hm(c.get("snapshot_time", "07:30")),
                    market_tz=ZoneInfo(str(c.get("market_tz", "America/New_York"))), market_close=_hm(c.get("market_close", "16:00")))


def prev_weekday(d: date) -> date:
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def next_weekday(d: date) -> date:
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def market_date(asof: datetime, rule: DateRule) -> date:
    """asof 에 이미 끝난 미국 정규장의 날짜."""
    t = (asof if asof.tzinfo else asof.replace(tzinfo=timezone.utc)).astimezone(rule.market_tz)
    d = t.date()
    if d.weekday() < 5 and t.time() >= rule.market_close:
        return d
    return prev_weekday(d)


def snapshot_date_for(mkt: date) -> date:
    return next_weekday(mkt)


def cutoff_of(snap: date, rule: DateRule) -> datetime:
    return datetime.combine(snap, rule.snapshot_time, tzinfo=rule.snapshot_tz).astimezone(timezone.utc)


@dataclass(frozen=True)
class RowDate:
    storage_date: date
    snapshot_date: date
    market_date: date | None
    data_asof: datetime | None
    basis: str  # data_asof | storage_date — data_asof 가 없으면 저장 키를 market 날짜로 본다

    def merged(self, source: str, reason: str) -> MergedRow:
        return MergedRow(storage_date=self.storage_date, source=source, data_asof=self.data_asof, market_date=self.market_date, reason=reason)


def row_date(storage: date, asof: datetime | None, rule: DateRule) -> RowDate:
    if asof is None:
        return RowDate(storage_date=storage, snapshot_date=snapshot_date_for(storage) if storage.weekday() < 5 else next_weekday(storage), market_date=None, data_asof=None, basis="storage_date")
    mkt = market_date(asof, rule)
    return RowDate(storage_date=storage, snapshot_date=snapshot_date_for(mkt), market_date=mkt, data_asof=asof, basis="data_asof")


@dataclass
class Resolved(Generic[T]):
    rows: list[tuple[T, RowDate, list[MergedRow]]] = field(default_factory=list)
    intraday: tuple[T, RowDate] | None = None
    gaps: list[date] = field(default_factory=list)


def resolve(items: Sequence[T], *, storage: Callable[[T], date], source: Callable[[T], str], asof: Callable[[T], datetime | None],
            rule: DateRule) -> Resolved[T]:
    """저장 순서의 행들 → KST snapshot 날짜마다 하나 + 장중 LIVE. 값은 건드리지 않는다."""
    items = list(items)
    out: Resolved[T] = Resolved()
    if not items:
        return out
    dated = [(it, row_date(storage(it), asof(it), rule)) for it in items]
    last_it, last_rd = dated[-1]
    if source(last_it) == "LIVE":
        out.intraday = (last_it, last_rd)
        dated = dated[:-1]
    groups: dict[date, list[tuple[T, RowDate]]] = {}
    for it, rd in dated:
        groups.setdefault(rd.snapshot_date, []).append((it, rd))
    for snap in sorted(groups):
        cands = groups[snap]
        cut = cutoff_of(snap, rule)

        def rank(c: tuple[T, RowDate]) -> tuple[int, float]:
            it, rd = c
            gap = abs((rd.data_asof - cut).total_seconds()) if rd.data_asof is not None else 1e12
            return PRIORITY.get(source(it), 2), gap

        best = min(cands, key=rank)
        merged = [rd.merged(source(it), f"같은 snapshot 날짜 {snap.isoformat()} — {source(best[0])} 행을 쓴다") for it, rd in cands if it is not best[0]]
        out.rows.append((best[0], best[1], merged))
    if out.rows:
        have = {rd.snapshot_date for _, rd, _ in out.rows}
        lo = out.rows[0][1].snapshot_date
        hi = max(out.rows[-1][1].snapshot_date, out.intraday[1].snapshot_date if out.intraday else lo)
        d = lo
        while d <= hi:
            if d.weekday() < 5 and d not in have:
                out.gaps.append(d)
            d += timedelta(days=1)
    return out


def parse_dt(v: object) -> datetime | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v
    s = str(v).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def parse_d(v: object) -> date:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    return date.fromisoformat(str(v)[:10])


def trim(res: Resolved[T], days: int) -> Resolved[T]:
    """마지막 days 개 snapshot 날짜만 — gaps 도 그 창 안으로."""
    rows = res.rows[-days:] if days > 0 else res.rows
    lo = rows[0][1].snapshot_date if rows else None
    return Resolved(rows=rows, intraday=res.intraday, gaps=[g for g in res.gaps if lo is not None and g >= lo])
