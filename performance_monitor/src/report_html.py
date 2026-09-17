"""주간 성과 리포트를 **파일 하나**로 내보낸다.

대시보드 서버를 외부에 노출하지 않고, 승인된 사내 채널(메일·그룹웨어)로
전달해서 휴대폰에서 보기 위한 것이다.

    import pm_engine as pm
    pm.export_html()                  # 최신 스냅샷, 주간
    pm.export_html(preset='MTD')      # 월간

계산은 `notebook_report.report()` 를 그대로 쓴다. **여기서 새로 계산하는 것은
없다.** 대시보드·노트북과 숫자가 같다.

기본값은 plotly.js 를 파일 안에 넣는 완전 독립 파일이다(약 4MB). 인터넷을
전혀 쓰지 않으므로 원 사양(외부 의존 금지)에 맞는다. 메일 용량이 문제면
``slim=True`` 로 plotly.js 를 CDN 에서 받게 할 수 있다(파일 ~1MB, 볼 때
인터넷 필요).

**이 파일에는 보유종목과 비중이 들어 있다. 사내 기밀이다.**
전달 경로는 회사 규정을 따르십시오.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from .colors import sign_colors
from .config import load_config
from .utils import fmt_pct

__all__ = ["export_html"]

CSS = """
:root { --pos:%(pos)s; --neg:%(neg)s; --ink:#0f172a; --muted:#64748b;
        --line:#e2e8f0; --bg:#ffffff; --panel:#f8fafc; }
* { box-sizing: border-box; }
body { margin:0; padding:0 16px 48px; background:var(--bg); color:var(--ink);
       font-family:-apple-system,BlinkMacSystemFont,"Malgun Gothic",system-ui,sans-serif;
       -webkit-text-size-adjust:100%%; }
.wrap { max-width: 1040px; margin: 0 auto; }
.notice { background:#fef3c7; color:#92400e; border-radius:6px; padding:.6rem .8rem;
          font-size:.82rem; margin:16px 0 8px; }
.demo { background:#fee2e2; color:#991b1b; border-radius:6px; padding:.6rem .8rem;
        font-weight:600; margin:16px 0 8px; }
h1 { font-size:1.25rem; margin:.8rem 0 .2rem; letter-spacing:-.01em; }
.meta { color:var(--muted); font-size:.82rem; line-height:1.7; margin-bottom:1rem; }
.meta b { color:var(--ink); font-weight:600; }
.kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
        gap:10px; margin:0 0 1.2rem; }
.kpi { background:var(--panel); border:1px solid var(--line); border-radius:8px;
       padding:.7rem .8rem; }
.kpi .label { color:var(--muted); font-size:.72rem; margin-bottom:.25rem; }
.kpi .value { font-size:1.25rem; font-weight:650; letter-spacing:-.02em; }
.pos { color:var(--pos); } .neg { color:var(--neg); }
h2 { font-size:.95rem; margin:1.6rem 0 .5rem; padding-bottom:.35rem;
     border-bottom:1px solid var(--line); }
table { border-collapse:collapse; width:100%%; font-size:.82rem; }
th, td { padding:.45rem .5rem; border-bottom:1px solid var(--line); text-align:right; }
th:first-child, td:first-child { text-align:left; }
th { color:var(--muted); font-weight:600; font-size:.74rem; }
.scroll { overflow-x:auto; -webkit-overflow-scrolling:touch; }
.figure { margin:.4rem 0 1rem; }
footer { color:var(--muted); font-size:.74rem; margin-top:2.5rem;
         border-top:1px solid var(--line); padding-top:.8rem; }
@media (max-width:560px) {
  h1 { font-size:1.1rem; }
  .kpis { grid-template-columns:repeat(2,1fr); }
  .kpi .value { font-size:1.05rem; }
}
"""


def _kpi(label: str, value: float) -> str:
    cls = "pos" if value >= 0 else "neg"
    return (f'<div class="kpi"><div class="label">{label}</div>'
            f'<div class="value {cls}">{fmt_pct(value)}</div></div>')


def _table(frame: pd.DataFrame, formatter=None) -> str:
    if frame is None or len(frame) == 0:
        return "<p style='color:#64748b'>해당 없음</p>"
    display = frame.copy()
    if formatter:
        for column in display.columns:
            if pd.api.types.is_numeric_dtype(display[column]):
                display[column] = display[column].map(formatter)
    return '<div class="scroll">' + display.to_html(
        border=0, escape=False, classes="", justify="right") + "</div>"


def export_html(as_of: str | None = None, model: str | None = None,
                preset: str = "1W", sector_field: str = "new_sector",
                top_n: int = 10, out: str | Path | None = None,
                slim: bool = False) -> Path:
    """리포트를 HTML 파일 하나로 저장하고 경로를 돌려준다.

    Parameters
    ----------
    slim   True 면 plotly.js 를 CDN 에서 받는다 (파일이 작아지지만 볼 때
           인터넷이 필요하다). 기본 False = 완전 독립 파일.
    """
    from .notebook_report import report as _report

    result = _report(as_of=as_of, model=model, preset=preset,
                     sector_field=sector_field, top_n=top_n, show=False)

    config = load_config()
    bundle = result["bundle"]
    manifest = bundle["manifest"]
    period = result["period"]
    rcf = period["return_contribution_final"]
    model = result["model"]
    names = config.model_display_names(manifest.get("analysis_bm", ""))
    dates = period["report_date_list"]

    total = float(rcf.loc["total", model])
    bm = float(rcf.loc["bm", model])
    active = float(rcf.loc["active", model])

    scheme = sign_colors()
    parts = [
        "<!DOCTYPE html><html lang='ko'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>MP Performance {manifest.get('mp_end_date','')} {preset}</title>",
        "<style>" + CSS % {"pos": scheme["positive"], "neg": scheme["negative"]}
        + "</style></head><body><div class='wrap'>",
    ]

    if manifest.get("source") == "demo_synthetic":
        parts.append("<div class='demo'>데모(합성) 데이터입니다. "
                     "실제 운용 성과가 아닙니다.</div>")
    parts.append("<div class='notice'><b>내부용 · 대외비</b> — 보유종목과 비중이 "
                 "포함되어 있습니다. 사내 규정에 따라 취급하십시오.</div>")

    start, end = str(dates[0])[:10], str(dates[-1])[:10]
    parts += [
        "<h1>MP PERFORMANCE REPORT</h1>",
        "<div class='meta'>",
        f"기간 <b>{start} ~ {end}</b> ({preset})<br>",
        f"Model <b>{names.get(model, model)}</b> · ",
        f"Benchmark <b>{config.benchmark_display(manifest.get('analysis_bm',''))}</b><br>",
        f"Data As of <b>{manifest.get('mp_end_date','')}</b> · ",
        f"계산 출처 <b>{period['source']}</b>",
        "</div>",
        '<div class="kpis">',
        _kpi("MP Return", total), _kpi("Benchmark", bm), _kpi("Excess Return", active),
        _kpi("Specific", float(rcf.loc["specific", model])),
        _kpi("Risk Factor", float(rcf.loc["risk_factor", model])),
        _kpi("Industry Factor", float(rcf.loc["industry_factor", model])),
        "</div>",
    ]

    parts.append("<h2>요약</h2>")
    parts.append(_table(result["tables"]["summary"].set_index("구분")))

    first = True
    titles = {"cumulative": "누적 성과", "attribution": "성과 기여도 (항목별)",
              "stocks": f"종목별 기여도 Top / Bottom {top_n}",
              "models": "모델별 Active", "sector": f"업종별 기여도 ({sector_field})"}
    for key, title in titles.items():
        figure = result["figures"].get(key)
        if figure is None:
            continue
        parts.append(f"<h2>{title}</h2>")
        # 제목은 위의 <h2> 로 이미 붙였다. 그림 안의 제목을 그대로 두면
        # 범례와 겹친다 (폰 화면에서 특히).
        figure.update_layout(title=None, margin=dict(l=8, r=8, t=28, b=8))
        # plotly.js 는 첫 그림에만 넣는다. 매번 넣으면 파일이 5배가 된다.
        js = ("cdn" if slim else True) if first else False
        parts.append('<div class="figure">' + figure.to_html(
            full_html=False, include_plotlyjs=js,
            config={"responsive": True, "displayModeBar": False}) + "</div>")
        first = False

    parts.append("<h2>항목별 기여도</h2>")
    parts.append(_table(result["tables"]["attribution"], lambda v: fmt_pct(v, 3)))

    stocks = result["tables"]["stocks"]
    if stocks is not None and len(stocks):
        columns = [c for c in ("name", "contribution", "weight", "return_d")
                   if c in stocks.columns]
        parts.append(f"<h2>기여 상위 {top_n}</h2>")
        parts.append(_table(result["tables"]["top"][columns], lambda v: fmt_pct(v, 3)))
        parts.append(f"<h2>기여 하위 {top_n}</h2>")
        parts.append(_table(result["tables"]["bottom"][columns], lambda v: fmt_pct(v, 3)))

    parts += [
        "<footer>",
        f"생성 {datetime.now().strftime('%Y-%m-%d %H:%M')} · ",
        "계산은 Dashboard 와 동일한 엔진(src/dashboard_engine.py)을 사용합니다.",
        "</footer></div></body></html>",
    ]

    if out is None:
        directory = config.data_dir / "reports"
        directory.mkdir(parents=True, exist_ok=True)
        stamp = str(manifest.get("mp_end_date", "")).replace("-", "")
        out = directory / f"performance_{stamp}_{preset}.html"
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(parts), encoding="utf-8")

    size = out.stat().st_size / 1024 / 1024
    print(f"리포트 저장: {out}  ({size:.1f} MB)")
    print("  내부용·대외비입니다. 전달은 사내 규정에 따르십시오.")
    if not slim:
        print("  인터넷 없이 열립니다 (plotly.js 포함).")
        print("  메일 용량이 문제면 pm.export_html(slim=True) 로 줄일 수 있습니다.")
    return out
