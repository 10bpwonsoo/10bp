"""Data Validation — 데이터 검증 및 실행 로그."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src import dashboard_engine as de, ui, validation as V  # noqa: E402
from src.data_loader import data_status  # noqa: E402

ui.bootstrap("Data Validation")
ctx = ui.sidebar()
if ctx is None:
    st.stop()

ui.header(ctx, "DATA VALIDATION")

bundle = ctx["bundle"]
report = V.run_validation(bundle, ctx["model"], ctx["report_date_list"],
                          ctx["config"].validation)

errors = [c for c in report.checks if c.status == V.ERROR]
warnings_ = [c for c in report.checks if c.status == V.WARN]

if errors:
    st.error(f"오류 {len(errors)}건 — 성과 수치를 신뢰하기 전에 확인이 필요합니다.", icon="🛑")
elif warnings_:
    st.warning(f"경고 {len(warnings_)}건", icon="⚠️")
else:
    st.success("모든 검증 항목 정상", icon="✅")

st.info("결측치를 자동으로 0 처리하지 않습니다. 문제가 있는 종목/일자를 그대로 나열합니다.",
        icon="ℹ️")

st.markdown("#### 검증 결과")
frame = report.to_frame()


def style_status(value):
    if value == V.ERROR:
        return "background-color:#fee2e2; color:#991b1b; font-weight:600;"
    if value == V.WARN:
        return "background-color:#fef3c7; color:#92400e; font-weight:600;"
    return "background-color:#dcfce7; color:#166534;"


st.dataframe(frame.style.map(style_status, subset=["상태"]),
             use_container_width=True, hide_index=True, height=420)

problems = report.problems
if problems:
    st.markdown("#### 상세")
    for check in problems:
        icon = "🛑" if check.status == V.ERROR else "⚠️"
        with st.expander(f"{icon} {check.name} — {check.detail}", expanded=True):
            st.write(f"**값**: {check.value}")
            if check.items:
                info = bundle.get("info_stock")
                rows = []
                for item in check.items:
                    name = None
                    if info is not None and item in info.index:
                        name = info.loc[item, "name_stock"]
                    rows.append({"대상": item, "종목명": name})
                st.dataframe(pd.DataFrame(rows), use_container_width=True,
                             hide_index=True, height=min(320, 40 + 35 * len(rows)))
            else:
                st.caption("개별 대상 없음")

st.markdown("---")
st.markdown("#### 데이터 상태")
status = data_status(bundle)
left, right = st.columns([1, 1])
with left:
    st.dataframe(
        pd.DataFrame(
            [{"항목": k, "상태": v} for k, v in status["checks"].items()]
            + [{"항목": "Missing Data", "상태": str(status["missing_data"])},
               {"항목": "종목 수", "상태": str(status["n_stocks"])}]),
        use_container_width=True, hide_index=True, height=300)
with right:
    manifest = dict(ctx["manifest"])
    for key in ("list_bpm_factor", "list_bpm_sector", "models"):
        if key in manifest and isinstance(manifest[key], list):
            manifest[key] = f"{len(manifest[key])}개: " + ", ".join(map(str, manifest[key][:6])) + (
                " ..." if len(manifest[key]) > 6 else "")
    st.json(manifest, expanded=True)

st.markdown("---")
st.markdown("#### 비중 합 추이")
model = ctx["model"]
total_col = f"total_{model}"
final_mp = bundle["final_mp"]
if total_col in final_mp.columns:
    window = final_mp.loc[(ctx["report_date_list"], slice(None)), :]
    sums = pd.DataFrame({
        "Portfolio": window.groupby("date", group_keys=False)[total_col].sum(),
        "Benchmark": window.groupby("date", group_keys=False)["bm"].sum(),
    })
    st.plotly_chart(ui.line_chart(sums, height=320, tickformat=".2%",
                                  bm_column="Benchmark"),
                    use_container_width=True)
    ui.download_buttons(sums, "weight_sum_check", "val_wsum")

st.markdown("---")
st.markdown("#### 실행 로그")
log_dir = ctx["config"].log_dir
logs = sorted(Path(log_dir).glob("*.log"), reverse=True) if Path(log_dir).exists() else []
if not logs:
    st.caption(f"로그 파일 없음 ({log_dir})")
else:
    picked = st.selectbox("로그 파일", logs, format_func=lambda p: p.name, key="val_log")
    lines = picked.read_text(encoding="utf-8").splitlines()
    st.code("\n".join(lines[-200:]) or "(비어 있음)", language="text")
    st.caption(f"{picked} · 최근 200줄")
