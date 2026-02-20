"""
기술적 지표 모듈 (Technical Indicators)
- RSI, MACD, Bollinger Bands, SMA/EMA, Stochastic, ATR, Volume Profile
- pandas/numpy 기반, ta 라이브러리 보조
"""

import numpy as np
import pandas as pd


# ──────────────────────────────────────────────
# 이동평균 (Simple / Exponential Moving Average)
# ──────────────────────────────────────────────
def sma(series: pd.Series, period: int = 20) -> pd.Series:
    """단순 이동평균"""
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int = 20) -> pd.Series:
    """지수 이동평균"""
    return series.ewm(span=period, adjust=False).mean()


# ──────────────────────────────────────────────
# RSI (Relative Strength Index)
# ──────────────────────────────────────────────
def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    RSI 계산 (Wilder's smoothing 방식)
    Returns: 0~100 사이의 RSI 값
    """
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


# ──────────────────────────────────────────────
# MACD (Moving Average Convergence Divergence)
# ──────────────────────────────────────────────
def macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """
    MACD 계산
    Returns: DataFrame(macd, signal, histogram)
    """
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line

    return pd.DataFrame({
        "macd": macd_line,
        "signal": signal_line,
        "histogram": histogram,
    })


# ──────────────────────────────────────────────
# Bollinger Bands
# ──────────────────────────────────────────────
def bollinger_bands(
    series: pd.Series,
    period: int = 20,
    num_std: float = 2.0,
) -> pd.DataFrame:
    """
    볼린저 밴드
    Returns: DataFrame(upper, middle, lower, bandwidth, pct_b)
    """
    middle = sma(series, period)
    std = series.rolling(window=period, min_periods=period).std()
    upper = middle + num_std * std
    lower = middle - num_std * std

    bandwidth = (upper - lower) / middle
    pct_b = (series - lower) / (upper - lower)

    return pd.DataFrame({
        "upper": upper,
        "middle": middle,
        "lower": lower,
        "bandwidth": bandwidth,
        "pct_b": pct_b,
    })


# ──────────────────────────────────────────────
# Stochastic Oscillator
# ──────────────────────────────────────────────
def stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3,
    smooth_k: int = 3,
) -> pd.DataFrame:
    """
    스토캐스틱 오실레이터 (%K, %D)
    Returns: DataFrame(k, d)
    """
    lowest_low = low.rolling(window=k_period, min_periods=k_period).min()
    highest_high = high.rolling(window=k_period, min_periods=k_period).max()

    raw_k = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
    k = raw_k.rolling(window=smooth_k, min_periods=1).mean()
    d = k.rolling(window=d_period, min_periods=1).mean()

    return pd.DataFrame({"k": k, "d": d})


# ──────────────────────────────────────────────
# ATR (Average True Range)
# ──────────────────────────────────────────────
def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """
    ATR 계산 (Wilder's smoothing)
    """
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


# ──────────────────────────────────────────────
# Volume Profile (가격대별 거래량)
# ──────────────────────────────────────────────
def volume_profile(
    close: pd.Series,
    volume: pd.Series,
    bins: int = 20,
) -> pd.DataFrame:
    """
    가격대별 거래량 분포 (Volume Profile)
    Returns: DataFrame(price_low, price_high, volume, pct)
    """
    price_min, price_max = close.min(), close.max()
    edges = np.linspace(price_min, price_max, bins + 1)

    vol_by_bin = []
    for i in range(bins):
        mask = (close >= edges[i]) & (close < edges[i + 1])
        if i == bins - 1:  # 마지막 구간은 오른쪽 끝 포함
            mask = (close >= edges[i]) & (close <= edges[i + 1])
        vol_by_bin.append({
            "price_low": edges[i],
            "price_high": edges[i + 1],
            "volume": volume[mask].sum(),
        })

    df = pd.DataFrame(vol_by_bin)
    total = df["volume"].sum()
    df["pct"] = df["volume"] / total if total > 0 else 0.0
    return df


# ──────────────────────────────────────────────
# VWAP (Volume Weighted Average Price)
# ──────────────────────────────────────────────
def vwap(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
) -> pd.Series:
    """일중 VWAP"""
    typical_price = (high + low + close) / 3
    cum_tp_vol = (typical_price * volume).cumsum()
    cum_vol = volume.cumsum()
    return cum_tp_vol / cum_vol.replace(0, np.nan)


# ──────────────────────────────────────────────
# 한 번에 모든 지표를 계산하여 DataFrame 에 추가
# ──────────────────────────────────────────────
def add_all_indicators(
    df: pd.DataFrame,
    open_col: str = "open",
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
    volume_col: str = "volume",
) -> pd.DataFrame:
    """
    OHLCV DataFrame에 주요 기술적 지표를 일괄 추가합니다.
    원본 DataFrame은 변경하지 않고 복사본을 반환합니다.
    """
    df = df.copy()
    c = df[close_col]
    h = df[high_col]
    lo = df[low_col]
    v = df[volume_col]

    # 이동평균
    df["sma_5"] = sma(c, 5)
    df["sma_20"] = sma(c, 20)
    df["sma_60"] = sma(c, 60)
    df["sma_120"] = sma(c, 120)
    df["ema_12"] = ema(c, 12)
    df["ema_26"] = ema(c, 26)

    # RSI
    df["rsi_14"] = rsi(c, 14)

    # MACD
    macd_df = macd(c)
    df["macd"] = macd_df["macd"]
    df["macd_signal"] = macd_df["signal"]
    df["macd_hist"] = macd_df["histogram"]

    # Bollinger Bands
    bb = bollinger_bands(c)
    df["bb_upper"] = bb["upper"]
    df["bb_middle"] = bb["middle"]
    df["bb_lower"] = bb["lower"]
    df["bb_bandwidth"] = bb["bandwidth"]
    df["bb_pct_b"] = bb["pct_b"]

    # Stochastic
    stoch = stochastic(h, lo, c)
    df["stoch_k"] = stoch["k"]
    df["stoch_d"] = stoch["d"]

    # ATR
    df["atr_14"] = atr(h, lo, c, 14)

    # VWAP
    df["vwap"] = vwap(h, lo, c, v)

    return df
