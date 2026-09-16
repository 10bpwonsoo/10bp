"""기간 프리셋 (일간 / 주간 / 월간 ...).

Streamlit 에 의존하지 않는다 - 노트북에서도 같은 구간 규칙을 쓰기 위해 분리했다.

기준일(시작일)은 원본 코드의 ``report_start_date`` 와 같은 의미다 -
**직전 영업일이며 그 날 수익률은 기간 성과에 포함되지 않는다.**
"""
from __future__ import annotations

import pandas as pd

__all__ = ["PERIOD_PRESETS", "resolve_preset"]

# 1D  : 종료일 직전 영업일          -> 하루 성과
# 1W  : 스냅샷의 report_start_date  -> 노트북과 동일한 주간 구간
# MTD/QTD/HTD/YTD/1Y : anchors(WORKDATE_MAST_TB 조회값)
PERIOD_PRESETS = [
    ("1D", "일간 (1D)"),
    ("1W", "주간 (1W)"),
    ("MTD", "월간 (MTD)"),
    ("QTD", "분기 (QTD)"),
    ("YTD", "연초 이후 (YTD)"),
    ("1Y", "최근 1년 (1Y)"),
    ("CUSTOM", "사용자 지정"),
]


def resolve_preset(key: str, date_options: list, end_date,
                   snapshot_report_start, anchors: dict):
    """프리셋 → (기준일, 종료일, 안내문).

    기준일은 원본 코드의 ``report_start_date`` 와 같은 의미다 —
    **직전 영업일이며 그 날 수익률은 기간 성과에 포함되지 않는다.**
    """
    dates = pd.DatetimeIndex(date_options)
    prior = [d for d in date_options if d < end_date]
    if not prior:
        return None, None, "종료일 이전 영업일이 없습니다."

    if key == "1D":
        return prior[-1], end_date, None

    if key == "1W":
        start = _nearest(dates, snapshot_report_start)
        if start is not None and start < end_date:
            return start, end_date, None
        # 스냅샷에 report_start_date 가 없으면 5영업일 전을 기준일로
        start = prior[-5] if len(prior) >= 5 else date_options[0]
        return start, end_date, "스냅샷 기준일이 없어 5영업일 전을 기준일로 잡았습니다."

    anchor = anchors.get(key)
    if anchor is None:
        return None, None, (
            f"스냅샷에 {key} 기준일이 없습니다. "
            "노트북의 WORKDATE_MAST_TB 조회 결과를 함께 export 하면 사용할 수 있습니다."
        )
    start = _nearest(dates, anchor)
    if start is None or start >= end_date:
        return None, None, f"{key} 기준일({anchor})이 스냅샷 데이터 구간을 벗어납니다."
    return start, end_date, None


def _nearest(dates: pd.DatetimeIndex, value):
    if value is None:
        return None
    target = pd.Timestamp(value)
    if target.tzinfo is None and dates.tz is not None:
        target = target.tz_localize(dates.tz)
    matches = dates[dates <= target]
    return matches[-1] if len(matches) else None
