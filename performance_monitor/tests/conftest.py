import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def toy():
    """작지만 구조가 동일한 합성 데이터.

    - 8 영업일, 6 종목, 3 모델
    - risk factor 2개 / industry factor 2개 / country
    """
    rng = np.random.default_rng(7)
    # 운영 코드의 date_list 는 sorted(set(...)) 으로 만들어져 freq 속성이 없다.
    # 동일한 조건을 맞추기 위해 freq 를 제거한다.
    dates = pd.DatetimeIndex(list(pd.bdate_range("2026-01-05", periods=8, tz="UTC")))
    items = [f"A{i:06d}" for i in (1, 2, 3, 4, 5, 6)]
    columns = ["MODEL_A_FP", "MODEL_B_FP", "RP"]
    list_bpm_factor = ["value", "momentum"]
    list_bpm_sector = ["banks", "chemicals"]

    index = pd.MultiIndex.from_product([dates, items], names=["date", "item"])
    n = len(index)
    frame = pd.DataFrame(index=index)

    cap = pd.DataFrame(
        rng.lognormal(0, 0.8, size=(len(dates), len(items))), index=dates, columns=items
    )
    bm_weight = cap.div(cap.sum(axis=1), axis=0)
    frame["bm"] = bm_weight.stack().reindex(index).values
    frame["bm_next"] = frame["bm"]

    returns = pd.DataFrame(
        rng.normal(0.001, 0.02, size=(len(dates), len(items))), index=dates, columns=items
    )
    returns.iloc[0] = 0.0
    frame["return_d"] = returns.stack().reindex(index).values
    frame["forward_return_d"] = frame["return_d"].groupby("item", group_keys=False).shift(-1)

    sectors = ["금융", "소재", "금융", "소재", "IT", "IT"]
    frame["q_sector"] = pd.Series(
        [sectors[items.index(i)] for i in index.get_level_values("item")], index=index
    )
    frame["new_sector"] = frame["q_sector"]

    for factor in list_bpm_factor:
        frame[factor] = rng.normal(0, 1, size=n)
    for pos, industry in enumerate(list_bpm_sector):
        frame[industry] = np.array(
            [1.0 if items.index(i) % 2 == pos else 0.0 for i in index.get_level_values("item")]
        )
    frame["country"] = 1.0
    frame["predictive_beta"] = 1.0 + rng.normal(0, 0.2, size=n)

    for model in columns:
        active = pd.DataFrame(
            rng.normal(0, 0.01, size=(len(dates), len(items))), index=dates, columns=items
        )
        active = active.sub(active.mean(axis=1), axis=0)
        total = active + bm_weight
        frame[f"total_{model}"] = total.stack().reindex(index).values
        frame[model] = frame[f"total_{model}"] - frame["bm"]
        frame[f"{model}_next"] = frame[f"total_{model}"] - frame["bm_next"]

    temp_return_final = pd.DataFrame(index=dates)
    for model in columns:
        weights = frame[f"total_{model}"].unstack()
        temp_return_final[model] = (weights.shift(1) * returns).sum(axis=1)
    temp_return_final["bm"] = (bm_weight.shift(1) * returns).sum(axis=1)
    temp_return_final.iloc[0] = 0.0

    list_bpm = list_bpm_factor + list_bpm_sector
    rtn_bpm = pd.DataFrame(
        rng.normal(0, 0.004, size=(len(dates), len(list_bpm))), index=dates, columns=list_bpm
    )
    rtn_bpm["country"] = temp_return_final["bm"].values

    bpm_pred_beta = frame["predictive_beta"].unstack()
    data_bpm_factor = frame[["q_sector", "new_sector"]].copy()
    data_bpm_factor["weight_kospi200"] = frame["bm"]
    data_bpm_factor["weight_kospi200_next"] = frame["bm_next"]

    index_market_cap = pd.DataFrame(index=index)
    index_market_cap["bm"] = cap.stack().reindex(index).values
    index_market_cap["bm_next"] = index_market_cap["bm"]
    index_market_cap["q_sector"] = frame["q_sector"]
    index_market_cap["new_sector"] = frame["new_sector"]

    return dict(
        final_mp=frame,
        temp_return_final=temp_return_final,
        rtn_bpm=rtn_bpm,
        bpm_pred_beta=bpm_pred_beta,
        data_bpm_factor=data_bpm_factor,
        index_market_cap=index_market_cap,
        dates=list(dates),
        items=items,
        columns=columns,
        list_bpm_factor=list_bpm_factor,
        list_bpm_sector=list_bpm_sector,
        date_list=list(dates),
        report_date_list=list(dates[-4:]),
        analysis_bm="kospi200",
    )
