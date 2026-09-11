"""
Normalization Layer — 어댑터 출력을 엔진 공통 입력으로 바꾼다.

어댑터가 무엇이든(MOCK / yfinance / FRED / CSV 리플레이) 이 지점을 지나면
모두 같은 MarketSnapshot 이 된다. 엔진은 데이터가 어디서 왔는지 모른다
(요구 15-5).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Mapping, Sequence

from ..models.common import DataMode
from ..models.market import Instrument, MarketDataPoint, MarketSeries, MarketSnapshot
from .features import compute_feature

logger = logging.getLogger(__name__)


def build_point(instrument: Instrument, series: MarketSeries) -> MarketDataPoint:
    """시계열의 마지막 두 점에서 관측치를 만든다."""
    last = series.last
    prev = series.prev

    change = change_pct = change_bp = None
    if prev is not None:
        change = last - prev
        if prev != 0:
            change_pct = change / abs(prev) * 100.0
        if instrument.unit == "percent":
            # 금리는 bp 로 말한다. 4.20% -> 4.35% 는 15bp 다.
            change_bp = change * 100.0
        elif instrument.unit == "bp":
            change_bp = change

    return MarketDataPoint(
        instrument_id=instrument.id,
        as_of=series.as_of,
        value=last,
        prev_close=prev,
        change=change,
        change_pct=change_pct,
        change_bp=change_bp,
        volume=series.volumes[-1] if series.volumes else None,
        meta=series.meta,
    )


def build_snapshot(
    instruments: Sequence[Instrument],
    series_by_id: Mapping[str, MarketSeries],
    *,
    mode: DataMode,
    as_of: datetime | None = None,
    zscore_window: int = 60,
) -> MarketSnapshot:
    """
    MarketSnapshot 을 조립한다.

    빠진 instrument 는 missing 에 남기고 넘어간다. 0 으로 채우지 않는다.
    coverage 가 떨어지면 이후 confidence 계산이 알아서 낮아진다.
    """
    points: dict[str, MarketDataPoint] = {}
    features = {}
    missing: list[str] = []

    for ins in instruments:
        series = series_by_id.get(ins.id)
        if series is None:
            missing.append(ins.id)
            continue
        try:
            points[ins.id] = build_point(ins, series)
            features[ins.id] = compute_feature(ins, series, window=zscore_window)
        except Exception:  # 한 종목 실패가 전체 스냅샷을 막으면 안 된다
            logger.exception("%s 정규화 실패. missing 으로 처리한다.", ins.id)
            points.pop(ins.id, None)
            missing.append(ins.id)

    resolved_as_of = as_of
    if resolved_as_of is None:
        resolved_as_of = (
            max(p.as_of for p in points.values()) if points else datetime.min
        )

    return MarketSnapshot(
        as_of=resolved_as_of,
        mode=mode,
        points=points,
        features=features,
        expected_instruments=[i.id for i in instruments],
        missing=missing,
    )
