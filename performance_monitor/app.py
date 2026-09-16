"""MP Performance Monitor — 메인 Dashboard.

실행::

    streamlit run app.py          # http://localhost:8501

사내 서버 배포::

    streamlit run app.py --server.port 8501 --server.address 0.0.0.0 \
        --server.baseUrlPath performance
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src import dashboard_engine as de  # noqa: E402
from src import model_analysis, ui  # noqa: E402
from src.utils import fmt_pct  # noqa: E402

ui.bootstrap("Dashboard")
ctx = ui.sidebar()
if ctx is None:
    st.stop()

ui.header(ctx)
ui.warn_if_validation_failed(ctx)

bundle = ctx["bundle"]
model = ctx["model"]
period = de.compute_period(bundle, ctx["report_date_list"], ctx["sector_field"])
rcf = period["return_contribution_final"]

# ---------------------------------------------------------------------------
# KPI
# ---------------------------------------------------------------------------
total = float(rcf.loc["total", model])
bm = float(rcf.loc["bm", model])
active = float(rcf.loc["active", model])

ui.metric_row([
    ("MP Return", fmt_pct(total)),
    ("Benchmark", fmt_pct(bm)),
    ("Excess Return", fmt_pct(active), fmt_pct(active),
     "total − bm (원본 return_contribution_final.loc['active'])"),
    ("Specific", fmt_pct(float(rcf.loc["specific", model])),
     None, "active − market_timing − risk_factor − industry_factor − country"),
    ("Risk Factor", fmt_pct(float(rcf.loc["risk_factor", model]))),
    ("Industry Factor", fmt_pct(float(rcf.loc["industry_factor", model]))),
])

optional = ctx["config"].optional_metrics
if any(optional.get(k) for k in ("tracking_error", "hit_ratio", "turnover")):
    st.caption(
        "아래 지표는 **기존 코드에 없는 Optional 지표**입니다 "
        "(config.yaml `optional_metrics` 로 켜짐). 원본 노트북과 대조 대상이 아닙니다."
    )
    from src import optional_metrics as om

    om.render_optional_kpis(ctx, period, model, optional)

st.markdown("---")

# ---------------------------------------------------------------------------
# WEEKLY PERFORMANCE SUMMARY
# ---------------------------------------------------------------------------
st.markdown(f"#### PERFORMANCE SUMMARY — {ctx['preset_label']}")
left, right = st.columns([1.15, 1])

with left:
    curve = period["cumulative"]
    plot = curve[[model, "bm"]].rename(
        columns={model: ctx["display_names"].get(model, model), "bm": "Benchmark"}
    )
    plot["Excess"] = curve[model] - curve["bm"]
    st.plotly_chart(
        ui.line_chart(plot, f"누적 성과 (MP / Benchmark / Excess) · {ctx['preset_label']}", height=330,
                      bm_column="Benchmark"),
        use_container_width=True,
    )

with right:
    stocks = de.stock_table(bundle, period, model)
    top, bottom = de.top_bottom(stocks, "contribution", 1)
    best_model, worst_model = model_analysis.best_worst_model(
        rcf, "active", exclude=[ctx["top_column"]]
    )

    def _name(frame):
        if frame.empty:
            return "-", 0.0
        row = frame.iloc[0]
        return (row.get("name") or frame.index[0]), float(row["contribution"])

    top_name, top_value = _name(top)
    bot_name, bot_value = _name(bottom)

    summary = pd.DataFrame(
        [
            ["Top Contributor", str(top_name), fmt_pct(top_value)],
            ["Bottom Contributor", str(bot_name), fmt_pct(bot_value)],
            ["Best Model",
             ctx["display_names"].get(best_model[0], best_model[0]) if best_model else "-",
             fmt_pct(best_model[1]) if best_model else "-"],
            ["Worst Model",
             ctx["display_names"].get(worst_model[0], worst_model[0]) if worst_model else "-",
             fmt_pct(worst_model[1]) if worst_model else "-"],
        ],
        columns=["구분", "대상", "값"],
    )
    st.dataframe(summary, hide_index=True, use_container_width=True, height=180)

    active_w = stocks.dropna(subset=["active_weight_end"]).sort_values(
        "active_weight_end", ascending=False
    )
    ow = active_w.head(3)[["name", "active_weight_end"]]
    uw = active_w.tail(3)[["name", "active_weight_end"]].sort_values("active_weight_end")
    aw = pd.concat([
        ow.assign(구분="Top Overweight"), uw.assign(구분="Top Underweight")
    ])
    aw = aw.rename(columns={"name": "종목", "active_weight_end": "Active Weight"})
    st.dataframe(
        aw[["구분", "종목", "Active Weight"]].style.format({"Active Weight": "{:.2%}"}),
        hide_index=True, use_container_width=True, height=250,
    )

st.markdown("---")

# ---------------------------------------------------------------------------
# 성과 분해 + Top/Bottom
# ---------------------------------------------------------------------------
left, right = st.columns([1, 1.2])

with left:
    st.markdown("##### 성과 기여도 (항목별)")
    rows = [r for r in ctx["config"].attribution["plot_rows"] if r in rcf.index]
    breakdown = rcf.loc[rows, model].astype(float)
    st.plotly_chart(ui.bar_chart(breakdown, height=360), use_container_width=True)
    st.dataframe(
        breakdown.to_frame("기여도").style.format({"기여도": "{:.3%}"}),
        use_container_width=True, height=330,
    )

with right:
    st.markdown("##### 종목별 기여도 Top / Bottom 10")
    top_n = int(ctx["config"].ui.get("top_n", 10))
    top, bottom = de.top_bottom(stocks, "contribution", top_n)
    combined = pd.concat([bottom, top])
    combined = combined.set_index(combined["name"].fillna(combined.index.to_series()))
    st.plotly_chart(
        ui.contribution_weight_chart(combined, "contribution", "avg_active_weight",
                                     height=420),
        use_container_width=True,
    )
    view = combined[["avg_weight", "period_return", "contribution"]].rename(
        columns={"avg_weight": "평균비중", "period_return": "기간수익률",
                 "contribution": "기여도"}
    )
    st.dataframe(
        view.style.format({"평균비중": "{:.2%}", "기간수익률": "{:.2%}", "기여도": "{:.3%}"}),
        use_container_width=True, height=260,
    )

st.markdown("---")

# ---------------------------------------------------------------------------
# 모델별 요약 + 섹터
# ---------------------------------------------------------------------------
left, right = st.columns(2)

with left:
    st.markdown("##### 모델별 Active (기간)")
    model_active = rcf.loc["active"].astype(float)
    model_active.index = [ctx["display_names"].get(i, i) for i in model_active.index]
    st.plotly_chart(
        ui.bar_chart(model_active.sort_values(), height=380, horizontal=True),
        use_container_width=True,
    )

with right:
    label = "new_sector (수기 조정)" if ctx["sector_field"] == "new_sector" else "q_sector"
    st.markdown(f"##### 업종별 Allocation / Selection — {label}")
    sector_compare = period["sector_compare_final"]
    if sector_compare is None:
        st.info(period["sector_note"] or "섹터 데이터 없음")
    else:
        suffix = period["sector_suffix"]
        alloc_col, select_col = f"{model}_allocation{suffix}", f"{model}_selection{suffix}"
        table = sector_compare[[select_col, alloc_col]].astype(float)
        table["합계"] = table[select_col] + table[alloc_col]
        table = table.sort_values("합계").rename(
            columns={select_col: "Selection", alloc_col: "Allocation"}
        )
        st.plotly_chart(ui.bar_chart(table["합계"], height=380, horizontal=True),
                        use_container_width=True)
        st.dataframe(
            table.style.format("{:.3%}"), use_container_width=True, height=240
        )

st.markdown("---")
st.caption(
    f"계산 출처: **{period['source']}** "
    f"(snapshot = 노트북이 만든 표 그대로 / recomputed = 동일 함수로 재집계) · "
    f"스냅샷 `{ctx['snapshot'].path.name}`"
)
