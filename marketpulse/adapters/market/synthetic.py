"""
결정론적 합성 시계열 생성기 — MOCK 모드의 엔진.

설계 의도
---------
시나리오 파일에 60일치 값을 손으로 적는 대신, 시나리오는 "체제(regime)"와
"충격(shock)"만 선언하고 히스토리는 고정 시드로 생성한다. 덕분에

  · 시나리오 파일이 사람이 읽을 수 있는 크기로 유지되고,
  · 같은 시드면 언제나 같은 시계열이 나와 요구 14 의 재현성이 성립하며,
  · shock 에 적은 σ 값이 z-score 로 **정확히** 재현된다.

마지막 관측치는 난수가 아니다. 직전 W개 변화량의 평균과 표준편차로부터
목표 z 를 만족하는 값을 역산해 넣는다. 따라서 시나리오에 'BRENT: +2.0' 이라
적으면 FeatureEngine 이 계산한 z_1d 가 정확히 +2.0 이 된다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ...models.market import Instrument


@dataclass(frozen=True)
class Regime:
    """한 instrument 의 정상 상태 파라미터."""

    base: float = 100.0
    #: 1기간 변화의 표준편차. price 는 로그수익률, level 은 절대 변화량.
    vol: float = 0.01
    #: 1기간 평균 변화(추세).
    drift: float = 0.0
    #: 평균회귀 강도 0~1. level 계열(금리, 수급)에 쓴다. 0 이면 순수 랜덤워크.
    mean_reversion: float = 0.0
    #: 값의 하한. 금리가 음수로 가거나 거래대금이 0 아래로 가는 것을 막는다.
    floor: float | None = None
    #: 값의 상한. 비율(상승종목 비율 등)이 1을 넘는 것을 막는다.
    cap: float | None = None


@dataclass
class GeneratedSeries:
    instrument_id: str
    values: list[float]
    changes: list[float] = field(default_factory=list)


def _change_series(rng: np.random.Generator, regime: Regime, n: int) -> np.ndarray:
    """n개의 변화량을 생성한다. 평균회귀가 있으면 OU 과정처럼 움직인다."""
    shocks = rng.normal(0.0, regime.vol, size=n)
    if regime.mean_reversion <= 0.0:
        return shocks + regime.drift

    # 누적 이탈을 끌어당기는 형태. level 계열이 무한정 표류하지 않게 한다.
    out = np.empty(n)
    level_dev = 0.0
    for i in range(n):
        pull = -regime.mean_reversion * level_dev
        step = pull + shocks[i] + regime.drift
        level_dev += step
        out[i] = step
    return out


def _rebuild(regime: Regime, changes: np.ndarray, is_price: bool) -> np.ndarray:
    """변화량에서 값 시계열을 복원한다. 길이는 len(changes) + 1."""
    if is_price:
        values = regime.base * np.exp(np.concatenate([[0.0], np.cumsum(changes)]))
    else:
        values = regime.base + np.concatenate([[0.0], np.cumsum(changes)])
    if regime.floor is not None:
        values = np.maximum(values, regime.floor)
    if regime.cap is not None:
        values = np.minimum(values, regime.cap)
    return values


def solve_last_change(
    prior_changes: np.ndarray, target_z: float, window: int
) -> float:
    """
    목표 z 를 만족하는 마지막 변화량을 역산한다.

    FeatureEngine 의 z_1d 정의와 정확히 같은 식을 쓴다:
        z = (chg[-1] - mean(chg[-W-1:-1])) / std(chg[-W-1:-1], ddof=1)
    직전 구간만 쓰는 out-of-sample 표준화다. 현재 관측치를 기준선에 포함시키면
    큰 충격일수록 자기 자신이 기준선을 키워 z 가 과소평가된다.
    """
    tail = prior_changes[-window:]
    if len(tail) < 2:
        raise ValueError("표준편차를 계산할 관측치가 부족하다")
    mu = float(np.mean(tail))
    sd = float(np.std(tail, ddof=1))
    if sd == 0.0:
        raise ValueError("표준편차가 0이다. vol 을 0보다 크게 설정하라")
    return mu + target_z * sd


def _natural_z(changes: np.ndarray, window: int) -> float | None:
    """생성된 마지막 변화량의 z. solve_last_change 와 같은 기준선을 쓴다."""
    tail = changes[-(window + 1) : -1]
    if len(tail) < 2:
        return None
    sd = float(np.std(tail, ddof=1))
    if sd <= 0.0:
        return None
    return (float(changes[-1]) - float(np.mean(tail))) / sd


def generate(
    instrument: Instrument,
    regime: Regime,
    *,
    bars: int,
    window: int,
    seed: int,
    shock_z: float | None = None,
    quiet_z: float | None = None,
) -> GeneratedSeries:
    """
    instrument 하나의 시계열을 만든다.

    bars 는 반환되는 값의 개수다. 변화량은 bars-1 개 생성된다.
    shock_z 가 주어지면 마지막 변화량을 그 z 에 맞춰 덮어쓴다.
    shock_z 가 없고 quiet_z 가 주어지면 마지막 변화의 z 를 tanh 로 연성 압축해
    그 값 근처를 넘지 않게 한다.
    """
    if bars < window + 3:
        raise ValueError(
            f"{instrument.id}: bars({bars}) 가 window({window}) 대비 부족하다. "
            "z-score 를 계산할 수 없다."
        )
    rng = np.random.default_rng(seed)
    is_price = instrument.series_kind == "price"

    changes = _change_series(rng, regime, bars - 1)
    if shock_z is not None:
        changes[-1] = solve_last_change(changes[:-1], shock_z, window)
    elif quiet_z is not None:
        # 충격을 선언하지 않은 instrument 의 마지막 변화가 우연히 커지는 것을
        # 누른다. 47개 종목이면 순전한 우연으로도 |z| 2.5 가 나오고, 그러면
        # 시나리오가 말하려는 이야기를 노이즈가 덮는다. 시연 상황을 우연이
        # 아니라 의도로 통제하기 위한 장치다 (설계서 STEP 7.7).
        #
        # 하드 컷이 아니라 tanh 연성 압축을 쓴다:
        #     z' = quiet_z * tanh(z / quiet_z)
        # 작은 움직임은 거의 그대로 두고 꼬리만 누른다. 하드 컷을 쓰면
        # 여러 종목이 정확히 같은 z 에 뭉쳐 한눈에 인공물로 보인다.
        # 히스토리는 건드리지 않고 마지막 한 점만 조정한다.
        natural = _natural_z(changes, window)
        if natural is not None:
            softened = quiet_z * math.tanh(natural / quiet_z)
            changes[-1] = solve_last_change(changes[:-1], softened, window)

    values = _rebuild(regime, changes, is_price)
    return GeneratedSeries(
        instrument_id=instrument.id,
        values=[float(v) for v in values],
        changes=[float(c) for c in changes],
    )


def derive(op: str, a: list[float], b: list[float]) -> list[float]:
    """파생 instrument 계산. 기초 자산이 생성된 뒤에 호출한다."""
    if len(a) != len(b):
        raise ValueError("파생 계산: 기초 시계열 길이가 다르다")
    if op == "ratio":
        return [
            float(x / y) if y not in (0.0, -0.0) and math.isfinite(y) else float("nan")
            for x, y in zip(a, b)
        ]
    if op == "spread":
        # 금리 스프레드는 bp 로 표현한다. 4.20% - 3.90% = 30bp.
        return [float((x - y) * 100.0) for x, y in zip(a, b)]
    raise ValueError(f"알 수 없는 파생 연산: {op}")


def stable_seed(*parts: str | int) -> int:
    """시나리오 시드 + instrument id 로 결정론적 하위 시드를 만든다."""
    h = 0
    for p in parts:
        for ch in str(p):
            h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    return h
