"""
AltMockAdapter — 종목·대체데이터 MOCK (2026-09-16 신설).

기존 synthetic.generate 를 그대로 쓴다. universe.yaml 의 mock_base / mock_vol
이 체제이고, 시나리오의 shocks 에 종목·대체데이터 id 를 적으면 마지막
봉의 z 가 그 값으로 정확히 재현된다 (기존 MOCK 과 같은 성질).

거래량은 로그정규 난수이고 scenario.volume_shocks 로 마지막 봉의 로그
거래량 z 를 지정한다. 수급(외국인·기관)은 MOCK 에서도 만들지 않는다 —
실데이터에서 없는 것을 MOCK 에서만 있는 것처럼 보이면 화면이 두 얼굴이 된다.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import numpy as np

from ...models.common import DataMeta, DataMode, DataQuality, utcnow
from ...models.intelligence import AltInstrument, StockMeta
from ...models.market import Instrument, MarketSeries
from ..market.mock import business_timestamps
from ..market.scenario import Scenario, load_scenario
from ..market.synthetic import Regime, generate, solve_last_change, stable_seed
from ...config.registry import get_stock_exposures

#: 사업 노출 중요도 → MOCK 에서 섞어 넣는 드라이버 베타. 실데이터의 통계
#: 노출이 어떻게 보이는지 시연하기 위한 것이지 추정치가 아니다.
MOCK_BETA = {"high": 0.6, "medium": 0.35, "low": 0.15}

#: 로그 거래량의 일별 표준편차. z 하나가 거래량 약 42% 에 해당한다.
VOLUME_LOG_SD = 0.35


class AltMockAdapter:
    mode = DataMode.MOCK
    name = "alt-mock"

    def __init__(self, mock_dir: Path, scenario_name: str = "baseline", *, zscore_window: int = 60) -> None:
        self.mock_dir = mock_dir
        self.scenario_name = scenario_name
        self.zscore_window = zscore_window
        self.outcomes: dict = {}

    @property
    def scenario(self) -> Scenario:
        return load_scenario(self.mock_dir, self.scenario_name)

    def fetch_series(
        self,
        stocks: Sequence[StockMeta],
        alternative: Sequence[AltInstrument],
        shared: Sequence[Instrument],
        *,
        bars: int,
        as_of: datetime | None = None,
    ) -> dict[str, MarketSeries]:
        sc = self.scenario
        bars = max(bars, sc.bars)
        end = (as_of or utcnow()).astimezone(timezone.utc)
        stamps = business_timestamps(end, bars)
        retrieved = utcnow()
        out: dict[str, MarketSeries] = {}

        def make(ins: Instrument, base: float, vol: float, *, volume: bool) -> None:
            regime = Regime(base=base, vol=vol, mean_reversion=0.02 if ins.series_kind == "price" else 0.1)
            gen = generate(
                ins, regime, bars=bars, window=self.zscore_window,
                seed=stable_seed(sc.seed, ins.id), shock_z=sc.shocks.get(ins.id), quiet_z=sc.quiet_z,
            )
            volumes = None
            if volume:
                rng = np.random.default_rng(stable_seed(sc.seed, ins.id, "volume"))
                logs = np.log(2_000_000.0) + rng.normal(0.0, VOLUME_LOG_SD, size=bars)
                vz = sc.volume_shocks.get(ins.id)
                if vz is not None:
                    base_mu = float(np.mean(logs[-(self.zscore_window + 1):-1]))
                    base_sd = float(np.std(logs[-(self.zscore_window + 1):-1], ddof=1))
                    logs[-1] = base_mu + vz * base_sd
                volumes = [float(math.exp(v)) for v in logs]
            out[ins.id] = MarketSeries(
                instrument_id=ins.id, timestamps=stamps, values=gen.values, volumes=volumes,
                meta=DataMeta(source=f"mock:scenario_{sc.name}", mode=DataMode.MOCK,
                              retrieved_at=retrieved, as_of=stamps[-1], quality=DataQuality.OK),
            )

        for a in alternative:
            make(a.as_instrument(), a.mock_base, a.mock_vol, volume=False)
        # 공유 드라이버(US10Y·USDKRW 등)는 기존 MOCK 어댑터와 같은 체제로 다시 만든다.
        for ins in shared:
            regime = sc.regime_for(ins)
            gen = generate(
                ins, regime, bars=bars, window=self.zscore_window,
                seed=stable_seed(sc.seed, ins.id), shock_z=sc.shocks.get(ins.id), quiet_z=sc.quiet_z,
            )
            out[ins.id] = MarketSeries(
                instrument_id=ins.id, timestamps=stamps, values=gen.values,
                meta=DataMeta(source=f"mock:scenario_{sc.name}", mode=DataMode.MOCK,
                              retrieved_at=retrieved, as_of=stamps[-1], quality=DataQuality.OK),
            )

        # 종목은 마지막에 만든다 — 사업 노출(stock_exposures.yaml)의 드라이버 수익률을
        # 베타만큼 섞어 통계 노출이 MOCK 에서도 존재하게 한다. 시나리오가 종목에
        # 충격을 지정했으면 섞은 뒤 마지막 변화를 다시 풀어 z 를 정확히 맞춘다.
        fundamentals = get_stock_exposures()
        for s in stocks:
            make(s.as_instrument(), s.mock_base, s.mock_vol, volume=True)
            own = out[s.id]
            vals = np.asarray(own.values, dtype=float)
            chg = np.diff(np.log(vals))
            mixed = chg.copy()
            for did, e in fundamentals.get(s.id, {}).items():
                drv = out.get(did)
                if drv is None:
                    continue
                dvals = np.asarray(drv.values, dtype=float)
                dchg = np.diff(np.log(dvals)) if drv.instrument_id and min(dvals) > 0 and self._is_price(did, shared, alternative) else np.diff(dvals) / max(1e-9, float(np.std(np.diff(dvals)))) * s.mock_vol
                if len(dchg) != len(mixed):
                    continue
                mixed = mixed + e.direction * MOCK_BETA[e.importance] * (dchg if self._is_price(did, shared, alternative) else dchg)
            shock = sc.shocks.get(s.id)
            if shock is not None:
                mixed[-1] = solve_last_change(mixed[:-1], shock, self.zscore_window)
            new_vals = [float(vals[0])]
            for c in mixed:
                new_vals.append(new_vals[-1] * math.exp(float(c)))
            out[s.id] = own.model_copy(update={"values": new_vals})
        return out

    @staticmethod
    def _is_price(iid: str, shared: Sequence[Instrument], alternative: Sequence[AltInstrument]) -> bool:
        for ins in shared:
            if ins.id == iid:
                return ins.series_kind == "price"
        for a in alternative:
            if a.id == iid:
                return a.series_kind == "price"
        return True
