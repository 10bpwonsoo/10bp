import pandas as pd
from shared_data import read_scores
from collections.abc import Sequence
from copy import copy

import numpy as np
from multipledispatch import dispatch
from numpy import isnan, ceil
from scipy import stats
from sklearn import linear_model
import simple_task_manager as stm
from commonutils.error import rethrow


def load_and_filter_score(score_name, do_not_hold_list, target_date):
    s = read_scores(score_name, target_date)
    s = s[~s.index.isin(do_not_hold_list)]
    s = _zscore(s)
    return s

def calc_weighted_scores(weights, do_not_hold_list, target_date):
    weighted_scores = {}
    raw_scores = {}

    for c in weights.keys():
        s = load_and_filter_score(c, do_not_hold_list, target_date)
        raw_scores[c] = s
        ws = s * weights[c]
        weighted_scores[c] = ws

    weighted_scores = pd.DataFrame(weighted_scores)
    weighted_scores = weighted_scores.fillna(0.0)

    raw_scores = pd.DataFrame(raw_scores)
    raw_scores = raw_scores.fillna(0.0)
    return weighted_scores, raw_scores

def _winsorize(row, min_percentile, max_percentile):
    """
    This implementation is based on scipy.stats.mstats.winsorize
    """
    a = row.copy()
    nan_count = isnan(row).sum()
    nonnan_count = a.size - nan_count

    nan = isnan(row)
    non_nan_a = a[~nan]

    # NOTE: argsort() sorts nans to the end of the array.
    idx = non_nan_a.argsort()

    # Set values at indices below the min percentile to the value of the entry
    # at the cutoff.
    if min_percentile > 0:
        lower_cutoff = int(min_percentile * nonnan_count)
        non_nan_a[idx[:lower_cutoff]] = non_nan_a[idx[lower_cutoff]]

    # Set values at indices above the max percentile to the value of the entry
    # at the cutoff.
    if max_percentile < 1:
        upper_cutoff = int(ceil(nonnan_count * max_percentile))
        # if max_percentile is close to 1, then upper_cutoff might not
        # remove any values.
        if upper_cutoff < nonnan_count:
            # start_of_nans = (-nan_count) if nan_count else None
            non_nan_a[idx[upper_cutoff:]] = non_nan_a[idx[upper_cutoff - 1]]

    a[~nan] = non_nan_a
    return a


def _zscore(x):
    z = stats.zscore(x)
    return pd.Series(index=x.index, data=z)


def _build_weights(scores, demeaned=True):
    if demeaned:
        scores = scores - scores.mean()

    return scores / scores.abs().sum()

### jsh 추가
def _build_restricted_weights(adj_wgt:pd.core.series.Series, bm_wgt:pd.core.series.Series, fund_wgt:pd.core.series.Series
                             , list_not_hold:list, list_not_trade:list):
    list_total = list_not_hold + list_not_trade
    temp_calc_df = pd.DataFrame(index=adj_wgt.index | fund_wgt.index | bm_wgt.index).reindex()
    temp_calc_df['bm_w'] = bm_wgt
    temp_calc_df['ac_w'] = adj_wgt
    temp_calc_df['fund_w'] = fund_wgt
    temp_calc_df = temp_calc_df.fillna(0)
    temp_calc_df['adj_w'] = temp_calc_df['ac_w'].copy()

    # do not hold 반영
    temp_calc_df.loc[temp_calc_df.index.isin(list_not_hold),'adj_w'] = - (temp_calc_df['bm_w'].copy())
    # do not trade 반영
    temp_calc_df.loc[temp_calc_df.index.isin(list_not_trade),'adj_w'] = - (temp_calc_df['bm_w'].copy() - temp_calc_df['fund_w'].copy())

    # 위에서 조정된 ac_w 이 0이 아닌 경우, ac_w < 0 경우 under를 올리고 ac_w > 0 인 경우 over를 내리는 방식으로 조정
    temp_sum_active = temp_calc_df['adj_w'].sum()
    temp_calc_df['temp_w'] = 0.0

    if temp_sum_active > 0.0:
        temp_over_active = temp_calc_df.loc[(temp_calc_df['adj_w']>0.0)&(~temp_calc_df.index.isin(list_total))]['adj_w'].sum()
        temp_calc_df.loc[(temp_calc_df['adj_w']>0.0)&(~temp_calc_df.index.isin(list_total)), 'temp_w'] = \
            - temp_calc_df.loc[(temp_calc_df['adj_w']>0.0)&(~temp_calc_df.index.isin(list_total))]['adj_w'].copy() * temp_sum_active / temp_over_active
    else:
        temp_under_active = temp_calc_df.loc[(temp_calc_df['adj_w']<0.0)&(~temp_calc_df.index.isin(list_total))]['adj_w'].sum()
        temp_calc_df.loc[(temp_calc_df['adj_w']<0.0)&(~temp_calc_df.index.isin(list_total)), 'temp_w'] = \
            - temp_calc_df.loc[(temp_calc_df['adj_w']<0.0)&(~temp_calc_df.index.isin(list_total))]['adj_w'].copy() * temp_sum_active / temp_under_active
    temp_calc_df['adj_w'] = temp_calc_df['adj_w'].copy() + temp_calc_df['temp_w'].copy()
    temp_calc_df['adj_total'] = temp_calc_df['bm_w'].copy() + temp_calc_df['adj_w'].copy()
    temp_calc_df['adj_trade'] = temp_calc_df['adj_total'].copy() - temp_calc_df['fund_w'].copy()
    temp_calc_df = temp_calc_df.drop('temp_w', axis=1)

    # check
    if temp_calc_df.loc[temp_calc_df.index.isin(list_not_hold)]['adj_total'].sum() != 0:
        display("do not hold")
        display(temp_calc_df.loc[temp_calc_df.index.isin(list_not_hold)])
        raise ValueError("Error - sum(do not hold stock weight) != 0")

    if temp_calc_df.loc[temp_calc_df.index.isin(list_not_trade)]['adj_trade'].sum() != 0:
        display("do not trade")
        display(temp_calc_df.loc[temp_calc_df.index.isin(list_not_trade)])
        raise ValueError("Error - sum(do not trade stock trade weight) != 0")

    temp_output = temp_calc_df['adj_w'].copy()
    return temp_output