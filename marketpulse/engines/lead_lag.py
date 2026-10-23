"""
Lead / Lag (2026-09-16 신설).

lead 계열의 변화량을 k 일 앞당겨 lag 계열과 상관을 잰다. |상관| 이 가장 큰
k 가 0 보다 크고 임계를 넘으면 "역사적으로 선행하는 경향" 이라고만 적는다.
인과가 아니다. 문장도 그렇게 쓴다.
"""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from ..config.registry import get_intelligence_config
from ..models.intelligence import LeadLag

ENGINE_VERSION = "0.1.0"


def lagged_correlation(frame: pd.DataFrame, lead: str, lag: str, k: int) -> tuple[float | None, int]:
    if lead not in frame.columns or lag not in frame.columns:
        return None, 0
    pair = pd.concat([frame[lead].shift(k).rename("lead"), frame[lag].rename("lag")], axis=1).dropna()
    n = len(pair)
    if n < 3:
        return None, n
    x, y = pair["lead"].to_numpy(), pair["lag"].to_numpy()
    if np.std(x) == 0 or np.std(y) == 0:
        return None, n
    return float(np.corrcoef(x, y)[0][1]), n


def compute_lead_lag(frame: pd.DataFrame, labels: Mapping[str, str], *, config_dir=None) -> list[LeadLag]:
    cfg = get_intelligence_config(config_dir)["lead_lag"]
    max_lag, min_obs, min_corr = int(cfg["max_lag_days"]), int(cfg["min_observations"]), float(cfg["min_abs_corr"])
    out: list[LeadLag] = []
    for pair in cfg["pairs"]:
        lead, lag, label = str(pair["lead"]), str(pair["lag"]), str(pair.get("label") or f"{lead} → {lag}")
        c0, n0 = lagged_correlation(frame, lead, lag, 0)
        if c0 is None or n0 < min_obs:
            out.append(LeadLag(lead_id=lead, lag_id=lag, label=label, observations=n0, verdict="insufficient",
                               note=f"겹치는 관측 {n0}개 — 최소 {min_obs}개 필요하거나 계열이 없다"))
            continue
        best_k, best_c = 0, c0
        for k in range(1, max_lag + 1):
            c, n = lagged_correlation(frame, lead, lag, k)
            if c is not None and n >= min_obs and abs(c) > abs(best_c):
                best_k, best_c = k, c
        if abs(best_c) < min_corr:
            verdict, note = "no_relationship", f"어느 시차에서도 |상관| 이 {min_corr:.2f} 를 넘지 않는다 (최대 {best_c:+.2f} @ {best_k}일)."
        elif best_k == 0:
            verdict, note = "coincident", f"같은 날 상관 {c0:+.2f} 가 가장 크다 — 동행이지 선행이 아니다."
        else:
            verdict, note = "tends_to_lead", f"역사적으로 {best_k}일 선행하는 경향 (상관 {best_c:+.2f}, 같은 날 {c0:+.2f}). 인과가 아니다."
        out.append(LeadLag(lead_id=lead, lag_id=lag, label=label, best_lag_days=best_k, corr_at_best=round(best_c, 3),
                           corr_at_zero=round(c0, 3), observations=n0, verdict=verdict, note=note))  # type: ignore[arg-type]
    return out
