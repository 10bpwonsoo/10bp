"""
CalendarEngine — 이벤트 창 판정.

    창 = [이벤트 D-window_days_before, 이벤트 D+window_days_after]

as_of 가 어느 이벤트의 창 안에 있으면 active 다. 그때 confidence 의
persistence 가중과 알림 임계에 배율이 걸린다 (scoring.yaml calendar 절).
배율은 여기서 정하고, 적용은 각 엔진이 한다 — 달력이 판정 로직을 알
필요는 없다.

순수 함수다. 달력 파일과 as_of 만 읽는다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import yaml

from ..config.settings import CONFIG_DIR
from ..models.calendar import CalendarEvent, EventWindow
from .scoring import load_scoring

ENGINE_VERSION = "0.1.0"


@lru_cache(maxsize=4)
def load_calendar(config_dir: Path | None = None) -> list[CalendarEvent]:
    d = config_dir or CONFIG_DIR
    path = d / "calendar.yaml"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        spec = yaml.safe_load(fh) or {}
    out = [CalendarEvent.model_validate(e) for e in spec.get("events", []) or []]
    out.sort(key=lambda e: (e.date, e.id))
    return out


def reset_calendar_cache() -> None:
    load_calendar.cache_clear()


def _cfg(config_dir: Path | None) -> dict:
    cfg = load_scoring(config_dir).get("calendar", {}) or {}
    return {
        "window_days_before": int(cfg.get("window_days_before", 2)),
        "window_days_after": int(cfg.get("window_days_after", 0)),
        "persistence_scale": float(cfg.get("persistence_scale", 0.5)),
        "alert_threshold_scale": float(cfg.get("alert_threshold_scale", 1.25)),
        "upcoming_days": int(cfg.get("upcoming_days", 14)),
    }


def dday(days_until: int | None) -> str:
    """D-2 / D-day / D+1. 양수는 앞으로 남은 날, 음수는 지난 날이다."""
    if days_until is None:
        return ""
    if days_until == 0:
        return "D-day"
    return f"D-{days_until}" if days_until > 0 else f"D+{-days_until}"


def _today(as_of: datetime) -> date:
    return as_of.astimezone(timezone.utc).date() if as_of.tzinfo else as_of.date()


def trading_days_between(start: datetime, end: datetime) -> int:
    """start 다음 날부터 end 까지의 평일(월~금) 수. 데이터 신선도를 '거래일' 로 세기 위한 것.

    주말만 뺀다. 각 시장의 휴장일(추석·감사절 등)은 여기서 알 수 없어 반영하지 않는다 —
    그래서 이 값은 실제 거래일 수의 **상한**이고, 화면에도 그렇게 적는다. end 가 start 보다
    앞이면 0.
    """
    d0, d1 = _today(start), _today(end)
    if d1 <= d0:
        return 0
    n = 0
    step = timedelta(days=1)
    d = d0 + step
    while d <= d1:
        if d.weekday() < 5:
            n += 1
        d += step
    return n


def event_window(as_of: datetime, *, config_dir: Path | None = None) -> EventWindow:
    cfg = _cfg(config_dir)
    today = _today(as_of)
    before, after = cfg["window_days_before"], cfg["window_days_after"]

    in_window: list[CalendarEvent] = []
    upcoming: list[CalendarEvent] = []
    for e in load_calendar(config_dir):
        days = (e.date - today).days
        stamped = e.model_copy(update={"days_until": days})
        if -after <= days <= before:
            in_window.append(stamped)
        elif before < days <= cfg["upcoming_days"]:
            upcoming.append(stamped)

    active = bool(in_window)
    p_scale = cfg["persistence_scale"] if active else 1.0
    a_scale = cfg["alert_threshold_scale"] if active else 1.0

    if active:
        heads = ", ".join(f"{e.label} {dday(e.days_until)}" for e in in_window)
        note = (
            f"이벤트 창: {heads}. 판정은 그대로 두되 지속성 가중을 ×{p_scale:.2f}, "
            f"급변 알림 임계를 ×{a_scale:.2f} 로 조정했다. 회의 결과 하나로 판정이 "
            "바뀔 수 있는 구간이다."
        )
    elif upcoming:
        nxt = upcoming[0]
        note = f"다음 이벤트: {nxt.label} {nxt.date.isoformat()} ({dday(nxt.days_until)}). 창 밖이라 조정 없음."
    else:
        note = "가까운 이벤트가 없다."

    return EventWindow(
        as_of=as_of,
        active=active,
        in_window=in_window,
        upcoming=upcoming,
        window_days_before=before,
        window_days_after=after,
        persistence_scale=p_scale,
        alert_threshold_scale=a_scale,
        note=note,
    )
