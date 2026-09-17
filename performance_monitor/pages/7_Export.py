"""Export — 회의자료용 Excel / CSV 내보내기."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src import dashboard_engine as de, export, ui  # noqa: E402

ui.bootstrap("Export")
ctx = ui.sidebar()
if ctx is None:
    st.stop()

ui.header(ctx, "EXPORT")

bundle = ctx["bundle"]
model = ctx["model"]
period = de.compute_period(bundle, ctx["report_date_list"], ctx["sector_field"])

st.markdown("#### Weekly Performance Snapshot")
st.caption(
    "Summary / Performance / Attribution / Models / Stocks / PositionChange / Validation "
    "시트를 하나의 Excel 파일로 내보낸다."
)

stamp = f"{str(ctx['start_date'])[:10]}_{str(ctx['end_date'])[:10]}".replace("-", "")
filename = f"weekly_performance_{model}_{stamp}.xlsx"

if st.button("Weekly Snapshot 생성", type="primary", use_container_width=True):
    with st.spinner("생성 중..."):
        try:
            payload = export.build_weekly_workbook(
                bundle, period, model, ctx["config"],
                display_names=ctx["display_names"], anchors=ctx["anchors"])
        except ImportError:
            st.error("openpyxl 이 설치되어 있지 않습니다. `pip install openpyxl`")
            payload = None
    if payload:
        st.success(f"{len(payload)/1024:.0f} KB 생성 완료")
        st.download_button(
            "Excel 다운로드", payload, file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True)
        ui.logger().info(
            f"Weekly snapshot export | model={model} "
            f"period={str(ctx['start_date'])[:10]}~{str(ctx['end_date'])[:10]}")

st.markdown("---")
st.markdown("#### 개별 표 내보내기")

sheets = export.build_sheets(bundle, period, model, ctx["config"],
                             ctx["display_names"], ctx["anchors"])
picked = st.selectbox("표 선택", list(sheets.keys()), key="exp_sheet")
frame = sheets[picked]
# 표시용으로만 혼합 dtype 을 맞춘다. 내려받는 파일 내용은 그대로다.
st.dataframe(export.display_safe(frame), use_container_width=True, height=440)
ui.download_buttons(frame, picked.lower(), "exp_single")

st.markdown("---")
st.markdown("#### 원본 스냅샷 테이블")
st.caption("노트북이 만든 원본 표를 그대로 내보낸다 (검증·대조용).")

raw_tables = {
    name: bundle[name] for name in
    ("return_contribution_final", "temp_return_final", "betalog_final",
     "compare_final", "sector_compare_final", "new_sector_compare_final")
    if bundle.get(name) is not None
}
if raw_tables:
    picked_raw = st.selectbox("테이블", list(raw_tables.keys()), key="exp_raw")
    raw = raw_tables[picked_raw]
    st.dataframe(raw, use_container_width=True, height=400)
    ui.download_buttons(raw, picked_raw, "exp_raw_dl")
else:
    st.caption("원본 테이블이 없습니다.")
