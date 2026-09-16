"""공통 유틸리티.

pandas 버전 차이를 흡수하는 얇은 헬퍼만 둔다.
계산 로직은 여기에 두지 않는다.
"""
from __future__ import annotations

import warnings

import pandas as pd

PANDAS_MAJOR = int(pd.__version__.split(".")[0])


def stack_dropna(obj, level=-1):
    """legacy ``stack(dropna=True)`` 동작을 재현한다.

    노트북은 pandas 1.x 에서 작성되었고 ``.unstack().shift(-1).stack()`` 패턴이
    NaN 을 떨어뜨리는 것에 의존한다. pandas >= 2.1 의 ``stack`` 은 NaN 을 보존하므로
    명시적으로 제거해 준다.
    """
    # 원본 notebook 표현식을 그대로 쓰는 자리라 pandas 가 FutureWarning 을 낸다.
    # pandas 1.5.3 / 2.3.3 / 3.0.5 에서 결과가 동일함을 테스트로 확인했으므로,
    # **이 호출에 한해서만** 경고를 숨긴다. (전역 억제가 아니다)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        try:
            out = obj.stack(level, dropna=True)  # pandas < 2.1
        except (TypeError, ValueError):
            # pandas >= 2.1: dropna 인자 제거. stack 후 직접 떨어뜨린다.
            out = obj.stack(level)
            out = out.dropna(how="all") if isinstance(out, pd.DataFrame) else out.dropna()
    return out


def to_utc_ts(value):
    """문자열/날짜를 UTC tz-aware Timestamp 로. 노트북 전반의 관례와 동일."""
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def to_utc_index(values) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(pd.to_datetime(list(values), utc=True))
    return idx


def date_str(value) -> str:
    """Timestamp -> 'YYYY-MM-DD' (노트북의 ``str(date)[:10]`` 과 동일)."""
    return str(pd.Timestamp(value))[:10]


def business_days_between(index, start, end) -> list:
    """index(날짜) 중 [start, end] 구간 날짜 리스트. 노트북의 sorted(set(...)) 과 동일."""
    start_ts, end_ts = to_utc_ts(start), to_utc_ts(end)
    idx = pd.DatetimeIndex(pd.to_datetime(pd.Index(index).unique(), utc=True))
    return sorted(d for d in idx if start_ts <= d <= end_ts)


def fmt_pct(value, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "-"
    return f"{float(value) * 100:.{digits}f}%"


def fmt_bp(value, digits: int = 1) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "-"
    return f"{float(value) * 10000:.{digits}f}bp"
