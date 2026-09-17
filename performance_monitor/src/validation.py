"""Data Validation Layer.

금융 데이터이므로 **오류를 숨기거나 자동으로 0 처리하지 않는다.**
문제가 있으면 해당 종목/일자를 그대로 열거해 화면 상단에 경고로 띄운다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

__all__ = ["Check", "ValidationReport", "run_validation"]

OK = "OK"
WARN = "WARNING"
ERROR = "ERROR"


@dataclass
class Check:
    name: str
    status: str
    value: object = None
    detail: str = ""
    items: list = field(default_factory=list)

    @property
    def is_ok(self) -> bool:
        return self.status == OK


@dataclass
class ValidationReport:
    checks: list = field(default_factory=list)

    def add(self, check: Check) -> None:
        self.checks.append(check)

    @property
    def has_error(self) -> bool:
        return any(c.status == ERROR for c in self.checks)

    @property
    def has_warning(self) -> bool:
        return any(c.status == WARN for c in self.checks)

    @property
    def problems(self) -> list:
        return [c for c in self.checks if c.status != OK]

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "항목": c.name,
                    "상태": c.status,
                    "값": c.value,
                    "설명": c.detail,
                    "대상 수": len(c.items),
                }
                for c in self.checks
            ]
        )


def _resolve_date(index, value):
    ts = pd.Timestamp(value)
    tz = getattr(index, "tz", None)
    if ts.tzinfo is None and tz is not None:
        ts = ts.tz_localize(tz)
    return ts


def run_validation(bundle: dict, model: str, report_date_list,
                   tolerances: dict | None = None) -> ValidationReport:
    """스냅샷 전체 검증.

    검증 항목: Missing Price / Missing Weight / Duplicate Stock / Weight Sum /
               Missing Benchmark / Missing Model / Date Gap / Invalid Return /
               Contribution Reconciliation
    """
    tolerances = tolerances or {}
    weight_tol = tolerances.get("weight_sum_tolerance", 0.005)
    bm_tol = tolerances.get("bm_weight_sum_tolerance", 0.005)
    recon_tol = tolerances.get("contribution_reconciliation_tolerance", 1e-6)

    report = ValidationReport()
    final_mp = bundle.get("final_mp")
    temp_return_final = bundle.get("temp_return_final")
    rcf = bundle.get("return_contribution_final")
    report_date_list = list(report_date_list)

    if final_mp is None or temp_return_final is None:
        report.add(Check("Snapshot", ERROR, None, "필수 테이블이 없습니다."))
        return report

    dates = pd.DatetimeIndex(final_mp.index.get_level_values("date").unique()).sort_values()
    window = final_mp.loc[(report_date_list, slice(None)), :]

    # --- Duplicate Stock ---------------------------------------------------
    dup_mask = final_mp.index.duplicated(keep=False)
    dup_items = sorted(set(final_mp.index[dup_mask].get_level_values("item"))) if dup_mask.any() else []
    report.add(Check(
        "Duplicate (date,item)",
        ERROR if dup_items else OK,
        int(dup_mask.sum()),
        "동일 (일자, 종목) 행이 중복되었습니다." if dup_items else "중복 없음",
        dup_items[:50],
    ))

    # --- Missing Price / Invalid Return -----------------------------------
    if "return_d" in final_mp.columns:
        holding = window[window[f"total_{model}"].abs() > 0] if f"total_{model}" in window.columns else window
        missing = holding[holding["return_d"].isna()]
        missing_items = sorted(set(missing.index.get_level_values("item")))
        report.add(Check(
            "Missing Price / Return",
            ERROR if missing_items else OK,
            len(missing),
            "보유 종목의 일별 수익률이 없습니다. (0으로 대체하지 않았습니다)"
            if missing_items else "결측 없음",
            missing_items[:50],
        ))

        invalid = holding[
            holding["return_d"].notna()
            & (~np.isfinite(holding["return_d"].astype(float)) | (holding["return_d"].astype(float) <= -1.0))
        ]
        invalid_items = sorted(set(invalid.index.get_level_values("item")))
        report.add(Check(
            "Invalid Return",
            ERROR if invalid_items else OK,
            len(invalid),
            "수익률이 -100% 이하이거나 inf 입니다." if invalid_items else "이상치 없음",
            invalid_items[:50],
        ))
    else:
        report.add(Check("Missing Price / Return", WARN, None,
                         "스냅샷에 return_d 컬럼이 없습니다."))

    # --- Missing Weight ----------------------------------------------------
    total_col = f"total_{model}"
    if total_col in final_mp.columns:
        nan_weight = window[window[total_col].isna()]
        nan_items = sorted(set(nan_weight.index.get_level_values("item")))
        report.add(Check(
            "Missing Weight",
            ERROR if nan_items else OK,
            len(nan_weight),
            f"{total_col} 값이 NaN 입니다." if nan_items else "결측 없음",
            nan_items[:50],
        ))
    else:
        report.add(Check("Missing Weight", ERROR, None,
                         f"모델 컬럼 {total_col} 이 없습니다."))

    # --- Weight Sum --------------------------------------------------------
    if total_col in final_mp.columns:
        sums = window.groupby("date", group_keys=False)[total_col].sum()
        worst_date = (sums - 1.0).abs().idxmax()
        worst = float(sums.loc[worst_date])
        bad = sums[(sums - 1.0).abs() > weight_tol]
        report.add(Check(
            "Portfolio Weight Sum",
            WARN if len(bad) else OK,
            f"{worst:.4%} ({str(worst_date)[:10]})",
            f"허용오차 ±{weight_tol:.2%} 를 벗어난 일자 {len(bad)}건"
            if len(bad) else f"모든 일자 1.0 ± {weight_tol:.2%}",
            [str(d)[:10] for d in bad.index[:50]],
        ))

    bm_sums = window.groupby("date", group_keys=False)["bm"].sum()
    bad_bm = bm_sums[(bm_sums - 1.0).abs() > bm_tol]
    report.add(Check(
        "Benchmark Weight Sum",
        WARN if len(bad_bm) else OK,
        f"{float(bm_sums.iloc[-1]):.4%}",
        f"허용오차를 벗어난 일자 {len(bad_bm)}건" if len(bad_bm) else "정상",
        [str(d)[:10] for d in bad_bm.index[:50]],
    ))

    # --- Missing Benchmark -------------------------------------------------
    bm_missing = temp_return_final.loc[report_date_list, "bm"].isna().sum()
    report.add(Check(
        "Missing Benchmark Return",
        ERROR if bm_missing else OK,
        int(bm_missing),
        "BM 일별 수익률 결측" if bm_missing else "결측 없음",
    ))

    # --- Missing Model -----------------------------------------------------
    missing_models = [
        c for c in (rcf.columns if rcf is not None else [])
        if c not in temp_return_final.columns
    ]
    report.add(Check(
        "Missing Model Return",
        ERROR if missing_models else OK,
        len(missing_models),
        "모델 수익률 시계열 누락" if missing_models else "전 모델 정상",
        missing_models,
    ))

    # --- Date Gap ----------------------------------------------------------
    gaps = []
    if len(dates) > 2:
        deltas = pd.Series(dates).diff().dt.days.dropna()
        # 주말(3일)은 정상. 4일 이상 벌어지면 공휴일 가능성 → 참고용 경고.
        for pos, delta in deltas.items():
            if delta > 5:
                gaps.append(f"{str(dates[pos-1])[:10]} → {str(dates[pos])[:10]} ({int(delta)}일)")
    report.add(Check(
        "Date Gap",
        WARN if gaps else OK,
        len(gaps),
        "영업일 간격이 5일을 초과하는 구간이 있습니다 (장기휴장 확인 필요)."
        if gaps else "정상",
        gaps[:20],
    ))

    # --- Contribution Reconciliation --------------------------------------
    if rcf is not None and model in rcf.columns:
        try:
            active = float(rcf.loc["active", model])
            parts = ["market_timing", "risk_factor", "industry_factor", "country", "specific"]
            total_parts = float(sum(float(rcf.loc[p, model]) for p in parts if p in rcf.index))
            diff = abs(active - total_parts)
            report.add(Check(
                "Contribution 합계 검증",
                OK if diff <= recon_tol else WARN,
                f"{diff:.3e}",
                "active = market_timing + risk_factor + industry_factor + country + specific",
            ))
        except (KeyError, TypeError, ValueError) as exc:
            report.add(Check("Contribution 합계 검증", WARN, None, f"검증 실패: {exc}"))

    return report
