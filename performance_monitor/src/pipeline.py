"""Analytics 오케스트레이션.

노트북 ``Function_calculation_return_contribution_ver2.ipynb`` 의
CELL 40 ~ CELL 54 (순수 계산 구간)를 **원본 순서 그대로** 실행한다.

앞 단계(DB 로드, jackhammer 백테스트)는 사내 라이브러리가 필요하므로
``tools/build_snapshot.py`` 가 담당하고, 그 결과를 이 함수에 넘긴다.

Notebook 과 Dashboard 가 동일한 이 함수를 호출하면 결과가 같을 수밖에 없다.
"""
from __future__ import annotations

import pandas as pd

from . import attribution, benchmark, performance

__all__ = ["run_attribution", "AttributionResult"]


class AttributionResult(dict):
    """dict 이면서 속성 접근도 되는 결과 컨테이너."""

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as exc:  # pragma: no cover - 접근 실수 방지용
            raise AttributeError(item) from exc


def run_attribution(final_mp: pd.DataFrame,
                    temp_return_final: pd.DataFrame,
                    rtn_bpm: pd.DataFrame,
                    data_bpm_factor: pd.DataFrame,
                    bpm_pred_beta: pd.DataFrame,
                    index_market_cap: pd.DataFrame,
                    date_list,
                    report_date_list,
                    analysis_bm: str,
                    list_bpm_factor,
                    list_bpm_sector,
                    top_model_column: str = "RP",
                    compute_daily_contributions: bool = True,
                    sector_field_primary: str = "q_sector",
                    sector_field_secondary: str = "new_sector",
                    logger=None) -> AttributionResult:
    """CELL 40 ~ 54 실행.

    Parameters
    ----------
    final_mp
        jackhammer 백테스트까지 끝난 상태의 ``final_mp``
        (일별 total/active weight, ``_next``, exposure, predictive_beta, return_d,
        forward_return_d, q_sector, new_sector 포함)
    compute_daily_contributions
        False 면 일별 기여도(CELL 46~51)가 이미 계산되어 있다고 보고 건너뛴다.
        노트북에서 그대로 넘어온 ``final_mp`` 를 재사용할 때 쓴다.
    """
    def log(message: str) -> None:
        if logger is not None:
            logger.info(message)

    date_list = list(date_list)
    report_date_list = list(report_date_list)

    # --- CELL 40: 골격 + scaling factor -----------------------------------
    log("CELL 40 | return_contribution_final 골격 + Alog/alphalog/betalog")
    return_contribution_final = attribution.build_return_contribution_table(
        temp_return_final, report_date_list
    )
    columns = list(return_contribution_final.columns)
    Alog_final, alphalog_final, betalog_final = performance.build_scaling_factors(
        temp_return_final, return_contribution_final, report_date_list
    )

    # --- CELL 46 ~ 51: 일별 · 종목별 기여도 -------------------------------
    if compute_daily_contributions:
        log("CELL 46~51 | 일별 종목별 기여도 (active/market_timing/factor/country/specific)")
        benchmark_pred_beta = attribution.benchmark_predictive_beta(
            data_bpm_factor, bpm_pred_beta, analysis_bm
        )
        final_mp = attribution.calc_all_daily_contributions(
            final_mp, temp_return_final, rtn_bpm, benchmark_pred_beta,
            date_list, columns, list_bpm_factor, list_bpm_sector,
        )
        # 컬럼 단위 대입으로 파편화된 프레임을 정리한다 (값은 바뀌지 않는다).
        final_mp = final_mp.copy()
    else:
        log("CELL 46~51 | 이미 계산된 일별 기여도 재사용")

    # --- CELL 52: 기간 집계 -----------------------------------------------
    log("CELL 52 | 항목별 기간 기여도 집계")
    return_contribution_final = attribution.aggregate_period_contribution(
        final_mp, return_contribution_final, betalog_final, report_date_list,
        list_bpm_factor, list_bpm_sector,
    )

    # --- CELL 53: 섹터 BM 수익률 + allocation/selection --------------------
    log("CELL 53 | 섹터 BM 수익률 / allocation / selection")
    # 원본 CELL 53 의 SQL 은 index_market_cap 을 report_start_date ~ mp_end_date 로만
    # 조회한다. 이후 계산이 `np.array(temp_return_final.loc[report_date_list])` 와
    # 행 수를 맞춰 정렬하므로 구간을 정확히 일치시켜야 한다.
    index_market_cap = index_market_cap.loc[(report_date_list, slice(None)), :]
    sector_mc = benchmark.build_sector_index_market_cap(
        index_market_cap, sector_field_primary
    )
    sector_tot_ret = benchmark.sector_total_return(sector_mc)
    sector_exc_ret = benchmark.sector_excess_return(
        sector_tot_ret, temp_return_final, report_date_list
    )
    return_contribution_final = attribution.calc_allocation_selection(
        final_mp, return_contribution_final, sector_mc, temp_return_final,
        betalog_final, report_date_list, sector_field_primary, suffix="",
    )
    sector_compare_final = attribution.calc_sector_allocation_selection(
        final_mp, data_bpm_factor[sector_field_primary], sector_mc,
        temp_return_final, betalog_final, report_date_list, columns,
        sector_exc_ret.index, sector_field_primary, suffix="",
    )

    new_sector_mc = benchmark.build_sector_index_market_cap(
        index_market_cap, sector_field_secondary
    )
    new_sector_tot_ret = benchmark.sector_total_return(new_sector_mc)
    new_sector_exc_ret = benchmark.sector_excess_return(
        new_sector_tot_ret, temp_return_final, report_date_list
    )
    return_contribution_final = attribution.calc_allocation_selection(
        final_mp, return_contribution_final, new_sector_mc, temp_return_final,
        betalog_final, report_date_list, sector_field_secondary, suffix="_new",
    )
    new_sector_compare_final = attribution.calc_sector_allocation_selection(
        final_mp, data_bpm_factor[sector_field_secondary], new_sector_mc,
        temp_return_final, betalog_final, report_date_list, columns,
        new_sector_exc_ret.index, sector_field_secondary, suffix="_new",
    )

    # --- CELL 54: 기여도 추이 ---------------------------------------------
    log("CELL 54 | compare_final (항목별 누적 기여도 추이)")
    compare_final = attribution.build_compare_final(
        final_mp, temp_return_final, betalog_final, report_date_list, columns,
        list_bpm_factor, list_bpm_sector, top_model_column,
    )

    return AttributionResult(
        final_mp=final_mp,
        temp_return_final=temp_return_final,
        return_contribution_final=return_contribution_final,
        Alog_final=Alog_final,
        alphalog_final=alphalog_final,
        betalog_final=betalog_final,
        compare_final=compare_final,
        sector_compare_final=sector_compare_final,
        new_sector_compare_final=new_sector_compare_final,
        sector_index_market_cap=sector_mc,
        new_sector_index_market_cap=new_sector_mc,
        sector_tot_ret=sector_tot_ret,
        sector_exc_ret=sector_exc_ret,
        new_sector_tot_ret=new_sector_tot_ret,
        new_sector_exc_ret=new_sector_exc_ret,
        date_list=date_list,
        report_date_list=report_date_list,
        columns=columns,
    )
