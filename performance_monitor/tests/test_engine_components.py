"""Portfolio / Model / Validation / Snapshot 계층 테스트."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src import model_analysis, performance, portfolio, validation
from src.data_loader import SnapshotStore, data_status, list_snapshots
from src.utils import stack_dropna


# ---------------------------------------------------------------------------
# utils
# ---------------------------------------------------------------------------
def test_stack_dropna_drops_na_rows():
    frame = pd.DataFrame(
        {"a": [1.0, np.nan], "b": [np.nan, 4.0]}, index=["x", "y"]
    )
    out = stack_dropna(frame)
    assert len(out) == 2
    assert out.loc[("x", "a")] == 1.0
    assert out.loc[("y", "b")] == 4.0


def test_stack_dropna_roundtrip_shift():
    """notebook 의 ``.unstack().shift(-1).stack()`` 패턴이 동작하는지."""
    dates = pd.bdate_range("2026-01-05", periods=3, tz="UTC")
    index = pd.MultiIndex.from_product([dates, ["A", "B"]], names=["date", "item"])
    series = pd.Series(range(6), index=index, dtype=float).to_frame("v")
    shifted = stack_dropna(series[["v"]].unstack().shift(-1))
    # 마지막 날은 shift(-1) 로 NaN → 제거되어야 한다
    assert len(shifted) == 4
    assert shifted.index.get_level_values("date").max() == dates[-2]


# ---------------------------------------------------------------------------
# portfolio
# ---------------------------------------------------------------------------
def test_weight_sum_is_one(toy):
    summary = portfolio.portfolio_weight_sum(toy["final_mp"], toy["dates"][-1], "RP")
    assert summary["total_weight_sum"] == pytest.approx(1.0, abs=1e-9)
    assert summary["bm_weight_sum"] == pytest.approx(1.0, abs=1e-9)
    assert summary["active_weight_sum"] == pytest.approx(0.0, abs=1e-9)


def test_stock_weight_table_shape(toy):
    table = portfolio.stock_weight_table(
        toy["final_mp"], toy["report_date_list"], "RP"
    )
    assert set(toy["items"]) == set(table.index)
    for column in ("start_weight", "end_weight", "avg_weight", "active_weight_end",
                   "period_return"):
        assert column in table.columns
    # active weight = portfolio - benchmark
    np.testing.assert_allclose(
        (table["end_weight"] - table["bm_weight_end"]).values,
        table["active_weight_end"].values, rtol=0, atol=1e-15,
    )


def test_period_return_matches_compounding(toy):
    table = portfolio.stock_weight_table(
        toy["final_mp"], toy["report_date_list"], "RP"
    )
    item = toy["items"][0]
    window = toy["final_mp"].loc[(toy["report_date_list"][1:], item), "return_d"]
    expected = float((1 + window).prod() - 1)
    assert float(table.loc[item, "period_return"]) == pytest.approx(expected, abs=1e-15)


def test_position_change_flags_new_and_removed(toy):
    frame = toy["final_mp"].copy()
    prev, curr = toy["dates"][-2], toy["dates"][-1]
    new_item, dropped_item = toy["items"][0], toy["items"][1]
    frame.loc[(prev, new_item), "total_RP"] = 0.0
    frame.loc[(curr, dropped_item), "total_RP"] = 0.0

    change = portfolio.position_change(frame, prev, curr, "RP")
    assert change.loc[new_item, "status"] == "신규편입"
    assert change.loc[dropped_item, "status"] == "제외"
    np.testing.assert_allclose(
        (change["current_weight"] - change["previous_weight"]).values,
        change["change"].values, rtol=0, atol=1e-15,
    )


# ---------------------------------------------------------------------------
# model analysis
# ---------------------------------------------------------------------------
def test_discover_models_prefers_contribution_table(toy):
    rcf = pd.DataFrame(index=["active"], columns=toy["columns"])
    assert model_analysis.discover_models(return_contribution_final=rcf) == toy["columns"]
    assert model_analysis.discover_models(
        temp_return_final=toy["temp_return_final"]
    ) == toy["columns"]
    assert sorted(
        model_analysis.discover_models(final_mp=toy["final_mp"])
    ) == sorted(toy["columns"])


def test_model_comparison_excess_is_return_minus_bm(toy):
    table = model_analysis.model_comparison_table(
        toy["temp_return_final"], toy["report_date_list"], toy["columns"],
    )
    np.testing.assert_allclose(
        (table["return"] - table["benchmark"]).values,
        table["excess_return"].values, rtol=0, atol=1e-15,
    )


def test_best_worst_model_excludes_top(toy):
    rcf = pd.DataFrame(
        {"MODEL_A_FP": [0.01], "MODEL_B_FP": [-0.02], "RP": [0.5]}, index=["active"]
    )
    best, worst = model_analysis.best_worst_model(rcf, "active", exclude=["RP"])
    assert best[0] == "MODEL_A_FP"
    assert worst[0] == "MODEL_B_FP"


def test_period_total_return_excludes_anchor_day(toy):
    """기준일(report_date_list[0]) 수익률은 기간 성과에 포함되지 않는다."""
    frame = toy["temp_return_final"].copy()
    frame.loc[toy["report_date_list"][0], "RP"] = 99.0  # 기준일에 극단값
    result = performance.period_total_return(frame, toy["report_date_list"], ["RP"])
    baseline = performance.period_total_return(
        toy["temp_return_final"], toy["report_date_list"], ["RP"]
    )
    assert float(result["RP"]) == pytest.approx(float(baseline["RP"]), abs=1e-15)


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
def _bundle(toy):
    rcf = pd.DataFrame(
        0.0,
        index=["total", "bm", "active", "market_timing", "specific",
               "risk_factor", "industry_factor", "country"],
        columns=toy["columns"],
    )
    return {
        "final_mp": toy["final_mp"],
        "temp_return_final": toy["temp_return_final"],
        "return_contribution_final": rcf,
        "manifest": {"as_of": "2026-01-14", "analysis_bm": "kospi200"},
    }


def test_validation_clean_data_has_no_error(toy):
    report = validation.run_validation(
        _bundle(toy), "RP", toy["report_date_list"], {"weight_sum_tolerance": 0.005}
    )
    assert not report.has_error, [c.name for c in report.problems]


def test_validation_detects_missing_price(toy):
    bundle = _bundle(toy)
    frame = bundle["final_mp"].copy()
    bad_item = toy["items"][2]
    frame.loc[(toy["report_date_list"][1], bad_item), "return_d"] = np.nan
    bundle["final_mp"] = frame

    report = validation.run_validation(bundle, "RP", toy["report_date_list"])
    check = next(c for c in report.checks if c.name == "Missing Price / Return")
    assert check.status == validation.ERROR
    assert bad_item in check.items


def test_validation_detects_weight_sum_break(toy):
    bundle = _bundle(toy)
    frame = bundle["final_mp"].copy()
    frame.loc[(toy["report_date_list"][-1], toy["items"][0]), "total_RP"] += 0.5
    bundle["final_mp"] = frame

    report = validation.run_validation(bundle, "RP", toy["report_date_list"])
    check = next(c for c in report.checks if c.name == "Portfolio Weight Sum")
    assert check.status == validation.WARN


def test_validation_detects_invalid_return(toy):
    bundle = _bundle(toy)
    frame = bundle["final_mp"].copy()
    frame.loc[(toy["report_date_list"][1], toy["items"][0]), "return_d"] = -1.5
    bundle["final_mp"] = frame

    report = validation.run_validation(bundle, "RP", toy["report_date_list"])
    check = next(c for c in report.checks if c.name == "Invalid Return")
    assert check.status == validation.ERROR


def test_validation_does_not_mutate_data(toy):
    """검증이 데이터를 0으로 채우거나 건드리지 않아야 한다."""
    bundle = _bundle(toy)
    frame = bundle["final_mp"].copy()
    frame.loc[(toy["report_date_list"][1], toy["items"][0]), "return_d"] = np.nan
    bundle["final_mp"] = frame
    before = frame["return_d"].isna().sum()
    validation.run_validation(bundle, "RP", toy["report_date_list"])
    assert frame["return_d"].isna().sum() == before


# ---------------------------------------------------------------------------
# snapshot store
# ---------------------------------------------------------------------------
def test_snapshot_roundtrip(tmp_path, toy):
    store = SnapshotStore.create(
        tmp_path, "2026-01-14", {"as_of": "2026-01-14", "analysis_bm": "kospi200"}
    )
    store.write_table("temp_return_final", toy["temp_return_final"])
    loaded = store.read_table("temp_return_final")
    pd.testing.assert_frame_equal(loaded, toy["temp_return_final"])
    assert store.manifest["as_of"] == "2026-01-14"


def test_snapshot_object_dtype_falls_back_to_pickle(tmp_path):
    """object dtype 이 섞인 return_contribution_final 도 저장되어야 한다."""
    frame = pd.DataFrame({"RP": [0.01, "n/a"]}, index=["total", "bm"], dtype=object)
    store = SnapshotStore.create(tmp_path, "2026-01-14", {"as_of": "2026-01-14"})
    store.write_table("return_contribution_final", frame)
    assert store.has("return_contribution_final")
    pd.testing.assert_frame_equal(store.read_table("return_contribution_final"), frame)


def test_snapshot_cache_key_changes_with_content(tmp_path, toy):
    from src.data_loader import SnapshotInfo

    store = SnapshotStore.create(tmp_path, "2026-01-14", {"as_of": "2026-01-14"})
    store.write_table("temp_return_final", toy["temp_return_final"])
    info = SnapshotInfo(path=store.path, manifest=store.manifest)
    before = info.cache_key
    store.write_table("betalog_final", toy["temp_return_final"])
    after = SnapshotInfo(path=store.path, manifest=store.manifest).cache_key
    assert before != after


def test_data_status_reports_missing(toy):
    bundle = _bundle(toy)
    status = data_status(bundle)
    assert status["data_as_of"] == "2026-01-14"
    assert status["checks"]["Portfolio Data"] == "정상"
    assert status["checks"]["Benchmark Data"] == "정상"
    assert status["n_stocks"] == len(toy["items"])


# ---------------------------------------------------------------------------
# 기간 프리셋 (일간 / 주간 / 월간 ...)
# ---------------------------------------------------------------------------
def _preset_dates():
    return list(pd.DatetimeIndex(list(pd.bdate_range("2026-01-02", periods=180, tz="UTC"))))


def test_preset_daily_covers_exactly_one_business_day():
    from src.ui import resolve_preset

    dates = _preset_dates()
    end = dates[-1]
    start, stop, note = resolve_preset("1D", dates, end, "2026-09-04", {})
    assert start == dates[-2] and stop == end and note is None
    # 기준일은 제외되므로 성과 구간은 정확히 1영업일
    assert len([d for d in dates if start < d <= stop]) == 1


def test_preset_weekly_uses_snapshot_report_start():
    """주간은 노트북의 report_start_date 를 그대로 기준일로 쓴다."""
    from src.ui import resolve_preset

    dates = _preset_dates()
    end = dates[-1]
    anchor = dates[-6]
    start, stop, note = resolve_preset(
        "1W", dates, end, str(anchor)[:10], {})
    assert start == anchor and stop == end and note is None
    assert len([d for d in dates if start < d <= stop]) == 5


def test_preset_weekly_falls_back_when_anchor_missing():
    from src.ui import resolve_preset

    dates = _preset_dates()
    start, stop, note = resolve_preset("1W", dates, dates[-1], None, {})
    assert start == dates[-6]
    assert "5영업일" in note


def test_preset_monthly_uses_workdate_anchor():
    from src.ui import resolve_preset

    dates = _preset_dates()
    end = dates[-1]
    anchor = dates[-15]
    start, stop, note = resolve_preset(
        "MTD", dates, end, "2026-09-04", {"MTD": str(anchor)[:10]})
    assert start == anchor and stop == end and note is None


def test_preset_reports_missing_anchor_instead_of_guessing():
    """기준일이 없으면 임의로 만들지 않고 사유를 알린다."""
    from src.ui import resolve_preset

    dates = _preset_dates()
    start, stop, note = resolve_preset("QTD", dates, dates[-1], "2026-09-04", {})
    assert start is None and stop is None
    assert "QTD" in note


def test_preset_rejects_anchor_outside_snapshot_window():
    from src.ui import resolve_preset

    dates = _preset_dates()
    start, stop, note = resolve_preset(
        "YTD", dates, dates[-1], "2026-09-04", {"YTD": "2020-01-02"})
    assert start is None
    assert "벗어납니다" in note
