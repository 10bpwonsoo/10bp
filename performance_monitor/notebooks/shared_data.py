import vrksa.research.v4 as vr
import vrksa.research.v4.datasets.kr as vdk
import numpy as np
import pandas as pd
import datetime
from multipledispatch import dispatch

def _get_kr_adj_close(start_date, end_date, date_rule=None):
    p = vr.load({'adj_close': vdk.KREquityPricing.adj_close}, start_date=start_date, end_date=end_date,
                date_rule=date_rule)['adj_close']
    p = p.unstack(level=1)
    return p


def get_kr_daily_adj_close(start_date, end_date):
    return _get_kr_adj_close(start_date, end_date)


def get_kr_monthly_adj_close(start_date, end_date, days_offset=0):
    return _get_kr_adj_close(start_date, end_date, vr.date_rule.month_end(days_offset=days_offset))


import numpy as np
import pandas as pd
from pandas.tseries.offsets import CustomBusinessDay, Day, BusinessDay


def infer_trading_calendar(factor_idx, prices_idx):
    """
    Infer the trading calendar from factor and price information.

    Parameters
    ----------
    factor_idx : pd.DatetimeIndex
        The factor datetimes for which we are computing the forward returns
    prices_idx : pd.DatetimeIndex
        The prices datetimes associated withthe factor data

    Returns
    -------
    calendar : pd.DateOffset
    """
    full_idx = factor_idx.union(prices_idx)

    traded_weekdays = []
    holidays = []

    days_of_the_week = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    for day, day_str in enumerate(days_of_the_week):

        weekday_mask = (full_idx.dayofweek == day)

        # drop days of the week that are not traded at all
        if not weekday_mask.any():
            continue
        traded_weekdays.append(day_str)

        # look for holidays
        used_weekdays = full_idx[weekday_mask].normalize()
        all_weekdays = pd.date_range(full_idx.min(), full_idx.max(),
                                     freq=CustomBusinessDay(weekmask=day_str)
                                     ).normalize()
        _holidays = all_weekdays.difference(used_weekdays)
        _holidays = [timestamp.date() for timestamp in _holidays]
        holidays.extend(_holidays)

    traded_weekdays = ' '.join(traded_weekdays)
    return CustomBusinessDay(weekmask=traded_weekdays, holidays=holidays)

@dispatch((pd.Index, list, tuple), pd.DataFrame)
def compute_forward_returns_daily(assets, prices, periods=(1, 5, 10), filter_zscore=20, cumulative_returns=True):
    # alphalens의 forward return 계산대비 차이나는 부분
    # 1. alphalens의 compute_forward_returns와 다르게 daily prices로 부터 직접 뽑으므로
    #    factor data의 freq 추론이나 delta 계산 등이 필요하지 않음.
    # 2. 위와 같은 이유로 forward return 계산시 factor dateindex로 reindex 하는 과정이 필요 없음.
    # 3. 상폐종목 수익률 처리: period로 forward fill한 담에 마지막 값 (마지막 종가) 대비로 수익률 산정.
    # (즉 마지막 종가로 청산 가정)

    prices = prices.filter(items=assets)

    raw_values_dict = {}
    column_list = []

    for period in sorted(periods):
        p = prices.copy()
        ffill_limit = period - 1 if period > 1 else None
        p = p.ffill(limit=ffill_limit)

        if cumulative_returns:
            returns = p.pct_change(period)
        else:
            returns = p.pct_change()

        forward_returns = returns.shift(-period)

        if filter_zscore is not None:
            mask = abs(
                forward_returns - forward_returns.mean()
            ) > (filter_zscore * forward_returns.std())
            forward_returns[mask] = np.nan

        label = f'{str(period)}D'
        column_list.append(label)

        raw_values_dict[label] = np.concatenate(forward_returns.values)

    df = pd.DataFrame.from_dict(raw_values_dict)
    df.set_index(
        pd.MultiIndex.from_product(
            [prices.index, prices.columns],
            names=['date', 'asset']
        ),
        inplace=True
    )

    # now set the columns correctly
    df = df[column_list]

    freq = infer_trading_calendar(prices.index, prices.index)
    try:
        df.index.levels[0].freq = freq
    except:
        pass
    df.index.set_names(['date', 'asset'])

    return df


@dispatch(pd.DataFrame)
def compute_forward_returns_daily(prices, periods=(1, 5, 10), filter_zscore=20, cumulative_returns=True):
    assets = prices.columns
    forward_returns = compute_forward_returns_daily(assets, prices,
                                                    periods=periods,
                                                    filter_zscore=filter_zscore,
                                                    cumulative_returns=cumulative_returns)

    return forward_returns


#### portfolio 관련
from collections.abc import Sequence
from copy import copy

import numpy as np
import pandas as pd
from multipledispatch import dispatch
from numpy import isnan, ceil
from scipy import stats
from sklearn import linear_model
import simple_task_manager as stm
from commonutils.error import rethrow

conn = stm.get_bquant_conn()

def read_scores(score_id, date):
    sql = f"""
        select * from portfolios.scores where date = '{date}' and score_id = '{score_id}'
        """
    
    scores = pd.read_sql(sql, conn)
    scores = scores[['asset', 'value']]
    scores = scores.set_index('asset')['value']
    return scores


import pyodbc

def get_fund_daily(fund_cd, start_date, end_date):
    
    str_stdt = start_date.replace('-', '')
    str_eddt = end_date.replace('-', '')
    
    conn_str = "Driver={Tibero6};Server=172.31.3.62;Port=8629;UID=uquant;Database=PBIDB;Password=uquant1"
    conn2 = pyodbc.connect(conn_str)
    conn2.setdecoding(pyodbc.SQL_CHAR, encoding='euckr')
#     conn2.setdecoding(pyodbc.SQL_WCHAR, encoding='utf-8')
#     conn2.setdecoding(pyodbc.SQL_WMETADATA, encoding='utf-32le')
    conn2.setencoding(encoding='utf-8')

    
    sql = f"""
    SELECT  TO_DATE(A.TRD_DT, 'YYYY-MM-DD') AS "dt"
              ,  B.SUP_AMT
              ,  B.SUP_BCC
              ,  B.NAV_TOT_AMT               AS "NAV"
              ,  NVL(C.TDT_SUP_AMT,0)        AS "Inflow"
              ,  NVL(C.TDT_CCC_AMT,0)        AS "Outflow"
              ,  NVL(D.equity,0)               AS "EQ"
              ,  NVL(D.index_futures,0)           AS "K200F"
              ,  NVL(D.equity_futures,0)           AS "EQF"
              ,  NVL(D.dividend_receivable,0) dividend_receivable

           FROM  HWBI.FNS_UD A
                 LEFT JOIN  HWBI.TCFM_FND_DLY_SAF_SFS B -- 펀드NAV
                        ON  A.TRD_DT     =  B.BSE_DT
                        AND B.IST_CD     =  '100'
                        AND B.DEL_YN     = 'N'

                 LEFT JOIN
                 (
                    SELECT BSE_DT
                         , AMCO_CD
                         , FND_CD
                         , SUM(TDT_SUP_AMT) TDT_SUP_AMT
                         , SUM(TDT_CCC_AMT) TDT_CCC_AMT
                    FROM   HWBI.TCFM_FND_SUP_CCC_SAF_SFS
                    WHERE  IST_CD = '100'
                    AND    DEL_YN = 'N'
                    GROUP BY BSE_DT, AMCO_CD, FND_CD                               
                 ) C -- 펀드설정환매
                 ON   B.BSE_DT     =  C.BSE_DT  
                 AND  B.AMCO_CD    =  C.AMCO_CD 
                 AND  B.FND_CD     =  C.FND_CD

                 LEFT JOIN (SELECT  A.BSE_DT
                                 ,  A.FND_CD 
                                 ,  NVL(SUM(CASE WHEN A.INTG_AST_TC='J' THEN A.MRPR_EVL_AMT END),0)  equity
                                 ,  NVL(SUM(CASE WHEN A.INTG_AST_TC ='P' AND B.INTG_AST_DTL_TC ='1' AND A.INTG_PT_TC='1' THEN A.MRPR_EVL_AMT END),0)
                                   -NVL(SUM(CASE WHEN A.INTG_AST_TC ='P' AND B.INTG_AST_DTL_TC ='1' AND A.INTG_PT_TC='2' THEN A.MRPR_EVL_AMT END),0) index_futures
                                 ,  NVL(SUM(CASE WHEN A.INTG_AST_TC ='P' AND B.INTG_AST_DTL_TC ='G' AND A.INTG_PT_TC='1' THEN A.MRPR_EVL_AMT END),0)
                                   -NVL(SUM(CASE WHEN A.INTG_AST_TC ='P' AND B.INTG_AST_DTL_TC ='G' AND A.INTG_PT_TC='2' THEN A.MRPR_EVL_AMT END),0) equity_futures
                                 ,  NVL(SUM(CASE WHEN A.INTG_AST_TC='Z' AND A.STN_ITM_CD = 'ACCT11000' THEN A.MRPR_EVL_AMT END),0)         dividend_receivable
                              FROM  HWBI.TWIA_PERD_INTG_AST_HLD_SAF A
                                    INNER JOIN HWBI.TWIA_PERD_INTG_AST_ITM_SAF B
                                            ON A.IST_CD        = B.IST_CD
                                           AND A.BSE_DT        = B.BSE_DT
                                           AND A.STN_ITM_CD    = B.STN_ITM_CD
                                           AND A.INTG_AST_TC   = B.INTG_AST_TC
                                           AND B.DEL_YN        = 'N'
                            WHERE  A.IST_CD         =  '100'
                            AND    A.FND_CD         =  '{fund_cd}'
                            AND    A.DEL_YN         =  'N'
                            GROUP BY A.BSE_DT, A.FND_CD
                         )  D
                        ON  B.BSE_DT     =  D.BSE_DT
                       AND  B.FND_CD     =  D.FND_CD

          WHERE  A.TRD_DT          BETWEEN  '{str_stdt}'
                                   AND  '{str_eddt}'
            AND  A.U_CD              =  'I.001'
            AND  B.AMCO_CD           =  'B7700' 
            AND  B.FND_CD            =  '{fund_cd}' 

          ORDER BY A.TRD_DT
    
    """
    
    data = pd.read_sql(sql, conn2)
    data.columns = ['date', 'sup_amt', 'sup_bcc', 'nav', 'inflow', 'outflow', 'eq', 'k200f', 'eqf', 'dividend_receivable']
    return data


from sqlalchemy import create_engine

def save_target_weights(pid, trade_date, weights):
    weights.name = 'weight'
    weights.index.name = 'asset'
    engine = create_engine('mssql+pymssql://performer:newquant@172.32.1.100')
    conn = engine.connect()
    ## BQUANT_BAK 추가
    # engine_bak = create_engine('mssql+pymssql://performer:newquant@172.32.1.100/BQUANT_BAK')
    # conn_bak = engine_bak.connect()

    delete_sql = f"delete from portfolios.simple_rebalancing_target_weights where portfolio_id = '{pid}' and date='{trade_date}'"
    conn.execute(delete_sql)
    ## BQUANT_BAK 추가
    # conn_bak.execute(delete_sql)

    data_to_insert = weights.to_frame()
    data_to_insert['portfolio_id'] = pid
    data_to_insert['date'] = trade_date
    data_to_insert = data_to_insert.rename(columns={'w_adj': 'weight'})
    data_to_insert.to_sql('simple_rebalancing_target_weights', conn, schema='portfolios', if_exists='append')
    ## BQUANT_BAK 추가
    # data_to_insert.to_sql('simple_rebalancing_target_weights', conn_bak, schema='portfolios', if_exists='append')

    
### 202303 수정
def load_target_weights(pid, target_date = 'all'):
    engine = create_engine('mssql+pymssql://performer:newquant@172.32.1.100')
    conn = engine.connect()

    if target_date == 'all':
        qry = f"select * from portfolios.simple_rebalancing_target_weights where portfolio_id = '{pid}'"
    else:
        qry = f"select * from portfolios.simple_rebalancing_target_weights where portfolio_id = '{pid}' and date='{target_date}'"
    
    result = conn.execute(qry)
    df = pd.DataFrame(result.fetchall())

    if df.empty:
        pass
    else:
        df.columns = result.keys()
        df = df[['date', 'asset', 'weight']]
        df['date'] = pd.to_datetime(df['date'], utc=True)
        df = df.rename(columns={'asset':'item'}).set_index(['date','item'])
        
    return df

def load_bm_weights(bm_nm, target_date = 'all'):
    engine = create_engine('mssql+pymssql://performer:newquant@172.32.1.100')
    conn = engine.connect()

    if target_date == 'all':
        qry = f"select * from BQUANT.portfolios.benchmark_weights where benchmark = '{bm_nm}'"
    else:
        qry = f"select * from BQUANT.portfolios.benchmark_weights where benchmark = '{bm_nm}' and date='{target_date}'"
    
    result = conn.execute(qry)
    df = pd.DataFrame(result.fetchall())

    if df.empty:
        pass
    else:
        df.columns = result.keys()
        df = df[['date', 'asset', 'weight']]
        df['date'] = pd.to_datetime(df['date'], utc=True)
        df = df.rename(columns={'asset':'item'}).set_index(['date','item'])
        
    return df

def save_bm_weights(bm_nm, target_date, weights:pd.Series):
       
    weights.name = 'weight'
    weights.index.name = 'asset'
    engine = create_engine('mssql+pymssql://performer:newquant@172.32.1.100')
    conn = engine.connect()
    ## BQUANT_BAK추가
    # engine_bak = create_engine('mssql+pymssql://performer:newquant@172.32.1.100/BQUANT_BAK')
    # conn_bak = engine_bak.connect()

#     delete_sql = f"delete from BQUANT.portfolios.benchmark_weights where benchmark = '{bm_nm}' and date='{target_date.strftime('%Y-%m-%d')}'"
    delete_sql = f"delete from BQUANT.portfolios.benchmark_weights where benchmark = '{bm_nm}' and date='{target_date}'"
    conn.execute(delete_sql)
    ## BQUANT_BAK추가
    # conn_bak.execute(delete_sql)

    data_to_insert = weights.to_frame()
    data_to_insert['benchmark'] = bm_nm
    data_to_insert['date'] = target_date
    data_to_insert = data_to_insert.rename(columns={'w_adj': 'weight'})
    data_to_insert.to_sql('benchmark_weights', conn, schema='portfolios', if_exists='append')
    ## BQUANT_BAK추가
    # data_to_insert.to_sql('benchmark_weights', conn_bak, schema='portfolios', if_exists='append')

    return None

def load_port_trades(pid, target_date = 'all'):
    engine = create_engine('mssql+pymssql://performer:newquant@172.32.1.100')
    conn = engine.connect()

    if target_date == 'all':
        qry = f"SELECT [date], asset, trade from BQUANT.portfolios.portfolio_trades where portfolio_id = '{pid}'"
    else:
        qry = f"SELECT [date], asset, trade from BQUANT.portfolios.portfolio_trades where portfolio_id = '{pid}' and date='{target_date}'"
    
    result = conn.execute(qry)
    df = pd.DataFrame(result.fetchall())

    if df.empty:
        pass
    else:
        df.columns = result.keys()
        df = df[['date', 'asset', 'trade']]
        df['date'] = pd.to_datetime(df['date'], utc=True)
        df = df.rename(columns={'asset':'item'})
        
    return df

def load_port_returns(pid, target_date = 'all'):
    engine = create_engine('mssql+pymssql://performer:newquant@172.32.1.100')
    conn = engine.connect()

    if target_date == 'all':
        qry = f"SELECT [date], [returns] from BQUANT.portfolios.portfolio_returns where portfolio_id = '{pid}'"
    else:
        qry = f"SELECT [date], [returns] from BQUANT.portfolios.portfolio_returns where portfolio_id = '{pid}' and date='{target_date}'"
    
    result = conn.execute(qry)
    df = pd.DataFrame(result.fetchall())

    if df.empty:
        pass
    else:
        df.columns = result.keys()
        df = df[['date', 'returns']]
        df['date'] = pd.to_datetime(df['date'], utc=True)
        df = df.rename(columns={'returns':pid})
        
    return df

def load_port_weights(pid, target_date = 'all'):
    engine = create_engine('mssql+pymssql://performer:newquant@172.32.1.100')
    conn = engine.connect()

    if target_date == 'all':
        qry = f"SELECT [date], asset, weight  FROM BQUANT.portfolios.portfolio_weights where portfolio_id = '{pid}'"
    else:
        qry = f"SELECT [date], asset, weight  FROM BQUANT.portfolios.portfolio_weights where portfolio_id = '{pid}' and date='{target_date}'"
    
    result = conn.execute(qry)
    df = pd.DataFrame(result.fetchall())

    if df.empty:
        display("None")
        pass
    else:
        df.columns = result.keys()
        df = df[['date', 'asset', 'weight']]
        df['date'] = pd.to_datetime(df['date'], utc=True)
        
    return df

def load_q_factor_scores(sid='all', target_date = 'all', min_date = '2020-01-01'):
    engine = create_engine('mssql+pymssql://performer:newquant@172.32.1.100')
    conn = engine.connect()

    if sid == 'all':
        if target_date == 'all':
            qry = f"SELECT [date], score_id, asset, value from BQUANT.portfolios.scores where date>='{min_date}'"
        else:
            qry = f"SELECT [date], score_id, asset, value from BQUANT.portfolios.scores where date='{target_date}'"
    else:
        if target_date == 'all':
            qry = f"SELECT [date], score_id, asset, value from BQUANT.portfolios.scores where score_id = '{sid} and date>='{min_date}'"
        else:
            qry = f"SELECT [date], score_id, asset, value from BQUANT.portfolios.scores where score_id = '{sid} and date='{target_date}'"
    
    result = conn.execute(qry)
    df = pd.DataFrame(result.fetchall())

    if df.empty:
        pass
    else:
        df.columns = result.keys()
        df = df[['date', 'score_id', 'asset', 'value']]
        df['date'] = pd.to_datetime(df['date'], utc=True)
        
    return df
###

