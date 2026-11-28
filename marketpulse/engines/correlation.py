"""
CorrelationEngine — 자산 간 롤링 상관 (GOAL Kickstart Exhibit 4·5·46~50 차용).

    corr_ij = 현재 window 봉의 변화량 상관 (가격은 로그수익률, 레벨은 차분)
    prior   = prior_shift 봉 전에 끝나는 같은 길이 창의 상관

왜 변화량인가: 레벨끼리의 상관은 추세만 있어도 1 에 붙는다. 관계가 살아
있는지는 "같이 움직이는가" 로 재야 하고 그것은 변화량 상관이다.

왜 두 장인가: 상관 하나로는 "지금 관계가 이렇다" 만 말한다. GS 가 1주 대
3개월, 현재 대 2001년 이후 백분위를 나란히 두듯, 여기서는 현재 창과 한
분기 전 창을 나란히 둔다. 부호가 갈리면 관계가 바뀐 것이다.

정렬은 **날짜**로 한다. 공급자마다 봉의 시각이 다르고 휴장일이 달라
datetime 그대로 맞추면 짝이 거의 안 맞는다 (live.py 의 파생 계산과 같은
이유). 쌍마다 두 값이 모두 있는 봉만 쓰고, 그 수가 min_observations 미만이면
None 이다 — 0 이 아니다.

순수 함수다. 숫자는 scoring.yaml 의 correlation 절에서 온다.
"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from ..models.correlation import CorrelationBook
from ..models.market import Instrument, MarketSeries
from .features import change_series
from .scoring import load_scoring

ENGINE_VERSION = "0.1.0"


def correlation_config(config_dir: Path | None = None) -> dict:
    cfg = load_scoring(config_dir).get("correlation", {}) or {}
    return {
        "window": int(cfg.get("window", 60)),
        "prior_shift": int(cfg.get("prior_shift", 63)),
        "min_observations": int(cfg.get("min_observations", 40)),
        "confirm_min_abs": float(cfg.get("confirm_min_abs", 0.2)),
        "reverse_min_abs": float(cfg.get("reverse_min_abs", 0.2)),
    }


def _change_frame(
    instruments: Sequence[Instrument], series_by_id: Mapping[str, MarketSeries]
) -> pd.DataFrame:
    columns: dict[str, pd.Series] = {}
    for ins in instruments:
        s = series_by_id.get(ins.id)
        if s is None or len(s.values) < 2:
            continue
        chg = change_series(np.asarray(s.values, dtype=float), ins.series_kind)
        dates = [t.date() for t in s.timestamps[1:]]
        col = pd.Series(chg, index=pd.Index(dates))
        # 같은 날 봉이 둘이면(공급자 중복) 마지막 것을 쓴다.
        col = col[~col.index.duplicated(keep="last")]
        columns[ins.id] = col
    if not columns:
        return pd.DataFrame()
    return pd.DataFrame(columns).sort_index()


def _matrix(frame: pd.DataFrame, min_obs: int) -> tuple[list[list[float | None]], list[list[int]]]:
    if frame.empty:
        return [], []
    present = frame.notna().astype(int)
    counts = present.T.values @ present.values
    corr = frame.corr(min_periods=min_obs).values
    n = len(frame.columns)
    out: list[list[float | None]] = []
    for i in range(n):
        row: list[float | None] = []
        for j in range(n):
            v = corr[i][j]
            if i == j or not math.isfinite(v) or counts[i][j] < min_obs:
                row.append(None)
            else:
                row.append(round(float(v), 3))
        out.append(row)
    return out, [[int(counts[i][j]) for j in range(n)] for i in range(n)]


def build_correlation_book(
    instruments: Sequence[Instrument],
    series_by_id: Mapping[str, MarketSeries],
    as_of: datetime,
    *,
    config_dir: Path | None = None,
) -> CorrelationBook | None:
    """모든 확보 자산의 상관 행렬 두 장. 자산이 둘 미만이면 None."""
    cfg = correlation_config(config_dir)
    window, shift, min_obs = cfg["window"], cfg["prior_shift"], cfg["min_observations"]

    frame = _change_frame(instruments, series_by_id)
    if frame.shape[1] < 2:
        return None

    current_frame = frame.iloc[-window:]
    current, counts = _matrix(current_frame, min_obs)

    prior: list[list[float | None]] = []
    if len(frame) >= window + shift:
        prior_frame = frame.iloc[-(window + shift) : -shift]
        prior, _ = _matrix(prior_frame, min_obs)

    return CorrelationBook(
        as_of=as_of,
        ids=list(frame.columns),
        window=window,
        prior_shift=shift,
        min_observations=min_obs,
        current=current,
        prior=prior,
        observations=counts,
    )


def classify(
    corr: float | None, expected_sign: int, *, config_dir: Path | None = None
) -> str:
    """
    사전 정의 부호와 실측 상관의 대조.

        confirmed  같은 부호로 충분히 크다
        reversed   반대 부호로 충분히 크다 — 관계가 뒤집혔다
        weakened   부호를 말할 만큼 크지 않다 — 관계가 약해졌다
        unknown    실측이 없거나 기대 부호가 없다
    """
    if corr is None or expected_sign == 0:
        return "unknown"
    cfg = correlation_config(config_dir)
    aligned = corr * expected_sign
    if aligned >= cfg["confirm_min_abs"]:
        return "confirmed"
    if aligned <= -cfg["reverse_min_abs"]:
        return "reversed"
    return "weakened"
