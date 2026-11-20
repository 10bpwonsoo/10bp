"""
FactorEngine — 11개 매크로 factor score (설계서 STEP 5.2).

    F_j = Σ_i (s_ij · w_ij · z_i) / Σ_i w_ij      (확보된 i 만, 재정규화)

순수 함수다. MarketSnapshot 을 받아 FactorScore 를 돌려준다.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from ..config.settings import CONFIG_DIR
from ..models.market import MarketSnapshot
from ..models.state import FactorScore
from ..models.theme import DataQualityBand
from .scoring import Component, load_scoring, weighted_z

ENGINE_VERSION = "0.1.0"
METHOD = "signed_weighted_z_v1"


@lru_cache(maxsize=4)
def load_factor_specs(config_dir: Path | None = None) -> dict[str, dict]:
    d = config_dir or CONFIG_DIR
    with (d / "factors.yaml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)["factors"]


def reset_factor_cache() -> None:
    load_factor_specs.cache_clear()


def _quality(coverage: float, cfg: dict) -> DataQualityBand:
    if coverage >= cfg["min_coverage_ok"]:
        return DataQualityBand.OK
    if coverage >= cfg["min_coverage_partial"]:
        return DataQualityBand.PARTIAL
    return DataQualityBand.INSUFFICIENT


def compute_factors(
    snapshot: MarketSnapshot,
    *,
    config_dir: Path | None = None,
    horizon: str = "1d",
) -> dict[str, FactorScore]:
    """
    모든 factor 를 계산한다.

    구성 instrument 가 전혀 없으면 그 factor 는 결과에서 빠진다. 0 으로
    채우지 않는다 — 데이터가 없는 것과 중립인 것은 다르다.
    """
    specs = load_factor_specs(config_dir)
    cfg = load_scoring(config_dir)["factor"]

    def z_of(instrument_id: str) -> float | None:
        return snapshot.z(instrument_id, horizon)

    def raw_of(instrument_id: str) -> float | None:
        feat = snapshot.features.get(instrument_id)
        return None if feat is None else feat.ret_1d

    out: dict[str, FactorScore] = {}
    for name, spec in specs.items():
        components = [
            Component(
                key=c["instrument_id"],
                weight=float(c["weight"]),
                sign=int(c.get("sign", 1)),
            )
            for c in spec["components"]
        ]
        value, breakdown, coverage = weighted_z(
            components, z_of, method=METHOD, raw=raw_of
        )
        if value is None:
            continue
        out[name] = FactorScore(
            factor=name,
            score=value,
            breakdown=breakdown,
            data_quality=_quality(coverage, cfg),
        )
    return out


#: 품질 등급이 coverage 에 기여하는 정도.
#: PARTIAL 을 0 으로 두면 데이터가 반쯤 빠진 상황에서 confidence 가 정확히
#: 0 이 되어 "조금 아는 것" 과 "전혀 모르는 것" 을 구분하지 못한다. 운용자가
#: 신뢰도를 조정해야 할 때가 바로 그 구간이다. 절반만 인정한다.
QUALITY_CREDIT: dict[DataQualityBand, float] = {
    DataQualityBand.OK: 1.0,
    DataQualityBand.PARTIAL: 0.5,
    DataQualityBand.INSUFFICIENT: 0.0,
}


def factor_coverage(factors: dict[str, FactorScore], *, config_dir: Path | None = None) -> float:
    """
    factor 들이 얼마나 확보되었는가. Confidence 의 coverage 항이다.

    분모는 계산된 factor 수가 아니라 **정의된 factor 수**다. 아예 계산되지
    못한 factor 를 분모에서 빼면 두 개만 살아남은 상황이 100% 로 보인다.
    """
    specs = load_factor_specs(config_dir)
    if not specs:
        return 0.0
    credit = sum(QUALITY_CREDIT.get(f.data_quality, 0.0) for f in factors.values())
    return min(1.0, credit / len(specs))
