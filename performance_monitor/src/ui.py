"""Dashboard 공통 레이어 (Streamlit).

화면 전반의 필터·헤더·차트 헬퍼를 모아둔다.
**계산은 하지 않는다.** 모든 수치는 `src/` 의 엔진 함수에서 가져온다.
외부 CDN / 폰트 / API 를 쓰지 않는다 (사내망 폐쇄 환경 전제).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import model_analysis  # noqa: E402
from src.config import load_config  # noqa: E402
from src.data_loader import SnapshotStore, data_status, list_snapshots  # noqa: E402
from src.logging_utils import get_logger  # noqa: E402

# 등락 색상 관례. config.yaml 의 ui.color_convention 으로 전환한다.
#   kr     : 양수=적색, 음수=청색  (국내 시장 관례, 기본값)
#   global : 양수=청색, 음수=적색  (해외 관례)
COLOR_SCHEMES = {
    "kr": {"positive": "#d32020", "negative": "#1d4ed8"},
    "global": {"positive": "#2563eb", "negative": "#dc2626"},
}
DEFAULT_SCHEME = "kr"

HIGHLIGHT = "#0f172a"   # 선택 모델 강조선 (부호와 무관한 색)
NEUTRAL = "#64748b"
BM_COLOR = "#94a3b8"
# 다중 시계열용 범주형 색상.
# 적색/청색은 부호(등락)를 뜻하므로 앞쪽에 두지 않는다 — 계열 구분과 혼동되지 않게.
SERIES_COLORS = [
    "#0f766e", "#7c3aed", "#b45309", "#0891b2", "#be185d",
    "#4d7c0f", "#475569", "#a16207", "#15803d", "#c2410c",
    "#1e40af", "#9f1239",
]

# 기간 프리셋. 기준일(시작일)은 원본 규칙대로 '직전 영업일'이며 성과에서 제외된다.
#   1D  : 종료일 직전 영업일          → 하루 성과
#   1W  : 스냅샷의 report_start_date  → 노트북과 동일한 주간 구간
#   MTD/QTD/HTD/YTD/1Y : anchors(WORKDATE_MAST_TB 조회값)
PERIOD_PRESETS = [
    ("1D", "일간 (1D)"),
    ("1W", "주간 (1W)"),
    ("MTD", "월간 (MTD)"),
    ("QTD", "분기 (QTD)"),
    ("YTD", "연초 이후 (YTD)"),
    ("1Y", "최근 1년 (1Y)"),
    ("CUSTOM", "사용자 지정"),
]

MENU = [
    ("Dashboard", "app.py"),
    ("Performance", "pages/1_Performance.py"),
    ("Attribution", "pages/2_Attribution.py"),
    ("Models", "pages/3_Models.py"),
    ("Stocks", "pages/4_Stocks.py"),
    ("Position Change", "pages/5_Position_Change.py"),
    ("Data Validation", "pages/6_Data_Validation.py"),
    ("Export", "pages/7_Export.py"),
]


# ---------------------------------------------------------------------------
# 부트스트랩
# ---------------------------------------------------------------------------
def bootstrap(title: str) -> None:
    st.set_page_config(page_title=f"MP Performance Monitor · {title}",
                       layout="wide", initial_sidebar_state="expanded")
    st.markdown(
        """
        <style>
          .block-container {padding-top: 2.2rem; padding-bottom: 2rem; max-width: 1600px;}
          div[data-testid="stMetricValue"] {font-size: 1.55rem;}
          div[data-testid="stMetricLabel"] {font-size: 0.78rem; color: #64748b;}
          .pm-title {font-size:1.55rem; font-weight:700; letter-spacing:-0.01em; margin-bottom:0.1rem;}
          .pm-sub {color:#64748b; font-size:0.86rem;}
          .pm-chip {display:inline-block; padding:2px 9px; margin-right:6px;
                    border-radius:4px; background:#f1f5f9; color:#0f172a;
                    font-size:0.78rem; font-family:ui-monospace, monospace;}
          .pm-chip b {color:#2563eb;}
          table {font-size: 0.86rem;}
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def _load_snapshot_cached(path: str, cache_key: tuple) -> dict:
    """스냅샷 로드.

    ``cache_key`` 에 파일 mtime/size 가 들어 있어 **데이터가 바뀌면 캐시가 자동 무효화**된다.
    """
    return SnapshotStore(path).load_all()


def get_snapshots():
    return list_snapshots(load_config())


def load_bundle(snapshot):
    return _load_snapshot_cached(str(snapshot.path), snapshot.cache_key)


# ---------------------------------------------------------------------------
# 사이드바 (공통 필터)
# ---------------------------------------------------------------------------
def sidebar(require_model: bool = True) -> dict | None:
    """공통 필터. 변경 시 session_state 에 저장되어 전 페이지가 함께 움직인다."""
    config = load_config()
    snapshots = get_snapshots()

    st.sidebar.markdown("### 필터")

    if not snapshots:
        st.sidebar.error("스냅샷이 없습니다.")
        st.error(
            "`data/processed/` 에 스냅샷이 없습니다.\n\n"
            "- 운영: notebook 실행 후 `tools/export_snapshot_from_notebook.py` 의 `export(globals())`\n"
            "- 점검: `python tools/make_demo_snapshot.py`"
        )
        return None

    by_path = {str(s.path): s for s in snapshots}
    labels = {str(s.path): f"{s.as_of}  ·  {s.benchmark or '?'}" for s in snapshots}
    picked = _stateful_pick(
        st.sidebar.selectbox, "데이터 기준일", list(by_path), "snapshot_path",
        format_func=lambda path: labels[path],
    )
    snapshot = by_path[picked]

    bundle = load_bundle(snapshot)
    manifest = bundle.get("manifest", {})
    rcf = bundle.get("return_contribution_final")
    temp_return_final = bundle.get("temp_return_final")

    # --- Benchmark (스냅샷에 기록된 값. 다른 BM 은 해당 스냅샷을 선택해야 한다) ---
    analysis_bm = manifest.get("analysis_bm", config.default_benchmark)
    st.sidebar.text_input("Benchmark", config.benchmark_display(analysis_bm), disabled=True,
                          help="Benchmark 는 스냅샷 생성 시 결정된다. 변경하려면 해당 BM 스냅샷을 선택하라.")

    # --- 분석 기간 ---
    all_dates = pd.DatetimeIndex(temp_return_final.index).sort_values()
    snapshot_report_start = manifest.get("report_start_date")
    snapshot_end = manifest.get("mp_end_date")
    anchors = bundle.get("anchors") or {}

    default_start = _nearest(all_dates, snapshot_report_start) or all_dates[0]
    default_end = _nearest(all_dates, snapshot_end) or all_dates[-1]
    date_options = list(all_dates)

    preset_key = _stateful_pick(
        st.sidebar.radio, "기간 프리셋", [p[0] for p in PERIOD_PRESETS],
        "period_preset", default_index=1,          # 기본 = 주간 (성과회의 기준)
        format_func=lambda k: dict(PERIOD_PRESETS)[k],
        help="일간/주간/월간을 바로 고른다. 기준일(시작일)은 원본 코드와 동일하게 "
             "**직전 영업일**이며 그 날 수익률은 기간 성과에서 제외된다.",
    )

    if preset_key == "CUSTOM":
        start_pick = _stateful_pick(
            st.sidebar.selectbox, "분석 시작일 (기준일)", date_options, "custom_start",
            default_index=date_options.index(default_start),
            format_func=lambda d: str(d)[:10],
            help="원본 코드와 동일하게 **직전 영업일**을 기준일로 넣는다. "
                 "이 날의 수익률은 기간 성과에 포함되지 않는다.",
        )
        end_candidates = [d for d in date_options if d > start_pick]
        if not end_candidates:
            st.sidebar.error("종료일 후보가 없습니다. 시작일을 앞당기세요.")
            return None
        end_default = default_end if default_end in end_candidates else end_candidates[-1]
        end_pick = _stateful_pick(
            st.sidebar.selectbox, "분석 종료일", end_candidates, "custom_end",
            default_index=end_candidates.index(end_default),
            format_func=lambda d: str(d)[:10],
        )
    else:
        start_pick, end_pick, note = resolve_preset(
            preset_key, date_options, default_end, snapshot_report_start, anchors
        )
        if start_pick is None:
            st.sidebar.error(note)
            st.sidebar.caption("'사용자 지정'으로 직접 기간을 고르십시오.")
            return None
        st.sidebar.caption(
            f"기준일 **{str(start_pick)[:10]}** → 종료일 **{str(end_pick)[:10]}**"
            f"  ({len([d for d in date_options if start_pick < d <= end_pick])} 영업일)"
        )
        if note:
            st.sidebar.caption(note)

    report_date_list = [d for d in date_options if start_pick <= d <= end_pick]

    recomputed = not (
        str(start_pick)[:10] == str(snapshot_report_start)
        and str(end_pick)[:10] == str(snapshot_end)
    )

    # --- 모델 ---
    models = model_analysis.discover_models(
        return_contribution_final=rcf, temp_return_final=temp_return_final
    )
    display = config.model_display_names(analysis_bm)
    top_column = manifest.get("top_model_column", config.top_model_column(analysis_bm))

    def label_of(name):
        return f"{display.get(name, name)}  ({name})" if name in display else name

    model = None
    if require_model:
        fallback = models.index(top_column) if top_column in models else len(models) - 1
        model = _stateful_pick(
            st.sidebar.selectbox, "상위 Model / MP", models, "model",
            default_index=fallback, format_func=label_of,
        )

    sub_models = _stateful_multiselect(
        st.sidebar.multiselect, "하위 Model (비교용)",
        [m for m in models if m != model], "sub_models", format_func=label_of,
    )

    sector_field = _stateful_pick(
        st.sidebar.radio, "섹터 기준", ["q_sector", "new_sector"], "sector_field",
        default_index=1,
        format_func=lambda v: "q_sector (vrksa 기본)" if v == "q_sector"
        else "new_sector (수기 조정)",
    )

    if manifest.get("source") == "demo_synthetic":
        st.sidebar.warning("⚠ 데모(합성) 데이터입니다. 실제 성과가 아닙니다.")

    st.sidebar.markdown("---")
    st.sidebar.caption(
        f"스냅샷 생성 {manifest.get('created_at','-')}\n\n출처 `{manifest.get('source','-')}`"
    )

    return {
        "config": config,
        "snapshot": snapshot,
        "bundle": bundle,
        "manifest": manifest,
        "analysis_bm": analysis_bm,
        "model": model,
        "models": models,
        "sub_models": sub_models,
        "top_column": top_column,
        "report_date_list": report_date_list,
        "start_date": start_pick,
        "end_date": end_pick,
        "sector_field": sector_field,
        "display_names": display,
        "recomputed": recomputed,
        "preset": preset_key,
        "preset_label": dict(PERIOD_PRESETS)[preset_key],
        "anchors": anchors,
        "list_bpm_factor": manifest.get("list_bpm_factor", []),
        "list_bpm_sector": manifest.get("list_bpm_sector", []),
    }


def resolve_preset(key: str, date_options: list, end_date,
                   snapshot_report_start, anchors: dict):
    """프리셋 → (기준일, 종료일, 안내문).

    기준일은 원본 코드의 ``report_start_date`` 와 같은 의미다 —
    **직전 영업일이며 그 날 수익률은 기간 성과에 포함되지 않는다.**
    """
    dates = pd.DatetimeIndex(date_options)
    prior = [d for d in date_options if d < end_date]
    if not prior:
        return None, None, "종료일 이전 영업일이 없습니다."

    if key == "1D":
        return prior[-1], end_date, None

    if key == "1W":
        start = _nearest(dates, snapshot_report_start)
        if start is not None and start < end_date:
            return start, end_date, None
        # 스냅샷에 report_start_date 가 없으면 5영업일 전을 기준일로
        start = prior[-5] if len(prior) >= 5 else date_options[0]
        return start, end_date, "스냅샷 기준일이 없어 5영업일 전을 기준일로 잡았습니다."

    anchor = anchors.get(key)
    if anchor is None:
        return None, None, (
            f"스냅샷에 {key} 기준일이 없습니다. "
            "노트북의 WORKDATE_MAST_TB 조회 결과를 함께 export 하면 사용할 수 있습니다."
        )
    start = _nearest(dates, anchor)
    if start is None or start >= end_date:
        return None, None, f"{key} 기준일({anchor})이 스냅샷 데이터 구간을 벗어납니다."
    return start, end_date, None


def _stateful_pick(widget, label, options, key, default_index=0, **kwargs):
    """선택값이 rerun·페이지 이동에도 유지되는 selectbox / radio.

    Streamlit 특성 두 가지를 함께 피해야 한다.

    1. ``index`` 인자를 session_state 에서 계산해 넘기면 위젯 identity 가 매번
       바뀌어 사용자의 선택이 버려진다 → ``key`` 로 상태를 맡긴다.
    2. 멀티페이지에서 페이지를 옮기면 그리지 않은 위젯의 state 는 정리된다
       → 별도 보관 키(``_pm_*``)에 값을 복사해 두고 매 실행마다 되살린다.

    스냅샷이 바뀌어 선택지에서 사라진 값은 기본값으로 되돌린다.
    """
    store, wkey = f"_pm_{key}", f"_pmw_{key}"
    # 위젯 키가 살아 있으면 그 값이 최신(사용자 클릭), 없으면 보관 값에서 복원
    value = st.session_state.get(wkey, st.session_state.get(store))
    if value not in options:
        value = options[min(default_index, len(options) - 1)]
    st.session_state[wkey] = value

    picked = widget(label, options, key=wkey, **kwargs)
    st.session_state[store] = picked
    return picked


def _stateful_multiselect(widget, label, options, key, default=None, **kwargs):
    """선택값이 유지되는 multiselect. 선택지에서 사라진 값은 조용히 떨어뜨린다."""
    store, wkey = f"_pm_{key}", f"_pmw_{key}"
    value = st.session_state.get(wkey, st.session_state.get(store))
    if value is None:
        value = list(options if default is None else default)
    value = [v for v in value if v in options]
    st.session_state[wkey] = value

    picked = widget(label, options, key=wkey, **kwargs)
    st.session_state[store] = picked
    return picked


def _nearest(dates: pd.DatetimeIndex, value):
    if value is None:
        return None
    target = pd.Timestamp(value)
    if target.tzinfo is None and dates.tz is not None:
        target = target.tz_localize(dates.tz)
    matches = dates[dates <= target]
    return matches[-1] if len(matches) else None


# ---------------------------------------------------------------------------
# 헤더
# ---------------------------------------------------------------------------
def header(ctx: dict, title: str = "MP PERFORMANCE MONITOR") -> None:
    config = ctx["config"]
    if ctx["manifest"].get("source") == "demo_synthetic":
        st.error(
            "**데모(합성) 데이터입니다. 실제 운용 성과가 아닙니다.** "
            "화면·엔진 점검용이며, 회의 자료로 사용하지 마십시오.",
            icon="🧪",
        )
    status = data_status(ctx["bundle"])
    period = f"{str(ctx['start_date'])[:10]} ~ {str(ctx['end_date'])[:10]}"
    model_label = ctx["display_names"].get(ctx["model"], ctx["model"]) if ctx["model"] else "-"

    st.markdown(f"<div class='pm-title'>{title}</div>", unsafe_allow_html=True)
    chips = (
        f"<span class='pm-chip'>{ctx.get('preset_label','기간')} <b>{period}</b></span>"
        f"<span class='pm-chip'>Model <b>{model_label}</b></span>"
        f"<span class='pm-chip'>Benchmark <b>{config.benchmark_display(ctx['analysis_bm'])}</b></span>"
        f"<span class='pm-chip'>Data As of <b>{status['data_as_of']}</b></span>"
        f"<span class='pm-chip'>종목수 <b>{status['n_stocks']}</b></span>"
    )
    st.markdown(f"<div class='pm-sub'>{chips}</div>", unsafe_allow_html=True)

    cols = st.columns(len(status["checks"]) + 1)
    for col, (name, state) in zip(cols, status["checks"].items()):
        col.markdown(
            f"<div class='pm-sub'>{'🟢' if state=='정상' else '⚪'} {name} · {state}</div>",
            unsafe_allow_html=True,
        )
    cols[-1].markdown(
        f"<div class='pm-sub'>{'🟢' if status['missing_data']==0 else '🔴'} "
        f"Missing Data · {status['missing_data']}</div>",
        unsafe_allow_html=True,
    )

    if ctx.get("recomputed"):
        st.info(
            "선택한 기간이 스냅샷 기본 구간과 다릅니다. "
            "수익률·기여도를 **스냅샷의 일별 값으로부터 재집계**해 표시합니다 "
            "(계산식은 원본과 동일). 노트북과 1:1 대조하려면 기본 구간을 쓰세요.",
            icon="ℹ️",
        )
    st.markdown("")


def warn_if_validation_failed(ctx: dict) -> None:
    """검증 오류가 있으면 화면 상단에 그대로 노출한다."""
    from src import validation as V

    report = V.run_validation(
        ctx["bundle"], ctx["model"], ctx["report_date_list"],
        ctx["config"].validation,
    )
    problems = report.problems
    if not problems:
        return
    level = st.error if report.has_error else st.warning
    lines = []
    for check in problems:
        lines.append(f"**{check.name}** — {check.detail} (값: {check.value})")
        if check.items:
            preview = ", ".join(map(str, check.items[:8]))
            more = f" 외 {len(check.items)-8}건" if len(check.items) > 8 else ""
            lines.append(f"　└ {preview}{more}")
    level("WARNING\n\n" + "\n\n".join(lines), icon="⚠️")
    st.caption("자세한 내용은 **Data Validation** 메뉴에서 확인하세요. "
               "결측치를 자동으로 0 처리하지 않습니다.")


# ---------------------------------------------------------------------------
# 표 / 차트 헬퍼
# ---------------------------------------------------------------------------
def sign_colors() -> dict:
    """설정에 따른 등락 색상. ``{"positive": ..., "negative": ...}``"""
    scheme = load_config().ui.get("color_convention", DEFAULT_SCHEME)
    return COLOR_SCHEMES.get(scheme, COLOR_SCHEMES[DEFAULT_SCHEME])


def sign_color(value) -> str:
    """값의 부호에 맞는 색."""
    colors = sign_colors()
    try:
        return colors["positive"] if float(value) >= 0 else colors["negative"]
    except (TypeError, ValueError):
        return NEUTRAL


def pct_frame(frame: pd.DataFrame, digits: int = 2):
    """퍼센트 서식 적용 (숫자 컬럼만)."""
    numeric = frame.select_dtypes(include=[np.number]).columns
    return frame.style.format({c: f"{{:.{digits}%}}" for c in numeric})


def bar_chart(series: pd.Series, title: str = "", height: int = 380,
              tickformat: str = ".2%", horizontal: bool = False):
    """부호별 색상 bar chart."""
    series = pd.Series(series).astype(float).dropna()
    scheme = sign_colors()
    colors = [scheme["positive"] if v >= 0 else scheme["negative"] for v in series.values]
    if horizontal:
        fig = go.Figure(go.Bar(x=series.values, y=[str(i) for i in series.index],
                               orientation="h", marker_color=colors,
                               hovertemplate="%{y}<br>%{x:.3%}<extra></extra>"))
        fig.update_xaxes(tickformat=tickformat, zeroline=True, zerolinecolor="#cbd5e1")
    else:
        fig = go.Figure(go.Bar(x=[str(i) for i in series.index], y=series.values,
                               marker_color=colors,
                               hovertemplate="%{x}<br>%{y:.3%}<extra></extra>"))
        fig.update_yaxes(tickformat=tickformat, zeroline=True, zerolinecolor="#cbd5e1")
    fig.update_layout(title=title, height=height, showlegend=False,
                      margin=dict(l=10, r=10, t=40 if title else 10, b=10),
                      plot_bgcolor="white")
    return fig


def line_chart(frame: pd.DataFrame, title: str = "", height: int = 420,
               tickformat: str = ".2%", highlight: str | None = None,
               bm_column: str | None = None):
    """다중 시계열. ``highlight`` 는 굵게, ``bm_column`` 은 회색 점선."""
    fig = go.Figure()
    color_index = 0
    for column in frame.columns:
        series = pd.to_numeric(frame[column], errors="coerce")
        if column == bm_column:
            style = dict(color=BM_COLOR, width=2, dash="dash")
        elif column == highlight:
            style = dict(color=HIGHLIGHT, width=3)
        else:
            style = dict(color=SERIES_COLORS[color_index % len(SERIES_COLORS)], width=1.5)
            color_index += 1
        fig.add_trace(go.Scatter(
            x=frame.index, y=series.values, name=str(column), mode="lines",
            line=style, hovertemplate="%{x|%Y-%m-%d}<br>%{y:.3%}<extra>" + str(column) + "</extra>",
        ))
    fig.update_yaxes(tickformat=tickformat, zeroline=True, zerolinecolor="#cbd5e1",
                     gridcolor="#f1f5f9")
    # 구간이 짧으면(예: 일간) plotly 가 시간 단위로 눈금을 쪼개므로 날짜로 고정한다.
    dtick = "D1" if len(frame.index) <= 10 else None
    fig.update_xaxes(gridcolor="#f8fafc", tickformat="%Y-%m-%d", dtick=dtick)
    fig.update_layout(title=title, height=height, plot_bgcolor="white",
                      margin=dict(l=10, r=10, t=40 if title else 10, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.0,
                                  xanchor="left", x=0, font=dict(size=10)),
                      hovermode="x unified")
    return fig


def contribution_weight_chart(frame: pd.DataFrame, contribution_col: str,
                              weight_col: str, title: str = "", height: int = 440):
    """기여도(bar) + active weight(line, 보조축).

    원본 노트북의 Top/Bottom 화면 구성(파랑 bar + 빨강 line, 보조축)을 그대로 따른다.
    """
    from plotly.subplots import make_subplots

    frame = frame.dropna(subset=[contribution_col])
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    scheme = sign_colors()
    colors = [scheme["positive"] if v >= 0 else scheme["negative"]
              for v in frame[contribution_col].astype(float)]
    fig.add_trace(
        go.Bar(name="Contribution", x=[str(i) for i in frame.index],
               y=frame[contribution_col].astype(float), marker_color=colors,
               hovertemplate="%{x}<br>기여도 %{y:.3%}<extra></extra>"),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(name="Active Weight", x=[str(i) for i in frame.index],
                   y=frame[weight_col].astype(float), mode="lines+markers",
                   line=dict(color=NEUTRAL, width=1.5),
                   marker=dict(size=5, color=NEUTRAL),
                   hovertemplate="%{x}<br>Active W %{y:.2%}<extra></extra>"),
        secondary_y=True,
    )
    fig.update_yaxes(title_text="Contribution", tickformat=".3%",
                     zeroline=True, zerolinecolor="#cbd5e1", secondary_y=False)
    fig.update_yaxes(title_text="Active Weight", tickformat=".2%", secondary_y=True,
                     showgrid=False)
    fig.update_layout(title=title, height=height, plot_bgcolor="white",
                      margin=dict(l=10, r=10, t=45 if title else 10, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0))
    return fig


def download_buttons(frame: pd.DataFrame, filename: str, key: str) -> None:
    """CSV / Excel 다운로드 버튼."""
    import io

    col1, col2 = st.columns(2)
    col1.download_button(
        "CSV 다운로드", frame.to_csv().encode("utf-8-sig"),
        file_name=f"{filename}.csv", mime="text/csv", key=f"{key}_csv",
        use_container_width=True,
    )
    buffer = io.BytesIO()
    try:
        from src.export import excel_safe

        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            excel_safe(frame).to_excel(writer, sheet_name=filename[:31] or "Sheet1")
        col2.download_button(
            "Excel 다운로드", buffer.getvalue(),
            file_name=f"{filename}.xlsx", key=f"{key}_xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    except ImportError:
        col2.caption("openpyxl 미설치 — Excel 내보내기 불가")


def metric_row(items: list) -> None:
    """(label, value, delta, help) 튜플 목록을 KPI 행으로."""
    cols = st.columns(len(items))
    for col, item in zip(cols, items):
        label, value = item[0], item[1]
        delta = item[2] if len(item) > 2 else None
        helptext = item[3] if len(item) > 3 else None
        col.metric(label, value, delta, help=helptext)


def logger():
    return get_logger(log_dir=load_config().log_dir)
