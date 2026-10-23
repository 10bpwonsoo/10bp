"""
메모리 가격 과거 DB → 반도체 사이클 탭 계산 입력(2026-10-23).

두 계열을 섞지 않는다:
  RAW SOURCE HISTORY   원천이 발표한 관측 그대로(관측일 · 값 · 공개 시각 · 출처 URL). 통계의 '관측 수' 는 이것만 센다.
  DAILY MARKET STATE   평일(월~금)마다 '그날까지 알려진(공개 시각 ≤ 그날 끝, ≤ as_of) 가장 최근 RAW 값'. 원천 갱신 사이는 CARRIED_FORWARD.
계약가도 같다 — 공개된 뒤부터 다음 공개 전까지 latest valid anchor. 미래 계약가를 이전 날짜에 쓰지 않는다(look-ahead 없음).
Spot Premium(t) = 그날 알려진 현물 ÷ 그날 알려진 비교 가능 계약가 − 1. Z-score · percentile 은 RAW 현물 관측일의 premium 만으로(일별 반복값을 관측으로 세지 않는다).
없는 값은 None — 다른 제품 값 · 보간 · 현재 값으로 과거를 만들지 않는다.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..config.settings import PACKAGE_ROOT

HIST = PACKAGE_ROOT / "data" / "memory_history"
SEMI = PACKAGE_ROOT / "data" / "semiconductor"
TPE = timezone(timedelta(hours=8))
#: 같은 관측일에 여러 출처가 있으면 이 순서로 하나만 쓴다(값이 다르면 conflict 로 남긴다)
SOURCE_RANK = {"dramexchange_daily_express": 0, "dramexchange_home": 1, "trendforce_weekly": 2}
FAMILY = {"NAND": "nand"}


@dataclass(frozen=True)
class Raw:
    obs: date              # 원천이 말한 관측일
    known: datetime        # 공개 시각(PIT 기준)
    v: float
    source: str
    url: str = ""
    freq: str = ""


@dataclass
class Series:
    pid: str
    raw: list[Raw] = field(default_factory=list)          # 관측일 순, 관측일당 하나
    conflicts: list[dict] = field(default_factory=list)
    sources: dict[str, int] = field(default_factory=dict)


def _dt(s: str) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _rows(p: Path) -> list[dict]:
    if not p.is_file():
        return []
    with p.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def load_spot_raw(pid: str, family: str, as_of: datetime, *, hist: Path = HIST, semi: Path = SEMI) -> Series:
    """memory_history/<family>/<pid>.csv(과거 DB) + semiconductor/spot/<pid>.csv(홈 수집기). 공개 시각 > as_of 는 버린다."""
    cand: dict[date, list[Raw]] = {}
    for r in _rows(hist / ("nand" if family == "NAND" else "dram") / f"{pid}.csv"):
        k, v = _dt(r.get("published_at", "")), r.get("price")
        try:
            obs, val = date.fromisoformat(r["date"]), float(v or "")
        except (KeyError, ValueError):
            continue
        if k is not None and k <= as_of and math.isfinite(val):
            cand.setdefault(obs, []).append(Raw(obs, k, val, r.get("source", ""), r.get("source_url", ""), r.get("frequency", "")))
    for r in _rows(semi / "spot" / f"{pid}.csv"):
        k = _dt(r.get("updated_at", ""))
        try:
            val = float(r.get("close") or "")
        except ValueError:
            continue
        if k is None or k > as_of or not math.isfinite(val):
            continue
        # 홈 표의 'Last Update' 시각 = 그 세션(대만) 날짜의 관측. legacy 행은 session_date T23:59+08
        obs = k.astimezone(TPE).date()
        cand.setdefault(obs, []).append(Raw(obs, k, val, "dramexchange_home", "https://dramexchange.com/", "daily" if family != "NAND" else "weekly"))
    s = Series(pid)
    for obs in sorted(cand):
        rs = sorted(cand[obs], key=lambda r: (SOURCE_RANK.get(r.source, 9), r.known))
        pick = rs[0]
        for o in rs[1:]:
            if abs(o.v / pick.v - 1.0) > 0.005:
                s.conflicts.append({"date": obs.isoformat(), "kept": [pick.source, pick.v], "other": [o.source, o.v]})
        # 같은 관측일의 값은 가장 이른 공개 시각부터 알려진 것으로 본다(같은 값일 때만)
        known = min((o.known for o in rs if abs(o.v / pick.v - 1.0) <= 0.005), default=pick.known)
        s.raw.append(Raw(obs, known, pick.v, pick.source, pick.url, pick.freq))
        s.sources[pick.source] = s.sources.get(pick.source, 0) + 1
    # 주간 기사의 '이번 주' 값은 기사일로 귀속돼 있다 — 직전 3일 안의 일간 RAW 와 값이 같으면 날짜 귀속 차이일 뿐 가격 충돌이 아니다
    vals = {r.obs: r.v for r in s.raw}
    s.conflicts = [c for c in s.conflicts
                   if not any(abs(vals.get(date.fromisoformat(c["date"]) - timedelta(days=k), -1.0) - c["other"][1]) < 1e-9 for k in range(1, 4))]
    return s


@dataclass(frozen=True)
class Anchor:
    period: str
    known: datetime
    v: float
    source: str
    url: str = ""
    quality: str = ""


def load_contract_raw(cid: str, as_of: datetime, *, hist: Path = HIST, semi: Path = SEMI) -> list[Anchor]:
    """memory_history/contract/<cid>.csv(월간 · 출처 링크) + semiconductor/contract/<cid>.csv(홈 표). 같은 기준월은 PRIMARY 우선."""
    by: dict[str, Anchor] = {}
    for r in _rows(hist / "contract" / f"{cid}.csv"):
        k = _dt(r.get("published_at", ""))
        try:
            v = float(r.get("price") or "")
        except ValueError:
            continue
        if k is not None and k <= as_of:
            by[r["reference_period"]] = Anchor(r["reference_period"], k, v, r.get("source", ""), r.get("source_url", ""), r.get("quality", ""))
    for r in _rows(semi / "contract" / f"{cid}.csv"):
        k = _dt(r.get("updated_at", ""))
        try:
            v = float(r.get("avg") or "")
        except ValueError:
            continue
        if k is None or k > as_of:
            continue
        per = k.astimezone(TPE).strftime("%Y-%m")
        cur = by.get(per)
        if cur is None or (cur.quality != "PRIMARY" and k <= cur.known):
            by[per] = Anchor(per, k if cur is None else min(k, cur.known), v, "dramexchange_home", "https://dramexchange.com/", "PRIMARY")
    return sorted(by.values(), key=lambda a: (a.known, a.period))


# ── Daily Market State ───────────────────────────────────
def weekdays(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def day_end(d: date) -> datetime:
    """그 날짜(원천 시간대 GMT+8)가 끝나는 시각 — 그날 공개된 원천 값이 그날 state 에 들어간다."""
    return datetime.combine(d, time(23, 59, 59), tzinfo=TPE)


def daily_state(raw: Sequence[Raw], days: Sequence[date], as_of: datetime) -> list[dict]:
    """[{d, v, origin, src, age}] — 그날 알려진 RAW 가 없으면 행을 만들지 않는다(앞쪽 빈 기간)."""
    known = sorted(raw, key=lambda r: r.known)
    out, i, latest = [], 0, None
    for d in days:
        cut = min(day_end(d), as_of)
        while i < len(known) and known[i].known <= cut:
            if latest is None or known[i].obs >= latest.obs:
                latest = known[i]
            i += 1
        if latest is None:
            continue
        out.append({"d": d.isoformat(), "v": latest.v, "origin": "RAW" if latest.obs == d else "CARRIED_FORWARD", "src": latest.obs.isoformat(),
                    "age": (d - latest.obs).days})
    return out


def anchor_state(anchors: Sequence[Anchor], days: Sequence[date], as_of: datetime) -> dict[str, Anchor]:
    out, i, cur = {}, 0, None
    for d in days:
        cut = min(day_end(d), as_of)
        while i < len(anchors) and anchors[i].known <= cut:
            if cur is None or anchors[i].period >= cur.period:
                cur = anchors[i]
            i += 1
        if cur is not None:
            out[d.isoformat()] = cur
    return out


# ── 통계 ─────────────────────────────────────────────────
def state_change(state: Sequence[Mapping], days: int, *, max_ref_age: int) -> tuple[float | None, str | None]:
    """마지막 state 대비 days 전(그 날짜 이하 마지막 state) 변화율(%). 기준 state 의 원천 관측이 max_ref_age 일보다 오래면 None."""
    if len(state) < 2:
        return None, None
    end = date.fromisoformat(state[-1]["d"]); target = end - timedelta(days=days)
    ref = next((s for s in reversed(state) if date.fromisoformat(s["d"]) <= target), None)
    if ref is None or ref["age"] > max_ref_age or not ref["v"]:
        return None, None
    # 그 사이 새 원천 관측이 없으면(같은 관측을 이어 쓴 값끼리) 변화율이 아니라 '정보 없음'
    if ref.get("src") is not None and ref.get("src") == state[-1].get("src"):
        return None, None
    return round((state[-1]["v"] / ref["v"] - 1.0) * 100.0, 2), ref["d"]


def moving_avg(state: Sequence[Mapping], n: int) -> float | None:
    if len(state) < n:
        return None
    w = [s["v"] for s in state[-n:]]
    return round(sum(w) / n, 4)


def zstats(values: Sequence[float], min_obs: int) -> dict:
    """현재값(마지막)의 1Y z-score · percentile. RAW 관측 수가 min_obs 미만이면 NOT ENOUGH HISTORY."""
    n = len(values)
    if n < min_obs:
        return {"status": "NOT ENOUGH HISTORY", "n": n, "min_obs": min_obs, "z": None, "percentile": None, "mean": None, "sd": None}
    mu = sum(values) / n; sd = (sum((x - mu) ** 2 for x in values) / (n - 1)) ** 0.5
    cur = values[-1]
    return {"status": "OK", "n": n, "min_obs": min_obs, "mean": round(mu, 2), "sd": round(sd, 2), "z": None if sd == 0 else round((cur - mu) / sd, 2),
            "percentile": round(100.0 * sum(1 for x in values if x <= cur) / n, 0)}


def window_coverage(raw: Sequence[Raw], end: date, days: int, *, max_gap: int, grace: int = 7) -> dict:
    """창 [end-days, end] 에 실제 RAW 이력이 있는가. 첫 RAW ≤ 창 시작+grace 이고 창 안의 RAW 간격이 max_gap 이하이면 GOOD."""
    start = end - timedelta(days=days)
    ds = [r.obs for r in raw if r.obs <= end]
    if not ds:
        return {"status": "UNAVAILABLE", "available_from": None, "raw": 0}
    inside = [d for d in ds if d >= start]
    prev = [d for d in ds if d < start]
    seq = ([prev[-1]] if prev else []) + inside
    gaps = [(b - a).days for a, b in zip(seq, seq[1:])]
    tail = (end - seq[-1]).days if seq else days
    ok = ds[0] <= start + timedelta(days=grace) and (max(gaps) if gaps else 0) <= max_gap and tail <= max_gap
    return {"status": "GOOD" if ok else "PARTIAL", "available_from": ds[0].isoformat(), "raw": len(inside), "max_gap": max(gaps) if gaps else None}


def months_between(a: date, b: date) -> int:
    return max(0, (b.year - a.year) * 12 + (b.month - a.month) + (1 if b.day >= a.day else 0))


def freshness(raw: Sequence[Raw], as_of: datetime, *, weekly: bool) -> dict:
    if not raw:
        return {"days_since_source": None, "state": "UNAVAILABLE"}
    age = (as_of.astimezone(timezone.utc).date() - raw[-1].obs).days
    lim = 9 if weekly else 4
    return {"days_since_source": age, "state": "FRESH" if age <= lim else "STALE" if age <= 3 * lim else "VERY STALE"}


def turning_point(state: Sequence[Mapping], *, lookback_days: int = 14, window: int = 30, max_ref_age: int = 10) -> dict:
    """1M 모멘텀의 부호가 최근 lookback 안에 바뀌었는가 — NEGATIVE→POSITIVE = 상승 전환, 반대 = 하락 전환."""
    if len(state) < 2:
        return {"spot_momentum": None}
    now, _ = state_change(state, window, max_ref_age=max_ref_age)
    end = date.fromisoformat(state[-1]["d"]); cut = end - timedelta(days=lookback_days)
    past_state = [s for s in state if date.fromisoformat(s["d"]) <= cut]
    then, _ = state_change(past_state, window, max_ref_age=max_ref_age) if past_state else (None, None)
    sig = None
    if now is not None and then is not None:
        if then < 0 <= now:
            sig = "NEGATIVE→POSITIVE"
        elif then > 0 >= now:
            sig = "POSITIVE→NEGATIVE"
    return {"spot_momentum": sig, "mom_1m_now": now, "mom_1m_before": then, "lookback_days": lookback_days}


def compact(state: Sequence[Mapping]) -> list[list[Any]]:
    """화면·저장용 — [날짜, 값, 'R'|'C', 원천 관측일]. 계산용 원본은 같은 값 그대로(축약하지 않는다)."""
    return [[s["d"], round(s["v"], 4), "R" if s["origin"] == "RAW" else "C", s["src"]] for s in state]
