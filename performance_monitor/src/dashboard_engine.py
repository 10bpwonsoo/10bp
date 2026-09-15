"""Dashboard 조회 계층.

스냅샷(일별 기여도까지 계산된 상태)에서 **사용자가 고른 기간**에 대한
집계 결과를 만들어 준다. 집계식은 `attribution` / `performance` 모듈,
즉 notebook 과 동일한 함수를 그대로 호출한다. 여기서 새 공식을 만들지 않는다.

기간이 스냅샷 기본 구간과 같으면 스냅샷에 저장된 원본 표를 그대로 쓴다
(= notebook 값 그대로). 다르면 동일 함수로 재집계한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import attribution, benchmark, performance

__all__ = ["PeriodResult", "compute_period"]


class PeriodResult(dict):
    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as exc:  # pragma: no cover
            raise AttributeError(item) from exc


def _as_list(dates):
    return list(pd.DatetimeIndex(dates))


def compute_period(bundle: dict, report_date_list, sector_field: str = "new_sector",
                   use_snapshot_when_default: bool = True) -> PeriodResult:
    """선택 기간에 대한 전체 집계 결과."""
    manifest = bundle.get("manifest", {})
    final_mp = bundle["final_mp"]
    temp_return_final = bundle["temp_return_final"]
    report_date_list = _as_list(report_date_list)

    list_bpm_factor = list(manifest.get("list_bpm_factor", []))
    list_bpm_sector = list(manifest.get("list_bpm_sector", []))
    top_column = manifest.get("top_model_column", "RP")

    is_default = (
        str(report_date_list[0])[:10] == str(manifest.get("report_start_date"))
        and str(report_date_list[-1])[:10] == str(manifest.get("mp_end_date"))
    )

    # --- 기간 성과 + scaling factor ---------------------------------------
    table = attribution.build_return_contribution_table(temp_return_final, report_date_list)
    columns = list(table.columns)
    Alog, alphalog, betalog = performance.build_scaling_factors(
        temp_return_final, table, report_date_list
    )

    if is_default and use_snapshot_when_default and bundle.get("return_contribution_final") is not None:
        # 노트북이 만든 원본 표를 그대로 사용한다.
        table = bundle["return_contribution_final"].copy()
        if bundle.get("betalog_final") is not None:
            betalog = bundle["betalog_final"]
        source = "snapshot"
    else:
        table = attribution.aggregate_period_contribution(
            final_mp, table, betalog, report_date_list, list_bpm_factor, list_bpm_sector
        )
        source = "recomputed"

    # --- 섹터 allocation / selection --------------------------------------
    sector_key = "sector_index_market_cap" if sector_field == "q_sector" else "new_sector_index_market_cap"
    compare_key = "sector_compare_final" if sector_field == "q_sector" else "new_sector_compare_final"
    suffix = "" if sector_field == "q_sector" else "_new"
    sector_mc = bundle.get(sector_key)
    sector_compare = None
    sector_note = None

    if source == "snapshot" and bundle.get(compare_key) is not None:
        sector_compare = bundle[compare_key].copy()
    elif sector_mc is not None:
        available = pd.DatetimeIndex(sector_mc.index.get_level_values("date").unique())
        covered = [d for d in report_date_list if d in available]
        if len(covered) == len(report_date_list):
            sector_tot = benchmark.sector_total_return(
                sector_mc.loc[(report_date_list, slice(None)), :]
            )
            sector_exc = benchmark.sector_excess_return(
                sector_tot, temp_return_final, report_date_list
            )
            table = attribution.calc_allocation_selection(
                final_mp, table, sector_mc.loc[(report_date_list, slice(None)), :],
                temp_return_final, betalog, report_date_list, sector_field, suffix=suffix,
            )
            sector_compare = attribution.calc_sector_allocation_selection(
                final_mp, final_mp[sector_field], sector_mc.loc[(report_date_list, slice(None)), :],
                temp_return_final, betalog, report_date_list, columns,
                sector_exc.index, sector_field, suffix=suffix,
            )
        else:
            sector_note = (
                "선택 기간이 스냅샷의 섹터 BM 시총 보유 구간을 벗어나 "
                "Allocation / Selection 을 재계산할 수 없습니다. "
                "(원본 코드도 report 구간만 조회합니다)"
            )
    else:
        sector_note = "스냅샷에 섹터 BM 시총 데이터가 없습니다."

    # --- 누적 곡선 ---------------------------------------------------------
    curve = performance.cumulative_curve(
        temp_return_final, report_date_list, columns + ["bm"]
    )

    # --- 항목별 기여도 추이 -------------------------------------------------
    if source == "snapshot" and bundle.get("compare_final") is not None:
        compare_final = bundle["compare_final"]
    else:
        compare_final = attribution.build_compare_final(
            final_mp, temp_return_final, betalog, report_date_list, columns,
            list_bpm_factor, list_bpm_sector, top_column,
        )

    return PeriodResult(
        source=source,
        columns=columns,
        report_date_list=report_date_list,
        return_contribution_final=table,
        betalog_final=betalog,
        alphalog_final=alphalog,
        Alog_final=Alog,
        cumulative=curve,
        compare_final=compare_final,
        sector_compare_final=sector_compare,
        sector_field=sector_field,
        sector_suffix=suffix,
        sector_note=sector_note,
        list_bpm_factor=list_bpm_factor,
        list_bpm_sector=list_bpm_sector,
        top_column=top_column,
    )


def stock_table(bundle: dict, period: PeriodResult, model: str,
                element: str = "active") -> pd.DataFrame:
    """종목별 비중 + 기여도 표."""
    from . import portfolio

    final_mp = bundle["final_mp"]
    report_date_list = period["report_date_list"]
    window = final_mp.loc[(report_date_list, slice(None)), :]
    stock_list = sorted(set(window.index.get_level_values("item")))

    contribution = attribution.stock_contribution(
        final_mp, period["betalog_final"], report_date_list, stock_list, [model],
        element=element,
        list_bpm_factor=period["list_bpm_factor"],
        list_bpm_sector=period["list_bpm_sector"],
    )[model]

    return portfolio.stock_weight_table(
        final_mp, report_date_list, model,
        contribution=contribution, info_stock=bundle.get("info_stock"),
    )


def top_bottom(frame: pd.DataFrame, column: str, n: int = 10):
    """Top / Bottom n 행."""
    clean = frame.dropna(subset=[column]).copy()
    clean[column] = clean[column].astype(float)
    ordered = clean.sort_values(column, ascending=False)
    return ordered.head(n), ordered.tail(n).sort_values(column)
