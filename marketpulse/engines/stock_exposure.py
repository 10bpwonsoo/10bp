"""
Market → Stock Exposure (2026-09-16 신설).

두 노출을 나란히 둔다.
  통계 노출  20/60/120일 롤링 beta·상관 (correlation.py 와 같은 날짜 정렬)
  사업 노출  stock_exposures.yaml — 매출·원가·수요·금융 구조

둘의 부호가 다르면 sign_agreement=False 다. 그것은 오류가 아니라 정보다 —
원가 노출은 큰데 시장이 아직 그 변수를 이 종목에 연결하지 않았다는 뜻이다.
"""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from ..config.registry import get_intelligence_config, get_stock_exposures
from ..models.intelligence import ExposureRow, ExposureWindow, FundamentalExposure, StockExposure, StockMeta
from ..models.market import Instrument, MarketSeries
from .features import change_series

ENGINE_VERSION = "0.1.0"


def change_frame(series_by_id: Mapping[str, MarketSeries], kinds: Mapping[str, str]) -> pd.DataFrame:
    """id → 변화량(날짜 인덱스) DataFrame. 가격은 로그수익률, 레벨은 차분."""
    cols: dict[str, pd.Series] = {}
    for iid, s in series_by_id.items():
        if len(s.values) < 3:
            continue
        chg = change_series(np.asarray(s.values, dtype=float), kinds.get(iid, "price"))
        col = pd.Series(chg, index=pd.Index([t.date() for t in s.timestamps[1:]]))
        cols[iid] = col[~col.index.duplicated(keep="last")]
    return pd.DataFrame(cols).sort_index() if cols else pd.DataFrame()


def rolling_beta(frame: pd.DataFrame, stock: str, driver: str, window: int, min_obs: int) -> ExposureWindow:
    if stock not in frame.columns or driver not in frame.columns:
        return ExposureWindow(window=window)
    pair = frame[[stock, driver]].dropna().tail(window)
    n = len(pair)
    if n < min_obs:
        return ExposureWindow(window=window, observations=n)
    x = pair[driver].to_numpy(); y = pair[stock].to_numpy()
    vx = float(np.var(x, ddof=1)); vy = float(np.var(y, ddof=1))
    if vx <= 0 or vy <= 0:
        return ExposureWindow(window=window, observations=n)
    cov = float(np.cov(x, y, ddof=1)[0][1])
    return ExposureWindow(
        window=window, beta=round(cov / vx, 4), corr=round(cov / (vx ** 0.5 * vy ** 0.5), 3), observations=n,
    )


def compute_exposures(
    stocks: Sequence[StockMeta],
    series_by_id: Mapping[str, MarketSeries],
    instruments_by_id: Mapping[str, Instrument],
    *,
    labels: Mapping[str, str] | None = None,
    config_dir=None,
) -> dict[str, StockExposure]:
    cfg = get_intelligence_config(config_dir)["impact"]
    windows = [int(w) for w in cfg["windows"]]
    primary = int(cfg["primary_window"])
    min_obs = int(cfg["min_observations"])
    fundamentals = get_stock_exposures(config_dir)
    kinds = {iid: ins.series_kind for iid, ins in instruments_by_id.items()}
    frame = change_frame(series_by_id, kinds)
    names = labels or {}

    out: dict[str, StockExposure] = {}
    for meta in stocks:
        fund = fundamentals.get(meta.id, {})
        driver_ids = list(dict.fromkeys(list(meta.drivers) + list(fund.keys())))
        rows: list[ExposureRow] = []
        for d in driver_ids:
            wins = [rolling_beta(frame, meta.id, d, w, min_obs) for w in windows]
            prim = next((w for w in wins if w.window == primary), wins[0] if wins else ExposureWindow(window=primary))
            f: FundamentalExposure | None = fund.get(d)
            agree = None
            if f is not None and prim.corr is not None and abs(prim.corr) >= 0.1:
                agree = (prim.corr > 0) == (f.direction > 0)
            note = ""
            if f is not None and agree is False:
                note = "사업 노출 부호와 최근 통계 부호가 다르다 — 시장이 아직 이 변수를 이 종목에 연결하지 않았거나 다른 요인이 덮고 있다"
            elif f is None and prim.corr is not None:
                note = "통계 관계만 있고 사업 노출 정의가 없다 — 우연일 수 있다"
            elif f is not None and prim.corr is None:
                note = "사업 노출은 정의돼 있으나 통계를 잴 데이터가 없다"
            rows.append(ExposureRow(
                driver_id=d, driver_label=names.get(d, d), windows=wins,
                beta=prim.beta, corr=prim.corr, fundamental=f, sign_agreement=agree, note=note,
            ))
        out[meta.id] = StockExposure(stock_id=meta.id, rows=rows, primary_window=primary)
    return out
