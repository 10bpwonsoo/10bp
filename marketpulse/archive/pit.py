"""
Point-in-time 절단 — 과거 날짜 D 의 화면을 만들 때 D cutoff(기본 07:30 KST) 에 **이미 닫혀 공개된 봉만** 남긴다.

어댑터의 as_of 절단은 봉의 타임스탬프(대개 개장 시각)만 본다. 그래서 cutoff 직전에 열린 봉(아직 진행 중이던 세션)의
'나중에 확정된 종가' 가 들어갈 수 있다. 여기서는 공급자별 '타임스탬프 → 그 봉이 끝나 공개되는 시각' 을 보수적으로 잡아,
봉이 끝난 시각이 cutoff 이하인 것만 쓴다.

    yahoo 주식·지수·ETF   타임스탬프 = 개장(미국 13:30Z · 한국/일본 00:00Z · 홍콩 01:30Z)     → +7h  (유럽 07:00Z 개장은 +9h)
    yahoo ^VIX            07:00Z 로 찍힌다 · 마감 20:15Z                                      → +14h
    yahoo 선물(=F) · DXY   뉴욕 0시(여름 04:00Z · 겨울 05:00Z)로 찍힌다 · 마감 17:00 ET         → 그 거래일 뉴욕 17:00 (0시 봉이면 +17h)
                          2026-11-25 스냅샷부터. 그 전 스냅샷은 +18h 였다 — 겨울(05:00Z)에는 23:00Z 가 돼 07:30 KST(22:30Z) 기준에서
                          이미 끝난 봉이 빠졌고, 11/03~11/24 스냅샷의 금 · 유가 · 구리 · 천연가스 · DXY 가 하루 늦었다(저장본은 그대로 둔다).
    yahoo 환율(=X)         전날 23:00Z 에 찍힌 하루 봉                                          → +24h
    fred                  관측일 00:00Z · H.15 금리·기대인플레는 다음 영업일 오후에 공개        → 관측일 다음 평일 22:00Z
    stooq · twelvedata    날짜만 있는 일봉(00:00Z) · 미국 종목·지수는 21:00Z 마감                → +22h (한국·일본 지수 +9h · 그 밖 +24h)
    csv · 그 밖            일 단위 수기·수집 파일                                               → +24h
    derived               구성 계열 중 가장 늦은 것

값은 지금 받은 것이다 — Yahoo 수정종가(배당 조정)·FRED 시장금리는 사후 수정이 거의 없지만 vintage 가 보장되지는 않는다(meta 에 적는다).
거시 지표(CPI·PCE·NFP 등)는 macro_fred 가 FRED realtime(그날 vintage)으로 따로 받는다.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Mapping
from zoneinfo import ZoneInfo

from ..models.market import MarketSeries

H = timedelta(hours=1)


FRED = timedelta(hours=-1)  # 표식 — 고정 지연이 아니라 '다음 평일 22:00Z' 규칙
FUTURES_OLD = 18 * H  # 2026-11-24 스냅샷까지 — 찍힌 시각 + 18h
FUTURES = 17 * H  # 2026-11-25 스냅샷부터 — 표식이기도 하다: bar_available 이 '그 거래일 뉴욕 17:00' 으로 판정한다
FUTURES_CLOSE_RULE_FROM = date(2026, 11, 25)  # KST Daily Snapshot 날짜(사용자 요청 2026-11-24)
_NY = ZoneInfo("America/New_York")
_KST = timezone(timedelta(hours=9))


def _futures_lag(cutoff: datetime | None) -> timedelta:
    if cutoff is not None and cutoff.astimezone(_KST).date() < FUTURES_CLOSE_RULE_FROM:
        return FUTURES_OLD
    return FUTURES


def _futures_close(ts: datetime) -> datetime:
    """그 봉이 속한 거래일의 마감(뉴욕 17:00). 뉴욕 18시 이후에 찍힌 봉은 다음 거래일 세션이다(진행 중 봉은 수집 시각으로 찍힌다)."""
    ny = ts.astimezone(_NY)
    d = ny.date() + timedelta(days=1 if ny.hour >= 18 else 0)
    return datetime(d.year, d.month, d.day, 17, 0, tzinfo=_NY)


def _next_weekday_22z(ts: datetime) -> datetime:
    d = ts.date() + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return datetime(d.year, d.month, d.day, 22, 0, tzinfo=ts.tzinfo)


def availability_lag(source: str, lags_by_id: Mapping[str, timedelta] | None = None, *, cutoff: datetime | None = None) -> timedelta:
    s = (source or "").strip()
    low = s.lower()
    if low.startswith("derived:"):
        ids = re.findall(r"[A-Z][A-Z0-9_]+", s.split(":", 1)[1])
        known = [lags_by_id[i] for i in ids if lags_by_id and i in lags_by_id]
        if FRED in known:
            return FRED
        return max(known) if known else 24 * H
    if low.startswith("fred:"):
        return FRED
    if low.startswith("yahoo:"):
        sym = s.split(":", 1)[1].upper()
        if sym.endswith("=X"):
            return 24 * H
        if sym.endswith("=F") or sym.startswith("DX-Y"):
            return _futures_lag(cutoff)
        if sym == "^VIX":
            return 14 * H
        return 7 * H  # 유럽(07:00Z 개장)은 bar_available 에서 +9h
    if low.startswith("stooq:") or low.startswith("twelvedata:"):
        # 날짜만 있는 일봉(00:00Z 로 찍는다). 미국 종목 · 지수는 그날 21:00Z(여름 20:00Z)에 끝난다 → +22h.
        # 한국 · 일본 지수는 그날 07:00Z 전에 끝난다 → +9h. 그 밖(환율 · 달러 인덱스 등)은 하루가 다 지난 뒤(+24h).
        sym = low.split(":", 1)[1]
        if low.startswith("twelvedata:") or sym.endswith(".us") or sym in ("^spx", "^ndq", "^dji"):
            return 22 * H
        if sym in ("^kospi", "^nkx"):
            return 9 * H
        return 24 * H
    return 24 * H


def bar_available(ts: datetime, lag: timedelta, cutoff: datetime) -> bool:
    if lag == FRED:
        return _next_weekday_22z(ts) <= cutoff
    if lag == FUTURES:
        return _futures_close(ts) <= cutoff
    if lag == 7 * H and ts.hour == 7:  # 유럽 지수·주식: 07:00Z 개장 · 15:30Z 마감
        lag = 9 * H
    return ts + lag <= cutoff


def cut_series(series: Mapping[str, MarketSeries], cutoff: datetime) -> dict[str, MarketSeries]:
    """cutoff 에 이미 끝나 공개된 봉만 남긴 새 계열. 남는 봉이 없으면 그 계열은 뺀다(지금 값으로 메우지 않는다)."""
    lags: dict[str, timedelta] = {}
    for iid, s in series.items():
        src = str(getattr(s.meta, "source", "") or "")
        if not src.lower().startswith("derived:"):
            lags[iid] = availability_lag(src, cutoff=cutoff)
    out: dict[str, MarketSeries] = {}
    for iid, s in series.items():
        src = str(getattr(s.meta, "source", "") or "")
        lag = lags.get(iid) or availability_lag(src, lags, cutoff=cutoff)
        keep = [i for i, t in enumerate(s.timestamps) if bar_available(t, lag, cutoff)]
        if not keep:
            continue
        ts = [s.timestamps[i] for i in keep]
        vals = [s.values[i] for i in keep]
        vols = [s.volumes[i] for i in keep] if s.volumes and len(s.volumes) == len(s.timestamps) else None
        meta = s.meta.model_copy(update={"as_of": ts[-1]})
        out[iid] = s.model_copy(update={"timestamps": ts, "values": vals, "volumes": vols, "meta": meta})
    return out


def last_bars(series: Mapping[str, MarketSeries]) -> dict[str, str]:
    """계열별 마지막 봉 시각 — manifest 에 남겨 무엇이 들어갔는지 확인한다."""
    return {k: v.timestamps[-1].isoformat() for k, v in sorted(series.items()) if v.timestamps}
