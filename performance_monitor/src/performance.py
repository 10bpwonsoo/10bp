"""수익률 / scaling factor 계산.

**모든 공식은 기존 notebook 코드를 그대로 옮긴 것이다.**
각 함수 docstring 에 원본 셀 번호와 원본 표현식을 그대로 적어두었다.
공식을 바꿔야 할 일이 생기면 이 파일과 notebook 을 함께 고쳐야 한다.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

__all__ = [
    "benchmark_simple_returns",
    "cumulative_return",
    "period_total_return",
    "compute_Alog",
    "compute_alphalog",
    "compute_betalog",
    "build_scaling_factors",
    "cumulative_curve",
    "period_return_by_anchor",
    "annualized_volatility",
]


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------
def benchmark_simple_returns(log_rtn_bm: pd.DataFrame, analysis_bm: str,
                             index=None) -> pd.Series:
    """BM 로그수익률 -> 단순수익률.

    원본 (Function_calculation_return_contribution_ver2.ipynb CELL 25)::

        temp_return_final.loc[:,'bm'] = np.array(
            np.exp(log_rtn_bm.loc[temp_return_final.index, analysis_bm]) - 1)
    """
    series = log_rtn_bm[analysis_bm]
    if index is not None:
        series = series.loc[index]
    return np.exp(series) - 1


# ---------------------------------------------------------------------------
# 누적 / 기간 수익률
# ---------------------------------------------------------------------------
def cumulative_return(returns):
    """원본: ``(temp_return_final + 1).cumprod() - 1`` (CELL 39)."""
    return (returns + 1).cumprod() - 1


def period_total_return(temp_return_final: pd.DataFrame, report_date_list,
                        columns=None):
    """기간 누적수익률.

    원본 (CELL 40)::

        return_contribution_final.loc['total',:] = (
            (temp_return_final.loc[report_date_list[1:], cols] + 1).cumprod()
        ).iloc[-1,:] - 1

    ``report_date_list[0]`` 은 기준일(직전 영업일)이므로 제외한다.
    """
    cols = list(temp_return_final.columns) if columns is None else list(columns)
    window = temp_return_final.loc[list(report_date_list)[1:], cols]
    return ((window + 1).cumprod()).iloc[-1] - 1


def cumulative_curve(temp_return_final: pd.DataFrame, report_date_list,
                     columns=None) -> pd.DataFrame:
    """리포트 구간 누적수익률 곡선.

    원본 (CELL 54)::

        temp_calc_array_final = temp_return_final.loc[report_date_list,:].copy()
        temp_calc_array_final.loc[report_date_list[0],:] = 0
        temp_calc_array_final = (1 + temp_calc_array_final).cumprod() - 1
    """
    report_date_list = list(report_date_list)
    cols = list(temp_return_final.columns) if columns is None else list(columns)
    frame = temp_return_final.loc[report_date_list, cols].copy()
    frame.loc[report_date_list[0], :] = 0
    return (1 + frame).cumprod() - 1


def period_return_by_anchor(temp_return_final: pd.DataFrame, anchor_date,
                            end_date=None, columns=None):
    """앵커일(기준일) 이후 누적수익률.

    원본 (Performance_Analysis_Module CELL 28) 은 기여도 합으로 기간별 표를 만들지만,
    수익률 자체는 `period_total_return` 과 동일한 규칙(기준일 제외)을 적용한다.
    즉 ``anchor_date`` 는 직전 영업일이며 그 다음 영업일부터 누적한다.
    """
    cols = list(temp_return_final.columns) if columns is None else list(columns)
    idx = temp_return_final.index
    anchor = pd.Timestamp(anchor_date)
    if anchor.tzinfo is None and getattr(idx, "tz", None) is not None:
        anchor = anchor.tz_localize(idx.tz)
    mask = idx > anchor
    if end_date is not None:
        end = pd.Timestamp(end_date)
        if end.tzinfo is None and getattr(idx, "tz", None) is not None:
            end = end.tz_localize(idx.tz)
        mask &= idx <= end
    window = temp_return_final.loc[mask, cols]
    if len(window) == 0:
        return pd.Series(np.nan, index=cols)
    return ((window + 1).cumprod()).iloc[-1] - 1


# ---------------------------------------------------------------------------
# Scaling factor (Barra 로직 차용, CELL 40)
# ---------------------------------------------------------------------------
def compute_Alog(return_contribution_final: pd.DataFrame) -> pd.DataFrame:
    """기간 단위 scaling factor.

    원본 (CELL 40)::

        Alog_final.loc['Alog',col] = (
            return_contribution_final.loc['active',col]
            / (np.log(1+return_contribution_final.loc['total',col])
               - np.log(1+return_contribution_final.loc['bm',col]))
            if return_contribution_final.loc['active',col]!=0
            else 1+return_contribution_final.loc['bm',col])
    """
    columns = list(return_contribution_final.columns)
    Alog_final = pd.DataFrame(index=["Alog"], columns=columns)
    for col in columns:
        active = return_contribution_final.loc["active", col]
        total = return_contribution_final.loc["total", col]
        bm = return_contribution_final.loc["bm", col]
        Alog_final.loc["Alog", col] = (
            active / (np.log(1 + total) - np.log(1 + bm)) if active != 0 else 1 + bm
        )
    return Alog_final


def compute_alphalog(temp_return_final: pd.DataFrame, report_date_list,
                     columns) -> pd.DataFrame:
    """일별 scaling factor.

    원본 (CELL 40)::

        for day in alphalog_final.index[1:]:
            for col in alphalog_final.columns:
                alphalog_final.loc[day,col] = (
                    (np.log(1+temp_return_final.loc[day,col])
                     - np.log(1+temp_return_final.loc[day,'bm']))
                    / (temp_return_final.loc[day,col]-temp_return_final.loc[day,'bm'])
                    if temp_return_final.loc[day,col]!=temp_return_final.loc[day,'bm']
                    else 1/(1+temp_return_final.loc[day,'bm']))

    ``index[0]`` (기준일) 행은 NaN 으로 남는다 — 원본과 동일.
    """
    report_date_list = list(report_date_list)
    columns = list(columns)
    alphalog_final = pd.DataFrame(index=report_date_list, columns=columns)
    for day in alphalog_final.index[1:]:
        bm_r = temp_return_final.loc[day, "bm"]
        for col in columns:
            r = temp_return_final.loc[day, col]
            alphalog_final.loc[day, col] = (
                (np.log(1 + r) - np.log(1 + bm_r)) / (r - bm_r)
                if r != bm_r
                else 1 / (1 + bm_r)
            )
    return alphalog_final


def compute_betalog(alphalog_final: pd.DataFrame, Alog_final: pd.DataFrame) -> pd.DataFrame:
    """원본 (CELL 40)::

        betalog_final = pd.DataFrame(np.array(alphalog_final)*np.array(Alog_final),
                                     index=report_date_list, columns=...)
        betalog_final = betalog_final.fillna(0)
    """
    betalog_final = pd.DataFrame(
        np.array(alphalog_final) * np.array(Alog_final),
        index=alphalog_final.index,
        columns=alphalog_final.columns,
    )
    # 원본 CELL 40 의 fillna(0) 을 그대로 쓴다. object dtype 다운캐스팅에 대해
    # pandas 2.x 가 FutureWarning 을 내지만, 1.5.3 / 2.3.3 / 3.0.5 에서 결과가
    # 같음을 확인했으므로 **이 호출에 한해서만** 숨긴다.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        return betalog_final.fillna(0)


def build_scaling_factors(temp_return_final: pd.DataFrame,
                          return_contribution_final: pd.DataFrame,
                          report_date_list):
    """CELL 40 전체를 한 번에 수행. ``(Alog, alphalog, betalog)`` 반환."""
    Alog_final = compute_Alog(return_contribution_final)
    alphalog_final = compute_alphalog(
        temp_return_final, report_date_list, return_contribution_final.columns
    )
    betalog_final = compute_betalog(alphalog_final, Alog_final)
    return Alog_final, alphalog_final, betalog_final


# ---------------------------------------------------------------------------
# Optional 지표 (기존 코드에 없음 - config 로 on/off)
# ---------------------------------------------------------------------------
def annualized_volatility(returns: pd.Series, periods_per_year: int = 250) -> float:
    """연율화 변동성.

    NOTE: 기존 MP 성과분해 코드에는 없는 Optional 지표다.
    (노트북의 risk profile 셀들은 '서버 과부하로 인한 미실행' 상태)
    모델 간 비교 화면에서만 참고용으로 쓰며 화면에 Optional 로 표기한다.
    """
    series = pd.Series(returns).dropna().astype(float)
    if len(series) < 2:
        return float("nan")
    return float(series.std(ddof=1) * np.sqrt(periods_per_year))
