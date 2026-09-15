"""PHASE 10 — 기존 notebook 결과와 Dashboard 결과 대조.

사용법 (Performance_Analysis_Module_ver2_.ipynb 를 **평소대로 끝까지 실행한 뒤**,
같은 커널에서)::

    import sys
    sys.path.append('/path/to/performance_monitor')
    from tools.compare_with_notebook import compare
    result = compare(globals())

출력::

    ================ PARITY CHECK ================
    항목                          Notebook      Dashboard     Difference
    RP / total                    0.41180000%   0.41180000%   0.00e+00
    ...
    ✅ 모든 항목 일치 (허용오차 1e-12)

핵심 값의 차이는 원칙적으로 0 이어야 한다. 부동소수점 오차만 허용한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from performance_monitor.src import attribution, benchmark, performance  # noqa: E402

DEFAULT_TOLERANCE = 1e-12


def _diff(actual, expected):
    a = np.asarray(pd.Series(actual).astype(float).values, dtype=float)
    e = np.asarray(pd.Series(expected).astype(float).values, dtype=float)
    if a.shape != e.shape:
        return np.inf
    mask = ~(np.isnan(a) & np.isnan(e))
    if not mask.any():
        return 0.0
    return float(np.nanmax(np.abs(a[mask] - e[mask])))


def compare(namespace: dict, tolerance: float = DEFAULT_TOLERANCE,
            verbose: bool = True, save_csv: str | None = None) -> pd.DataFrame:
    """notebook globals 를 받아 `src/` 엔진 결과와 비교한다."""
    rows = []

    def check(name: str, notebook_value, dashboard_value):
        difference = _diff(dashboard_value, notebook_value)
        rows.append({
            "항목": name,
            "Notebook": _scalar(notebook_value),
            "Dashboard": _scalar(dashboard_value),
            "Difference": difference,
            "일치": "OK" if difference <= tolerance else "MISMATCH",
        })

    def _scalar(value):
        series = pd.Series(value).astype(float)
        return float(series.iloc[0]) if len(series) == 1 else f"[{len(series)} values]"

    # 필요한 notebook 객체
    final_mp = namespace["final_mp"]
    temp_return_final = namespace["temp_return_final"]
    nb_rcf = namespace["return_contribution_final"]
    nb_betalog = namespace["betalog_final"]
    report_date_list = list(namespace["report_date_list"])
    list_bpm_factor = list(namespace["list_bpm_factor"])
    list_bpm_sector = list(namespace["list_bpm_sector"])
    columns = list(nb_rcf.columns)

    # --- 1. 기간 수익률 + scaling factor ----------------------------------
    dash_rcf = attribution.build_return_contribution_table(
        temp_return_final, report_date_list
    )
    _, _, dash_betalog = performance.build_scaling_factors(
        temp_return_final, dash_rcf, report_date_list
    )
    for row in ("total", "bm", "active"):
        check(f"{row} (전 모델)", nb_rcf.loc[row], dash_rcf.loc[row])
    check("betalog_final", nb_betalog.values.ravel(), dash_betalog.values.ravel())

    # --- 2. 항목별 기간 기여도 ---------------------------------------------
    dash_rcf = attribution.aggregate_period_contribution(
        final_mp, dash_rcf, dash_betalog, report_date_list,
        list_bpm_factor, list_bpm_sector,
    )
    for row in ("market_timing", "risk_factor", "industry_factor", "country", "specific"):
        check(f"{row} (전 모델)", nb_rcf.loc[row], dash_rcf.loc[row])

    # --- 3. Allocation / Selection ----------------------------------------
    if "sector_index_market_cap" in namespace:
        dash_rcf = attribution.calc_allocation_selection(
            final_mp, dash_rcf, namespace["sector_index_market_cap"],
            temp_return_final, dash_betalog, report_date_list, "q_sector",
        )
        for row in ("allocation", "selection"):
            if row in nb_rcf.index:
                check(f"{row} (전 모델)", nb_rcf.loc[row], dash_rcf.loc[row])

    if "new_sector_index_market_cap" in namespace:
        dash_rcf = attribution.calc_allocation_selection(
            final_mp, dash_rcf, namespace["new_sector_index_market_cap"],
            temp_return_final, dash_betalog, report_date_list, "new_sector",
            suffix="_new",
        )
        for row in ("allocation_new", "selection_new"):
            if row in nb_rcf.index:
                check(f"{row} (전 모델)", nb_rcf.loc[row], dash_rcf.loc[row])

    # --- 4. 섹터별 allocation / selection ----------------------------------
    if "sector_compare_final" in namespace and "sector_index_market_cap" in namespace:
        sector_mc = namespace["sector_index_market_cap"]
        nb_sector = namespace["sector_compare_final"]
        sector_tot = benchmark.sector_total_return(sector_mc)
        sector_exc = benchmark.sector_excess_return(
            sector_tot, temp_return_final, report_date_list
        )
        dash_sector = attribution.calc_sector_allocation_selection(
            final_mp, namespace["data_bpm_factor"]["q_sector"], sector_mc,
            temp_return_final, dash_betalog, report_date_list, columns,
            sector_exc.index, "q_sector",
        )
        for column in nb_sector.columns:
            if column in dash_sector.columns:
                check(f"sector_compare_final[{column}]",
                      nb_sector[column], dash_sector[column])

    # --- 5. 종목별 기여도 ---------------------------------------------------
    stock_list = sorted(set(final_mp.index.get_level_values("item")))
    dash_stock = attribution.stock_contribution(
        final_mp, dash_betalog, report_date_list, stock_list, columns, element="active"
    )
    nb_stock = pd.DataFrame(index=stock_list, columns=columns)
    for column in columns:
        nb_stock.loc[stock_list, column] = (
            final_mp.loc[(report_date_list, stock_list), "active_contribution_" + column]
            .unstack().T * np.array(nb_betalog.loc[:, column].shift(-1))
        ).sum(axis=1)
    for column in columns:
        check(f"stock_contribution[{column}]", nb_stock[column], dash_stock[column])

    # --- 6. compare_final ---------------------------------------------------
    if "compare_final" in namespace:
        nb_compare = namespace["compare_final"]
        dash_compare = attribution.build_compare_final(
            final_mp, temp_return_final, dash_betalog, report_date_list, columns,
            list_bpm_factor, list_bpm_sector,
            top_model_column=namespace.get("mp_weight", pd.DataFrame()).columns[0]
            if hasattr(namespace.get("mp_weight"), "columns") else "RP",
        )
        common = nb_compare.index.intersection(dash_compare.index)
        for column in columns:
            check(f"compare_final[{column}]",
                  nb_compare.loc[common, column], dash_compare.loc[common, column])

    result = pd.DataFrame(rows)

    if verbose:
        mismatched = result[result["일치"] != "OK"]
        print("=" * 78)
        print("PARITY CHECK — Notebook vs Dashboard Analytics Engine")
        print("=" * 78)
        with pd.option_context("display.max_rows", 200, "display.width", 160):
            print(result.to_string(index=False))
        print("-" * 78)
        if mismatched.empty:
            print(f"✅ 전 항목 일치 (허용오차 {tolerance:g})")
        else:
            print(f"❌ 불일치 {len(mismatched)}건 — 아래 항목을 확인하십시오")
            print(mismatched.to_string(index=False))

    if save_csv:
        result.to_csv(save_csv, index=False, encoding="utf-8-sig")
        print(f"\n저장: {save_csv}")

    return result


if __name__ == "__main__":  # pragma: no cover
    print(__doc__)
