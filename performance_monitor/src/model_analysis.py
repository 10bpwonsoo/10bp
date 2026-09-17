"""상위 모델 / 하위 모델(Sub-model) 분석.

원본 구조 (Function_calculation_return_contribution_ver2.ipynb CELL 3):
    ``return_contribution_final`` 의 컬럼 = ``mp_list + ['RP']``
    - RP                  : 상위 실운용 포트폴리오
    - Hanwha_Quant_*_MP   : 하위 FP 합성 모델
    - *_FP                : 개별 하위 모델(Sub-model)

**RP 는 하위 모델의 가중합이 아니다.** 각 모델은 독립적인 active weight 시계열이며
동일한 분해식을 각각 적용한 결과를 나란히 비교하는 구조다. (Aggregation 없음)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .performance import (
    annualized_volatility,
    period_return_by_anchor,
    period_total_return,
)

__all__ = [
    "discover_models",
    "model_performance_table",
    "model_comparison_table",
    "model_cumulative_returns",
    "model_contribution_breakdown",
    "best_worst_model",
]


def discover_models(final_mp: pd.DataFrame = None,
                    temp_return_final: pd.DataFrame = None,
                    return_contribution_final: pd.DataFrame = None) -> list:
    """스냅샷에서 모델 목록을 **자동으로** 읽어온다.

    임의의 모델명을 코드에 넣지 않는다. 우선순위:
      1. ``return_contribution_final.columns`` (원본이 쓰는 정본)
      2. ``temp_return_final.columns`` 에서 'bm' 제외
      3. ``final_mp`` 의 ``total_*`` 컬럼
    """
    if return_contribution_final is not None and len(return_contribution_final.columns):
        return list(return_contribution_final.columns)
    if temp_return_final is not None and len(temp_return_final.columns):
        return [c for c in temp_return_final.columns if c != "bm"]
    if final_mp is not None:
        return [c[len("total_"):] for c in final_mp.columns if c.startswith("total_")]
    return []


def model_performance_table(temp_return_final: pd.DataFrame,
                            report_date_list,
                            anchors: dict,
                            models=None,
                            contribution: pd.Series | None = None) -> pd.DataFrame:
    """모델별 기간 성과 표 (Model / Weekly / MTD / YTD / ... / Contribution).

    수익률은 모두 ``period_total_return`` 규칙 = 앵커 다음 영업일부터 누적.
    Contribution 열은 인자로 받은 값(=`return_contribution_final.loc['active']`)을 쓴다.
    """
    models = discover_models(temp_return_final=temp_return_final) if models is None else list(models)
    end_date = list(report_date_list)[-1]

    rows = {}
    week = period_total_return(temp_return_final, report_date_list, models + ["bm"])
    rows["WTD"] = week
    for key, anchor in anchors.items():
        if anchor is None or key == "WTD":
            continue
        rows[key] = period_return_by_anchor(
            temp_return_final, anchor, end_date, models + ["bm"]
        )

    table = pd.DataFrame(rows)
    # 초과성과
    excess = table.loc[models].sub(table.loc["bm"], axis=1)
    excess.columns = [f"{c}_excess" for c in excess.columns]
    out = table.loc[models].join(excess)

    if contribution is not None:
        out["contribution"] = pd.Series(contribution).reindex(out.index)
    return out


def model_comparison_table(temp_return_final: pd.DataFrame,
                           report_date_list,
                           models,
                           return_contribution_final: pd.DataFrame | None = None,
                           include_volatility: bool = True) -> pd.DataFrame:
    """선택한 모델들의 동일 기간 비교.

    Return / Excess Return / Contribution 은 기존 코드 값 그대로.
    Volatility 는 Optional 지표(기존 코드에 없음) — config 로 끌 수 있다.
    """
    models = list(models)
    report_date_list = list(report_date_list)
    totals = period_total_return(temp_return_final, report_date_list, models + ["bm"])
    bm = totals["bm"]

    out = pd.DataFrame(index=models)
    out["return"] = totals[models]
    out["benchmark"] = bm
    out["excess_return"] = totals[models] - bm

    if include_volatility:
        window = temp_return_final.loc[report_date_list[1:]]
        out["volatility(optional)"] = [
            annualized_volatility(window[m]) for m in models
        ]

    if return_contribution_final is not None:
        for row in ("specific", "risk_factor", "industry_factor", "market_timing",
                    "country", "allocation", "selection"):
            if row in return_contribution_final.index:
                out[row] = return_contribution_final.loc[row, models].astype(float)
    return out


def model_cumulative_returns(temp_return_final: pd.DataFrame, report_date_list,
                             models, relative_to_bm: bool = False) -> pd.DataFrame:
    """모델별 누적수익률 곡선.

    원본 (CELL 54) 의 ``temp_calc_array_final`` 과 동일한 규칙:
    기준일(report_date_list[0]) 을 0 으로 두고 cumprod.
    """
    from .performance import cumulative_curve

    models = list(models)
    curve = cumulative_curve(temp_return_final, report_date_list, models + ["bm"])
    if relative_to_bm:
        return curve[models].sub(curve["bm"], axis=0)
    return curve


def model_contribution_breakdown(return_contribution_final: pd.DataFrame,
                                 rows=None) -> pd.DataFrame:
    """항목 × 모델 기여도 표 (원본 `return_contribution_final` 그대로)."""
    if rows is None:
        return return_contribution_final.copy()
    rows = [r for r in rows if r in return_contribution_final.index]
    return return_contribution_final.loc[rows].copy()


def best_worst_model(return_contribution_final: pd.DataFrame,
                     row: str = "active",
                     exclude=()):
    """Summary 화면용 Best / Worst 모델.

    상위 모델(RP)은 비교 대상에서 제외할 수 있도록 ``exclude`` 를 받는다.
    """
    series = return_contribution_final.loc[row].drop(labels=list(exclude), errors="ignore")
    series = pd.to_numeric(series, errors="coerce").dropna()
    if series.empty:
        return None, None
    return (series.idxmax(), series.max()), (series.idxmin(), series.min())
