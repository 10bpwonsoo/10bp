"""Models — 상위 모델 / 하위 모델(Sub-model) 분석 및 비교."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src import attribution, dashboard_engine as de  # noqa: E402
from src import model_analysis, performance, ui  # noqa: E402
from src.utils import fmt_pct  # noqa: E402

ui.bootstrap("Models")
ctx = ui.sidebar()
if ctx is None:
    st.stop()

ui.header(ctx, "MODEL / SUB-MODEL ANALYSIS")

bundle = ctx["bundle"]
model = ctx["model"]
period = de.compute_period(bundle, ctx["report_date_list"], ctx["sector_field"])
rcf = period["return_contribution_final"]
temp_return_final = bundle["temp_return_final"]
models = period["columns"]
top_column = period["top_column"]

st.info(
    f"**모델 구조** — 상위: `{top_column}` "
    f"({ctx['display_names'].get(top_column, top_column)}) · 하위 {len(models)-1}개.\n\n"
    "원본 코드에서 상위 모델은 하위 모델의 가중합이 **아니다**. "
    "각 모델이 독립적인 active weight 시계열이며 동일한 분해식을 각각 적용한다 "
    "(Aggregation 없음). 따라서 하위 모델 기여도의 합은 상위 모델 성과와 일치하지 않는다.",
    icon="ℹ️",
)

tabs = st.tabs(["Model Performance", "모델 간 비교", "누적 성과", "기여도 분해"])

# ---------------------------------------------------------------------------
with tabs[0]:
    anchors = dict(ctx["anchors"])
    end_date = ctx["report_date_list"][-1]
    rows = {"WTD": performance.period_total_return(
        temp_return_final, ctx["report_date_list"], models + ["bm"])}
    for key, anchor in anchors.items():
        if anchor is None or key == "WTD":
            continue
        rows[key] = performance.period_return_by_anchor(
            temp_return_final, anchor, end_date, models + ["bm"])

    table = pd.DataFrame(rows)
    excess = table.loc[models].sub(table.loc["bm"], axis=1)
    excess.columns = [f"{c} 초과" for c in excess.columns]

    out = table.loc[models].join(excess)
    out["Contribution(active)"] = rcf.loc["active"].astype(float)
    out.index = [ctx["display_names"].get(i, i) for i in out.index]
    st.dataframe(out.style.format("{:.2%}"), use_container_width=True, height=440)
    ui.download_buttons(out, "model_performance", "mdl_perf")

    st.markdown("##### Model Contribution")
    series = rcf.loc["active"].astype(float)
    series.index = [ctx["display_names"].get(i, i) for i in series.index]
    st.plotly_chart(ui.bar_chart(series.sort_values(), height=420, horizontal=True),
                    use_container_width=True)

# ---------------------------------------------------------------------------
with tabs[1]:
    picked = st.multiselect(
        "비교할 모델", models,
        default=[model] + [m for m in ctx["sub_models"]][:5],
        format_func=lambda m: ctx["display_names"].get(m, m),
        key="mdl_compare_pick")
    if not picked:
        st.info("모델을 하나 이상 선택하세요.")
    else:
        include_vol = bool(ctx["config"].optional_metrics.get("volatility", True))
        table = model_analysis.model_comparison_table(
            temp_return_final, ctx["report_date_list"], picked,
            return_contribution_final=rcf, include_volatility=include_vol)
        table.index = [ctx["display_names"].get(i, i) for i in table.index]
        st.dataframe(table.style.format("{:.3%}"), use_container_width=True)
        if include_vol:
            st.caption("`volatility(optional)` 은 기존 코드에 없는 참고 지표다 "
                       "(일별 초과 아닌 모델 수익률의 연율화 표준편차).")
        ui.download_buttons(table, "model_comparison", "mdl_cmp")

        left, right = st.columns(2)
        with left:
            st.plotly_chart(ui.bar_chart(table["excess_return"].astype(float).sort_values(),
                            "Excess Return", height=380, horizontal=True),
                            use_container_width=True)
        with right:
            parts = [c for c in ("specific", "risk_factor", "industry_factor",
                                 "market_timing", "country") if c in table.columns]
            if parts:
                st.dataframe(table[parts].style.format("{:.3%}"),
                             use_container_width=True, height=380)

# ---------------------------------------------------------------------------
with tabs[2]:
    picked = st.multiselect(
        "모델", models, default=[model] + [m for m in ctx["sub_models"]][:5],
        format_func=lambda m: ctx["display_names"].get(m, m), key="mdl_curve_pick")
    relative = st.checkbox("Benchmark 대비 (초과 누적)", value=True, key="mdl_curve_rel")
    if picked:
        curve = model_analysis.model_cumulative_returns(
            temp_return_final, ctx["report_date_list"], picked, relative_to_bm=relative)
        plot = curve[picked] if not relative else curve
        plot = plot.rename(columns={**ctx["display_names"], "bm": "Benchmark"})
        st.plotly_chart(
            ui.line_chart(plot, "Sub-model 누적 " + ("초과성과" if relative else "성과"),
                          height=470,
                          highlight=ctx["display_names"].get(model, model),
                          bm_column=None if relative else "Benchmark"),
            use_container_width=True)
        ui.download_buttons(plot, "model_cumulative", "mdl_curve")

# ---------------------------------------------------------------------------
with tabs[3]:
    rows = [r for r in ctx["config"].attribution["plot_rows"] if r in rcf.index]
    table = rcf.loc[rows].astype(float)
    table.columns = [ctx["display_names"].get(c, c) for c in table.columns]
    st.dataframe(table.style.format("{:.3%}"), use_container_width=True, height=400)
    ui.download_buttons(table, "model_attribution", "mdl_attr")

    st.markdown("---")
    st.markdown("##### 모델 Drill-down — 하위 모델이 왜 부진했는가")
    picked = st.selectbox("모델", models, index=models.index(model),
                          format_func=lambda m: ctx["display_names"].get(m, m),
                          key="mdl_drill")
    ui.metric_row([
        ("Total", fmt_pct(float(rcf.loc["total", picked]))),
        ("Benchmark", fmt_pct(float(rcf.loc["bm", picked]))),
        ("Active", fmt_pct(float(rcf.loc["active", picked]))),
        ("Specific", fmt_pct(float(rcf.loc["specific", picked]))),
        ("Risk Factor", fmt_pct(float(rcf.loc["risk_factor", picked]))),
        ("Industry Factor", fmt_pct(float(rcf.loc["industry_factor", picked]))),
    ])

    stocks = de.stock_table(bundle, period, picked)
    top_n = int(ctx["config"].ui.get("top_n", 10))
    top, bottom = de.top_bottom(stocks, "contribution", top_n)

    left, right = st.columns(2)
    with left:
        st.markdown(f"###### Top {top_n} Positive Contribution")
        view = top.set_index(top["name"].fillna(top.index.to_series()))[
            ["avg_active_weight", "period_return", "contribution"]]
        view.columns = ["평균 Active W", "기간수익률", "기여도"]
        st.dataframe(view.style.format(
            {"평균 Active W": "{:.2%}", "기간수익률": "{:.2%}", "기여도": "{:.3%}"}),
            use_container_width=True, height=380)
    with right:
        st.markdown(f"###### Top {top_n} Negative Contribution")
        view = bottom.set_index(bottom["name"].fillna(bottom.index.to_series()))[
            ["avg_active_weight", "period_return", "contribution"]]
        view.columns = ["평균 Active W", "기간수익률", "기여도"]
        st.dataframe(view.style.format(
            {"평균 Active W": "{:.2%}", "기간수익률": "{:.2%}", "기여도": "{:.3%}"}),
            use_container_width=True, height=380)

    with st.expander(f"{ctx['display_names'].get(picked, picked)} Holdings (종료일 기준)"):
        from src import portfolio as pf

        holdings = pf.active_weight_table(
            bundle["final_mp"], ctx["report_date_list"][-1], picked,
            contribution=stocks["contribution"], info_stock=bundle.get("info_stock"))
        holdings = holdings[holdings["portfolio_weight"].abs() > 0]
        st.dataframe(
            holdings.style.format({
                "portfolio_weight": "{:.3%}", "benchmark_weight": "{:.3%}",
                "active_weight": "{:.3%}", "active_contribution": "{:.4%}"}),
            use_container_width=True, height=420)
        ui.download_buttons(holdings, f"holdings_{picked}", "mdl_holdings")
