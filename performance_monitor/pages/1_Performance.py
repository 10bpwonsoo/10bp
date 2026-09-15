"""Performance — 누적 성과 / 기간별 성과."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src import dashboard_engine as de  # noqa: E402
from src import model_analysis, performance, ui  # noqa: E402
from src.utils import fmt_pct  # noqa: E402

ui.bootstrap("Performance")
ctx = ui.sidebar()
if ctx is None:
    st.stop()

ui.header(ctx, "PERFORMANCE")

bundle = ctx["bundle"]
model = ctx["model"]
period = de.compute_period(bundle, ctx["report_date_list"], ctx["sector_field"])
rcf = period["return_contribution_final"]
temp_return_final = bundle["temp_return_final"]

# ---------------------------------------------------------------------------
# Cumulative Performance
# ---------------------------------------------------------------------------
st.markdown("#### Cumulative Performance")
ui.metric_row([
    ("MP Return", fmt_pct(float(rcf.loc["total", model]))),
    ("Benchmark", fmt_pct(float(rcf.loc["bm", model]))),
    ("Excess Return", fmt_pct(float(rcf.loc["active", model]))),
])

curve = period["cumulative"]
mode = st.radio("표시", ["MP vs Benchmark", "Excess Return", "전 모델"],
                horizontal=True, key="perf_mode")

if mode == "MP vs Benchmark":
    plot = curve[[model, "bm"]].rename(
        columns={model: ctx["display_names"].get(model, model), "bm": "Benchmark"})
    plot["Excess"] = curve[model] - curve["bm"]
    st.plotly_chart(ui.line_chart(plot, height=430, bm_column="Benchmark"),
                    use_container_width=True)
elif mode == "Excess Return":
    selected = [model] + [m for m in ctx["sub_models"]]
    plot = curve[selected].sub(curve["bm"], axis=0)
    plot.columns = [ctx["display_names"].get(c, c) for c in plot.columns]
    st.plotly_chart(
        ui.line_chart(plot, "Benchmark 대비 누적 초과성과", height=430,
                      highlight=ctx["display_names"].get(model, model)),
        use_container_width=True)
else:
    plot = curve.rename(columns={**ctx["display_names"], "bm": "Benchmark"})
    st.plotly_chart(ui.line_chart(plot, height=470, bm_column="Benchmark"),
                    use_container_width=True)

ui.download_buttons(curve, "cumulative_performance", "perf_curve")

st.markdown("---")

# ---------------------------------------------------------------------------
# 기간 성과
# ---------------------------------------------------------------------------
st.markdown("#### 기간 성과")
anchors = dict(ctx["anchors"])
if not anchors:
    st.info("스냅샷에 비교기간 기준일(anchors) 이 없습니다. "
            "노트북의 WORKDATE_MAST_TB 조회 결과를 export 하면 표시됩니다.")
else:
    st.caption(
        "기준일(anchor) 은 원본 노트북의 `AQUANT.dbo.WORKDATE_MAST_TB` 조회 결과다. "
        "각 기간 수익률은 기준일 **다음** 영업일부터 누적한다 (원본 규칙과 동일)."
    )
    end_date = ctx["report_date_list"][-1]
    rows = {}
    for key, anchor in anchors.items():
        if anchor is None:
            continue
        if key == "WTD":
            values = performance.period_total_return(
                temp_return_final, ctx["report_date_list"], period["columns"] + ["bm"])
        else:
            values = performance.period_return_by_anchor(
                temp_return_final, anchor, end_date, period["columns"] + ["bm"])
        rows[key] = values

    table = pd.DataFrame(rows)
    excess = table.loc[period["columns"]].sub(table.loc["bm"], axis=1)

    tab1, tab2, tab3 = st.tabs(["Total Return", "Excess Return", "선택 모델"])
    with tab1:
        show = table.copy()
        show.index = [ctx["display_names"].get(i, i) if i != "bm" else "Benchmark"
                      for i in show.index]
        st.dataframe(show.style.format("{:.2%}"), use_container_width=True)
        ui.download_buttons(show, "period_total_return", "perf_period_total")
    with tab2:
        show = excess.copy()
        show.index = [ctx["display_names"].get(i, i) for i in show.index]
        st.dataframe(show.style.format("{:.2%}"), use_container_width=True)
        st.plotly_chart(ui.bar_chart(show.loc[
            ctx["display_names"].get(model, model)], "선택 모델 기간별 초과성과", height=330),
            use_container_width=True)
        ui.download_buttons(show, "period_excess_return", "perf_period_excess")
    with tab3:
        single = pd.DataFrame({
            "Total": table.loc[model],
            "Benchmark": table.loc["bm"],
            "Excess": excess.loc[model],
        })
        st.dataframe(single.style.format("{:.2%}"), use_container_width=True)
        st.plotly_chart(ui.bar_chart(single["Excess"], "기간별 초과성과", height=330),
                        use_container_width=True)

st.markdown("---")

# ---------------------------------------------------------------------------
# 일별 성과
# ---------------------------------------------------------------------------
with st.expander("일별 수익률 상세", expanded=False):
    daily = temp_return_final.loc[ctx["report_date_list"]][[model, "bm"]].copy()
    daily.columns = [ctx["display_names"].get(model, model), "Benchmark"]
    daily["Excess(일별차)"] = daily.iloc[:, 0] - daily.iloc[:, 1]
    daily.index = [str(d)[:10] for d in daily.index]
    st.dataframe(daily.style.format("{:.4%}"), use_container_width=True, height=360)
    st.caption("첫 행은 기준일이며 기간 성과 계산에서 제외된다 (원본 `report_date_list[1:]` 규칙).")
    ui.download_buttons(daily, "daily_returns", "perf_daily")
