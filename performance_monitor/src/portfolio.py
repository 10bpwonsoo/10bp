"""종목 비중 / Active Weight / 주간 포지션 변화.

원본 `final_mp` 의 컬럼 규칙:
    <model>        active weight (당일 BM 대비)
    <model>_next   active weight (차기 BM 대비)  ← 기여도 계산용
    total_<model>  total weight  (= active + bm)
    bm, bm_next    BM weight

화면용 표는 원본 노트북 CELL 48/55/73/76 의 조합을 하나의 표로 정리한 것이다.
비중·기여도 값 자체는 `final_mp` 원본 값을 그대로 사용한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "weight_snapshot",
    "stock_weight_table",
    "active_weight_table",
    "position_change",
    "portfolio_weight_sum",
]


def _model_columns(model: str):
    return {
        "active": model,
        "active_next": model + "_next",
        "total": "total_" + model,
    }


def weight_snapshot(final_mp: pd.DataFrame, date, model: str) -> pd.DataFrame:
    """특정 일자의 모델 비중 스냅샷 (total / active / bm)."""
    cols = _model_columns(model)
    frame = final_mp.xs(pd.Timestamp(date))
    out = pd.DataFrame(index=frame.index)
    out["total_weight"] = frame[cols["total"]]
    out["bm_weight"] = frame["bm"]
    out["active_weight"] = frame[cols["active"]]
    return out


def stock_weight_table(final_mp: pd.DataFrame, report_date_list, model: str,
                       contribution: pd.Series | None = None,
                       info_stock: pd.DataFrame | None = None) -> pd.DataFrame:
    """종목별 시작/종료/평균 비중 + 기간수익률 + 기여도.

    - 시작비중 = ``report_date_list[0]`` (기준일) 의 weight
    - 종료비중 = ``report_date_list[-1]`` 의 weight
    - 평균비중 = 리포트 구간 평균 (원본 CELL 68 의 ``groupby('item')['weight'].mean()`` 규칙)
    - 기간수익률 = ``(1 + return_d).prod() - 1`` (report_date_list[1:] 구간)
      → ``return_d`` 는 원본 `data_bpm_factor['return_d']` 가 final_mp 에 join 된 값이다.
    - 기여도 = 인자로 받은 값 (attribution.stock_contribution 결과)
    """
    report_date_list = list(report_date_list)
    cols = _model_columns(model)
    start_date, end_date = report_date_list[0], report_date_list[-1]

    window = final_mp.loc[(report_date_list, slice(None)), :]
    items = sorted(set(window.index.get_level_values("item")))

    out = pd.DataFrame(index=pd.Index(items, name="item"))
    start_slice = final_mp.loc[(start_date, slice(None)), :].droplevel("date")
    end_slice = final_mp.loc[(end_date, slice(None)), :].droplevel("date")

    out["start_weight"] = start_slice[cols["total"]].reindex(items)
    out["end_weight"] = end_slice[cols["total"]].reindex(items)
    out["avg_weight"] = window[cols["total"]].groupby("item", group_keys=False).mean().reindex(items)
    out["bm_weight_start"] = start_slice["bm"].reindex(items)
    out["bm_weight_end"] = end_slice["bm"].reindex(items)
    out["active_weight_start"] = start_slice[cols["active"]].reindex(items)
    out["active_weight_end"] = end_slice[cols["active"]].reindex(items)
    out["avg_active_weight"] = (
        window[cols["active"]].groupby("item", group_keys=False).mean().reindex(items)
    )

    if "return_d" in final_mp.columns:
        period_window = final_mp.loc[(report_date_list[1:], slice(None)), "return_d"]
        out["period_return"] = (
            (1 + period_window).groupby("item", group_keys=False).prod() - 1
        ).reindex(items)

    if contribution is not None:
        out["contribution"] = pd.Series(contribution).reindex(items)

    if info_stock is not None and "name_stock" in info_stock.columns:
        out.insert(0, "name", info_stock["name_stock"].reindex(items))
    return out


def active_weight_table(final_mp: pd.DataFrame, date, model: str,
                        contribution: pd.Series | None = None,
                        info_stock: pd.DataFrame | None = None) -> pd.DataFrame:
    """Overweight / Underweight 분석용 표.

    Active Weight = Portfolio Weight − Benchmark Weight  (= final_mp[model] 원본값)
    """
    snap = weight_snapshot(final_mp, date, model)
    out = snap.rename(
        columns={
            "total_weight": "portfolio_weight",
            "bm_weight": "benchmark_weight",
        }
    )
    if contribution is not None:
        out["active_contribution"] = pd.Series(contribution).reindex(out.index)
    if info_stock is not None and "name_stock" in info_stock.columns:
        out.insert(0, "name", info_stock["name_stock"].reindex(out.index))
    return out.sort_values("active_weight", ascending=False)


def position_change(final_mp: pd.DataFrame, prev_date, curr_date, model: str,
                    info_stock: pd.DataFrame | None = None,
                    threshold: float = 0.0) -> pd.DataFrame:
    """주간 포지션 변화.

    ``final_mp`` 의 total weight 를 두 일자에서 비교한다.
    - 신규 편입: prev == 0 (또는 미존재) & curr > threshold
    - 제외: prev > threshold & curr == 0 (또는 미존재)
    """
    cols = _model_columns(model)
    prev = final_mp.loc[(pd.Timestamp(prev_date), slice(None)), :].droplevel("date")
    curr = final_mp.loc[(pd.Timestamp(curr_date), slice(None)), :].droplevel("date")
    items = sorted(set(prev.index) | set(curr.index))

    out = pd.DataFrame(index=pd.Index(items, name="item"))
    out["previous_weight"] = prev[cols["total"]].reindex(items).fillna(0.0)
    out["current_weight"] = curr[cols["total"]].reindex(items).fillna(0.0)
    out["change"] = out["current_weight"] - out["previous_weight"]
    out["previous_active"] = prev[cols["active"]].reindex(items).fillna(0.0)
    out["current_active"] = curr[cols["active"]].reindex(items).fillna(0.0)
    out["active_change"] = out["current_active"] - out["previous_active"]

    out["status"] = "유지"
    out.loc[(out["previous_weight"] <= threshold) & (out["current_weight"] > threshold), "status"] = "신규편입"
    out.loc[(out["previous_weight"] > threshold) & (out["current_weight"] <= threshold), "status"] = "제외"

    if info_stock is not None and "name_stock" in info_stock.columns:
        out.insert(0, "name", info_stock["name_stock"].reindex(items))
    return out.sort_values("change", ascending=False)


def portfolio_weight_sum(final_mp: pd.DataFrame, date, model: str) -> dict:
    """비중 합 검증용."""
    cols = _model_columns(model)
    frame = final_mp.xs(pd.Timestamp(date))
    return {
        "total_weight_sum": float(frame[cols["total"]].sum()),
        "bm_weight_sum": float(frame["bm"].sum()),
        "active_weight_sum": float(frame[cols["active"]].sum()),
        "n_holdings": int((frame[cols["total"]].abs() > 0).sum()),
    }
