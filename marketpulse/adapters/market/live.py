"""
LiveMarketAdapter — sources.yaml 을 읽어 공급자들을 순서대로 시도한다.

한 instrument 가 실패해도 나머지는 나온다. 전부 실패하면 그 instrument 는
빠진 채로 돌아가고, 엔진이 coverage 와 confidence 를 알아서 낮춘다.
**절대 0 으로 채우지 않는다** (개발 규칙 3).

어디서 왔는지가 데이터에 남는다. DataMeta.source 에 "yahoo:^GSPC" 처럼
공급자와 심볼이 적히므로 화면에서 종목별로 출처를 볼 수 있다 (요구 15-6).

mode 는 DELAYED 다. 무료 공급자의 일봉 종가를 실시간이라 표시하는 것은
이 시스템이 피하려는 부정직함이다 (설계서 STEP 7.2). LIVE 를 요구하면
그 사실을 경고로 남긴다.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Sequence

import yaml

from ...config.settings import CONFIG_DIR
from ...models.common import DataMeta, DataMode, utcnow
from ...models.market import Instrument, MarketSeries
from ..base import MarketAdapter
from ..http import FetchError, HttpClient
from .providers import (
    CsvProvider,
    FredProvider,
    GithubCsvProvider,
    KrxProvider,
    Provider,
    StooqProvider,
    YahooProvider,
)
from .mock import derive

logger = logging.getLogger(__name__)

#: 최소 관측 수. FeatureEngine 의 MIN_OBSERVATIONS 와 같은 이유다 —
#: 이보다 짧으면 z-score 의 분모가 잡음이다.
MIN_POINTS = 20


@lru_cache(maxsize=4)
def load_sources(config_dir: Path | None = None) -> dict[str, list[dict]]:
    d = config_dir or CONFIG_DIR
    with (d / "sources.yaml").open(encoding="utf-8") as fh:
        spec = yaml.safe_load(fh) or {}
    return {k: list(v or []) for k, v in (spec.get("sources") or {}).items()}


def reset_sources_cache() -> None:
    load_sources.cache_clear()


def _source_label(spec: dict, fallback: str) -> str:
    """DataMeta.source 에 적을 이름. 어디서 온 값인지 되짚을 수 있어야 한다."""
    if spec.get("path"):
        parts = str(spec["path"]).split("/")
        # owner/repo/ref/dir/file → repo/file 로 줄인다
        label = f"{parts[1]}/{parts[-1]}" if len(parts) > 3 else str(spec["path"])
        where = (spec.get("filter") or {}).get("Country")
        return f"{label}[{where}]" if where else label
    return str(spec.get("symbol") or spec.get("dataset") or fallback)


@dataclass
class FetchOutcome:
    """instrument 하나의 수집 결과. probe CLI 가 그대로 표로 낸다."""

    instrument_id: str
    provider: str | None = None
    symbol: str | None = None
    points: int = 0
    attempts: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.provider is not None

    @property
    def reason(self) -> str:
        if self.ok:
            return f"{self.provider}:{self.symbol} · {self.points}개"
        if not self.attempts:
            return "공급자가 설정되지 않았다"
        return " / ".join(f"{name} {why}" for name, why in self.attempts)


class LiveMarketAdapter(MarketAdapter):
    """공급자 우선순위를 따라 실데이터를 가져온다."""

    def __init__(
        self,
        *,
        replay_dir: Path,
        config_dir: Path | None = None,
        mode: DataMode = DataMode.DELAYED,
        client: HttpClient | None = None,
        fred_api_key: str | None = None,
    ) -> None:
        self.mode = mode
        self.name = "live"
        self.config_dir = config_dir
        self.client = client or HttpClient()
        self.csv = CsvProvider(replay_dir)
        self.providers: dict[str, Provider] = {
            "yahoo": YahooProvider(self.client),
            "stooq": StooqProvider(self.client),
            "fred": FredProvider(
                self.client, fred_api_key or os.environ.get("FRED_API_KEY")
            ),
            "krx": KrxProvider(self.client),
            "github": GithubCsvProvider(self.client),
            "csv": self.csv,
        }
        #: 직전 fetch 의 instrument 별 결과. health 와 probe 가 읽는다.
        self.outcomes: dict[str, FetchOutcome] = {}

    # ── 조회 계획 ─────────────────────────────────────────
    def plan_for(self, instrument: Instrument) -> list[dict]:
        """
        이 instrument 를 시도할 순서. sources.yaml 의 목록 + 로컬 CSV.

        CSV 는 항상 마지막에 자동으로 붙는다. 파일을 넣어 두면 설정을
        고치지 않아도 대체된다 — 막힌 네트워크에서의 탈출구다.
        """
        configured = load_sources(self.config_dir).get(instrument.id, [])
        plan = [dict(s) for s in configured]
        if self.csv.path_for(instrument.id).exists():
            plan.append({"provider": "csv", "symbol": instrument.id})
        return plan

    def supports(self, instrument: Instrument) -> bool:
        return bool(self.plan_for(instrument)) or instrument.derived_from is not None

    # ── 수집 ──────────────────────────────────────────────
    def fetch_series(
        self,
        instruments: Sequence[Instrument],
        *,
        bars: int,
        as_of: datetime | None = None,
    ) -> dict[str, MarketSeries]:
        end = (as_of or utcnow()).astimezone(timezone.utc)
        retrieved = utcnow()
        by_id = {i.id: i for i in instruments}
        self.outcomes = {}

        raw: dict[str, list[tuple[datetime, float]]] = {}
        for ins in instruments:
            if ins.derived_from is not None:
                continue  # 2단계에서 계산한다
            outcome = FetchOutcome(instrument_id=ins.id)
            for spec in self.plan_for(ins):
                name = str(spec.get("provider") or "")
                provider = self.providers.get(name)
                if provider is None:
                    outcome.attempts.append((name, "알 수 없는 공급자"))
                    continue
                usable, why = provider.available()
                if not usable:
                    outcome.attempts.append((name, why))
                    continue
                try:
                    points = provider.fetch(spec, bars=bars, as_of=end)
                except FetchError as exc:
                    outcome.attempts.append((name, str(exc)))
                    continue
                except Exception as exc:  # noqa: BLE001
                    logger.exception("%s: %s 공급자에서 예상 못 한 오류", ins.id, name)
                    outcome.attempts.append((name, f"예상 못 한 오류: {exc}"))
                    continue

                if len(points) < MIN_POINTS:
                    outcome.attempts.append(
                        (name, f"{len(points)}개뿐 — 최소 {MIN_POINTS}개 필요")
                    )
                    continue
                raw[ins.id] = points
                outcome.provider = name
                # 출처는 사람이 읽고 검증할 수 있어야 한다. github 는 심볼이
                # 아니라 파일 경로가 곧 출처다 (요구 15-6).
                outcome.symbol = _source_label(spec, ins.id)
                outcome.points = len(points)
                break
            self.outcomes[ins.id] = outcome

        # 2단계: 파생. 기초 자산이 둘 다 있어야 계산된다.
        for ins in instruments:
            spec = ins.derived_from
            if spec is None:
                continue
            outcome = FetchOutcome(instrument_id=ins.id)
            a, b = raw.get(spec.a), raw.get(spec.b)
            if a is None or b is None:
                missing = ", ".join(x for x, v in ((spec.a, a), (spec.b, b)) if v is None)
                outcome.attempts.append(("derived", f"기초 자산 누락: {missing}"))
                self.outcomes[ins.id] = outcome
                continue
            # 공급자마다 휴장일이 달라 길이가 어긋난다. 날짜 교집합만 쓴다.
            shared = sorted(set(dict(a)) & set(dict(b)))
            if len(shared) < MIN_POINTS:
                outcome.attempts.append(
                    ("derived", f"공통 날짜 {len(shared)}개뿐 — 최소 {MIN_POINTS}개 필요")
                )
                self.outcomes[ins.id] = outcome
                continue
            amap, bmap = dict(a), dict(b)
            values = derive(spec.op, [amap[t] for t in shared], [bmap[t] for t in shared])
            raw[ins.id] = list(zip(shared, values))
            outcome.provider = "derived"
            outcome.symbol = f"{spec.op}({spec.a},{spec.b})"
            outcome.points = len(shared)
            self.outcomes[ins.id] = outcome

        out: dict[str, MarketSeries] = {}
        for iid, points in raw.items():
            ins = by_id.get(iid)
            if ins is None:
                continue
            oc = self.outcomes[iid]
            stamps = [t for t, _ in points]
            out[iid] = MarketSeries(
                instrument_id=iid,
                timestamps=stamps,
                values=[v for _, v in points],
                meta=DataMeta(
                    source=f"{oc.provider}:{oc.symbol}",
                    mode=self.mode,
                    retrieved_at=retrieved,
                    as_of=stamps[-1] if stamps else retrieved,
                ),
            )
        return out

    # ── 진단 ──────────────────────────────────────────────
    def probe(self) -> dict[str, tuple[bool, str]]:
        """공급자별 사용 가능 여부. 네트워크를 쓰지 않는다."""
        return {name: p.available() for name, p in self.providers.items()}

    def host_status(self) -> dict[str, str]:
        return self.client.status()
