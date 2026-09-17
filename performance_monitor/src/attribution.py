"""성과 기여도(Attribution) 계산.

**모든 공식은 기존 notebook 코드를 그대로 옮긴 것이다.**
원본: ``Function_calculation_return_contribution_ver2.ipynb`` CELL 46~54,
      ``Performance_Analysis_Module_ver2_.ipynb`` CELL 48.

루프 구조(일자 × 팩터 × 모델)도 원본 그대로 유지했다.
벡터화하면 부동소수점 누적 순서가 달라져 값이 미세하게 어긋날 수 있어 의도적으로 보존한다.
이 계산은 주 1회 스냅샷 생성 시에만 수행되므로 대시보드 응답속도와 무관하다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .utils import stack_dropna

__all__ = [
    "benchmark_predictive_beta",
    "calc_active_contribution",
    "calc_market_timing_contribution",
    "calc_factor_contribution",
    "calc_country_contribution",
    "calc_specific_contribution",
    "calc_all_daily_contributions",
    "build_return_contribution_table",
    "aggregate_period_contribution",
    "calc_allocation_selection",
    "calc_sector_allocation_selection",
    "build_compare_final",
    "stock_contribution",
    "sector_contribution_timeseries",
    "period_contribution_by_anchor",
]

IDX = pd.IndexSlice


# ---------------------------------------------------------------------------
# Benchmark predictive beta (CELL 47)
# ---------------------------------------------------------------------------
def benchmark_predictive_beta(data_bpm_factor: pd.DataFrame,
                              bpm_pred_beta: pd.DataFrame,
                              analysis_bm: str) -> pd.Series:
    """원본 (CELL 47)::

        benchmark_pred_beta = data_bpm_factor[['weight_<bm>_next']].join(
            bpm_pred_beta.stack().to_frame().rename(columns={0:'predictive_beta'}))
        benchmark_pred_beta = benchmark_pred_beta.groupby('date').apply(
            lambda x: (x['weight_<bm>_next']*x['predictive_beta']).sum())
    """
    weight_col = f"weight_{analysis_bm}_next"
    frame = data_bpm_factor[[weight_col]].join(
        stack_dropna(bpm_pred_beta).to_frame().rename(columns={0: "predictive_beta"})
    )
    return frame.groupby("date", group_keys=False).apply(
        lambda x: (x[weight_col] * x["predictive_beta"]).sum()
    )


# ---------------------------------------------------------------------------
# 일별 · 종목별 기여도 (CELL 46 ~ 51)
# ---------------------------------------------------------------------------
def calc_active_contribution(final_mp: pd.DataFrame,
                             temp_return_final: pd.DataFrame,
                             date_list, columns) -> pd.DataFrame:
    """종목별 active return contribution.

    원본 (CELL 46)::

        for i,day in enumerate(date_list):
            for col in return_contribution_final.columns:
                final_mp.loc[(day,slice(None)),'active_contribution_'+col] = (
                    np.array(final_mp.loc[(day,slice(None)),col+'_next'])
                    * np.array(final_mp.loc[(day,slice(None)),'forward_return_d']
                               - temp_return_final.loc[date_list[i+1],'bm'])
                    if i<len(date_list)-1 else 0)

    계산식: (전일 active weight, next 지수 기준) × (당일 excess return)
    """
    date_list = list(date_list)
    for i, day in enumerate(date_list):
        for col in columns:
            final_mp.loc[(day, slice(None)), "active_contribution_" + col] = (
                np.array(final_mp.loc[(day, slice(None)), col + "_next"])
                * np.array(
                    final_mp.loc[(day, slice(None)), "forward_return_d"]
                    - temp_return_final.loc[date_list[i + 1], "bm"]
                )
                if i < len(date_list) - 1
                else 0
            )
    return final_mp


def calc_market_timing_contribution(final_mp: pd.DataFrame,
                                    temp_return_final: pd.DataFrame,
                                    benchmark_pred_beta: pd.Series,
                                    date_list, columns) -> pd.DataFrame:
    """원본 (CELL 47)::

        final_mp.loc[(day,slice(None)),'market_timing_contribution_'+col] = (
            np.array(final_mp.loc[(date_list[i],slice(None)),col+'_next'])
            * np.array(final_mp.loc[(date_list[i],slice(None)),'predictive_beta']
                       - benchmark_pred_beta.loc[date_list[i+1]])
            * np.array(temp_return_final.loc[date_list[i+1],'bm'])
            if i<len(date_list)-1 else 0)
    """
    date_list = list(date_list)
    for i, day in enumerate(date_list):
        for col in columns:
            final_mp.loc[(day, slice(None)), "market_timing_contribution_" + col] = (
                np.array(final_mp.loc[(date_list[i], slice(None)), col + "_next"])
                * np.array(
                    final_mp.loc[(date_list[i], slice(None)), "predictive_beta"]
                    - benchmark_pred_beta.loc[date_list[i + 1]]
                )
                * np.array(temp_return_final.loc[date_list[i + 1], "bm"])
                if i < len(date_list) - 1
                else 0
            )
    return final_mp


def calc_factor_contribution(final_mp: pd.DataFrame, rtn_bpm: pd.DataFrame,
                             date_list, factors, columns) -> pd.DataFrame:
    """risk factor / industry factor 기여도.

    원본 (CELL 48 = risk factor, CELL 49 = industry factor — 식이 동일)::

        final_mp.loc[(day,slice(None)),factor+'_contribution_'+col] = (
            np.array(final_mp.loc[(day,slice(None)),col+'_next'])
            * np.array(final_mp.loc[(day,slice(None)),factor])
            * np.array(rtn_bpm.loc[date_list[i+1],factor])
            if i<len(date_list)-1 else 0)

    계산식: (전일 active weight) × (전일 팩터 exposure) × (당일 팩터 return)
    """
    date_list = list(date_list)
    for i, day in enumerate(date_list):
        for factor in factors:
            for col in columns:
                final_mp.loc[(day, slice(None)), factor + "_contribution_" + col] = (
                    np.array(final_mp.loc[(day, slice(None)), col + "_next"])
                    * np.array(final_mp.loc[(day, slice(None)), factor])
                    * np.array(rtn_bpm.loc[date_list[i + 1], factor])
                    if i < len(date_list) - 1
                    else 0
                )
    return final_mp


def calc_country_contribution(final_mp: pd.DataFrame, rtn_bpm: pd.DataFrame,
                              date_list, columns) -> pd.DataFrame:
    """원본 (CELL 50)::

        final_mp.loc[(day,slice(None)),'country_contribution_'+col] = (
            np.array(final_mp.loc[(day,slice(None)),col+'_next'])
            * np.array(rtn_bpm.loc[date_list[i+1],'country'])
            if i<len(date_list)-1 else 0)

    country factor exposure 는 1 이므로 곱하지 않는다.
    """
    date_list = list(date_list)
    for i, day in enumerate(date_list):
        for col in columns:
            final_mp.loc[(day, slice(None)), "country_contribution_" + col] = (
                np.array(final_mp.loc[(day, slice(None)), col + "_next"])
                * np.array(rtn_bpm.loc[date_list[i + 1], "country"])
                if i < len(date_list) - 1
                else 0
            )
    return final_mp


def calc_specific_contribution(final_mp: pd.DataFrame, date_list, list_bpm,
                               columns) -> pd.DataFrame:
    """원본 (CELL 51)::

        final_mp.loc[(day,slice(None)),'specific_contribution_'+col] = (
            np.array(final_mp.loc[(day,slice(None)),'active_contribution_'+col]
                     - final_mp.loc[(day,slice(None)),'market_timing_contribution_'+col]
                     - final_mp.loc[(day,slice(None)),'country_contribution_'+col]
                     - final_mp.loc[(day,slice(None)),
                         [i+'_contribution_'+col for i in list_bpm]].sum(axis=1))
            if i<len(date_list)+1 else 0)

    NOTE: 원본의 ``i < len(date_list)+1`` 은 항상 참이다. 원본 그대로 유지한다.
    """
    date_list = list(date_list)
    for i, day in enumerate(date_list):
        for col in columns:
            final_mp.loc[(day, slice(None)), "specific_contribution_" + col] = (
                np.array(
                    final_mp.loc[(day, slice(None)), "active_contribution_" + col]
                    - final_mp.loc[(day, slice(None)), "market_timing_contribution_" + col]
                    - final_mp.loc[(day, slice(None)), "country_contribution_" + col]
                    - final_mp.loc[
                        (day, slice(None)),
                        [f + "_contribution_" + col for f in list_bpm],
                    ].sum(axis=1)
                )
                if i < len(date_list) + 1
                else 0
            )
    return final_mp


def calc_all_daily_contributions(final_mp: pd.DataFrame,
                                 temp_return_final: pd.DataFrame,
                                 rtn_bpm: pd.DataFrame,
                                 benchmark_pred_beta: pd.Series,
                                 date_list, columns,
                                 list_bpm_factor, list_bpm_sector) -> pd.DataFrame:
    """CELL 46~51 을 원본 순서대로 실행."""
    list_bpm = list(list_bpm_factor) + list(list_bpm_sector)
    final_mp = calc_active_contribution(final_mp, temp_return_final, date_list, columns)
    final_mp = calc_market_timing_contribution(
        final_mp, temp_return_final, benchmark_pred_beta, date_list, columns
    )
    final_mp = calc_factor_contribution(
        final_mp, rtn_bpm, date_list, list_bpm_factor, columns
    )
    final_mp = calc_factor_contribution(
        final_mp, rtn_bpm, date_list, list_bpm_sector, columns
    )
    final_mp = calc_country_contribution(final_mp, rtn_bpm, date_list, columns)
    final_mp = calc_specific_contribution(final_mp, date_list, list_bpm, columns)
    return final_mp


# ---------------------------------------------------------------------------
# 기간 집계 (CELL 40 골격 + CELL 52)
# ---------------------------------------------------------------------------
SUMMARY_ROWS = [
    "total", "bm", "active", "market_timing", "specific",
    "risk_factor", "industry_factor", "country", "selection", "allocation",
]


def build_return_contribution_table(temp_return_final: pd.DataFrame,
                                    report_date_list) -> pd.DataFrame:
    """total / bm / active 행만 채운 골격 생성.

    원본 (CELL 40)::

        return_contribution_final = pd.DataFrame(
            index=['total','bm','active','market_timing','specific','risk_factor',
                   'industry_factor','country','selection','allocation'],
            columns=[i for i in temp_return_final.columns if i!='bm'])
        return_contribution_final.loc['total',:] = (
            (temp_return_final.loc[report_date_list[1:], cols]+1).cumprod()).iloc[-1,:]-1
        return_contribution_final.loc['bm',:] = (
            (temp_return_final.loc[report_date_list[1:],'bm']+1).cumprod()).iloc[-1]-1
        return_contribution_final.loc['active',:] = total - bm
    """
    report_date_list = list(report_date_list)
    columns = [c for c in temp_return_final.columns if c != "bm"]
    table = pd.DataFrame(index=list(SUMMARY_ROWS), columns=columns)

    window = temp_return_final.loc[report_date_list[1:], columns]
    table.loc["total", :] = ((window + 1).cumprod()).iloc[-1, :] - 1
    table.loc["bm", :] = (
        (temp_return_final.loc[report_date_list[1:], "bm"] + 1).cumprod()
    ).iloc[-1] - 1
    table.loc["active", :] = table.loc["total", columns] - table.loc["bm", columns]
    return table


def aggregate_period_contribution(final_mp: pd.DataFrame,
                                  return_contribution_final: pd.DataFrame,
                                  betalog_final: pd.DataFrame,
                                  report_date_list,
                                  list_bpm_factor, list_bpm_sector) -> pd.DataFrame:
    """항목별 기간 기여도.

    원본 (CELL 52)::

        return_contribution_final.loc['market_timing',col] = (
            final_mp.loc[(report_date_list,slice(None)),'market_timing_contribution_'+col]
            .groupby('date').sum() * (betalog_final.loc[:,col].shift(-1))).sum()
        ... risk_factor / industry_factor / country 동일 ...
        return_contribution_final.loc['specific',col] = (
            return_contribution_final.loc['active',col]
            - return_contribution_final.loc[
                ['market_timing','risk_factor','industry_factor','country'],col].sum())
    """
    report_date_list = list(report_date_list)
    for col in return_contribution_final.columns:
        scale = betalog_final.loc[:, col].shift(-1)

        return_contribution_final.loc["market_timing", col] = (
            final_mp.loc[(report_date_list, slice(None)), "market_timing_contribution_" + col]
            .groupby("date", group_keys=False).sum() * scale
        ).sum()

        return_contribution_final.loc["risk_factor", col] = (
            final_mp.loc[
                (report_date_list, slice(None)),
                [f + "_contribution_" + col for f in list_bpm_factor],
            ].sum(axis=1).groupby("date", group_keys=False).sum() * scale
        ).sum()

        return_contribution_final.loc["industry_factor", col] = (
            final_mp.loc[
                (report_date_list, slice(None)),
                [f + "_contribution_" + col for f in list_bpm_sector],
            ].sum(axis=1).groupby("date", group_keys=False).sum() * scale
        ).sum()

        return_contribution_final.loc["country", col] = (
            final_mp.loc[(report_date_list, slice(None)), "country_contribution_" + col]
            .groupby("date", group_keys=False).sum() * scale
        ).sum()

        return_contribution_final.loc["specific", col] = (
            return_contribution_final.loc["active", col]
            - return_contribution_final.loc[
                ["market_timing", "risk_factor", "industry_factor", "country"], col
            ].sum()
        )
    return return_contribution_final


# ---------------------------------------------------------------------------
# Allocation / Selection (CELL 53)
# ---------------------------------------------------------------------------
def calc_allocation_selection(final_mp: pd.DataFrame,
                              return_contribution_final: pd.DataFrame,
                              sector_index_market_cap: pd.DataFrame,
                              temp_return_final: pd.DataFrame,
                              betalog_final: pd.DataFrame,
                              report_date_list,
                              sector_field: str = "q_sector",
                              suffix: str = "") -> pd.DataFrame:
    """전체 allocation / selection.

    원본 (CELL 53)::

        return_contribution_final.loc['allocation',col] = (
            (final_mp.loc[(report_date_list,slice(None)),[col+'_next', sector_field]]
               .groupby(['date',sector_field]).sum().unstack().xs(col+'_next',axis=1)
             * (sector_index_market_cap['return'].unstack()
                - np.array(temp_return_final.loc[report_date_list,['bm']])).shift(-1)
            ).sum(axis=1) * (betalog_final.loc[:,col].shift(-1))).sum()

        return_contribution_final.loc['selection',:] = active - allocation

    ``suffix`` 는 new_sector 기준일 때 ``'_new'`` (원본의 allocation_new/selection_new).
    """
    report_date_list = list(report_date_list)
    alloc_row = "allocation" + suffix
    select_row = "selection" + suffix

    sector_excess = (
        sector_index_market_cap["return"].unstack()
        - np.array(temp_return_final.loc[report_date_list, ["bm"]])
    ).shift(-1)

    for col in return_contribution_final.columns:
        active_w = (
            final_mp.loc[(report_date_list, slice(None)), [col + "_next", sector_field]]
            .groupby(["date", sector_field], group_keys=False).sum()
            .unstack().xs(col + "_next", axis=1)
        )
        return_contribution_final.loc[alloc_row, col] = (
            (active_w * sector_excess).sum(axis=1)
            * (betalog_final.loc[:, col].shift(-1))
        ).sum()

    return_contribution_final.loc[select_row, :] = (
        return_contribution_final.loc["active", :]
        - return_contribution_final.loc[alloc_row, :]
    )
    return return_contribution_final


def calc_sector_allocation_selection(final_mp: pd.DataFrame,
                                     data_bpm_factor_sector: pd.Series,
                                     sector_index_market_cap: pd.DataFrame,
                                     temp_return_final: pd.DataFrame,
                                     betalog_final: pd.DataFrame,
                                     report_date_list,
                                     columns,
                                     sector_index,
                                     sector_field: str = "q_sector",
                                     suffix: str = "") -> pd.DataFrame:
    """섹터별 allocation / selection.

    원본 (CELL 53)::

        sector_compare_final.loc[idx, col+'_allocation'] = (
            (active_w * sector_excess).mul(betalog_final.loc[:,col].shift(-1), axis=0)).sum()

        sector_compare_final.loc[idx, col+'_selection'] = (
            final_mp.loc[(report_date_list,slice(None)),'active_contribution_'+col].unstack()
              .mul(betalog_final.loc[:,col].shift(-1), axis=0).stack().to_frame('con')
              .join(data_bpm_factor[sector_field]).groupby(sector_field).sum()['con']
            - sector_compare_final[col+'_allocation'])
    """
    report_date_list = list(report_date_list)
    columns = list(columns)
    alloc_suffix = "_allocation" + suffix
    select_suffix = "_selection" + suffix

    result = pd.DataFrame(
        index=sector_index,
        columns=[c + alloc_suffix for c in columns] + [c + select_suffix for c in columns],
    )

    sector_excess = (
        sector_index_market_cap["return"].unstack()
        - np.array(temp_return_final.loc[report_date_list, ["bm"]])
    ).shift(-1)

    for col in columns:
        scale = betalog_final.loc[:, col].shift(-1)

        active_w = (
            final_mp.loc[(report_date_list, slice(None)), [col + "_next", sector_field]]
            .groupby(["date", sector_field], group_keys=False).sum()
            .unstack().xs(col + "_next", axis=1)
        )
        result.loc[sector_index, col + alloc_suffix] = (
            (active_w * sector_excess).mul(scale, axis=0)
        ).sum()

        scaled_stock = (
            final_mp.loc[(report_date_list, slice(None)), "active_contribution_" + col]
            .unstack().mul(scale, axis=0)
        )
        by_sector = (
            stack_dropna(scaled_stock).to_frame("con")
            .join(data_bpm_factor_sector)
            .groupby(sector_field, group_keys=False).sum()["con"]
        )
        result.loc[sector_index, col + select_suffix] = (
            by_sector - result[col + alloc_suffix]
        )
    return result


# ---------------------------------------------------------------------------
# 기여도 추이 (CELL 54)
# ---------------------------------------------------------------------------
def build_compare_final(final_mp: pd.DataFrame,
                        temp_return_final: pd.DataFrame,
                        betalog_final: pd.DataFrame,
                        report_date_list,
                        columns,
                        list_bpm_factor,
                        list_bpm_sector,
                        top_model_column: str = "RP") -> pd.DataFrame:
    """일자별 항목별 누적 기여도 추이.

    원본 (CELL 54) 을 그대로 옮긴 것이다. 요약하면::

        compare_final[d,'<item>_contribution',col]
            = cumsum(Σ_i contribution[d,i,col] * betalog[col].shift(-1)[d]).shift(1).fillna(0)
        risk_factor_contribution / industry_factor_contribution 는 팩터군 합으로 별도 계산
        active_contribution 은 누적 total - 누적 bm (cumprod 기반)
        specific_contribution = active - market_timing - country - Σ(list_bpm)
    """
    report_date_list = list(report_date_list)
    columns = list(columns)
    list_bpm = list(list_bpm_factor) + list(list_bpm_sector)

    # 원본: column_list = [i for i in final_mp.columns if '_contribution' in i
    #                      and 'active_contribution' not in i]
    #       column_list = [i.replace('_RP','') for i in column_list if '_RP' in i]
    suffix = "_" + top_model_column
    column_list = [
        c for c in final_mp.columns
        if "_contribution" in c and "active_contribution" not in c
    ]
    column_list = [c.replace(suffix, "") for c in column_list if suffix in c]

    compare_final = pd.DataFrame(
        index=pd.MultiIndex.from_product(
            [report_date_list, column_list], names=["date", "contribution"]
        ),
        columns=columns,
    )
    for col in columns:
        compare_final[col] = np.array(
            stack_dropna(
                (
                    final_mp.loc[
                        (report_date_list, slice(None)),
                        [c + "_" + col for c in column_list],
                    ].groupby("date", group_keys=False).sum()
                    * np.array(
                        pd.DataFrame(
                            np.tile(betalog_final[[col]].shift(-1), (1, len(column_list)))
                        )
                    )
                ).cumsum().shift(1).fillna(0.0)
            )
        )

    risk_cont_final = pd.DataFrame(
        index=pd.MultiIndex.from_product(
            [report_date_list, ["risk_factor_contribution"]], names=["date", "contribution"]
        ),
        columns=columns,
    )
    for col in columns:
        risk_cont_final[col] = np.array(
            (
                final_mp.loc[
                    (report_date_list, slice(None)),
                    [f + "_contribution_" + col for f in list_bpm_factor],
                ].sum(axis=1).groupby("date", group_keys=False).sum()
                * (betalog_final.loc[:, col].shift(-1))
            ).cumsum().shift(1).fillna(0.0)
        )

    industry_cont_final = pd.DataFrame(
        index=pd.MultiIndex.from_product(
            [report_date_list, ["industry_factor_contribution"]],
            names=["date", "contribution"],
        ),
        columns=columns,
    )
    for col in columns:
        industry_cont_final[col] = np.array(
            (
                final_mp.loc[
                    (report_date_list, slice(None)),
                    [f + "_contribution_" + col for f in list_bpm_sector],
                ].sum(axis=1).groupby("date", group_keys=False).sum()
                * (betalog_final.loc[:, col].shift(-1))
            ).cumsum().shift(1).fillna(0.0)
        )

    temp_calc_array_final = temp_return_final.loc[report_date_list, :].copy()
    temp_calc_array_final.loc[report_date_list[0], :] = 0
    temp_calc_array_final = (1 + temp_calc_array_final).cumprod() - 1
    active_cont_final = pd.DataFrame(
        np.array(
            temp_calc_array_final[columns]
            - np.array(
                pd.DataFrame(np.tile(temp_calc_array_final[["bm"]], (1, len(columns))))
            )
        ),
        index=pd.MultiIndex.from_product(
            [report_date_list, ["active_contribution"]], names=["date", "contribution"]
        ),
        columns=columns,
    )

    compare_final = pd.concat(
        [compare_final, risk_cont_final, industry_cont_final, active_cont_final], axis=0
    ).sort_index()

    for day in report_date_list:
        for col in columns:
            compare_final.loc[(day, "specific_contribution"), col] = (
                compare_final.loc[(day, "active_contribution"), col]
                - compare_final.loc[(day, "market_timing_contribution"), col]
                - compare_final.loc[(day, "country_contribution"), col]
                - compare_final.loc[
                    (day, [f + "_contribution" for f in list_bpm]), col
                ].sum()
            )
    return compare_final


# ---------------------------------------------------------------------------
# 종목별 기여도 (Performance_Analysis_Module CELL 48)
# ---------------------------------------------------------------------------
def stock_contribution(final_mp: pd.DataFrame, betalog_final: pd.DataFrame,
                       report_date_list, stock_list, columns,
                       element: str = "active",
                       list_bpm_factor=None, list_bpm_sector=None) -> pd.DataFrame:
    """종목별 기간 기여도.

    원본 (Performance_Analysis_Module CELL 48)::

        compare_contribution_final.loc[stock_list,col] = (
            final_mp.loc[(report_date_list,stock_list),
                         contribution_element+'_contribution_'+col]
            .unstack().T * np.array(betalog_final.loc[:,col].shift(-1))).sum(axis=1)

        # risk_factor / industry_factor 인 경우 해당 팩터군의 합을 사용
    """
    report_date_list = list(report_date_list)
    stock_list = list(stock_list)
    columns = list(columns)
    result = pd.DataFrame(index=stock_list, columns=columns)

    for col in columns:
        scale = np.array(betalog_final.loc[:, col].shift(-1))
        if element == "risk_factor":
            values = final_mp.loc[
                (report_date_list, stock_list),
                [f + "_contribution_" + col for f in list_bpm_factor],
            ].sum(axis=1).unstack().T
        elif element == "industry_factor":
            values = final_mp.loc[
                (report_date_list, stock_list),
                [f + "_contribution_" + col for f in list_bpm_sector],
            ].sum(axis=1).unstack().T
        else:
            values = final_mp.loc[
                (report_date_list, stock_list), element + "_contribution_" + col
            ].unstack().T
        result.loc[stock_list, col] = (values * scale).sum(axis=1)
    return result


def sector_contribution_timeseries(final_mp: pd.DataFrame, report_date_list,
                                   model_column: str = "RP",
                                   sector_field: str = "q_sector",
                                   element: str = "specific") -> pd.DataFrame:
    """업종별 기여도 누적 추이.

    원본 (Performance_Analysis_Module CELL 39/42)::

        tmp_dt = final_mp[['specific_contribution_RP','q_sector']]...
        tmp_dt.groupby(['date','q_sector']).sum().unstack()['specific_contribution_RP']
              .cumsum().shift(1).fillna(0)
    """
    col = f"{element}_contribution_{model_column}"
    frame = final_mp[[col, sector_field]].copy()
    frame[sector_field] = frame[sector_field].astype("str")
    frame = frame.dropna()
    frame = frame.loc[list(report_date_list)[0]:]
    grouped = frame.groupby(["date", sector_field], group_keys=False).sum().unstack()[col]
    return grouped.cumsum().shift(1).fillna(0)


def period_contribution_by_anchor(final_mp: pd.DataFrame, anchors: dict,
                                  columns) -> pd.DataFrame:
    """기간별(WTD/MTD/QTD/HTD/YTD/1Y) 모델별 active 기여도 합.

    원본 (Performance_Analysis_Module CELL 28)::

        temp_mp_return_total['WTD'] = final_mp.loc[report_start_date:][
            ['active_contribution_'+x for x in plot_data]].sum()
        ... MTD/QTD/HTD/YTD/1Y 동일 (앵커 날짜만 다름) ...

    NOTE: 원본은 betalog scaling 없이 단순 합이다. 그대로 유지한다.
    """
    columns = list(columns)
    cols = ["active_contribution_" + c for c in columns]
    out = pd.DataFrame(index=columns)
    for key, anchor in anchors.items():
        if anchor is None:
            continue
        out[key] = final_mp.loc[str(anchor)[:10]:][cols].sum().values
    return out
