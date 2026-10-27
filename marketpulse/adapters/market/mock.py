"""
MOCK 마켓데이터 어댑터.

현재 개발 환경은 외부 마켓데이터 API 가 조직 네트워크 정책으로 전면 차단되어
있다 (설계서 STEP 1.2 실측). 따라서 MOCK 은 임시방편이 아니라 1급 시민이다.
전체 분석 파이프라인과 UI 가 이 어댑터만으로 완전히 동작해야 한다 (요구 12).
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

from ...models.common import DataMeta, DataMode, DataQuality, utcnow
from ...models.market import Instrument, MarketSeries
from ..base import MarketAdapter
from .scenario import Scenario, load_scenario
from .synthetic import derive, generate, stable_seed

logger = logging.getLogger(__name__)


def business_timestamps(end: datetime, bars: int) -> list[datetime]:
    """주말을 건너뛰며 end 에서 과거로 bars 개의 타임스탬프를 만든다."""
    out: list[datetime] = []
    cur = end
    while len(out) < bars:
        if cur.weekday() < 5:  # 0=월 .. 4=금
            out.append(cur)
        cur -= timedelta(days=1)
    return list(reversed(out))


class MockMarketAdapter(MarketAdapter):
    """시나리오 파일에서 결정론적 시계열을 만들어 돌려준다."""

    mode = DataMode.MOCK

    def __init__(
        self,
        mock_dir: Path,
        scenario_name: str = "baseline",
        *,
        zscore_window: int = 60,
    ) -> None:
        self.mock_dir = mock_dir
        self.scenario_name = scenario_name
        self.zscore_window = zscore_window
        self.name = f"mock:scenario_{scenario_name}"

    @property
    def scenario(self) -> Scenario:
        return load_scenario(self.mock_dir, self.scenario_name)

    def fetch_series(
        self,
        instruments: Sequence[Instrument],
        *,
        bars: int,
        as_of: datetime | None = None,
    ) -> dict[str, MarketSeries]:
        sc = self.scenario
        bars = max(bars, sc.bars)
        end = (as_of or utcnow()).astimezone(timezone.utc)
        stamps = business_timestamps(end, bars)
        retrieved = utcnow()

        by_id = {i.id: i for i in instruments}
        base_values: dict[str, list[float]] = {}

        # 1단계: 파생이 아닌 instrument 를 먼저 만든다.
        for ins in instruments:
            if ins.derived_from is not None:
                continue
            shock = sc.shocks.get(ins.id)
            try:
                gen = generate(
                    ins,
                    sc.regime_for(ins),
                    bars=bars,
                    window=self.zscore_window,
                    seed=stable_seed(sc.seed, ins.id),
                    shock_z=shock,
                    quiet_z=sc.quiet_z,
                )
            except ValueError as exc:
                logger.warning("%s 시계열 생성 실패: %s", ins.id, exc)
                continue
            base_values[ins.id] = gen.values

        # 2단계: 파생 instrument. 기초 자산이 있어야 계산된다.
        for ins in instruments:
            spec = ins.derived_from
            if spec is None:
                continue
            a, b = base_values.get(spec.a), base_values.get(spec.b)
            if a is None or b is None:
                logger.warning(
                    "%s: 파생 기초 자산 누락 (%s, %s). 건너뛴다.", ins.id, spec.a, spec.b
                )
                continue
            if ins.id in sc.shocks:
                logger.warning(
                    "%s 는 파생 지표라 shock 설정을 무시한다. "
                    "기초 자산(%s, %s)에 shock 을 주어야 한다.",
                    ins.id, spec.a, spec.b,
                )
            base_values[ins.id] = derive(spec.op, a, b)

        out: dict[str, MarketSeries] = {}
        for iid, values in base_values.items():
            ins = by_id[iid]
            # 파생값은 앞부분이 비어 있을 수 있다 (vol_premium 의 첫 20봉).
            # 빈 봉은 버린다. 0 으로 채우면 '없음' 이 '중립' 으로 둔갑한다.
            kept = [(t, v) for t, v in zip(stamps, values) if math.isfinite(v)]
            if not kept:
                logger.warning("%s: 유효한 값이 없어 건너뛴다.", iid)
                continue
            own_stamps = [t for t, _ in kept]
            out[iid] = MarketSeries(
                instrument_id=iid,
                timestamps=own_stamps,
                values=[v for _, v in kept],
                meta=DataMeta(
                    source=self.name,
                    mode=DataMode.MOCK,
                    retrieved_at=retrieved,
                    as_of=own_stamps[-1],
                    quality=DataQuality.OK,
                ),
            )
        return out
