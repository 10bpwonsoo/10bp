"""
시나리오 파일 스키마와 로더.

시나리오는 60일치 숫자 대신 '체제(regime)'와 '충격(shock)'만 선언한다.
이렇게 두면 시나리오 파일을 사람이 읽고 손으로 고칠 수 있고,
데모에서 보여줄 상황을 우연이 아니라 의도로 통제할 수 있다 (설계서 STEP 7.7).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator

from ...models.common import Base
from ...models.market import AssetClass, Instrument
from .synthetic import Regime


class RegimeSpec(Base):
    """시나리오에 적는 체제 파라미터. 미지정 항목은 자산군 기본값을 쓴다."""

    base: float | None = None
    vol: float | None = None
    drift: float | None = None
    mean_reversion: float | None = None
    floor: float | None = None
    cap: float | None = None


class NewsSpec(Base):
    """시나리오에 포함된 기사. P1 의 RuleExtractor 가 여기서 테마를 뽑는다."""

    id: str
    title: str
    body: str = ""
    publisher: str = ""
    url: str | None = None
    #: as_of 기준 몇 시간 전에 나온 기사인가. 시간 감쇠 가중에 쓴다.
    hours_ago: float = 1.0
    language: str = "ko"


class AnalystSpec(Base):
    """
    시나리오에 적는 종목 컨센서스 상태 (Investment Intelligence, 2026-09-16).

    실데이터에서는 공개 API 가 없어 CSV 로만 받는 값이다. MOCK 에서는 이
    한 줄로 EPS·목표가 리비전과 등급을 준다. % 는 1개월 기준이다.
    """

    eps_revision_1w: float = 0.0
    eps_revision_1m: float = 0.0
    eps_revision_3m: float = 0.0
    tp_change_1w: float = 0.0
    tp_change_1m: float = 0.0
    tp_change_3m: float = 0.0
    rating: str = "HOLD"
    rating_change: str | None = None
    brokers: int = 12


class Scenario(Base):
    name: str
    title: str = ""
    description: str = ""
    seed: int = 20260911
    bars: int = 180
    #: Investment Intelligence — 종목 거래량의 마지막 봉 목표 z (로그 거래량 기준).
    volume_shocks: dict[str, float] = Field(default_factory=dict)
    #: Investment Intelligence — 종목별 컨센서스 상태.
    analyst: dict[str, AnalystSpec] = Field(default_factory=dict)

    #: 자산군별 기본 체제. 개별 instrument 가 override 할 수 있다.
    class_defaults: dict[AssetClass, RegimeSpec] = Field(default_factory=dict)
    #: instrument 별 체제. base 는 보통 여기서만 준다.
    regimes: dict[str, RegimeSpec] = Field(default_factory=dict)
    #: instrument 별 마지막 관측치의 목표 z-score. 이것이 '충격'이다.
    shocks: dict[str, float] = Field(default_factory=dict)
    #: 충격을 선언하지 않은 instrument 의 마지막 변화 z 에 대한 연성 상한.
    #: tanh 로 압축하므로 작은 움직임은 그대로 남고 꼬리만 눌린다.
    #: None 이면 압축하지 않는다(순수 난수).
    quiet_z: float | None = Field(default=None, gt=0.0)
    news: list[NewsSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sane(self) -> "Scenario":
        for iid, z in self.shocks.items():
            if not -6.0 <= z <= 6.0:
                raise ValueError(f"shock {iid}={z} 가 비현실적이다 (-6 ~ +6)")
        return self

    def regime_for(self, instrument: Instrument) -> Regime:
        """자산군 기본값 위에 instrument 개별값을 덮어쓴 최종 체제."""
        merged = RegimeSpec()
        for spec in (
            self.class_defaults.get(instrument.asset_class),
            self.regimes.get(instrument.id),
        ):
            if spec is None:
                continue
            for fname in RegimeSpec.model_fields:
                v = getattr(spec, fname)
                if v is not None:
                    setattr(merged, fname, v)

        fallback = _FALLBACK_BY_CLASS[instrument.asset_class]
        return Regime(
            base=merged.base if merged.base is not None else fallback.base,
            vol=merged.vol if merged.vol is not None else fallback.vol,
            drift=merged.drift if merged.drift is not None else fallback.drift,
            mean_reversion=(
                merged.mean_reversion
                if merged.mean_reversion is not None
                else fallback.mean_reversion
            ),
            floor=merged.floor if merged.floor is not None else fallback.floor,
            cap=merged.cap if merged.cap is not None else fallback.cap,
        )


#: 시나리오가 아무것도 안 적어도 동작하도록 하는 최후 기본값.
#: price 계열의 vol 은 로그수익률 표준편차, level 계열은 절대 변화량이다.
_FALLBACK_BY_CLASS: dict[AssetClass, Regime] = {
    AssetClass.EQUITY: Regime(base=100.0, vol=0.010, mean_reversion=0.02),
    AssetClass.RATE: Regime(base=4.0, vol=0.045, mean_reversion=0.05, floor=0.01),
    AssetClass.FX: Regime(base=100.0, vol=0.005, mean_reversion=0.03),
    AssetClass.COMMODITY: Regime(base=80.0, vol=0.016, mean_reversion=0.02),
    AssetClass.VOLATILITY: Regime(base=15.0, vol=0.055, mean_reversion=0.10, floor=5.0),
    AssetClass.CREDIT: Regime(base=320.0, vol=6.0, mean_reversion=0.06, floor=50.0),
    AssetClass.FLOW: Regime(base=0.0, vol=420.0, mean_reversion=0.35),
    AssetClass.BREADTH: Regime(base=0.5, vol=0.09, mean_reversion=0.40),
}


def scenario_path(mock_dir: Path, name: str) -> Path:
    return mock_dir / f"scenario_{name}.json"


@lru_cache(maxsize=8)
def load_scenario(mock_dir: Path, name: str) -> Scenario:
    path = scenario_path(mock_dir, name)
    if not path.exists():
        available = sorted(p.stem.removeprefix("scenario_") for p in mock_dir.glob("scenario_*.json"))
        raise FileNotFoundError(
            f"시나리오 '{name}' 를 찾을 수 없다: {path}. 사용 가능: {available}"
        )
    with path.open(encoding="utf-8") as fh:
        return Scenario.model_validate(json.load(fh))


def available_scenarios(mock_dir: Path) -> list[str]:
    return sorted(p.stem.removeprefix("scenario_") for p in mock_dir.glob("scenario_*.json"))


def reset_scenario_cache() -> None:
    load_scenario.cache_clear()
