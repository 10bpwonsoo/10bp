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
SOURCE_RANK = {"dramexchange_daily_express": 0, "dramexchange_home": 1, "trendforce_weekly": 2, "dramexchange_archived": 3, "trendforce_archived": 4}
#: source → 등급(A 직접 공개 · B 보존된 공개 스냅샷 · C 공공 고정가 · D 보고서·보도 인용 · E 기타). 계산은 A/B 만 RAW 로 쓴다
SOURCE_GRADE = {"dramexchange_daily_express": "A", "dramexchange_home": "A", "trendforce_weekly": "A", "dramexchange_archived": "B", "trendforce_archived": "B"}
GRADE_WEIGHT = {"A": 1.0, "B": 0.9, "C": 0.6, "D": 0.4, "E": 0.2}
FAMILY = {"NAND": "nand"}


@dataclass(frozen=True)
class Raw:
    obs: date              # 원천이 말한 관측일
    known: datetime        # 공개 시각(PIT 기준)
    v: float
    source: str
    url: str = ""
    freq: str = ""
    grade: str = "A"


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
        g = r.get("grade") or SOURCE_GRADE.get(r.get("source", ""), "E")
        if k is not None and k <= as_of and math.isfinite(val) and g in ("A", "B"):
            cand.setdefault(obs, []).append(Raw(obs, k, val, r.get("source", ""), r.get("source_url", ""), r.get("frequency", ""), g))
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
        s.raw.append(Raw(obs, known, pick.v, pick.source, pick.url, pick.freq, pick.grade))
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


def window_coverage(raw: Sequence[Raw], end: date, days: int, *, max_gap: int | None = None, grace: int = 7) -> dict:
    """창 [end-days, end] 의 실제 원천 이력 coverage — 관측 '개수' 가 아니라 기간 · 주간 밀도 · 출처 품질 · 공백으로 본다.

    score = Calendar Coverage 40% + Observation Density 30% + Source Quality 20% + Gap Severity 10%.
      calendar = 창 안에서 원천이 덮는 기간(첫 관측~끝, 창 시작 전 관측이 있으면 창 시작부터) ÷ 창 길이
      density  = 관측이 하나라도 있는 주 ÷ 창 안의 주(평일이 있는 ISO 주)
      quality  = 관측 등급 가중 평균(A 1.0 · B 0.9 · C 0.6 · D 0.4 · E 0.2)
      gap      = 최대 공백 14일 이하 1.0 → 60일 0.0
    GOOD = 덮는 기간 ≥ 창의 90%(1Y 면 330일) 그리고 관측 주 ≥ 85%. 주 비율은 낮아도 모든 달에 관측이 있으면 MONTHLY.
    max_gap 인자는 예전 호출과의 호환용(판정에는 쓰지 않는다)."""
    start = end - timedelta(days=days)
    ds = [r for r in raw if r.obs <= end]
    if not ds:
        return {"status": "UNAVAILABLE", "available_from": None, "raw": 0, "score": 0.0, "max_gap": None, "expected_weeks": 0, "observed_weeks": 0}
    inside = [r for r in ds if r.obs >= start]
    before = [r for r in ds if r.obs < start]
    cover_from = start if before else (inside[0].obs if inside else end)
    cover_days = (end - cover_from).days if inside or before else 0
    weeks = {(d.isocalendar()[0], d.isocalendar()[1]) for d in weekdays(start + timedelta(days=1), end)}
    obs_weeks = {(r.obs.isocalendar()[0], r.obs.isocalendar()[1]) for r in inside} & weeks
    seq = ([before[-1].obs] if before else []) + [r.obs for r in inside]
    gaps = [(b - a).days for a, b in zip(seq, seq[1:])] + ([(end - seq[-1]).days] if seq else [])
    mg = max(gaps) if gaps else days
    cal = min(1.0, cover_days / days); dens = len(obs_weeks) / len(weeks) if weeks else 0.0
    qual = sum(GRADE_WEIGHT.get(r.grade, 0.2) for r in inside) / len(inside) if inside else 0.0
    gap_s = 1.0 if mg <= 14 else max(0.0, 1.0 - (mg - 14) / 46)
    months = {(start + timedelta(days=k)).strftime("%Y-%m") for k in range(1, days + 1)}
    obs_months = {r.obs.strftime("%Y-%m") for r in inside}
    if cover_days >= 0.9 * days and dens >= 0.85:
        status = "GOOD"
    elif cover_days >= 0.9 * days and months <= obs_months:
        status = "MONTHLY"
    else:
        status = "PARTIAL"
    grades: dict[str, int] = {}
    for r in inside:
        grades[r.grade] = grades.get(r.grade, 0) + 1
    return {"status": status, "available_from": ds[0].obs.isoformat(), "raw": len(inside), "score": round(100 * (0.4 * cal + 0.3 * dens + 0.2 * qual + 0.1 * gap_s), 1),
            "calendar_days": cover_days, "calendar_coverage": round(cal, 3), "expected_weeks": len(weeks), "observed_weeks": len(obs_weeks),
            "density": round(dens, 3), "source_quality": round(qual, 3), "max_gap": mg, "grades": grades}


def history_quality(raw: Sequence[Raw], cov1y: Mapping, *, weekly: bool, end: date) -> dict:
    """제품의 1Y 이력 분류 — FULL(직접 공개 일간) · RECONSTRUCTED GOOD(보존 스냅샷을 조합해 복원) · PARTIAL · UNAVAILABLE.
    RECONSTRUCTED 는 가짜라는 뜻이 아니라 공개 과거 스냅샷을 조합했다는 뜻."""
    st = cov1y.get("status")
    inside = [r for r in raw if (end - r.obs).days <= 365]
    n = len(inside)
    b_share = sum(1 for r in inside if r.grade == "B") / n if n else 0.0
    sources = sorted({r.source for r in inside})
    if st == "UNAVAILABLE" or not n:
        cls, label = "UNAVAILABLE", "UNAVAILABLE"
    elif st == "GOOD":
        if b_share >= 0.25:
            cls, label = "RECONSTRUCTED GOOD", "RECONSTRUCTED · GOOD"
        elif weekly:
            cls, label = "RECONSTRUCTED GOOD" if b_share else "FULL", "WEEKLY · GOOD"
        else:
            cls, label = "FULL", "DAILY · GOOD"
    elif st == "MONTHLY":
        cls, label = "PARTIAL", "MONTHLY COVERAGE GOOD"
    else:
        cls, label = "PARTIAL", "PARTIAL"
    return {"class": cls, "label": label, "status": st, "raw_obs": n, "archived_share": round(b_share, 2), "sources": sources,
            "expected_obs": (cov1y.get("expected_weeks") if weekly else len(weekdays(end - timedelta(days=364), end))),
            "max_gap": cov1y.get("max_gap"), "calendar_coverage": cov1y.get("calendar_coverage"), "score": cov1y.get("score"),
            "observed_weeks": cov1y.get("observed_weeks"), "expected_weeks": cov1y.get("expected_weeks")}


def load_validation(pid: str, as_of: datetime, *, hist: Path = HIST) -> list[dict]:
    """검증 전용 시계열(memory_history/validation/<pid>.csv) — RAW 와 합치지 않는다. 공개 시각 ≤ as_of 만."""
    out = []
    for r in _rows(hist / "validation" / f"{pid}.csv"):
        k = _dt(r.get("published_at", ""))
        if k is None or k > as_of:
            continue
        try:
            v = float(r.get("value") or "")
        except ValueError:
            continue
        out.append({**r, "value": v})
    return out


def check_validation(rows: Sequence[Mapping], raw: Sequence[Raw]) -> list[dict]:
    """LEVEL = 같은 날(±3일) RAW 와의 차이(%) · CHANGE_PCT = 그 기간 RAW 변화 방향과 같은가. RAW 가 없으면 NO RAW."""
    by = {r.obs: r.v for r in raw}
    out = []
    for v in rows:
        res: dict[str, Any] = {k: v.get(k) for k in ("reference_period", "value", "value_type", "basis", "source", "source_type", "grade", "source_url", "note")}
        if v.get("value_type") == "LEVEL":
            d = date.fromisoformat(v["reference_period"][:10])
            near = [(abs((o - d).days), o, x) for o, x in by.items() if abs((o - d).days) <= 3]
            if near:
                _, o, x = min(near)
                diff = round((x / v["value"] - 1.0) * 100.0, 2)
                res.update({"raw_date": o.isoformat(), "raw_value": x, "diff_pct": diff, "check": "CONSISTENT" if abs(diff) <= 3.0 else "DIVERGENT"})
            else:
                res["check"] = "NO RAW"
        else:
            per = v["reference_period"][:7]
            y, m = int(per[:4]), int(per[5:7])
            first = date(y, m, 1); last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
            prev_end = first - timedelta(days=1)
            a = [x for o, x in sorted(by.items()) if o <= prev_end][-1:]
            b = [x for o, x in sorted(by.items()) if first <= o <= last][-1:]
            if a and b:
                chg = round((b[0] / a[0] - 1.0) * 100.0, 2)
                same = (chg > 0) == (v["value"] > 0) or abs(chg) < 0.5 and abs(v["value"]) < 0.5
                res.update({"raw_change_pct": chg, "check": "CONSISTENT" if same else "DIVERGENT"})
            else:
                res["check"] = "NO RAW"
        out.append(res)
    return out


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
