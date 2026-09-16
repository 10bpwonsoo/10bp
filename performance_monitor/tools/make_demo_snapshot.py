"""데모(합성) 스냅샷 생성기.

사내 DB / vrksa / jackhammer 없이 **화면과 엔진을 점검**하기 위한 도구다.
여기서 만드는 숫자는 난수 기반 합성 데이터이며 실제 운용 데이터가 아니다.
manifest 의 ``source`` 가 ``demo_synthetic`` 으로 표시되고, 화면 상단에도 경고가 뜬다.

실제 운용에서는 ``tools/export_snapshot_from_notebook.py`` 또는
``tools/build_snapshot.py`` 를 사용한다.

사용법::

    python tools/make_demo_snapshot.py --weeks 26 --stocks 120
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from performance_monitor.src import pipeline  # noqa: E402
from performance_monitor.src.config import load_config  # noqa: E402
from performance_monitor.src.data_loader import SnapshotStore  # noqa: E402
from performance_monitor.src.logging_utils import RunLog, get_logger  # noqa: E402

IDX = pd.IndexSlice
SECTORS = ["반도체", "2차전지", "자동차", "은행", "화장품", "방산", "헬스케어",
           "소프트웨어", "철강", "유통", "화학", "로봇"]


def build_demo_inputs(n_days: int, n_stocks: int, models: list, seed: int = 20260911):
    rng = np.random.default_rng(seed)
    config = load_config()

    factor_map = config.bpm_factor_name_match
    list_bpm_factor = list(config.list_bpm_factor)
    all_names = sorted(set(factor_map.values()))
    list_bpm_sector = [n for n in all_names if n not in list_bpm_factor and n != "country"]
    list_bpm = list_bpm_factor + list_bpm_sector

    # freq 속성이 붙지 않도록 list 경유 (운영 date_list 와 동일 조건)
    dates = pd.DatetimeIndex(list(pd.bdate_range("2026-03-02", periods=n_days, tz="UTC")))
    items = [f"A{100000 + i * 7:06d}" for i in range(n_stocks)]
    index = pd.MultiIndex.from_product([dates, items], names=["date", "item"])
    n = len(index)

    frame = pd.DataFrame(index=index)

    # --- BM 비중 (시총 가중) ------------------------------------------------
    base_cap = rng.lognormal(mean=0.0, sigma=1.1, size=n_stocks)
    cap = pd.DataFrame(
        base_cap * np.exp(rng.normal(0, 0.01, size=(n_days, n_stocks)).cumsum(axis=0)),
        index=dates, columns=items,
    )
    bm_weight = cap.div(cap.sum(axis=1), axis=0)
    frame["bm"] = bm_weight.stack().reindex(index).values
    frame["bm_next"] = frame["bm"]

    # --- 가격/수익률 --------------------------------------------------------
    returns = pd.DataFrame(
        rng.normal(0.0004, 0.018, size=(n_days, n_stocks)), index=dates, columns=items
    )
    returns.iloc[0] = 0.0
    frame["return_d"] = returns.stack().reindex(index).values
    frame["forward_return_d"] = (
        frame["return_d"].groupby("item", group_keys=False).shift(-1)
    )

    # --- 섹터 --------------------------------------------------------------
    sector_of = {item: SECTORS[i % len(SECTORS)] for i, item in enumerate(items)}
    sector_series = pd.Series([sector_of[i] for i in index.get_level_values("item")],
                              index=index)
    frame["q_sector"] = sector_series
    frame["new_sector"] = sector_series

    # --- Barra exposure ----------------------------------------------------
    for factor in list_bpm_factor:
        frame[factor] = rng.normal(0, 1, size=n)
    industry_of = {item: list_bpm_sector[i % len(list_bpm_sector)]
                   for i, item in enumerate(items)}
    for industry in list_bpm_sector:
        flags = np.array([1.0 if industry_of[i] == industry else 0.0
                          for i in index.get_level_values("item")])
        frame[industry] = flags
    frame["country"] = 1.0
    frame["predictive_beta"] = 1.0 + rng.normal(0, 0.25, size=n)

    # --- 모델 active weight (리밸런싱 + drift) ------------------------------
    # NOTE: 실제 운용에서는 jackhammer 백테스트가 이 값을 만든다. 데모 전용 근사다.
    rebal_dates = list(dates[::5])
    for model in models:
        raw = pd.DataFrame(0.0, index=dates, columns=items)
        for rebal in rebal_dates:
            picks = rng.choice(n_stocks, size=max(8, n_stocks // 4), replace=False)
            active = np.zeros(n_stocks)
            active[picks] = rng.normal(0, 0.004, size=len(picks))
            active -= active.mean()
            raw.loc[rebal] = active
        total = raw.add(bm_weight)
        # 리밸런싱일 사이 drift
        drifted = total.copy()
        for pos in range(1, n_days):
            if dates[pos] in rebal_dates:
                continue
            prev = drifted.iloc[pos - 1] * (1 + returns.iloc[pos])
            drifted.iloc[pos] = prev / prev.sum()
        frame[f"total_{model}"] = drifted.stack().reindex(index).values
        frame[model] = frame[f"total_{model}"] - frame["bm"]
        frame[f"{model}_next"] = frame[f"total_{model}"] - frame["bm_next"]

    # --- 포트폴리오 / BM 일별 수익률 ---------------------------------------
    # NOTE: 실제로는 jackhammer backtest_result.returns 를 쓴다. 데모 전용 근사다.
    temp_return_final = pd.DataFrame(index=dates)
    for model in models:
        weights = frame[f"total_{model}"].unstack()
        temp_return_final[model] = (weights.shift(1) * returns).sum(axis=1)
    temp_return_final["bm"] = (bm_weight.shift(1) * returns).sum(axis=1)
    temp_return_final.iloc[0] = 0.0

    # --- Barra factor return -----------------------------------------------
    rtn_bpm = pd.DataFrame(
        rng.normal(0, 0.003, size=(n_days, len(list_bpm))), index=dates, columns=list_bpm
    )
    rtn_bpm["country"] = temp_return_final["bm"].values * 0.9

    bpm_pred_beta = frame["predictive_beta"].unstack()

    data_bpm_factor = frame[["q_sector", "new_sector", "return_d", "forward_return_d"]].copy()
    data_bpm_factor["weight_kospi200"] = frame["bm"]
    data_bpm_factor["weight_kospi200_next"] = frame["bm_next"]

    index_market_cap = pd.DataFrame(index=index)
    index_market_cap["bm"] = cap.stack().reindex(index).values
    index_market_cap["bm_next"] = index_market_cap["bm"]
    index_market_cap["q_sector"] = sector_series
    index_market_cap["new_sector"] = sector_series

    info_stock = pd.DataFrame(
        {"name_stock": [f"데모종목{i+1:03d}" for i in range(n_stocks)]},
        index=pd.Index(items, name="item"),
    )

    return dict(
        final_mp=frame, temp_return_final=temp_return_final, rtn_bpm=rtn_bpm,
        data_bpm_factor=data_bpm_factor, bpm_pred_beta=bpm_pred_beta,
        index_market_cap=index_market_cap, info_stock=info_stock,
        dates=dates, list_bpm_factor=list_bpm_factor, list_bpm_sector=list_bpm_sector,
    )


def main(weeks: int, stocks: int, report_days: int, seed: int) -> Path:
    config = load_config()
    log = RunLog(get_logger("demo_snapshot", log_dir=config.log_dir))

    analysis_bm = config.default_benchmark
    models = config.mp_list(analysis_bm) + [config.top_model_column(analysis_bm)]
    n_days = weeks * 5

    log.info(f"데모 데이터 생성 | {n_days}영업일 × {stocks}종목 × {len(models)}모델")
    data = build_demo_inputs(n_days, stocks, models, seed=seed)

    dates = data["dates"]
    date_list = list(dates)
    report_date_list = list(dates[-(report_days + 1):])

    log.info(f"분석 구간 {str(date_list[0])[:10]} ~ {str(date_list[-1])[:10]}")
    log.info(f"리포트 구간 {str(report_date_list[0])[:10]} ~ {str(report_date_list[-1])[:10]}")

    result = pipeline.run_attribution(
        final_mp=data["final_mp"],
        temp_return_final=data["temp_return_final"],
        rtn_bpm=data["rtn_bpm"],
        data_bpm_factor=data["data_bpm_factor"],
        bpm_pred_beta=data["bpm_pred_beta"],
        index_market_cap=data["index_market_cap"],
        date_list=date_list,
        report_date_list=report_date_list,
        analysis_bm=analysis_bm,
        list_bpm_factor=data["list_bpm_factor"],
        list_bpm_sector=data["list_bpm_sector"],
        top_model_column=config.top_model_column(analysis_bm),
        logger=log,
    )

    as_of = str(report_date_list[-1])[:10]
    manifest = {
        "as_of": as_of,
        "analysis_bm": analysis_bm,
        "mp_start_date": str(date_list[0])[:10],
        "report_start_date": str(report_date_list[0])[:10],
        "mp_end_date": as_of,
        "models": result["columns"],
        "top_model_column": config.top_model_column(analysis_bm),
        "list_bpm_factor": data["list_bpm_factor"],
        "list_bpm_sector": data["list_bpm_sector"],
        "source": "demo_synthetic",
        "warning": "합성 데이터입니다. 실제 운용 성과가 아닙니다.",
        "n_rows_final_mp": int(len(result["final_mp"])),
    }

    store = SnapshotStore.create(config.processed_dir, as_of, manifest)
    for name in ("final_mp", "temp_return_final", "betalog_final",
                 "return_contribution_final", "compare_final",
                 "sector_compare_final", "new_sector_compare_final",
                 "sector_index_market_cap", "new_sector_index_market_cap"):
        store.write_table(name, result[name])
    store.write_table("rtn_bpm", data["rtn_bpm"])
    store.write_table("info_stock", data["info_stock"])

    # 비교기간 기준일. 운영에서는 WORKDATE_MAST_TB 조회값이지만,
    # 데모에서는 같은 의미(직전 월말/분기말/반기말/연말 영업일)를 달력으로 계산한다.
    end = dates[-1]

    def _last_bd_before(period_end):
        """period_end 이전(미포함)의 마지막 영업일."""
        prior = [d for d in dates if d <= period_end]
        return prior[-1] if prior else None

    def _prev_month_end(ts, months=1):
        first = ts.normalize().replace(day=1)
        for _ in range(months):
            first = (first - pd.Timedelta(days=1)).replace(day=1)
        return first + pd.offsets.MonthEnd(0)

    anchors = {"WTD": str(report_date_list[0])[:10]}
    candidates = {
        "MTD": _prev_month_end(end),
        "QTD": _last_bd_before(pd.Timestamp(f"{end.year}-{((end.month - 1) // 3) * 3:02d}-28", tz="UTC"))
        if end.month > 3 else None,
        "HTD": _last_bd_before(pd.Timestamp(f"{end.year}-06-30", tz="UTC"))
        if end.month > 6 else None,
        "YTD": dates[0],
        "1Y": dates[0],
    }
    for key, value in candidates.items():
        if value is None:
            continue
        anchor = _last_bd_before(pd.Timestamp(value))
        if anchor is not None and anchor < end:
            anchors[key] = str(anchor)[:10]
    log.info(f"anchors: {anchors}")
    store.write_json("anchors", anchors)

    log.info(f"데모 스냅샷 완료: {store.path}")
    rcf = result["return_contribution_final"]
    top = manifest["top_model_column"]
    log.info(
        f"{top} | total {float(rcf.loc['total', top]):.4%} "
        f"| bm {float(rcf.loc['bm', top]):.4%} "
        f"| active {float(rcf.loc['active', top]):.4%}"
    )
    return store.path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weeks", type=int, default=26)
    parser.add_argument("--stocks", type=int, default=120)
    parser.add_argument("--report-days", type=int, default=5,
                        help="리포트 구간 영업일 수 (기준일 제외)")
    parser.add_argument("--seed", type=int, default=20260911)
    args = parser.parse_args()
    main(args.weeks, args.stocks, args.report_days, args.seed)
