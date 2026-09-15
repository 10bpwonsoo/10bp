"""Attribution — 성과 분해. 주간 성과회의 핵심 화면."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src import attribution, dashboard_engine as de, ui  # noqa: E402
from src.utils import fmt_pct  # noqa: E402

ui.bootstrap("Attribution")
ctx = ui.sidebar()
if ctx is None:
    st.stop()

ui.header(ctx, "PERFORMANCE ATTRIBUTION")
ui.warn_if_validation_failed(ctx)

bundle = ctx["bundle"]
model = ctx["model"]
period = de.compute_period(bundle, ctx["report_date_list"], ctx["sector_field"])
rcf = period["return_contribution_final"]
final_mp = bundle["final_mp"]
top_n = int(ctx["config"].ui.get("top_n", 10))

st.markdown(
    """
    ```
    Portfolio Return
        ├─ Market Timing        (전일 active weight × active pred beta × 당일 BM 수익률)
        ├─ Risk Factor          (전일 active weight × 팩터 exposure × 당일 팩터 수익률)
        ├─ Industry Factor      (동일, 업종 팩터)
        ├─ Country              (전일 active weight × 당일 country 팩터 수익률)
        └─ Specific             (active − 위 4개 합)
    ```
    """
)

tabs = st.tabs(["항목별", "종목별", "섹터별", "Factor / Industry", "기여도 추이"])

# ---------------------------------------------------------------------------
# 1. 항목별
# ---------------------------------------------------------------------------
with tabs[0]:
    rows = [r for r in ctx["config"].attribution["plot_rows"] if r in rcf.index]
    left, right = st.columns([1.2, 1])
    with left:
        st.plotly_chart(
            ui.bar_chart(rcf.loc[rows, model].astype(float),
                         f"{ctx['display_names'].get(model, model)} 성과 기여도", height=400),
            use_container_width=True)
    with right:
        summary_rows = [r for r in ctx["config"].attribution["summary_rows"] if r in rcf.index]
        st.dataframe(
            rcf.loc[summary_rows, model].astype(float).to_frame("기여도")
               .style.format({"기여도": "{:.3%}"}),
            use_container_width=True, height=400)

    st.markdown("##### 전 모델 × 항목")
    table = rcf.loc[rows].astype(float)
    table.columns = [ctx["display_names"].get(c, c) for c in table.columns]
    st.dataframe(table.style.format("{:.3%}"), use_container_width=True)
    ui.download_buttons(table, "attribution_by_item", "attr_item")

    st.caption(
        "`selection` / `allocation` 은 q_sector 기준, "
        "`selection_new` / `allocation_new` 는 new_sector(수기 조정) 기준이다. "
        "둘 다 `active` 를 두 가지 방식으로 나눈 것이므로 서로 더하지 않는다."
    )

# ---------------------------------------------------------------------------
# 2. 종목별
# ---------------------------------------------------------------------------
with tabs[1]:
    element = st.selectbox(
        "분해 항목", ["active", "specific", "market_timing", "country",
                     "risk_factor", "industry_factor"],
        format_func=lambda v: {"active": "Active (전체)", "specific": "Specific",
                               "market_timing": "Market Timing", "country": "Country",
                               "risk_factor": "Risk Factor (합)",
                               "industry_factor": "Industry Factor (합)"}[v],
        key="attr_stock_element")

    stocks = de.stock_table(bundle, period, model, element=element)
    top, bottom = de.top_bottom(stocks, "contribution", top_n)
    combined = pd.concat([bottom, top])
    combined = combined.set_index(combined["name"].fillna(combined.index.to_series()))

    st.plotly_chart(
        ui.contribution_weight_chart(
            combined, "contribution", "avg_active_weight",
            f"Top / Bottom {top_n} — {element}", height=460),
        use_container_width=True)

    left, right = st.columns(2)
    with left:
        st.markdown(f"###### Top {top_n} Contributors")
        view = top.set_index(top["name"].fillna(top.index.to_series()))[
            ["avg_weight", "period_return", "contribution"]]
        view.columns = ["평균비중", "기간수익률", "기여도"]
        st.dataframe(view.style.format(
            {"평균비중": "{:.2%}", "기간수익률": "{:.2%}", "기여도": "{:.3%}"}),
            use_container_width=True, height=380)
    with right:
        st.markdown(f"###### Bottom {top_n} Contributors")
        view = bottom.set_index(bottom["name"].fillna(bottom.index.to_series()))[
            ["avg_weight", "period_return", "contribution"]]
        view.columns = ["평균비중", "기간수익률", "기여도"]
        st.dataframe(view.style.format(
            {"평균비중": "{:.2%}", "기간수익률": "{:.2%}", "기여도": "{:.3%}"}),
            use_container_width=True, height=380)

    total = float(stocks["contribution"].astype(float).sum())
    st.caption(
        f"종목 기여도 합 **{fmt_pct(total, 4)}** vs 기간 active "
        f"**{fmt_pct(float(rcf.loc['active', model]), 4)}** "
        f"(차이 {abs(total - float(rcf.loc['active', model]))*1e4:.4f}bp)"
        if element == "active" else ""
    )
    ui.download_buttons(stocks, f"stock_contribution_{element}", "attr_stock")

# ---------------------------------------------------------------------------
# 3. 섹터별
# ---------------------------------------------------------------------------
with tabs[2]:
    sector_compare = period["sector_compare_final"]
    if sector_compare is None:
        st.info(period["sector_note"] or "섹터 데이터가 없습니다.")
    else:
        suffix = period["sector_suffix"]
        alloc_col, select_col = f"{model}_allocation{suffix}", f"{model}_selection{suffix}"
        table = sector_compare[[select_col, alloc_col]].astype(float)
        table.columns = ["Selection", "Allocation"]
        table["합계"] = table.sum(axis=1)
        table = table.sort_values("합계")

        st.plotly_chart(ui.bar_chart(table["합계"],
                        f"업종별 기여도 ({period['sector_field']})", height=430,
                        horizontal=True), use_container_width=True)
        st.dataframe(table.style.format("{:.3%}"), use_container_width=True)
        ui.download_buttons(table, "sector_allocation_selection", "attr_sector")

        st.markdown("---")
        st.markdown("##### 업종 Drill-down")
        sectors = sorted(str(s) for s in table.index)
        picked = st.selectbox("업종 선택", sectors, key="attr_sector_pick")

        sector_field = period["sector_field"]
        window = final_mp.loc[(ctx["report_date_list"], slice(None)), :]
        members = sorted(set(
            window[window[sector_field].astype(str) == picked]
            .index.get_level_values("item")))
        excluded = ctx["config"].ui.get("excluded_items_in_sector_view", []) or []
        members = [m for m in members if m not in excluded]

        if not members:
            st.info("해당 업종 종목이 없습니다.")
        else:
            contribution = attribution.stock_contribution(
                final_mp, period["betalog_final"], ctx["report_date_list"],
                members, [model], element="active")[model].astype(float)
            info = bundle.get("info_stock")
            frame = contribution.to_frame("contribution")
            if info is not None:
                frame["name"] = info["name_stock"].reindex(frame.index)
            last = ctx["report_date_list"][-1]
            frame["avg_active_weight"] = (
                final_mp.loc[(ctx["report_date_list"], members), model]
                .groupby("item", group_keys=False).mean().reindex(frame.index))
            frame = frame.sort_values("contribution")
            frame = frame.set_index(frame.get("name", pd.Series(frame.index, index=frame.index))
                                    .fillna(pd.Series(frame.index, index=frame.index)))
            st.plotly_chart(
                ui.contribution_weight_chart(frame, "contribution", "avg_active_weight",
                                             f"{picked} 내 종목 기여도", height=420),
                use_container_width=True)
            if excluded:
                st.caption(f"원본 코드와 동일하게 제외한 종목: {', '.join(excluded)}")

# ---------------------------------------------------------------------------
# 4. Factor / Industry
# ---------------------------------------------------------------------------
with tabs[3]:
    kind = st.radio("구분", ["Risk Factor", "Industry Factor"], horizontal=True,
                    key="attr_factor_kind")
    factors = (period["list_bpm_factor"] if kind == "Risk Factor"
               else period["list_bpm_sector"])
    if not factors:
        st.info("스냅샷 manifest 에 팩터 목록이 없습니다.")
    else:
        scale = period["betalog_final"].loc[:, model].shift(-1)
        values = {}
        for factor in factors:
            column = f"{factor}_contribution_{model}"
            if column not in final_mp.columns:
                continue
            values[factor] = float((
                final_mp.loc[(ctx["report_date_list"], slice(None)), column]
                .groupby("date", group_keys=False).sum() * scale).sum())
        if not values:
            st.info("스냅샷에 팩터별 기여도 컬럼이 없습니다. "
                    "export 시 slim 옵션으로 제외되었는지 확인하세요.")
        else:
            series = pd.Series(values).sort_values()
            st.plotly_chart(
                ui.bar_chart(series, f"{kind} 기여도", height=460, horizontal=True,
                             tickformat=".3%"),
                use_container_width=True)
            st.dataframe(series.to_frame("기여도").style.format({"기여도": "{:.4%}"}),
                         use_container_width=True, height=320)
            total = series.sum()
            row = "risk_factor" if kind == "Risk Factor" else "industry_factor"
            st.caption(
                f"합계 **{fmt_pct(total, 4)}** vs `{row}` "
                f"**{fmt_pct(float(rcf.loc[row, model]), 4)}**")
            ui.download_buttons(series.to_frame("contribution"),
                                f"{row}_contribution", "attr_factor")

# ---------------------------------------------------------------------------
# 5. 기여도 추이
# ---------------------------------------------------------------------------
with tabs[4]:
    compare_final = period["compare_final"]
    if compare_final is None:
        st.info("compare_final 이 스냅샷에 없습니다.")
    else:
        available = sorted(set(compare_final.index.get_level_values("contribution")))
        view = st.radio("보기", ["항목별 (선택 모델)", "모델별 (선택 항목)"],
                        horizontal=True, key="attr_trend_view")
        if view == "항목별 (선택 모델)":
            defaults = [c for c in ["active_contribution", "specific_contribution",
                                    "market_timing_contribution", "risk_factor_contribution",
                                    "industry_factor_contribution", "country_contribution"]
                        if c in available]
            picked = st.multiselect("항목", available, default=defaults,
                                    key="attr_trend_items")
            if picked:
                plot = compare_final.loc[(slice(None), picked), model].unstack()
                plot.columns = [c.replace("_contribution", "") for c in plot.columns]
                st.plotly_chart(
                    ui.line_chart(plot, f"{ctx['display_names'].get(model, model)} 항목별 누적 기여도",
                                  height=460), use_container_width=True)
                ui.download_buttons(plot, "contribution_trend_items", "attr_trend_i")
        else:
            default_item = "active_contribution" if "active_contribution" in available else available[0]
            item = st.selectbox("항목", available,
                                index=available.index(default_item), key="attr_trend_item")
            plot = compare_final.xs(item, level=1)
            plot.columns = [ctx["display_names"].get(c, c) for c in plot.columns]
            st.plotly_chart(
                ui.line_chart(plot, f"{item} 모델별 추이", height=460,
                              highlight=ctx["display_names"].get(model, model)),
                use_container_width=True)
            ui.download_buttons(plot, f"contribution_trend_{item}", "attr_trend_m")
