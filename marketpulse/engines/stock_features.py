"""
종목 feature (Investment Intelligence, 2026-09-16 신설).

기존 FeatureEngine(compute_feature)을 그대로 쓴다 — z·백분위·1주 전·3개월·
실현변동성은 종목에도 같은 정의다. 여기서 더하는 것은 거래량 z, 시장 대비
상대 수익률과 그 z, 업종 평균 수익률이다. 수급(외국인·기관)·일중 범위는
데이터가 없어 None 이다. 0 이 아니다.
"""

from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from ..models.intelligence import StockFeature, StockMeta
from ..models.market import MarketSeries
from .features import MIN_OBSERVATIONS, change_series, compute_feature, rolling_z

ENGINE_VERSION = "0.1.0"


def _by_date(series: MarketSeries) -> pd.Series:
    vals = np.asarray(series.values, dtype=float)
    chg = change_series(vals, "price")
    idx = pd.Index([t.date() for t in series.timestamps[1:]])
    s = pd.Series(chg, index=idx)
    return s[~s.index.duplicated(keep="last")]


def volume_z(series: MarketSeries, window: int) -> tuple[float | None, float | None]:
    """로그 거래량의 레벨 z 와 20일 평균 대비 배수. 거래량이 없으면 (None, None)."""
    if not series.volumes:
        return None, None
    vols = np.asarray([v for v in series.volumes if v and v > 0], dtype=float)
    if len(vols) < MIN_OBSERVATIONS + 1:
        return None, None
    logs = np.log(vols)
    current = float(logs[-1])
    baseline = logs[-(window + 1):-1]
    if len(baseline) < MIN_OBSERVATIONS:
        return None, None
    sd = float(np.std(baseline, ddof=1))
    z = None if sd <= 0 else float(np.clip((current - float(np.mean(baseline))) / sd, -4.0, 4.0))
    ratio = float(vols[-1] / np.mean(vols[-21:-1])) if len(vols) >= 21 else None
    return z, ratio


def build_stock_features(
    stocks: Sequence[StockMeta],
    series_by_id: Mapping[str, MarketSeries],
    *,
    market_id: str = "KOSPI",
    window: int = 60,
) -> dict[str, StockFeature]:
    market = series_by_id.get(market_id)
    market_chg = _by_date(market) if market is not None else None

    out: dict[str, StockFeature] = {}
    for meta in stocks:
        s = series_by_id.get(meta.id)
        if s is None:
            continue
        ins = meta.as_instrument()
        price = compute_feature(ins, s, window=window)
        vz, vratio = volume_z(s, window)

        rel_1d = rel_z = None
        if market_chg is not None:
            own = _by_date(s)
            joined = pd.concat([own.rename("s"), market_chg.rename("m")], axis=1).dropna()
            if len(joined) >= MIN_OBSERVATIONS + 1:
                diff = (joined["s"] - joined["m"]).to_numpy()
                # 마지막 봉이 같은 날일 때만 '오늘' 의 상대 수익률이다
                if joined.index[-1] == own.index[-1]:
                    rel_1d = float((math.expm1(joined["s"].iloc[-1]) - math.expm1(joined["m"].iloc[-1])) * 100.0)
                    rel_z, _ = rolling_z(diff, window)

        out[meta.id] = StockFeature(
            stock_id=meta.id, price=price, volume_z=vz, volume_ratio_20d=vratio,
            relative_return_1d=rel_1d, relative_z=rel_z, meta=s.meta,
        )

    # 업종 평균 수익률. 같은 업종에 자기 하나뿐이면 None.
    by_sector: dict[str, list[float]] = {}
    for meta in stocks:
        f = out.get(meta.id)
        if f is not None and f.price.ret_1d is not None:
            by_sector.setdefault(meta.sector, []).append(f.price.ret_1d)
    for meta in stocks:
        f = out.get(meta.id)
        if f is None:
            continue
        rets = by_sector.get(meta.sector, [])
        if len(rets) >= 2:
            out[meta.id] = f.model_copy(update={"sector_return_1d": float(np.mean(rets))})
    return out
