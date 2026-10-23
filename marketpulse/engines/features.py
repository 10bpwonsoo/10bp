"""
FeatureEngine — 원자료를 표준화된 파생 지표로 바꾼다 (설계서 STEP 5.1).

이 모듈이 하는 일이 정량 레이어 전체의 기초다. 유가는 %, 금리는 bp,
VIX 는 포인트, 수급은 십억원이다. 단위가 다른 것을 그대로 더하면 의미가
없으므로 모두 rolling z-score 로 표준화한다.

z-score 정의 (중요)
-------------------
    z = (chg[-1] - mean(chg[-W-1:-1])) / std(chg[-W-1:-1], ddof=1)

기준선에서 **현재 관측치를 제외한다.** 현재 값을 기준선에 포함시키면 충격이
클수록 자기 자신이 기준선을 부풀려 z 가 과소평가된다. 2σ 짜리 사건이
1.7σ 로 보이는 식이다. out-of-sample 표준화가 정직하다.

결측 처리
---------
관측치가 부족하면 None 을 돌려준다. 0 이 아니다. 0 은 '데이터 없음' 을
'중립' 이라는 거짓 정보로 바꾼다 (설계서 STEP 5.0 원칙 3).

모든 함수는 순수 함수다. I/O 도 전역 상태도 시계도 없다.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..models.market import Instrument, MarketFeature, MarketSeries
from ..vendor import indicators as ind

#: z 계산에 필요한 최소 관측치. 이보다 적으면 표준편차를 믿을 수 없다.
MIN_OBSERVATIONS = 20
#: clamp 범위 (설계서 STEP 5.1). 극단치가 합성 점수를 지배하는 것을 막는다.
Z_CLAMP = 4.0
#: 연율화 계수. 영업일 기준.
TRADING_DAYS = 252
#: "1주 전" 을 뜻하는 봉 수. 일봉 5개 = 한 거래주.
WEEK_BARS = 5
#: "3개월 전" 을 뜻하는 봉 수. 일봉 63개 ≈ 한 분기.
QUARTER_BARS = 63


def change_series(values: np.ndarray, series_kind: str) -> np.ndarray:
    """
    변화량 시계열. price 는 로그수익률, level 은 절대 차분.

    금리를 로그수익률로 다루면 안 된다. 4.20% -> 4.35% 는 "3.6% 상승" 이
    아니라 "15bp 상승" 이다.
    """
    if series_kind == "price":
        safe = np.where(values > 0, values, np.nan)
        return np.diff(np.log(safe))
    return np.diff(values)


def rolling_z(series: np.ndarray, window: int) -> tuple[float | None, int]:
    """
    series 의 마지막 값을 직전 window 개 대비 표준화한다.

    Returns: (z 또는 None, 기준선에 실제로 쓰인 관측치 수)
    """
    clean = series[np.isfinite(series)]
    if len(clean) < MIN_OBSERVATIONS + 1:
        return None, max(0, len(clean) - 1)

    current = float(clean[-1])
    baseline = clean[-(window + 1) : -1]
    if len(baseline) < MIN_OBSERVATIONS:
        return None, len(baseline)

    mu = float(np.mean(baseline))
    sd = float(np.std(baseline, ddof=1))
    if sd <= 0.0 or not math.isfinite(sd):
        return None, len(baseline)

    z = (current - mu) / sd
    return float(np.clip(z, -Z_CLAMP, Z_CLAMP)), len(baseline)


def rolling_z_at(series: np.ndarray, window: int, offset: int) -> tuple[float | None, int]:
    """
    offset 봉 전 시점의 z. 그때 알 수 있었던 것만 쓴다.

    "1주 전 z" 는 오늘의 기준선으로 지난주 값을 재는 것이 아니라, 지난주
    그 시점에 계산했을 z 다. 그래야 오늘 값과 같은 잣대가 된다.
    """
    if offset <= 0:
        return rolling_z(series, window)
    if len(series) <= offset:
        return None, 0
    return rolling_z(series[:-offset], window)


def rolling_sums(chg: np.ndarray, span: int) -> np.ndarray:
    """span 기간 누적 변화량 시계열. 5일/20일 수익률의 z 를 내기 위한 것."""
    if len(chg) < span:
        return np.array([])
    return np.convolve(chg, np.ones(span), mode="valid")


def _display_change(chg_value: float, instrument: Instrument) -> float:
    """
    변화량을 사람이 읽는 단위로 바꾼다.

    price  -> 퍼센트
    금리   -> bp  (unit == 'percent' 인 rate 계열)
    나머지 -> 원 단위 그대로
    """
    if instrument.series_kind == "price":
        return (math.expm1(chg_value)) * 100.0
    if instrument.unit == "percent":
        return chg_value * 100.0
    return chg_value


def percentile_rank(values: np.ndarray, lookback: int = TRADING_DAYS) -> float | None:
    """마지막 값이 최근 lookback 구간에서 몇 퍼센타일인가. 0~100."""
    value, _ = percentile_rank_detailed(values, lookback)
    return value


def percentile_rank_detailed(
    values: np.ndarray, lookback: int = TRADING_DAYS
) -> tuple[float | None, int]:
    """
    percentile_rank 와 같되 실제로 쓰인 관측치 수를 함께 돌려준다.

    "1년 백분위 98%" 가 180일짜리 히스토리로 잰 값이면 그렇게 말해야 한다.
    구간이 짧을수록 백분위는 극단으로 쏠리기 쉬우므로, 화면은 이 수를
    라벨에 적는다 (요구 15-6).
    """
    tail = values[-lookback:]
    tail = tail[np.isfinite(tail)]
    if len(tail) < MIN_OBSERVATIONS:
        return None, len(tail)
    below = float(np.sum(tail < tail[-1]))
    equal = float(np.sum(tail == tail[-1]))
    # 동률은 절반씩 나눈다 (중간 순위법).
    return float(100.0 * (below + 0.5 * equal) / len(tail)), len(tail)


def compute_feature(
    instrument: Instrument, series: MarketSeries, *, window: int = 60
) -> MarketFeature:
    """한 instrument 의 파생 지표 일괄 계산."""
    values = np.asarray(series.values, dtype=float)
    chg = change_series(values, instrument.series_kind)

    z1, obs = rolling_z(chg, window)
    z5, _ = rolling_z(rolling_sums(chg, 5), window)
    z20, _ = rolling_z(rolling_sums(chg, 20), window)
    # 1주 전 그 시점의 z. 오늘 값 옆에 흐린 표식으로 놓기 위한 것이다.
    z1_week_ago, _ = rolling_z_at(chg, window, WEEK_BARS)

    ret_1d = _display_change(float(chg[-1]), instrument) if len(chg) else None
    ret_5d = (
        _display_change(float(np.sum(chg[-5:])), instrument) if len(chg) >= 5 else None
    )
    ret_20d = (
        _display_change(float(np.sum(chg[-20:])), instrument) if len(chg) >= 20 else None
    )
    # 3개월 변화. 백분위와 짝을 이룬다 — "역사적으로 어디 있고, 최근에
    # 얼마나 움직여 거기 왔는가".
    ret_3m = (
        _display_change(float(np.sum(chg[-QUARTER_BARS:])), instrument)
        if len(chg) >= QUARTER_BARS
        else None
    )

    realized_vol = None
    if len(chg) >= 20:
        sd = float(np.std(chg[-20:], ddof=1))
        if math.isfinite(sd):
            if instrument.series_kind == "price":
                # 연율화 변동성 (%). 주식/원자재/FX 의 관례다.
                realized_vol = sd * math.sqrt(TRADING_DAYS) * 100.0
            else:
                # level 계열은 연율화하지 않는다. 1기간 변화의 표준편차를
                # ret_1d 와 같은 단위로 맞춘다 (금리는 bp).
                realized_vol = _display_change(sd, instrument)

    rsi14 = None
    if len(values) >= 15:
        rsi_series = ind.rsi(pd.Series(values), period=14)
        last = rsi_series.iloc[-1]
        if pd.notna(last):
            rsi14 = float(last)

    def ma_distance(span: int) -> float | None:
        if len(values) < span:
            return None
        ma = float(np.mean(values[-span:]))
        if not math.isfinite(ma):
            return None
        if instrument.series_kind == "price":
            return None if ma == 0 else (values[-1] / ma - 1.0) * 100.0
        return float(values[-1] - ma)

    pct, pct_obs = percentile_rank_detailed(values)

    return MarketFeature(
        instrument_id=instrument.id,
        as_of=series.as_of,
        ret_1d=ret_1d,
        ret_5d=ret_5d,
        ret_20d=ret_20d,
        ret_3m=ret_3m,
        z_1d=z1,
        z_5d=z5,
        z_20d=z20,
        z_1d_week_ago=z1_week_ago,
        zscore_window=window,
        realized_vol_20d=realized_vol,
        rsi_14=rsi14,
        ma_dist_20=ma_distance(20),
        ma_dist_60=ma_distance(60),
        percentile_1y=pct,
        percentile_observations=pct_obs,
        observations=obs,
        meta=series.meta,
    )
