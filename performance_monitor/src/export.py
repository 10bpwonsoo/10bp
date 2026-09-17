"""Weekly Performance Snapshot Export.

화면의 주요 표를 하나의 Excel 파일로 내보낸다.
시트: Summary / Performance / Attribution / Models / Stocks / PositionChange / Validation
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd

from . import dashboard_engine as de
from . import model_analysis, performance, portfolio, validation

__all__ = ["build_weekly_workbook", "build_sheets", "excel_safe",
           "display_safe"]


def _strip_tz(index):
    """openpyxl 은 tz-aware datetime 을 쓰지 못한다. 문자열 날짜로 바꾼다."""
    if isinstance(index, pd.MultiIndex):
        levels = []
        for pos in range(index.nlevels):
            level = index.get_level_values(pos)
            if isinstance(level, pd.DatetimeIndex) and level.tz is not None:
                level = pd.Index([str(v)[:10] for v in level], name=index.names[pos])
            levels.append(level)
        return pd.MultiIndex.from_arrays(levels, names=index.names)
    if isinstance(index, pd.DatetimeIndex) and index.tz is not None:
        return pd.Index([str(v)[:10] for v in index], name=index.name)
    return index


def excel_safe(frame: pd.DataFrame) -> pd.DataFrame:
    """Excel 로 내보낼 수 있도록 tz-aware datetime 을 문자열로 바꾼다.

    수치는 건드리지 않는다.
    """
    out = frame.copy()
    out.index = _strip_tz(out.index)
    out.columns = _strip_tz(out.columns)
    for column in out.columns:
        values = out[column]
        if isinstance(values.dtype, pd.DatetimeTZDtype):
            out[column] = values.map(lambda v: str(v)[:10])
    return out


def display_safe(frame: pd.DataFrame) -> pd.DataFrame:
    """st.dataframe 표시용으로 혼합 dtype 컬럼을 문자열로 바꾼다.

    Summary 시트의 '값' 은 문자열("KOSPI200")과 숫자(0.0123)가 섞여 있다.
    엑셀에서는 숫자 서식이 필요하므로 그대로 두어야 하지만, Arrow 는 object
    컬럼의 혼합 타입을 변환하지 못해 화면에 오류 로그를 남긴다. **표시할 때만**
    문자열로 맞춘다. 파일로 내보내는 내용은 건드리지 않는다.
    """
    out = frame.copy()
    for column in out.columns:
        values = out[column]
        if values.dtype != object:
            continue
        kinds = {type(v) for v in values if v is not None and v == v}
        if len(kinds) > 1:
            out[column] = values.map(lambda v: "" if v is None or v != v else str(v))
    return out


def build_sheets(bundle: dict, period, model: str, config,
                 display_names: dict | None = None,
                 anchors: dict | None = None) -> dict:
    """내보낼 시트들을 dict 로 만든다 (Excel / CSV 공용)."""
    display_names = display_names or {}
    anchors = dict(anchors or {})
    rcf = period["return_contribution_final"]
    report_date_list = period["report_date_list"]
    temp_return_final = bundle["temp_return_final"]
    final_mp = bundle["final_mp"]
    manifest = bundle.get("manifest", {})
    sheets: dict[str, pd.DataFrame] = {}

    # --- Summary -----------------------------------------------------------
    stocks = de.stock_table(bundle, period, model)
    top, bottom = de.top_bottom(stocks, "contribution", 1)
    best, worst = model_analysis.best_worst_model(
        rcf, "active", exclude=[period["top_column"]]
    )

    def _label(frame):
        if frame.empty:
            return "-", np.nan
        row = frame.iloc[0]
        return str(row.get("name") or frame.index[0]), float(row["contribution"])

    top_name, top_value = _label(top)
    bottom_name, bottom_value = _label(bottom)

    sheets["Summary"] = pd.DataFrame([
        ["Data As of", manifest.get("as_of", "-"), ""],
        ["Benchmark", config.benchmark_display(manifest.get("analysis_bm", "")), ""],
        ["Model", display_names.get(model, model), ""],
        ["분석기간", f"{str(report_date_list[0])[:10]} ~ {str(report_date_list[-1])[:10]}", ""],
        ["계산 출처", period["source"], "snapshot=노트북 결과 그대로 / recomputed=동일 함수 재집계"],
        ["", "", ""],
        ["Portfolio", float(rcf.loc["total", model]), ""],
        ["Benchmark Return", float(rcf.loc["bm", model]), ""],
        ["Excess", float(rcf.loc["active", model]), ""],
        ["", "", ""],
        ["Top Contributor", top_name, top_value],
        ["Bottom Contributor", bottom_name, bottom_value],
        ["Best Model", display_names.get(best[0], best[0]) if best else "-",
         best[1] if best else np.nan],
        ["Worst Model", display_names.get(worst[0], worst[0]) if worst else "-",
         worst[1] if worst else np.nan],
    ], columns=["항목", "값", "비고"])

    # --- Performance -------------------------------------------------------
    columns = period["columns"]
    rows = {"WTD": performance.period_total_return(
        temp_return_final, report_date_list, columns + ["bm"])}
    end_date = report_date_list[-1]
    for key, anchor in anchors.items():
        if anchor is None or key == "WTD":
            continue
        rows[key] = performance.period_return_by_anchor(
            temp_return_final, anchor, end_date, columns + ["bm"])
    period_table = pd.DataFrame(rows)
    excess = period_table.loc[columns].sub(period_table.loc["bm"], axis=1)
    excess.columns = [f"{c}_excess" for c in excess.columns]
    sheets["Performance"] = period_table.join(excess)

    curve = period["cumulative"]
    curve = curve.copy()
    curve.index = [str(d)[:10] for d in curve.index]
    sheets["Performance_Cumulative"] = curve

    # --- Attribution -------------------------------------------------------
    summary_rows = [r for r in config.attribution["summary_rows"] if r in rcf.index]
    sheets["Attribution"] = rcf.loc[summary_rows].astype(float)

    if period["sector_compare_final"] is not None:
        sheets["Attribution_Sector"] = period["sector_compare_final"].astype(float)

    # --- Models ------------------------------------------------------------
    models_table = period_table.loc[columns].copy()
    models_table["excess_WTD"] = excess["WTD_excess"]
    models_table["contribution_active"] = rcf.loc["active"].astype(float)
    models_table["display_name"] = [display_names.get(i, i) for i in models_table.index]
    sheets["Models"] = models_table

    # --- Stocks ------------------------------------------------------------
    sheets["Stocks"] = stocks

    # --- PositionChange ----------------------------------------------------
    sheets["PositionChange"] = portfolio.position_change(
        final_mp, report_date_list[0], report_date_list[-1], model,
        info_stock=bundle.get("info_stock"))

    # --- Validation --------------------------------------------------------
    report = validation.run_validation(bundle, model, report_date_list, config.validation)
    frame = report.to_frame()
    frame["대상 목록"] = [", ".join(map(str, c.items[:30])) for c in report.checks]
    sheets["Validation"] = frame

    return sheets


def build_weekly_workbook(bundle: dict, period, model: str, config,
                          display_names: dict | None = None,
                          anchors: dict | None = None) -> bytes:
    """Weekly Performance Snapshot 을 xlsx 바이트로 반환."""
    sheets = build_sheets(bundle, period, model, config, display_names, anchors)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            excel_safe(frame).to_excel(writer, sheet_name=name[:31])
    return buffer.getvalue()
