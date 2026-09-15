"""가장 중요한 테스트: `src/` 결과가 notebook 원본 코드 결과와 동일한가.

부동소수점 오차만 허용한다 (rtol=0, atol=1e-15 수준).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src import attribution, benchmark, performance
from tests import notebook_reference as ref

ATOL = 1e-15


def _values(frame):
    return np.asarray(frame.values, dtype=float)


def assert_same(actual, expected, atol=ATOL, name=""):
    np.testing.assert_allclose(
        _values(actual), _values(expected), rtol=0, atol=atol,
        err_msg=f"{name}: notebook 결과와 불일치",
    )


# ---------------------------------------------------------------------------
# Benchmark 수익률
# ---------------------------------------------------------------------------
def test_benchmark_simple_returns_matches_notebook():
    dates = pd.bdate_range("2026-01-05", periods=10, tz="UTC")
    prices = pd.DataFrame({"kospi200": np.linspace(350.0, 372.0, 10)}, index=dates)
    log_rtn_bm = benchmark.log_returns_from_prices(prices)

    expected = ref.ref_bm_simple_returns(log_rtn_bm, "kospi200", dates)
    actual = performance.benchmark_simple_returns(log_rtn_bm, "kospi200", dates)
    np.testing.assert_allclose(actual.values, expected, rtol=0, atol=ATOL)


def test_log_return_roundtrip():
    """exp(log(1+r)) - 1 == r  — BM 수익률 변환 경로 무결성."""
    dates = pd.bdate_range("2026-01-05", periods=30, tz="UTC")
    rng = np.random.default_rng(3)
    prices = pd.DataFrame(
        {"kospi200": 350 * np.exp(rng.normal(0, 0.01, 30).cumsum())}, index=dates
    )
    simple = prices["kospi200"].pct_change().fillna(0)
    log_rtn_bm = benchmark.log_returns_from_prices(prices)
    recovered = performance.benchmark_simple_returns(log_rtn_bm, "kospi200", dates)
    np.testing.assert_allclose(recovered.values, simple.values, rtol=0, atol=1e-14)


# ---------------------------------------------------------------------------
# return_contribution_final 골격 + scaling factor
# ---------------------------------------------------------------------------
def test_return_contribution_skeleton(toy):
    expected = ref.ref_return_contribution_skeleton(
        toy["temp_return_final"], toy["report_date_list"]
    )
    actual = attribution.build_return_contribution_table(
        toy["temp_return_final"], toy["report_date_list"]
    )
    assert list(actual.columns) == list(expected.columns)
    for row in ("total", "bm", "active"):
        assert_same(actual.loc[[row]], expected.loc[[row]], name=f"skeleton.{row}")


def test_scaling_factors(toy):
    skeleton = ref.ref_return_contribution_skeleton(
        toy["temp_return_final"], toy["report_date_list"]
    )
    exp_alog, exp_alpha, exp_beta = ref.ref_scaling_factors(
        toy["temp_return_final"], skeleton, toy["report_date_list"]
    )
    act_alog, act_alpha, act_beta = performance.build_scaling_factors(
        toy["temp_return_final"], skeleton.copy(), toy["report_date_list"]
    )
    assert_same(act_alog, exp_alog, name="Alog")
    # alphalog 첫 행은 원본과 동일하게 NaN
    assert act_alpha.iloc[0].isna().all()
    assert_same(act_alpha.iloc[1:], exp_alpha.iloc[1:], name="alphalog")
    assert_same(act_beta, exp_beta, name="betalog")


def test_alphalog_equal_returns_branch():
    """r == r_bm 인 날의 분기(1/(1+r_bm))가 원본과 같은지."""
    dates = pd.bdate_range("2026-01-05", periods=3, tz="UTC")
    temp = pd.DataFrame({"M": [0.0, 0.01, 0.01], "bm": [0.0, 0.01, 0.005]}, index=dates)
    actual = performance.compute_alphalog(temp, list(dates), ["M"])
    assert actual.loc[dates[1], "M"] == pytest.approx(1 / (1 + 0.01))
    expected_day2 = (np.log(1.01) - np.log(1.005)) / (0.01 - 0.005)
    assert actual.loc[dates[2], "M"] == pytest.approx(expected_day2)


def test_Alog_zero_active_branch():
    table = pd.DataFrame(
        {"M": [0.02, 0.02, 0.0]}, index=["total", "bm", "active"]
    )
    actual = performance.compute_Alog(table)
    assert actual.loc["Alog", "M"] == pytest.approx(1 + 0.02)


# ---------------------------------------------------------------------------
# 일별 기여도 (CELL 46 ~ 51)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def daily(toy):
    bench_beta = attribution.benchmark_predictive_beta(
        toy["data_bpm_factor"], toy["bpm_pred_beta"], toy["analysis_bm"]
    )
    expected = ref.ref_daily_contributions(
        toy["final_mp"].copy(), toy["temp_return_final"], toy["rtn_bpm"], bench_beta,
        toy["date_list"], toy["columns"], toy["list_bpm_factor"], toy["list_bpm_sector"],
    )
    actual = attribution.calc_all_daily_contributions(
        toy["final_mp"].copy(), toy["temp_return_final"], toy["rtn_bpm"], bench_beta,
        toy["date_list"], toy["columns"], toy["list_bpm_factor"], toy["list_bpm_sector"],
    )
    return expected, actual, bench_beta


def test_daily_contributions_match_notebook(daily, toy):
    expected, actual, _ = daily
    contrib_cols = [c for c in expected.columns if "_contribution_" in c]
    assert len(contrib_cols) == (
        (2 + len(toy["list_bpm_factor"]) + len(toy["list_bpm_sector"]) + 2)
        * len(toy["columns"])
    ), "기여도 컬럼 개수가 원본과 다름"
    for col in contrib_cols:
        assert_same(actual[[col]], expected[[col]], name=col)


def test_specific_is_residual(daily, toy):
    """specific = active - market_timing - country - Σ(risk+industry)."""
    _, actual, _ = daily
    list_bpm = toy["list_bpm_factor"] + toy["list_bpm_sector"]
    for col in toy["columns"]:
        residual = (
            actual["active_contribution_" + col]
            - actual["market_timing_contribution_" + col]
            - actual["country_contribution_" + col]
            - actual[[f + "_contribution_" + col for f in list_bpm]].sum(axis=1)
        )
        np.testing.assert_allclose(
            actual["specific_contribution_" + col].astype(float).values,
            residual.astype(float).values, rtol=0, atol=ATOL,
        )


def test_last_day_contribution_is_zero(daily, toy):
    """원본과 동일하게 마지막 영업일 기여도는 0."""
    _, actual, _ = daily
    last = toy["date_list"][-1]
    for col in toy["columns"]:
        assert float(actual.loc[(last, slice(None)), "active_contribution_" + col].sum()) == 0.0
        assert float(actual.loc[(last, slice(None)), "market_timing_contribution_" + col].sum()) == 0.0


def test_benchmark_predictive_beta_matches_notebook(toy):
    """원본 CELL 47 의 groupby-apply 식과 동일한지."""
    from src.utils import stack_dropna

    weight_col = "weight_kospi200_next"
    expected_frame = toy["data_bpm_factor"][[weight_col]].join(
        stack_dropna(toy["bpm_pred_beta"]).to_frame().rename(columns={0: "predictive_beta"})
    )
    expected = expected_frame.groupby("date", group_keys=False).apply(
        lambda x: (x[weight_col] * x["predictive_beta"]).sum()
    )
    actual = attribution.benchmark_predictive_beta(
        toy["data_bpm_factor"], toy["bpm_pred_beta"], toy["analysis_bm"]
    )
    np.testing.assert_allclose(actual.values, expected.values, rtol=0, atol=ATOL)


# ---------------------------------------------------------------------------
# 기간 집계 (CELL 52)
# ---------------------------------------------------------------------------
def test_period_aggregation_matches_notebook(daily, toy):
    _, actual_mp, _ = daily
    skeleton = attribution.build_return_contribution_table(
        toy["temp_return_final"], toy["report_date_list"]
    )
    _, _, betalog = performance.build_scaling_factors(
        toy["temp_return_final"], skeleton, toy["report_date_list"]
    )

    expected = ref.ref_aggregate(
        actual_mp, skeleton.copy(), betalog, toy["report_date_list"],
        toy["list_bpm_factor"], toy["list_bpm_sector"],
    )
    result = attribution.aggregate_period_contribution(
        actual_mp, skeleton.copy(), betalog, toy["report_date_list"],
        toy["list_bpm_factor"], toy["list_bpm_sector"],
    )
    for row in ("market_timing", "risk_factor", "industry_factor", "country", "specific"):
        assert_same(result.loc[[row]], expected.loc[[row]], name=f"aggregate.{row}")


def test_period_attribution_sums_to_active(daily, toy):
    """active = market_timing + risk_factor + industry_factor + country + specific."""
    _, actual_mp, _ = daily
    skeleton = attribution.build_return_contribution_table(
        toy["temp_return_final"], toy["report_date_list"]
    )
    _, _, betalog = performance.build_scaling_factors(
        toy["temp_return_final"], skeleton, toy["report_date_list"]
    )
    table = attribution.aggregate_period_contribution(
        actual_mp, skeleton, betalog, toy["report_date_list"],
        toy["list_bpm_factor"], toy["list_bpm_sector"],
    )
    for col in toy["columns"]:
        parts = table.loc[
            ["market_timing", "risk_factor", "industry_factor", "country", "specific"], col
        ].astype(float).sum()
        assert float(table.loc["active", col]) == pytest.approx(parts, abs=1e-15)


# ---------------------------------------------------------------------------
# 종목별 기여도 (Performance_Analysis_Module CELL 48)
# ---------------------------------------------------------------------------
def test_stock_contribution_matches_notebook(daily, toy):
    _, actual_mp, _ = daily
    skeleton = attribution.build_return_contribution_table(
        toy["temp_return_final"], toy["report_date_list"]
    )
    _, _, betalog = performance.build_scaling_factors(
        toy["temp_return_final"], skeleton, toy["report_date_list"]
    )
    stock_list = sorted(set(actual_mp.index.get_level_values("item")))

    expected = ref.ref_stock_contribution(
        actual_mp, betalog, toy["report_date_list"], stock_list, toy["columns"]
    )
    result = attribution.stock_contribution(
        actual_mp, betalog, toy["report_date_list"], stock_list, toy["columns"],
        element="active",
    )
    assert_same(result, expected, name="stock_contribution")


def test_stock_contribution_sums_to_active(daily, toy):
    """종목별 기여도 합 == 기간 active (Barra scaling 정의상 성립해야 한다)."""
    _, actual_mp, _ = daily
    skeleton = attribution.build_return_contribution_table(
        toy["temp_return_final"], toy["report_date_list"]
    )
    _, _, betalog = performance.build_scaling_factors(
        toy["temp_return_final"], skeleton, toy["report_date_list"]
    )
    stock_list = sorted(set(actual_mp.index.get_level_values("item")))
    result = attribution.stock_contribution(
        actual_mp, betalog, toy["report_date_list"], stock_list, toy["columns"]
    )
    for col in toy["columns"]:
        assert float(result[col].astype(float).sum()) == pytest.approx(
            float(skeleton.loc["active", col]), abs=1e-12
        )


# ---------------------------------------------------------------------------
# Allocation / Selection (CELL 53)
# ---------------------------------------------------------------------------
def test_allocation_plus_selection_equals_active(daily, toy):
    _, actual_mp, _ = daily
    report_date_list = toy["report_date_list"]
    skeleton = attribution.build_return_contribution_table(
        toy["temp_return_final"], report_date_list
    )
    _, _, betalog = performance.build_scaling_factors(
        toy["temp_return_final"], skeleton, report_date_list
    )
    imc = toy["index_market_cap"].loc[(report_date_list, slice(None)), :]
    sector_mc = benchmark.build_sector_index_market_cap(imc, "q_sector")

    table = attribution.calc_allocation_selection(
        actual_mp, skeleton, sector_mc, toy["temp_return_final"], betalog,
        report_date_list, "q_sector",
    )
    for col in toy["columns"]:
        total = float(table.loc["allocation", col]) + float(table.loc["selection", col])
        assert total == pytest.approx(float(table.loc["active", col]), abs=1e-15)


def test_sector_allocation_selection_sums_to_total(daily, toy):
    """섹터별 allocation 합 == 전체 allocation."""
    _, actual_mp, _ = daily
    report_date_list = toy["report_date_list"]
    skeleton = attribution.build_return_contribution_table(
        toy["temp_return_final"], report_date_list
    )
    _, _, betalog = performance.build_scaling_factors(
        toy["temp_return_final"], skeleton, report_date_list
    )
    imc = toy["index_market_cap"].loc[(report_date_list, slice(None)), :]
    sector_mc = benchmark.build_sector_index_market_cap(imc, "q_sector")
    table = attribution.calc_allocation_selection(
        actual_mp, skeleton, sector_mc, toy["temp_return_final"], betalog,
        report_date_list, "q_sector",
    )
    sector_tot = benchmark.sector_total_return(sector_mc)
    sector_exc = benchmark.sector_excess_return(
        sector_tot, toy["temp_return_final"], report_date_list
    )
    per_sector = attribution.calc_sector_allocation_selection(
        actual_mp, toy["data_bpm_factor"]["q_sector"], sector_mc,
        toy["temp_return_final"], betalog, report_date_list, toy["columns"],
        sector_exc.index, "q_sector",
    )
    for col in toy["columns"]:
        assert float(per_sector[col + "_allocation"].astype(float).sum()) == pytest.approx(
            float(table.loc["allocation", col]), abs=1e-14
        )
        assert float(per_sector[col + "_selection"].astype(float).sum()) == pytest.approx(
            float(table.loc["selection", col]), abs=1e-14
        )


# ---------------------------------------------------------------------------
# compare_final (CELL 54)
# ---------------------------------------------------------------------------
def test_compare_final_active_matches_cumulative(daily, toy):
    _, actual_mp, _ = daily
    report_date_list = toy["report_date_list"]
    skeleton = attribution.build_return_contribution_table(
        toy["temp_return_final"], report_date_list
    )
    _, _, betalog = performance.build_scaling_factors(
        toy["temp_return_final"], skeleton, report_date_list
    )
    compare_final = attribution.build_compare_final(
        actual_mp, toy["temp_return_final"], betalog, report_date_list, toy["columns"],
        toy["list_bpm_factor"], toy["list_bpm_sector"], top_model_column="RP",
    )
    curve = performance.cumulative_curve(
        toy["temp_return_final"], report_date_list, toy["columns"] + ["bm"]
    )
    for col in toy["columns"]:
        series = compare_final.xs("active_contribution", level=1)[col].astype(float)
        expected = (curve[col] - curve["bm"]).astype(float)
        np.testing.assert_allclose(series.values, expected.values, rtol=0, atol=ATOL)


def test_compare_final_last_active_equals_period_active(daily, toy):
    """추이의 마지막 값 == 기간 active (두 경로가 같은 값을 내야 한다)."""
    _, actual_mp, _ = daily
    report_date_list = toy["report_date_list"]
    skeleton = attribution.build_return_contribution_table(
        toy["temp_return_final"], report_date_list
    )
    _, _, betalog = performance.build_scaling_factors(
        toy["temp_return_final"], skeleton, report_date_list
    )
    compare_final = attribution.build_compare_final(
        actual_mp, toy["temp_return_final"], betalog, report_date_list, toy["columns"],
        toy["list_bpm_factor"], toy["list_bpm_sector"], top_model_column="RP",
    )
    for col in toy["columns"]:
        last = float(
            compare_final.loc[(report_date_list[-1], "active_contribution"), col]
        )
        assert last == pytest.approx(float(skeleton.loc["active", col]), abs=1e-15)
