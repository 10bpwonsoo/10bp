"""Benchmark 관련 계산.

원본: ``Function_calculation_return_contribution_ver2.ipynb`` CELL 15, CELL 53.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .utils import stack_dropna

__all__ = [
    "log_returns_from_prices",
    "index_weights_from_market_cap",
    "build_sector_index_market_cap",
    "sector_total_return",
    "sector_excess_return",
]


def log_returns_from_prices(prices: pd.DataFrame) -> pd.DataFrame:
    """원본 (CELL 15)::

        rtn_kospi = np.log(1 + prc_kospi.pct_change(periods=1))
        rtn_kospi = rtn_kospi.fillna(0)
    """
    return np.log(1 + prices.pct_change(periods=1)).fillna(0)


def index_weights_from_market_cap(index_market_cap: pd.DataFrame,
                                  value_column: str = "index_market_cap",
                                  out_column: str = "weight") -> pd.DataFrame:
    """지수 시가총액 -> 일자별 비중.

    원본 (CELL 7)::

        index_weight['weight_kospi'] = index_weight.groupby('date')['index_market_cap']
                                        .apply(lambda x: x/x.sum()).sort_index()
    """
    out = index_market_cap.copy()
    out[out_column] = (
        out.groupby("date", group_keys=False)[value_column]
        .apply(lambda x: x / x.sum())
        .sort_index()
    )
    return out


def build_sector_index_market_cap(index_market_cap: pd.DataFrame,
                                  sector_field: str = "q_sector") -> pd.DataFrame:
    """섹터별 BM 지수시총 및 수익률.

    원본 (CELL 53)::

        index_market_cap['q_sector_next'] = index_market_cap[['q_sector']].unstack().shift(-1).stack()
        sector_index_market_cap = index_market_cap[['bm','q_sector']].groupby(['date','q_sector']).sum()
        sector_index_market_cap_next = index_market_cap[['bm_next','q_sector_next']]
                                        .groupby(['date','q_sector_next']).sum()
        sector_index_market_cap['bm_next'] = sector_index_market_cap_next['bm_next']
                                              .unstack().shift(1).stack()
        sector_index_market_cap['return'] = sector_index_market_cap['bm']
                                            / sector_index_market_cap['bm_next'] - 1
    """
    frame = index_market_cap.copy()
    next_field = sector_field + "_next"
    frame[next_field] = stack_dropna(frame[[sector_field]].unstack().shift(-1))

    sector_mc = frame[["bm", sector_field]].groupby(
        ["date", sector_field], group_keys=False
    ).sum()
    sector_mc_next = frame[["bm_next", next_field]].groupby(
        ["date", next_field], group_keys=False
    ).sum()
    sector_mc["bm_next"] = stack_dropna(sector_mc_next["bm_next"].unstack().shift(1))
    sector_mc["return"] = sector_mc["bm"] / sector_mc["bm_next"] - 1
    return sector_mc


def sector_total_return(sector_index_market_cap: pd.DataFrame) -> pd.DataFrame:
    """원본 (CELL 53)::

        sector_tot_ret = ((sector_index_market_cap['return']+1).unstack().cumprod()-1)
                          .iloc[-1,:].to_frame('bm')
    """
    return (
        (sector_index_market_cap["return"] + 1).unstack().cumprod() - 1
    ).iloc[-1, :].to_frame("bm")


def sector_excess_return(sector_tot_ret: pd.DataFrame,
                         temp_return_final: pd.DataFrame,
                         report_date_list) -> pd.DataFrame:
    """원본 (CELL 53)::

        sector_exc_ret = sector_tot_ret - (
            (1+temp_return_final.loc[report_date_list[1:],'bm']).cumprod().iloc[-1] - 1)
    """
    bm_cum = (
        1 + temp_return_final.loc[list(report_date_list)[1:], "bm"]
    ).cumprod().iloc[-1] - 1
    return sector_tot_ret - bm_cum
