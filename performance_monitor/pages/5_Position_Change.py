"""Position Change — 주간 포지션 변화."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src import dashboard_engine as de, portfolio as pf, ui  # noqa: E402

ui.bootstrap("Position Change")
ctx = ui.sidebar()
if ctx is None:
    st.stop()

ui.header(ctx, "POSITION CHANGE")

bundle = ctx["bundle"]
model = ctx["model"]
final_mp = bundle["final_mp"]
report_date_list = ctx["report_date_list"]
top_n = int(ctx["config"].ui.get("top_n", 10))

st.caption(
    "비중은 `final_mp` 의 일별 total weight (jackhammer drift 반영) 를 그대로 쓴다. "
    "따라서 변화량에는 **리밸런싱 매매와 가격 변동에 의한 drift 가 함께** 들어 있다. "
    "순수 매매만 보려면 `portfolios.portfolio_trades` 가 필요하며, 현재 스냅샷에는 없다."
)

col1, col2 = st.columns(2)
prev_date = col1.selectbox("비교 시작일", report_date_list, index=0,
                           format_func=lambda d: str(d)[:10], key="pos_prev")
later = [d for d in report_date_list if d > prev_date]
if not later:
    st.warning("비교 종료일이 없습니다.")
    st.stop()
curr_date = col2.selectbox("비교 종료일", later, index=len(later) - 1,
                           format_func=lambda d: str(d)[:10], key="pos_curr")

change = pf.position_change(final_mp, prev_date, curr_date, model,
                            info_stock=bundle.get("info_stock"))

period = de.compute_period(bundle, report_date_list, ctx["sector_field"])
stocks = de.stock_table(bundle, period, model)
change["contribution"] = stocks["contribution"].reindex(change.index)

new_in = change[change["status"] == "신규편입"]
dropped = change[change["status"] == "제외"]

ui.metric_row([
    ("신규 편입", f"{len(new_in)} 종목"),
    ("제외", f"{len(dropped)} 종목"),
    ("비중 증가", f"{int((change['change'] > 1e-12).sum())} 종목"),
    ("비중 감소", f"{int((change['change'] < -1e-12).sum())} 종목"),
    ("총 변화량", f"{change['change'].abs().sum() / 2:.2%}"),
])

st.markdown("---")

FORMATS = {"이전비중": "{:.3%}", "현재비중": "{:.3%}", "변화": "{:.3%}",
           "이전 Active": "{:.3%}", "현재 Active": "{:.3%}",
           "Active 변화": "{:.3%}", "기여도": "{:.4%}"}
RENAME = {"name": "종목", "previous_weight": "이전비중", "current_weight": "현재비중",
          "change": "변화", "previous_active": "이전 Active",
          "current_active": "현재 Active", "active_change": "Active 변화",
          "contribution": "기여도", "status": "구분"}


def show(frame: pd.DataFrame, height: int = 360) -> None:
    view = frame.rename(columns=RENAME)
    columns = [c for c in ["종목", "이전비중", "현재비중", "변화", "Active 변화", "기여도"]
               if c in view.columns]
    st.dataframe(
        view[columns].style.format({c: FORMATS[c] for c in columns if c in FORMATS}),
        use_container_width=True, height=height)


left, right = st.columns(2)
with left:
    st.markdown(f"##### Top {top_n} Increase")
    increase = change.nlargest(top_n, "change")
    plot = increase.set_index(increase["name"].fillna(increase.index.to_series()))
    st.plotly_chart(ui.bar_chart(plot["change"].astype(float), height=300,
                                 horizontal=True, tickformat=".2%"),
                    use_container_width=True)
    show(increase)
with right:
    st.markdown(f"##### Top {top_n} Decrease")
    decrease = change.nsmallest(top_n, "change").sort_values("change")
    plot = decrease.set_index(decrease["name"].fillna(decrease.index.to_series()))
    st.plotly_chart(ui.bar_chart(plot["change"].astype(float), height=300,
                                 horizontal=True, tickformat=".2%"),
                    use_container_width=True)
    show(decrease)

st.markdown("---")
left, right = st.columns(2)
with left:
    st.markdown("##### 신규 편입")
    if new_in.empty:
        st.caption("없음")
    else:
        show(new_in.sort_values("current_weight", ascending=False), 300)
with right:
    st.markdown("##### 제외 종목")
    if dropped.empty:
        st.caption("없음")
    else:
        show(dropped.sort_values("previous_weight", ascending=False), 300)

st.markdown("---")
with st.expander("전체 변화 내역", expanded=False):
    st.dataframe(change.rename(columns=RENAME), use_container_width=True, height=520)
ui.download_buttons(change, "position_change", "pos_all")
