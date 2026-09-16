"""
AltLiveAdapter — 종목·대체데이터 실데이터 (2026-09-16 신설).

기존 LiveMarketAdapter 의 공급자(YahooProvider·CsvProvider)를 그대로 쓴다.
다른 점 셋:
  1. 거래량을 같이 받는다 (YahooProvider.fetch_with_volume).
  2. 일별 저장소(alt_daily)에 upsert 하고, **같은 날 이미 받은 계열은 다시
     받지 않는다** (요구 31: incremental fetch / historical cache).
  3. 네트워크가 실패하면 저장소의 마지막 값을 STALE 로 돌려준다 — 0 으로
     채우지 않고, 낡았다는 사실을 DataMeta.quality 에 남긴다.

universe.yaml 에 sources 가 없는 id(WTI·US10Y 같은 공유 드라이버)는
sources.yaml 의 설정을 그대로 쓴다.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from ...config.settings import CONFIG_DIR
from ...models.common import DataMeta, DataMode, DataQuality, utcnow
from ...models.intelligence import SourceSpec
from ...models.market import Instrument, MarketSeries
from ..http import FetchError, HttpClient
from ..market.live import MIN_POINTS, FetchOutcome, load_sources
from ..market.providers import CsvProvider, Provider, StooqProvider, YahooProvider

logger = logging.getLogger(__name__)


class AltLiveAdapter:
    mode = DataMode.DELAYED
    name = "alt-live"

    def __init__(
        self,
        *,
        replay_dir: Path,
        config_dir: Path | None = None,
        client: HttpClient | None = None,
        store=None,
    ) -> None:
        self.config_dir = config_dir
        self.client = client or HttpClient()
        self.csv = CsvProvider(replay_dir / "alternative")
        self.csv_base = CsvProvider(replay_dir)
        self.providers: dict[str, Provider] = {
            "yahoo": YahooProvider(self.client),
            "stooq": StooqProvider(self.client),
            "csv": self.csv,
        }
        #: SqliteSnapshotRepository (선택). 없으면 매번 네트워크다.
        self.store = store
        self.outcomes: dict[str, FetchOutcome] = {}
        #: 네트워크 호출 사이의 예의 지연(초). Yahoo 는 100여 심볼을 연달아 치면
        #: 429 를 돌려준다. 저장소에서 읽을 때는 기다리지 않는다.
        self.politeness_sec = 0.25

    # ── 조회 계획 ─────────────────────────────────────────
    def plan_for(self, instrument: Instrument, sources: Mapping[str, list[SourceSpec]]) -> list[dict]:
        plan: list[dict] = [s.model_dump() for s in sources.get(instrument.id, [])]
        if not plan:
            # 공유 드라이버는 sources.yaml 을 따른다 (KRX 등 알 수 없는 공급자는 건너뛴다)
            plan = [dict(s) for s in load_sources(self.config_dir).get(instrument.id, []) if s.get("provider") in self.providers]
            if self.csv_base.path_for(instrument.id).exists():
                plan.append({"provider": "csv_base", "symbol": instrument.id})
        if self.csv.path_for(instrument.id).exists() and not any(p.get("provider") == "csv" for p in plan):
            plan.append({"provider": "csv", "symbol": instrument.id})
        return plan

    # ── 저장소 ────────────────────────────────────────────
    def _from_store(self, iid: str, bars: int) -> tuple[list[tuple[datetime, float]], list[tuple[datetime, float]], str] | None:
        if self.store is None:
            return None
        rows = self.store.load_daily(iid, limit=bars)
        if len(rows) < MIN_POINTS:
            return None
        pts = [(datetime.fromisoformat(d).replace(tzinfo=timezone.utc), v) for d, v, _, _ in rows]
        vols = [(datetime.fromisoformat(d).replace(tzinfo=timezone.utc), vol) for d, _, vol, _ in rows if vol is not None]
        return pts, vols, rows[-1][3]

    def _cached_today(self, iid: str, today: str) -> bool:
        if self.store is None:
            return False
        log = self.store.fetch_log(iid)
        return bool(log and log.get("fetched_date") == today)

    def _persist(self, iid: str, pts, vols, source: str) -> None:
        if self.store is None:
            return
        vol_by_date = {t.date().isoformat(): v for t, v in vols}
        rows = [(t.date().isoformat(), v, vol_by_date.get(t.date().isoformat())) for t, v in pts]
        try:
            self.store.upsert_daily(iid, rows, source)
        except Exception:  # 저장 실패가 화면을 막으면 안 된다
            logger.exception("%s 일별 저장 실패", iid)

    # ── 수집 ──────────────────────────────────────────────
    def fetch_series(
        self,
        instruments: Sequence[Instrument],
        sources: Mapping[str, list[SourceSpec]],
        *,
        bars: int,
        as_of: datetime | None = None,
    ) -> dict[str, MarketSeries]:
        end = (as_of or utcnow()).astimezone(timezone.utc)
        retrieved = utcnow()
        today = end.date().isoformat()
        self.outcomes = {}
        out: dict[str, MarketSeries] = {}

        for ins in instruments:
            outcome = FetchOutcome(instrument_id=ins.id)
            pts: list = []
            vols: list = []
            src = ""
            quality = DataQuality.OK

            # 1. 오늘 이미 받았으면 저장소에서
            if self._cached_today(ins.id, today):
                cached = self._from_store(ins.id, bars)
                if cached:
                    pts, vols, src = cached
                    outcome.provider, outcome.symbol = "store", src
                    outcome.attempts.append(("store", "오늘 수집분 재사용"))

            # 2. 공급자 순서대로
            if not pts:
                for spec in self.plan_for(ins, sources):
                    name = str(spec.get("provider") or "")
                    provider = self.csv_base if name == "csv_base" else self.providers.get(name)
                    if provider is None:
                        outcome.attempts.append((name, "알 수 없는 공급자"))
                        continue
                    usable, why = provider.available()
                    if not usable:
                        outcome.attempts.append((name, why))
                        continue
                    try:
                        if isinstance(provider, YahooProvider):
                            if self.politeness_sec:
                                time.sleep(self.politeness_sec)
                            pts, vols = provider.fetch_with_volume(spec, bars=bars, as_of=end)
                        else:
                            pts = provider.fetch(spec, bars=bars, as_of=end)
                    except FetchError as exc:
                        outcome.attempts.append((name, str(exc)))
                        continue
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("%s: %s 공급자 오류", ins.id, name)
                        outcome.attempts.append((name, f"예상 못 한 오류: {exc}"))
                        continue
                    if len(pts) < MIN_POINTS:
                        outcome.attempts.append((name, f"{len(pts)}개뿐 — 최소 {MIN_POINTS}개 필요"))
                        pts = []
                        continue
                    src = f"{name}:{spec.get('symbol', ins.id)}"
                    outcome.provider, outcome.symbol = name, str(spec.get("symbol", ins.id))
                    self._persist(ins.id, pts, vols, src)
                    break

            # 3. 전부 실패 — 저장소의 마지막 값을 STALE 로
            if not pts:
                cached = self._from_store(ins.id, bars)
                if cached:
                    pts, vols, src = cached
                    quality = DataQuality.STALE
                    outcome.provider, outcome.symbol = "store", src
                    outcome.attempts.append(("store", "공급자 실패 — 저장된 마지막 값(STALE)"))

            outcome.points = len(pts)
            self.outcomes[ins.id] = outcome
            if not pts:
                continue

            stamps = [t for t, _ in pts]
            vol_by_date = {t.date(): v for t, v in vols}
            volumes = [vol_by_date.get(t.date()) for t in stamps]
            has_vol = all(v is not None for v in volumes) and bool(volumes)
            out[ins.id] = MarketSeries(
                instrument_id=ins.id,
                timestamps=stamps,
                values=[v for _, v in pts],
                volumes=[float(v) for v in volumes] if has_vol else None,  # type: ignore[misc]
                meta=DataMeta(
                    source=src, mode=self.mode, retrieved_at=retrieved,
                    as_of=stamps[-1], quality=quality,
                ),
            )
        return out
