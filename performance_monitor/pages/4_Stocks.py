"""Stocks — 종목 분석 / Active Weight 분석 / 종목 상세."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src import dashboard_engine as de, portfolio as pf, ui  # noqa: E402
from src.utils import fmt_pct  # noqa: E402

ui.bootstrap("Stocks")
ctx = ui.sidebar()
if ctx is None:
    st.stop()

ui.header(ctx, "STOCK ANALYSIS")

bundle = ctx["bundle"]
model = ctx["model"]
final_mp = bundle["final_mp"]
info_stock = bundle.get("info_stock")
period = de.compute_period(bundle, ctx["report_date_list"], ctx["sector_field"])
report_date_list = ctx["report_date_list"]
stocks = de.stock_table(bundle, period, model)
top_n = int(ctx["config"].ui.get("top_n", 10))

FORMATS = {
    "start_weight": "{:.3%}", "end_weight": "{:.3%}", "avg_weight": "{:.3%}",
    "bm_weight_start": "{:.3%}", "bm_weight_end": "{:.3%}",
    "active_weight_start": "{:.3%}", "active_weight_end": "{:.3%}",
    "avg_active_weight": "{:.3%}", "period_return": "{:.2%}", "contribution": "{:.4%}",
}
LABELS = {
    "name": "종목", "start_weight": "시작비중", "end_weight": "종료비중",
    "avg_weight": "평균비중", "bm_weight_end": "BM비중", "active_weight_end": "Active W",
    "avg_active_weight": "평균 Active W", "period_return": "기간수익률",
    "contribution": "기여도",
}

tabs = st.tabs(["종목 목록", "Active Weight", "종목 상세"])

# ---------------------------------------------------------------------------
with tabs[0]:
    col1, col2, col3 = st.columns([2, 1, 1])
    query = col1.text_input("종목 검색 (종목명 / 코드)", key="stk_query")
    sector_field = ctx["sector_field"]
    sectors = ["(전체)"] + sorted(
        set(final_mp.loc[(report_date_list, slice(None)), sector_field].astype(str).dropna()))
    sector_pick = col2.selectbox(f"{sector_field} 필터", sectors, key="stk_sector")
    holdings_only = col3.checkbox("보유 종목만", value=True, key="stk_holdings")

    view = stocks.copy()
    if holdings_only:
        view = view[(view["end_weight"].abs() > 0) | (view["avg_weight"].abs() > 0)]
    if sector_pick != "(전체)":
        last_sector = final_mp.loc[(report_date_list[-1], slice(None)), sector_field] \
            .droplevel("date").astype(str)
        view = view[view.index.map(last_sector).eq(sector_pick)]
    if query:
        needle = query.strip().lower()
        mask = view.index.str.lower().str.contains(needle)
        if "name" in view.columns:
            mask = mask | view["name"].fillna("").str.lower().str.contains(needle)
        view = view[mask]

    sort_by = st.selectbox(
        "정렬", ["contribution", "end_weight", "active_weight_end", "period_return"],
        format_func=lambda c: LABELS.get(c, c), key="stk_sort")
    view = view.sort_values(sort_by, ascending=False)

    columns = [c for c in ["name", "start_weight", "end_weight", "avg_weight",
                           "bm_weight_end", "active_weight_end", "period_return",
                           "contribution"] if c in view.columns]
    st.caption(f"{len(view)} 종목")
    st.dataframe(
        view[columns].rename(columns=LABELS)
            .style.format({LABELS.get(c, c): FORMATS[c] for c in columns if c in FORMATS}),
        use_container_width=True, height=560)
    ui.download_buttons(view[columns], "stock_analysis", "stk_list")

# ---------------------------------------------------------------------------
with tabs[1]:
    st.markdown("##### Benchmark 대비 Overweight / Underweight")
    active = pf.active_weight_table(
        final_mp, report_date_list[-1], model,
        contribution=stocks["contribution"], info_stock=info_stock)
    active = active[(active["active_weight"].abs() > 1e-12)]

    left, right = st.columns(2)
    with left:
        st.markdown(f"###### Top {top_n} Overweight")
        over = active.head(top_n)
        show = over.set_index(over["name"].fillna(over.index.to_series()))
        st.plotly_chart(ui.bar_chart(show["active_weight"].astype(float), height=300,
                                     horizontal=True, tickformat=".2%"),
                        use_container_width=True)
        st.dataframe(
            show[["portfolio_weight", "benchmark_weight", "active_weight",
                  "active_contribution"]].style.format("{:.3%}"),
            use_container_width=True, height=330)
    with right:
        st.markdown(f"###### Top {top_n} Underweight")
        under = active.tail(top_n).sort_values("active_weight")
        show = under.set_index(under["name"].fillna(under.index.to_series()))
        st.plotly_chart(ui.bar_chart(show["active_weight"].astype(float), height=300,
                                     horizontal=True, tickformat=".2%"),
                        use_container_width=True)
        st.dataframe(
            show[["portfolio_weight", "benchmark_weight", "active_weight",
                  "active_contribution"]].style.format("{:.3%}"),
            use_container_width=True, height=330)

    summary = pf.portfolio_weight_sum(final_mp, report_date_list[-1], model)
    st.caption(
        f"종료일 기준 · Portfolio Weight 합 {summary['total_weight_sum']:.4%} · "
        f"BM Weight 합 {summary['bm_weight_sum']:.4%} · "
        f"Active Weight 합 {summary['active_weight_sum']:.4%} · "
        f"보유 {summary['n_holdings']}종목")
    ui.download_buttons(active, "active_weight", "stk_active")

# ---------------------------------------------------------------------------
with tabs[2]:
    labels = {}
    for item in stocks.index:
        name = stocks.loc[item, "name"] if "name" in stocks.columns else None
        labels[item] = f"{name} ({item})" if isinstance(name, str) else item
    default = stocks["contribution"].astype(float).abs().idxmax()
    picked = st.selectbox("종목", list(stocks.index),
                          index=list(stocks.index).index(default),
                          format_func=lambda i: labels.get(i, i), key="stk_detail")

    row = stocks.loc[picked]
    ui.metric_row([
        ("기간 수익률", fmt_pct(row.get("period_return"))),
        ("기여도", fmt_pct(row.get("contribution"), 4)),
        ("시작비중", fmt_pct(row.get("start_weight"), 3)),
        ("종료비중", fmt_pct(row.get("end_weight"), 3)),
        ("BM 비중", fmt_pct(row.get("bm_weight_end"), 3)),
        ("Active Weight", fmt_pct(row.get("active_weight_end"), 3)),
    ])

    series = final_mp.loc[(report_date_list, picked), :].droplevel("item")
    left, right = st.columns(2)
    with left:
        weights = pd.DataFrame({
            "Portfolio Weight": series[f"total_{model}"],
            "Benchmark Weight": series["bm"],
            "Active Weight": series[model],
        })
        st.plotly_chart(ui.line_chart(weights, "비중 추이", height=360,
                                      bm_column="Benchmark Weight"),
                        use_container_width=True)
    with right:
        if "return_d" in series.columns:
            cum = pd.DataFrame({
                "종목 누적수익률": (1 + series["return_d"].fillna(0)).cumprod() - 1,
                "Benchmark": (1 + bundle["temp_return_final"].loc[report_date_list, "bm"]).cumprod() - 1,
            })
            st.plotly_chart(ui.line_chart(cum, "누적 수익률", height=360,
                                          bm_column="Benchmark"),
                            use_container_width=True)

    contribution_cols = [c for c in series.columns
                         if c.endswith(f"_contribution_{model}")]
    if contribution_cols:
        scale = period["betalog_final"].loc[:, model].shift(-1)
        values = {c.replace(f"_contribution_{model}", ""):
                  float((series[c] * scale).sum()) for c in contribution_cols}
        detail = pd.Series(values)
        detail = detail[detail.abs() > 1e-15].sort_values()
        if not detail.empty:
            st.markdown("###### 항목별 기여도 분해")
            st.plotly_chart(ui.bar_chart(detail, height=340, horizontal=True,
                                         tickformat=".4%"),
                            use_container_width=True)

    with st.expander("일별 상세"):
        columns = [c for c in [f"total_{model}", model, "bm", "return_d",
                               f"active_contribution_{model}"] if c in series.columns]
        detail = series[columns].copy()
        detail.index = [str(d)[:10] for d in detail.index]
        st.dataframe(detail.style.format("{:.5%}"), use_container_width=True, height=320)
