"""
스코어링 공통 부품 (설계서 STEP 5).

여기 있는 것은 전부 순수 함수다. 숫자는 하나도 하드코딩되어 있지 않고
scoring.yaml 에서 온다 (요구 15-9).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Literal, Mapping, Sequence

import yaml

from ..config.settings import CONFIG_DIR
from ..models.common import ScoreBreakdown, ScoreContribution


@lru_cache(maxsize=4)
def load_scoring(config_dir: Path | None = None) -> dict:
    d = config_dir or CONFIG_DIR
    with (d / "scoring.yaml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def reset_scoring_cache() -> None:
    load_scoring.cache_clear()


# ──────────────────────────────────────────────────────────
# 표준화
# ──────────────────────────────────────────────────────────
def squash(z: float, *, scale: float = 100.0, divisor: float = 2.0) -> float:
    """
    z 를 -scale ~ +scale 로 압축한다.

    선형 스케일링은 극단치에서 포화되지 않아 한 자산이 전체 점수를 지배한다.
    tanh 는 ±2σ 부근에서 부드럽게 포화되어 outlier 에 견고하면서도 꼬리의
    정보를 버리지 않는다. squash(1)≈46, squash(2)≈76, squash(3)≈91.
    """
    return scale * math.tanh(z / divisor)


def unsquash(value: float, *, scale: float = 100.0, divisor: float = 2.0) -> float:
    """squash 의 역함수. 표시값(-100~100)을 z 로 되돌린다."""
    ratio = max(-0.999999, min(0.999999, value / scale))
    return divisor * math.atanh(ratio)


# ──────────────────────────────────────────────────────────
# 가중 평균 (결측은 0 이 아니라 재정규화)
# ──────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Component:
    key: str
    weight: float
    sign: int = 1
    note: str = ""


def weighted_z(
    components: Sequence[Component],
    resolve: Callable[[str], float | None],
    *,
    method: str,
    raw: Callable[[str], float | None] | None = None,
) -> tuple[float | None, ScoreBreakdown, float]:
    """
    부호 가중 z 평균.

        F = Σ(sign · weight · z) / Σ weight        (확보된 항목만)

    결측은 0 으로 채우지 않는다. 가중치 분모에서 빼고 coverage 를 낮춘다.
    0 으로 채우면 '데이터 없음' 이 '중립임' 이라는 거짓 정보가 된다.

    Returns: (값 또는 None, 계산 근거, coverage 0~1)
    """
    contributions: list[ScoreContribution] = []
    missing: list[str] = []
    total_weight = 0.0
    weighted_sum = 0.0
    requested_weight = sum(abs(c.weight) for c in components)

    for c in components:
        z = resolve(c.key)
        if z is None:
            missing.append(c.key)
            continue
        contribution = c.sign * c.weight * z
        weighted_sum += contribution
        total_weight += abs(c.weight)
        contributions.append(
            ScoreContribution(
                key=c.key,
                raw_value=raw(c.key) if raw else None,
                normalized=z,
                weight=c.sign * c.weight,
                contribution=contribution,
                note=c.note,
            )
        )

    coverage = (total_weight / requested_weight) if requested_weight else 0.0
    value = (weighted_sum / total_weight) if total_weight > 0 else None

    breakdown = ScoreBreakdown.build(
        value=value if value is not None else 0.0,
        method=method,
        contributions=contributions,
        missing_inputs=missing,
    )
    return value, breakdown, coverage


# ──────────────────────────────────────────────────────────
# 룰 표현식
# ──────────────────────────────────────────────────────────
_OPS: dict[str, Callable[[float, float], bool]] = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
}

_PATTERN = re.compile(
    r"""^\s*
    (?P<abs>abs\(\s*)?
    (?:z\(\s*(?P<instrument>[A-Za-z0-9_]+)\s*\)|(?P<factor>[A-Za-z_][A-Za-z0-9_]*))
    (?(abs)\s*\)|)
    \s*(?P<op><=|>=|==|<|>)\s*
    (?P<threshold>-?\d+(?:\.\d+)?)
    \s*$""",
    re.VERBOSE,
)


@dataclass(frozen=True)
class Expression:
    """
    룰 표현식.

    eval() 을 쓰지 않는다. 설정 파일이 임의 코드를 실행할 수 있으면 그것은
    설정이 아니라 코드다. 허용 문법만 정규식으로 파싱한다.
    """

    raw: str
    kind: Literal["factor", "instrument"]
    name: str
    absolute: bool
    op: str
    threshold: float

    def evaluate(
        self, resolve: Callable[[str, str], float | None]
    ) -> tuple[bool, float | None]:
        """
        Returns: (통과 여부, 관측값 또는 None)

        관측값이 None 이면 평가할 수 없었다는 뜻이고, 통과로 보지 않는다.
        평가 불가를 통과로 처리하면 데이터가 없을수록 라벨이 잘 붙는
        기괴한 시스템이 된다.
        """
        value = resolve(self.kind, self.name)
        if value is None:
            return False, None
        observed = abs(value) if self.absolute else value
        return _OPS[self.op](observed, self.threshold), observed


def parse_expression(raw: str) -> Expression:
    m = _PATTERN.match(raw)
    if not m:
        raise ValueError(
            f"표현식을 해석할 수 없다: {raw!r}. "
            "허용 문법: 'Factor >= 1.0', 'z(BRENT) >= 1.0', 'abs(Rates) >= 1.2'"
        )
    instrument = m.group("instrument")
    return Expression(
        raw=raw.strip(),
        kind="instrument" if instrument else "factor",
        name=instrument or m.group("factor"),
        absolute=bool(m.group("abs")),
        op=m.group("op"),
        threshold=float(m.group("threshold")),
    )


def renormalized_average(parts: Mapping[str, float | None], weights: Mapping[str, float]) -> tuple[float | None, list[str]]:
    """
    가중 평균. None 인 항목은 분모에서 빼고 이름을 돌려준다.

    Confidence 계산처럼 '구성요소 중 일부를 알 수 없는' 상황에서 쓴다.
    모르는 것을 0 으로 두면 그 항목이 점수를 끌어내린다. 모르는 것은
    빼고 아는 것들로만 평균해야 한다.
    """
    total = 0.0
    acc = 0.0
    unknown: list[str] = []
    for key, weight in weights.items():
        v = parts.get(key)
        if v is None:
            unknown.append(key)
            continue
        acc += weight * v
        total += weight
    return (acc / total if total > 0 else None), unknown
