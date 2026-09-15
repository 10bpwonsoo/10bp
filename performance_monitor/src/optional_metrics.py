"""Optional 지표 (Tracking Error / Hit Ratio / Turnover).

⚠ **이 지표들은 기존 notebook / Python 코드에 존재하지 않는다.**
노트북의 risk profile 셀(CELL 57~64)은 '서버 과부하로 인한 미실행' 상태라
Tracking Error 를 만들지 않는다.

따라서 기본값은 OFF 이고 (`config.yaml` → `optional_metrics`),
켜더라도 화면에 'Optional (기존 코드 외)' 로 명시한다.
**노트북 결과와의 대조 대상이 아니다.**

여기의 정의는 업계 표준 정의이며, 회사 내부 정의와 다를 수 있다.
실제로 쓰려면 운용팀 확인 후 정의를 확정해야 한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = ["tracking_error", "hit_ratio", "turnover", "render_optional_kpis"]


def tracking_error(model_returns: pd.Series, bm_returns: pd.Series,
                   periods_per_year: int = 250) -> float:
    """연율화 Tracking Error = std(active daily return) × √250.

    OPTIONAL — 기존 코드에 없음. ex-post(실현) TE 정의를 사용한다.
    (Barra 의 ex-ante predicted TE 와 다르다)
    """
    active = pd.Series(model_returns).astype(float) - pd.Series(bm_returns).astype(float)
    active = active.dropna()
    if len(active) < 2:
        return float("nan")
    return float(active.std(ddof=1) * np.sqrt(periods_per_year))


def hit_ratio(model_returns: pd.Series, bm_returns: pd.Series) -> float:
    """일별 초과수익률이 양(+)인 날의 비율.

    OPTIONAL — 기존 코드에 없음.
    """
    active = pd.Series(model_returns).astype(float) - pd.Series(bm_returns).astype(float)
    active = active.dropna()
    if active.empty:
        return float("nan")
    return float((active > 0).sum() / len(active))


def turnover(final_mp: pd.DataFrame, report_date_list, model: str) -> float:
    """구간 단방향 turnover = Σ_d Σ_i |w[d,i] − w[d-1,i]| / 2.

    OPTIONAL — 기존 코드에 없음. 주의: 여기 weight 는 jackhammer drift 가 반영된
    일별 total weight 이므로, 리밸런싱 매매회전율이 아니라 **비중 변화량**이다.
    실제 매매 turnover 는 `portfolios.portfolio_trades` 를 써야 한다.
    """
    column = f"total_{model}"
    if column not in final_mp.columns:
        return float("nan")
    report_date_list = list(report_date_list)
    weights = final_mp.loc[(report_date_list, slice(None)), column].unstack().fillna(0.0)
    return float(weights.diff().abs().sum(axis=1).sum() / 2)


def render_optional_kpis(ctx: dict, period, model: str, enabled: dict) -> None:
    """Streamlit 표시 (app.py 에서 호출)."""
    import streamlit as st

    bundle = ctx["bundle"]
    report_date_list = period["report_date_list"]
    returns = bundle["temp_return_final"].loc[report_date_list[1:]]

    items = []
    if enabled.get("tracking_error"):
        value = tracking_error(returns[model], returns["bm"])
        items.append(("Tracking Ratio (Optional)", f"{value:.2%}",
                      None, "연율화 실현 TE. 기존 코드에 없는 지표."))
    if enabled.get("hit_ratio"):
        value = hit_ratio(returns[model], returns["bm"])
        items.append(("Hit Ratio (Optional)", f"{value:.1%}",
                      None, "일별 초과수익 양(+) 비율. 기존 코드에 없는 지표."))
    if enabled.get("turnover"):
        value = turnover(bundle["final_mp"], report_date_list, model)
        items.append(("Weight Change (Optional)", f"{value:.2%}",
                      None, "일별 비중 변화량 합/2. 실제 매매 turnover 가 아니다."))
    if items:
        from src import ui

        ui.metric_row(items)
