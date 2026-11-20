"""
Point-in-time 절단 — 과거 날짜 D 의 화면을 만들 때 D cutoff(기본 07:30 KST) 에 **이미 닫혀 공개된 봉만** 남긴다.

어댑터의 as_of 절단은 봉의 타임스탬프(대개 개장 시각)만 본다. 그래서 cutoff 직전에 열린 봉(아직 진행 중이던 세션)의
'나중에 확정된 종가' 가 들어갈 수 있다. 여기서는 공급자별 '타임스탬프 → 그 봉이 끝나 공개되는 시각' 을 보수적으로 잡아,
봉이 끝난 시각이 cutoff 이하인 것만 쓴다.

    yahoo 주식·지수·ETF   타임스탬프 = 개장(미국 13:30Z · 한국/일본 00:00Z · 홍콩 01:30Z)     → +7h  (유럽 07:00Z 개장은 +9h)
    yahoo ^VIX            07:00Z 로 찍힌다 · 마감 20:15Z                                      → +14h
    yahoo 선물(=F) · DXY   04:00Z(뉴욕 0시) 로 찍힌다 · 정산 17:00 ET                          → +18h
    yahoo 환율(=X)         전날 23:00Z 에 찍힌 하루 봉                                          → +24h
    fred                  관측일 00:00Z · H.15 금리·기대인플레는 다음 영업일 오후에 공개        → 관측일 다음 평일 22:00Z
    csv · 그 밖            일 단위 수기·수집 파일                                               → +24h
    derived               구성 계열 중 가장 늦은 것

값은 지금 받은 것이다 — Yahoo 수정종가(배당 조정)·FRED 시장금리는 사후 수정이 거의 없지만 vintage 가 보장되지는 않는다(meta 에 적는다).
거시 지표(CPI·PCE·NFP 등)는 macro_fred 가 FRED realtime(그날 vintage)으로 따로 받는다.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Mapping

from ..models.market import MarketSeries

H = timedelta(hours=1)


FRED = timedelta(hours=-1)  # 표식 — 고정 지연이 아니라 '다음 평일 22:00Z' 규칙


def _next_weekday_22z(ts: datetime) -> datetime:
    d = ts.date() + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return datetime(d.year, d.month, d.day, 22, 0, tzinfo=ts.tzinfo)


def availability_lag(source: str, lags_by_id: Mapping[str, timedelta] | None = None) -> timedelta:
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
            return 18 * H
        if sym == "^VIX":
            return 14 * H
        return 7 * H  # 유럽(07:00Z 개장)은 bar_available 에서 +9h
    return 24 * H


def bar_available(ts: datetime, lag: timedelta, cutoff: datetime) -> bool:
    if lag == FRED:
        return _next_weekday_22z(ts) <= cutoff
    if lag == 7 * H and ts.hour == 7:  # 유럽 지수·주식: 07:00Z 개장 · 15:30Z 마감
        lag = 9 * H
    return ts + lag <= cutoff


def cut_series(series: Mapping[str, MarketSeries], cutoff: datetime) -> dict[str, MarketSeries]:
    """cutoff 에 이미 끝나 공개된 봉만 남긴 새 계열. 남는 봉이 없으면 그 계열은 뺀다(지금 값으로 메우지 않는다)."""
    lags: dict[str, timedelta] = {}
    for iid, s in series.items():
        src = str(getattr(s.meta, "source", "") or "")
        if not src.lower().startswith("derived:"):
            lags[iid] = availability_lag(src)
    out: dict[str, MarketSeries] = {}
    for iid, s in series.items():
        src = str(getattr(s.meta, "source", "") or "")
        lag = lags.get(iid) or availability_lag(src, lags)
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
