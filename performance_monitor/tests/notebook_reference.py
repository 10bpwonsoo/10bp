"""Notebook 원본 코드를 **그대로 붙여넣은** 참조 구현.

이 파일은 리팩토링 대상이 아니다. 예쁘게 고치지 마라.
`src/` 의 함수들이 이 코드와 **같은 값**을 내는지 검증하기 위한 기준선이다.

출처: Function_calculation_return_contribution_ver2.ipynb CELL 40, 46~54
"""
from __future__ import annotations

import numpy as np
import pandas as pd

idx = pd.IndexSlice


def ref_scaling_factors(temp_return_final, return_contribution_final, report_date_list):
    """CELL 40 원본."""
    Alog_final = pd.DataFrame(index=['Alog'], columns=return_contribution_final.columns)
    for _, col in enumerate(Alog_final.columns):
        Alog_final.loc['Alog', col] = return_contribution_final.loc['active', col] / (
            np.log(1 + return_contribution_final.loc['total', col])
            - np.log(1 + return_contribution_final.loc['bm', col])
        ) if return_contribution_final.loc['active', col] != 0 \
            else 1 + return_contribution_final.loc['bm', col]

    alphalog_final = pd.DataFrame(index=report_date_list,
                                  columns=return_contribution_final.columns)
    for _, day in enumerate(alphalog_final.index[1:]):
        for _, col in enumerate(alphalog_final.columns):
            alphalog_final.loc[day, col] = (
                np.log(1 + temp_return_final.loc[day, col])
                - np.log(1 + temp_return_final.loc[day, 'bm'])
            ) / (temp_return_final.loc[day, col] - temp_return_final.loc[day, 'bm']) \
                if temp_return_final.loc[day, col] != temp_return_final.loc[day, 'bm'] \
                else 1 / (1 + temp_return_final.loc[day, 'bm'])

    betalog_final = pd.DataFrame(np.array(alphalog_final) * np.array(Alog_final),
                                 index=report_date_list,
                                 columns=return_contribution_final.columns)
    betalog_final = betalog_final.fillna(0)
    return Alog_final, alphalog_final, betalog_final


def ref_return_contribution_skeleton(temp_return_final, report_date_list):
    """CELL 40 원본 (앞부분)."""
    return_contribution_final = pd.DataFrame(
        index=['total', 'bm', 'active', 'market_timing', 'specific', 'risk_factor',
               'industry_factor', 'country', 'selection', 'allocation'],
        columns=[i for i in temp_return_final.columns if i != 'bm'])

    return_contribution_final.loc['total', :] = (
        (temp_return_final.loc[report_date_list[1:], return_contribution_final.columns] + 1).cumprod()
    ).iloc[-1, :] - 1
    return_contribution_final.loc['bm', :] = (
        (temp_return_final.loc[report_date_list[1:], 'bm'] + 1).cumprod()).iloc[-1] - 1
    return_contribution_final.loc['active', :] = \
        return_contribution_final.loc['total', return_contribution_final.columns] - \
        return_contribution_final.loc['bm', return_contribution_final.columns]
    return return_contribution_final


def ref_daily_contributions(final_mp, temp_return_final, rtn_bpm, benchmark_pred_beta,
                            date_list, columns, list_bpm_factor, list_bpm_sector):
    """CELL 46~51 원본."""
    list_bpm = list_bpm_factor + list_bpm_sector

    # CELL 46
    for i, day in enumerate(date_list):
        for _, col in enumerate(columns):
            final_mp.loc[(day, slice(None)), 'active_contribution_' + col] = \
                np.array(final_mp.loc[(day, slice(None)), col + '_next']) * \
                np.array(final_mp.loc[(day, slice(None)), 'forward_return_d']
                         - temp_return_final.loc[date_list[i + 1], 'bm']) \
                if i < len(date_list) - 1 else 0

    # CELL 47
    for i, day in enumerate(date_list):
        for _, col in enumerate(columns):
            final_mp.loc[(day, slice(None)), 'market_timing_contribution_' + col] = \
                np.array(final_mp.loc[(date_list[i], slice(None)), col + '_next']) * \
                np.array(final_mp.loc[(date_list[i], slice(None)), 'predictive_beta']
                         - benchmark_pred_beta.loc[date_list[i + 1]]) * \
                np.array(temp_return_final.loc[date_list[i + 1], 'bm']) \
                if i < len(date_list) - 1 else 0

    # CELL 48
    for i, day in enumerate(date_list):
        for j, factor in enumerate(list_bpm_factor):
            for _, col in enumerate(columns):
                final_mp.loc[(day, slice(None)), factor + '_contribution_' + col] = \
                    np.array(final_mp.loc[(day, slice(None)), col + '_next']) * \
                    np.array(final_mp.loc[(day, slice(None)), factor]) * \
                    np.array(rtn_bpm.loc[date_list[i + 1], factor]) \
                    if i < len(date_list) - 1 else 0

    # CELL 49
    for i, day in enumerate(date_list):
        for j, factor in enumerate(list_bpm_sector):
            for _, col in enumerate(columns):
                final_mp.loc[(day, slice(None)), factor + '_contribution_' + col] = \
                    np.array(final_mp.loc[(day, slice(None)), col + '_next']) * \
                    np.array(final_mp.loc[(day, slice(None)), factor]) * \
                    np.array(rtn_bpm.loc[date_list[i + 1], factor]) \
                    if i < len(date_list) - 1 else 0

    # CELL 50
    for i, day in enumerate(date_list):
        for _, col in enumerate(columns):
            final_mp.loc[(day, slice(None)), 'country_contribution_' + col] = \
                np.array(final_mp.loc[(day, slice(None)), col + '_next']) * \
                np.array(rtn_bpm.loc[date_list[i + 1], 'country']) \
                if i < len(date_list) - 1 else 0

    # CELL 51
    for i, day in enumerate(date_list):
        for _, col in enumerate(columns):
            final_mp.loc[(day, slice(None)), 'specific_contribution_' + col] = \
                np.array(final_mp.loc[(day, slice(None)), 'active_contribution_' + col]
                         - final_mp.loc[(day, slice(None)), 'market_timing_contribution_' + col]
                         - final_mp.loc[(day, slice(None)), 'country_contribution_' + col]
                         - final_mp.loc[(day, slice(None)),
                                        [i2 + '_contribution_' + col for i2 in list_bpm]].sum(axis=1)) \
                if i < len(date_list) + 1 else 0

    return final_mp


def ref_aggregate(final_mp, return_contribution_final, betalog_final, report_date_list,
                  list_bpm_factor, list_bpm_sector):
    """CELL 52 원본."""
    for _, col in enumerate(return_contribution_final.columns):
        return_contribution_final.loc['market_timing', col] = (
            final_mp.loc[(report_date_list, slice(None)), 'market_timing_contribution_' + col]
            .groupby('date', group_keys=False).sum() * (betalog_final.loc[:, col].shift(-1))).sum()
        return_contribution_final.loc['risk_factor', col] = (
            final_mp.loc[(report_date_list, slice(None)),
                         [i + '_contribution_' + col for i in list_bpm_factor]].sum(axis=1)
            .groupby('date', group_keys=False).sum() * (betalog_final.loc[:, col].shift(-1))).sum()
        return_contribution_final.loc['industry_factor', col] = (
            final_mp.loc[(report_date_list, slice(None)),
                         [i + '_contribution_' + col for i in list_bpm_sector]].sum(axis=1)
            .groupby('date', group_keys=False).sum() * (betalog_final.loc[:, col].shift(-1))).sum()
        return_contribution_final.loc['country', col] = (
            final_mp.loc[(report_date_list, slice(None)), 'country_contribution_' + col]
            .groupby('date', group_keys=False).sum() * (betalog_final.loc[:, col].shift(-1))).sum()
        return_contribution_final.loc['specific', col] = \
            return_contribution_final.loc['active', col] - (
                return_contribution_final.loc[
                    ['market_timing', 'risk_factor', 'industry_factor', 'country'], col].sum())
    return return_contribution_final


def ref_stock_contribution(final_mp, betalog_final, report_date_list, stock_list, columns):
    """Performance_Analysis_Module CELL 48 원본 (contribution_element='active')."""
    compare_contribution_final = pd.DataFrame(index=stock_list, columns=columns)
    for _, col in enumerate(compare_contribution_final.columns):
        compare_contribution_final.loc[stock_list, col] = (
            final_mp.loc[(report_date_list, stock_list), 'active_contribution_' + col]
            .unstack().T * np.array(betalog_final.loc[:, col].shift(-1))).sum(axis=1)
    return compare_contribution_final


def ref_bm_simple_returns(log_rtn_bm, analysis_bm, index):
    """CELL 25 원본."""
    return np.array(np.exp(log_rtn_bm.loc[index, analysis_bm]) - 1)
