"""노트북 안에서 대시보드 화면을 그대로 보기.

Streamlit 서버를 띄울 수 없는 환경(포트 차단 등)을 위한 경로다.
**계산은 Dashboard 와 동일한 엔진**(`dashboard_engine`)을 쓰므로 숫자가 같다.
여기서 새로 계산하는 것은 없다.

사용::

    import pm_engine as pm
    pm.report()                      # 최신 스냅샷, 상위 모델, 주간
    pm.report(preset='MTD')          # 월간
    pm.report(model='KS2_VALUE_FP')  # 특정 하위 모델

plotly 를 쓰며, 폐쇄망에서는 노트북 첫 셀에서 아래를 한 번 실행해 두어야
그래프가 보인다 (CDN 을 쓰지 않도록 plotly.js 를 노트북에 임베드).

    import plotly.offline as po
    po.init_notebook_mode(connected=False)   # connected=True 는 CDN 을 쓴다
"""
from __future__ import annotations

import pandas as pd

from . import dashboard_engine as de
from . import model_analysis
from .config import load_config
from .data_loader import SnapshotStore, data_status, latest_snapshot, list_snapshots
from .utils import fmt_pct

__all__ = ["report", "load", "available_snapshots"]

# 화면과 같은 색 관례·기간 규칙을 쓴다.
# colors / periods 는 streamlit 에 의존하지 않으므로 노트북 커널에서 안전하다.
from .colors import SERIES_COLORS, sign_colors as _colors  # noqa: E402
from .periods import resolve_preset  # noqa: E402


def available_snapshots() -> pd.DataFrame:
    """쓸 수 있는 스냅샷 목록."""
    rows = [{"as_of": s.as_of, "benchmark": s.benchmark,
             "source": s.manifest.get("source", "-"),
             "created_at": s.created_at, "path": str(s.path)}
            for s in list_snapshots(load_config())]
    return pd.DataFrame(rows)


def load(as_of: str | None = None) -> dict:
    """스냅샷 로드. ``as_of`` 없으면 최신."""
    config = load_config()
    if as_of is None:
        snapshot = latest_snapshot(config)
        if snapshot is None:
            raise FileNotFoundError(
                f"스냅샷이 없습니다: {config.processed_dir}\n"
                "노트북에서 pm.export_snapshot(globals()) 를 먼저 실행하거나,\n"
                "점검용이라면 tools/make_demo_snapshot.py 를 쓰십시오."
            )
    else:
        matches = [s for s in list_snapshots(config) if s.as_of == as_of]
        if not matches:
            raise FileNotFoundError(f"해당 기준일 스냅샷이 없습니다: {as_of}")
        snapshot = matches[0]
    return SnapshotStore(snapshot.path).load_all()


def _resolve_period(bundle: dict, preset: str):
    """프리셋 -> report_date_list. 화면의 기간 프리셋과 같은 규칙."""
    manifest = bundle["manifest"]
    dates = list(pd.DatetimeIndex(bundle["temp_return_final"].index).sort_values())
    end = [d for d in dates if str(d)[:10] <= str(manifest.get("mp_end_date"))]
    end = end[-1] if end else dates[-1]
    anchors = bundle.get("anchors") or {}

    start, stop, note = resolve_preset(
        preset, dates, end, manifest.get("report_start_date"), anchors)
    if start is None:
        raise ValueError(note)
    return [d for d in dates if start <= d <= stop]


def _bar(series: pd.Series, title: str, horizontal: bool = False, height: int = 380):
    import plotly.graph_objects as go

    series = pd.Series(series).astype(float).dropna()
    scheme = _colors()
    colors = [scheme["positive"] if v >= 0 else scheme["negative"] for v in series.values]
    if horizontal:
        fig = go.Figure(go.Bar(x=series.values, y=[str(i) for i in series.index],
                               orientation="h", marker_color=colors))
        fig.update_xaxes(tickformat=".3%", zeroline=True, zerolinecolor="#cbd5e1")
    else:
        fig = go.Figure(go.Bar(x=[str(i) for i in series.index], y=series.values,
                               marker_color=colors))
        fig.update_yaxes(tickformat=".3%", zeroline=True, zerolinecolor="#cbd5e1")
    fig.update_layout(title=title, height=height, showlegend=False,
                      plot_bgcolor="white", margin=dict(l=10, r=10, t=45, b=10))
    return fig


def _line(frame: pd.DataFrame, title: str, height: int = 380):
    import plotly.graph_objects as go

    palette = SERIES_COLORS
    fig = go.Figure()
    for i, column in enumerate(frame.columns):
        style = (dict(color="#94a3b8", width=2, dash="dash") if column == "Benchmark"
                 else dict(color="#0f172a", width=3) if i == 0
                 else dict(color=palette[i % len(palette)], width=1.5))
        fig.add_trace(go.Scatter(x=frame.index, y=pd.to_numeric(frame[column], errors="coerce"),
                                 name=str(column), mode="lines", line=style))
    fig.update_yaxes(tickformat=".2%", zeroline=True, zerolinecolor="#cbd5e1",
                     gridcolor="#f1f5f9")
    fig.update_xaxes(tickformat="%Y-%m-%d", gridcolor="#f8fafc")
    fig.update_layout(title=title, height=height, plot_bgcolor="white",
                      margin=dict(l=10, r=10, t=45, b=10), hovermode="x unified",
                      legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0))
    return fig


def report(as_of: str | None = None, model: str | None = None,
           preset: str = "1W", sector_field: str = "new_sector",
           top_n: int = 10, show: bool = True) -> dict:
    """노트북 안에 대시보드 요약 화면을 그린다.

    Parameters
    ----------
    as_of    스냅샷 기준일 (None = 최신)
    model    모델 컬럼 (None = 상위 모델, 보통 'RP')
    preset   '1D' / '1W' / 'MTD' / 'QTD' / 'YTD' / '1Y'
    show     False 면 그리지 않고 결과 dict 만 반환

    Returns
    -------
    dict — figures / tables. 추가 가공이 필요하면 여기서 꺼내 쓴다.
    """
    config = load_config()
    bundle = load(as_of)
    manifest = bundle["manifest"]
    model = model or manifest.get("top_model_column", "RP")
    report_date_list = _resolve_period(bundle, preset)

    period = de.compute_period(bundle, report_date_list, sector_field)
    rcf = period["return_contribution_final"]
    status = data_status(bundle)
    names = config.model_display_names(manifest.get("analysis_bm", ""))

    total = float(rcf.loc["total", model])
    bm = float(rcf.loc["bm", model])
    active = float(rcf.loc["active", model])

    stocks = de.stock_table(bundle, period, model)
    top, bottom = de.top_bottom(stocks, "contribution", top_n)
    best, worst = model_analysis.best_worst_model(
        rcf, "active", exclude=[period["top_column"]])

    # --- 화면 구성 ---------------------------------------------------------
    header = f"""
    <div style="font-family:system-ui,sans-serif">
      <div style="font-size:1.35rem;font-weight:700">MP PERFORMANCE MONITOR</div>
      <div style="color:#64748b;font-size:.85rem;margin:.3rem 0 .8rem">
        기간 <b>{str(report_date_list[0])[:10]} ~ {str(report_date_list[-1])[:10]}</b> ·
        Model <b>{names.get(model, model)}</b> ·
        Benchmark <b>{config.benchmark_display(manifest.get('analysis_bm',''))}</b> ·
        Data As of <b>{status['data_as_of']}</b> ·
        종목수 <b>{status['n_stocks']}</b> ·
        계산 출처 <b>{period['source']}</b>
      </div>
    </div>"""

    scheme = _colors()

    def kpi(label, value):
        color = scheme["positive"] if value >= 0 else scheme["negative"]
        return (f"<td style='padding:.4rem 1.4rem .4rem 0'>"
                f"<div style='color:#64748b;font-size:.75rem'>{label}</div>"
                f"<div style='font-size:1.3rem;font-weight:600;color:{color}'>"
                f"{fmt_pct(value)}</div></td>")

    kpis = "<table style='font-family:system-ui,sans-serif'><tr>" + "".join([
        kpi("MP Return", total), kpi("Benchmark", bm), kpi("Excess Return", active),
        kpi("Specific", float(rcf.loc["specific", model])),
        kpi("Risk Factor", float(rcf.loc["risk_factor", model])),
        kpi("Industry Factor", float(rcf.loc["industry_factor", model])),
    ]) + "</tr></table>"

    if manifest.get("source") == "demo_synthetic":
        header = ("<div style='background:#fee2e2;color:#991b1b;padding:.6rem;"
                  "border-radius:4px;font-family:system-ui'>🧪 <b>데모(합성) 데이터입니다. "
                  "실제 운용 성과가 아닙니다.</b></div>") + header

    curve = period["cumulative"]
    plot = curve[[model, "bm"]].rename(
        columns={model: names.get(model, model), "bm": "Benchmark"})
    plot["Excess"] = curve[model] - curve["bm"]
    fig_curve = _line(plot, f"누적 성과 · {preset}")

    rows = [r for r in config.attribution["plot_rows"] if r in rcf.index]
    fig_attr = _bar(rcf.loc[rows, model].astype(float), "성과 기여도 (항목별)")

    combined = pd.concat([bottom, top])
    combined = combined.set_index(combined["name"].fillna(combined.index.to_series()))
    fig_stock = _bar(combined["contribution"].astype(float),
                     f"종목별 기여도 Top / Bottom {top_n}", horizontal=True, height=460)

    model_active = rcf.loc["active"].astype(float)
    model_active.index = [names.get(i, i) for i in model_active.index]
    fig_model = _bar(model_active.sort_values(), "모델별 Active", horizontal=True)

    figures = {"cumulative": fig_curve, "attribution": fig_attr,
               "stocks": fig_stock, "models": fig_model}

    sector_compare = period["sector_compare_final"]
    sector_table = None
    if sector_compare is not None:
        suffix = period["sector_suffix"]
        sector_table = sector_compare[[f"{model}_selection{suffix}",
                                       f"{model}_allocation{suffix}"]].astype(float)
        sector_table.columns = ["Selection", "Allocation"]
        sector_table["합계"] = sector_table.sum(axis=1)
        sector_table = sector_table.sort_values("합계")
        figures["sector"] = _bar(sector_table["합계"],
                                 f"업종별 기여도 ({sector_field})", horizontal=True)

    summary = pd.DataFrame([
        ["Top Contributor", str(top.iloc[0].get("name") or top.index[0]),
         fmt_pct(float(top.iloc[0]["contribution"]))],
        ["Bottom Contributor", str(bottom.iloc[0].get("name") or bottom.index[0]),
         fmt_pct(float(bottom.iloc[0]["contribution"]))],
        ["Best Model", names.get(best[0], best[0]) if best else "-",
         fmt_pct(best[1]) if best else "-"],
        ["Worst Model", names.get(worst[0], worst[0]) if worst else "-",
         fmt_pct(worst[1]) if worst else "-"],
    ], columns=["구분", "대상", "값"])

    tables = {
        "attribution": rcf.loc[rows, model].astype(float).to_frame("기여도"),
        "summary": summary,
        "stocks": stocks,
        "top": top, "bottom": bottom,
        "sector": sector_table,
        "return_contribution_final": rcf,
    }

    if show:
        # IPython 은 화면에 그릴 때만 필요하다. show=False 로 숫자만 쓸 때는
        # 노트북 밖(배치·테스트)에서도 돌아야 하므로 여기서 import 한다.
        from IPython.display import HTML, display

        display(HTML(header + kpis))
        display(summary.style.hide(axis="index"))
        for key in ("cumulative", "attribution", "stocks", "models", "sector"):
            if key in figures:
                figures[key].show()
        if period.get("sector_note"):
            display(HTML(f"<div style='color:#92400e'>※ {period['sector_note']}</div>"))

    return {"figures": figures, "tables": tables, "period": period,
            "bundle": bundle, "model": model}
