"""API 의존성. 스냅샷 생성과 짧은 TTL 캐시."""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import HTTPException, Query

from ..adapters.base import AdapterError
from ..adapters.market.scenario import available_scenarios
from ..config.settings import Settings, get_settings
from ..engines.orchestrator import (
    WEEK_AGO_TARGET,
    WEEK_AGO_TOLERANCE,
    run_pipeline_detailed,
)
from ..models.common import DataMode, utcnow
from ..models.divergence import Divergence
from ..models.snapshot import IntelligenceSnapshot
from ..storage.repository import SnapshotRepository

logger = logging.getLogger(__name__)

#: 프론트가 5초 간격으로 폴링한다. 그 사이 재계산은 낭비다.
CACHE_TTL_SEC = 4.0

#: 모드별 캐시 수명.
#
# MOCK 은 순수 계산이라 4초면 된다. 실데이터는 다르다 — 공급자 47곳을
# 도는 데 수 초에서 수십 초가 걸리고, **TTL 이 그보다 짧으면 매 폴링이
# 새 수집을 띄워 어떤 요청도 끝나지 않는다.** 실제로 그 상태가 되어
# 화면이 영영 비어 있었다.
#
# 값 자체도 데이터의 성질을 따라야 한다. 무료 공급자는 일봉 종가를 준다.
# 하루에 한 번 바뀌는 값을 4초마다 다시 받을 이유가 없다.
MODE_CACHE_TTL_SEC: dict[DataMode, float] = {
    DataMode.MOCK: CACHE_TTL_SEC,
    DataMode.DELAYED: 300.0,
    DataMode.LIVE: 300.0,
}


#: Persistence / Stability / (P2) duration 계산에 쓸 과거 틱 보관 수.
HISTORY_LIMIT = 12


@dataclass
class _Entry:
    snapshot: IntelligenceSnapshot
    created_at: float


class SnapshotService:
    """
    스냅샷 생성 + 프로세스 내 TTL 캐시.

    Redis 는 P4 옵션이다. 단일 프로세스 데모에서는 dict 로 충분하고,
    의존성이 하나 줄면 데모가 죽을 경로도 하나 줄어든다.
    """

    def __init__(
        self,
        ttl_sec: float = CACHE_TTL_SEC,
        repository: SnapshotRepository | None = None,
    ) -> None:
        self._ttl = ttl_sec
        #: 선택적이다. 없으면 프로세스 메모리만 쓴다 — 데모는 그것으로 충분하고,
        #: 의존성이 하나 줄면 데모가 죽을 경로도 하나 준다.
        self._repo = repository
        self._cache: dict[str, _Entry] = {}
        self._lock = threading.Lock()
        #: 과거 스냅샷(오래된 것부터). 상태 판정의 지속성과 테마 점수의
        #: 안정성을 재려면 한 틱 전만으로는 부족하다. P2 의 divergence
        #: duration 과 alert baseline 도 여기서 온다.
        self._history: dict[str, deque[IntelligenceSnapshot]] = defaultdict(
            lambda: deque(maxlen=HISTORY_LIMIT)
        )
        #: 아직 지속 기간을 못 채운 divergence 후보. 다음 틱에서 이어붙인다.
        self._pending: dict[str, list[Divergence]] = defaultdict(list)
        #: 마지막 틱의 원시 시계열 (히스토리 재생용). 스냅샷과 같은 데이터다.
        self._series: dict[str, dict] = {}

    def ttl_for(self, mode: DataMode) -> float:
        """MOCK 은 짧게, 실데이터는 길게. 수집 시간보다 짧으면 안 된다."""
        if self._ttl != CACHE_TTL_SEC:
            return self._ttl  # 테스트가 명시적으로 지정한 값을 존중한다
        return MODE_CACHE_TTL_SEC.get(mode, CACHE_TTL_SEC)

    def get(self, settings: Settings, *, force: bool = False) -> IntelligenceSnapshot:
        key = f"{settings.data_mode.value}:{settings.scenario}"
        now = time.monotonic()
        ttl = self.ttl_for(settings.data_mode)

        with self._lock:
            entry = self._cache.get(key)
            if entry and not force and (now - entry.created_at) < ttl:
                return entry.snapshot

            history = list(self._history[key])
            pending = list(self._pending[key])

        if not history and self._repo is not None:
            # 프로세스가 재시작돼도 지속 기간이 끊기지 않게 저장소에서 잇는다.
            history = self._repo.recent(key, limit=HISTORY_LIMIT)
            pending = self._repo.latest_pending(key)

        # "1주 전" 표식. 메모리 히스토리(12틱)로는 못 미치므로 저장소에만 묻는다.
        week_ago = None
        if self._repo is not None:
            try:
                week_ago = self._repo.at_or_before(
                    key, utcnow() - WEEK_AGO_TARGET, max_distance=WEEK_AGO_TOLERANCE
                )
            except Exception:
                logger.exception("1주 전 스냅샷 조회 실패. 표식 없이 진행한다.")

        result = run_pipeline_detailed(
            settings, history=history, pending_divergences=pending, week_ago=week_ago
        )

        with self._lock:
            # 방금 계산한 스냅샷을 히스토리에 넣는다. 캐시에 있던 것을 넣으면
            # 엔진이 보는 '직전 스냅샷' 이 한 틱 밀리고, divergence 의 지속
            # 기간이 이어지지 않아 결과가 매 틱 나타났다 사라진다.
            # 히스토리는 캐시와 독립이어야 한다 — 캐시는 TTL 최적화일 뿐이고,
            # 비워도 시계열이 끊기면 안 된다.
            self._history[key].append(result.snapshot)
            self._pending[key] = result.pending
            self._series[key] = result.series_by_id
            self._cache[key] = _Entry(
                snapshot=result.snapshot, created_at=time.monotonic()
            )

        if self._repo is not None:
            try:
                self._repo.save(key, result.snapshot, result.pending)
            except Exception:
                # 저장 실패가 화면을 막으면 안 된다.
                logger.exception("스냅샷 저장 실패. 화면은 그대로 진행한다.")
        return result.snapshot

    def history(self, settings: Settings) -> list[IntelligenceSnapshot]:
        key = f"{settings.data_mode.value}:{settings.scenario}"
        with self._lock:
            return list(self._history[key])

    def state_observations(self, settings: Settings, *, limit: int = 600) -> list:
        """
        장중 판정 관측 (as_of, 판정, 확신) — 저장소의 최근 스냅샷과 메모리 히스토리를 합쳐 as_of 로 중복을 없앤다.
        실시간 2 히스토리의 dominant/end regime·dwell 재료. 저장소가 없으면 메모리(최근 12틱)만이다.
        """
        from ..engines.regime_history import StateObservation

        key = f"{settings.data_mode.value}:{settings.scenario}"
        snaps: dict[datetime, IntelligenceSnapshot] = {}
        if self._repo is not None:
            try:
                for s in self._repo.recent(key, limit=limit):
                    snaps[s.as_of] = s
            except Exception:
                logger.exception("저장소 스냅샷 조회 실패 — 메모리 히스토리만 쓴다")
        with self._lock:
            for s in self._history[key]:
                snaps[s.as_of] = s
        return [StateObservation(as_of=t, label=s.market_state.primary_label.value, confidence=float(s.market_state.confidence)) for t, s in sorted(snaps.items())]

    def series(self, settings: Settings) -> dict:
        """마지막 틱의 원시 시계열. get() 뒤에만 채워져 있다."""
        key = f"{settings.data_mode.value}:{settings.scenario}"
        with self._lock:
            return dict(self._series.get(key, {}))

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._history.clear()
            self._pending.clear()
            self._series.clear()


_service = SnapshotService()


def get_service() -> SnapshotService:
    return _service


def resolve_settings(
    scenario: str | None = Query(
        default=None,
        description=(
            "MOCK 모드에서 재생할 시나리오. 시연을 우연이 아니라 의도로 "
            "통제하기 위한 파라미터다."
        ),
    ),
) -> Settings:
    """쿼리 파라미터로 시나리오를 바꿀 수 있게 한 설정."""
    settings = get_settings()
    if scenario is None or scenario == settings.scenario:
        return settings

    if settings.data_mode is not DataMode.MOCK:
        raise HTTPException(
            status_code=400,
            detail=f"scenario 파라미터는 MOCK 모드에서만 쓸 수 있다 (현재 {settings.data_mode.value}).",
        )
    known = available_scenarios(settings.mock_dir)
    if scenario not in known:
        raise HTTPException(
            status_code=404,
            detail=f"알 수 없는 시나리오 '{scenario}'. 사용 가능: {known}",
        )
    return settings.model_copy(update={"scenario": scenario})


def load_snapshot(settings: Settings, *, force: bool = False) -> IntelligenceSnapshot:
    """force 면 TTL 캐시를 건너뛰고 지금 새로 수집·계산한다 (화면의 '지금 업데이트')."""
    try:
        return get_service().get(settings, force=force)
    except AdapterError as exc:
        # 어댑터 부재는 설정 문제다. 500 이 아니라 503 으로 알린다.
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ── Investment Intelligence (2026-09-16 신설, 전부 추가) ──────────
#: 종목 계층 캐시 수명. 기존 스냅샷보다 길다 — 계산이 무겁고 일봉이라 하루에
#: 한 번 바뀐다. MOCK 은 시나리오 전환이 바로 보여야 하므로 짧게.
INVESTMENT_TTL_SEC: dict[DataMode, float] = {
    DataMode.MOCK: CACHE_TTL_SEC,
    DataMode.DELAYED: 900.0,
    DataMode.LIVE: 900.0,
}


class InvestmentService:
    """
    Investment Intelligence 캐시. 기존 SnapshotService 위에 얹힌다 —
    기존 스냅샷을 먼저 받고(그쪽 캐시를 그대로 탄다) 그 위에 종목 계층을 만든다.
    """

    def __init__(self, base: SnapshotService, *, store_path: str | None = None) -> None:
        self._base = base
        self._store_path = store_path
        self._cache: dict[str, tuple[object, float]] = {}
        self._previous: dict[str, object] = {}
        self._lock = threading.Lock()

    def get(self, settings: Settings, *, force: bool = False):
        from ..engines.investment import run_investment

        key = f"{settings.data_mode.value}:{settings.scenario}"
        ttl = INVESTMENT_TTL_SEC.get(settings.data_mode, CACHE_TTL_SEC)
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(key)
            if hit and not force and (now - hit[1]) < ttl:
                return hit[0]
            previous = self._previous.get(key)
        base = self._base.get(settings, force=force)
        result = run_investment(settings, base, previous=previous, store_path=self._store_path)  # type: ignore[arg-type]
        with self._lock:
            self._cache[key] = (result, time.monotonic())
            self._previous[key] = result
        try:
            get_history_service().attach_memory(settings, result, base)
        except Exception:
            logger.exception("메모리 사이클 daily snapshot 기록 실패 — 화면은 그대로 진행한다")
        return result

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._previous.clear()


_investment = InvestmentService(_service)


def get_investment_service() -> InvestmentService:
    return _investment


def load_investment(settings: Settings, *, force: bool = False):
    try:
        return get_investment_service().get(settings, force=force)
    except AdapterError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ── Market State 히스토리 (2026-09-23) ─────────────────────────────
class StateHistoryService:
    """
    Market State 히스토리 — 저장된 daily snapshot 의 sequence (2026-10-07). 과거 날짜는 다시 계산하지 않는다.
    같은 as_of 면 조립도 캐시한다. mode="recomputed" 는 현재 모델로 과거를 다시 계산한 별도 뷰(RECOMPUTED HISTORY)다.
    """

    def __init__(self, base: SnapshotService) -> None:
        self._base = base
        self._cache: dict[tuple[str, int, str], tuple[datetime, object]] = {}
        self._lock = threading.Lock()

    def get(self, settings: Settings, *, days: int | None = None, mode: str = "stored"):
        from ..config.registry import get_instruments
        from ..engines.state_history import replay_market_state

        snapshot = self._base.get(settings)
        n = int(days or settings.state_history_days)
        key = (f"{settings.data_mode.value}:{settings.scenario}", n, mode)
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] == snapshot.as_of:
                return hit[1]
        series = self._base.series(settings)
        if mode == "recomputed":
            result = replay_market_state(
                get_instruments().instruments, series, as_of=snapshot.as_of, days=n,
                mode=snapshot.mode, events=snapshot.events, zscore_window=settings.zscore_window, config_dir=settings.config_dir,
            )
        else:
            result = get_history_service().market(settings, snapshot, series, days=n)
        with self._lock:
            self._cache[key] = (snapshot.as_of, result)
        return result

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


_state_history_service = StateHistoryService(_service)


def get_state_history_service() -> StateHistoryService:
    return _state_history_service


# ── Daily snapshot history (2026-10-07) ───────────────────────────
class HistoryService:
    """
    모든 탭의 History 저장·backfill·조립을 한 곳에서. 저장소는 settings.history_db(SQLite) 또는 settings.history_dir(JSON, 기본).
    MOCK 시나리오는 프로세스 메모리 저장소에 'mock-{scenario}-' 접두로 분리한다 — 실데이터 기록과 섞이지 않는다.
    탭의 live 값은 각 서비스(스냅샷·AI·금리·유가·Investment)가 만들고 여기로 넘긴다; 이 서비스는 과거를 다시 계산하지 않는다.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._persistent = None
        self._mock = None
        self._override = None
        #: 탭별로 '마지막 live 값으로 backfill 까지 돌리는' 작업. attach_* 는 오늘 값만 기록하고(빠름), /history/{tab} 요청 때 비로소 빈 과거를 채운다.
        self._pending: dict[tuple[str, str], object] = {}

    def use(self, manager) -> None:
        """테스트·스크립트가 저장소를 바꿔 끼운다."""
        with self._lock:
            self._override = manager

    def manager(self, settings: Settings):
        from ..history import DailySnapshotManager, JsonDirStore, SqliteDailyStore
        with self._lock:
            if self._override is not None:
                return self._override
            if settings.data_mode is DataMode.MOCK:
                if self._mock is None:
                    self._mock = SqliteDailyStore(":memory:")
                return DailySnapshotManager(self._mock, namespace=f"mock-{settings.scenario}-", config_dir=settings.config_dir)
            if self._persistent is None:
                self._persistent = SqliteDailyStore(settings.history_db) if settings.history_db else JsonDirStore(settings.history_dir)
            return DailySnapshotManager(self._persistent, config_dir=settings.config_dir)

    def market(self, settings: Settings, snapshot, series: dict, *, days: int | None = None):
        from ..config.registry import get_instruments
        from ..history.calculators import MarketInputs
        from ..history.integrate import sync_market
        with self._lock:
            return sync_market(self.manager(settings), inputs=MarketInputs(instruments=get_instruments().instruments, series_by_id=series, events=snapshot.events, mode=snapshot.mode,
                                                                           zscore_window=settings.zscore_window, config_dir=settings.config_dir), snapshot=snapshot, as_of=snapshot.as_of, days=days)

    def attach_ai(self, settings: Settings, regime, snapshot, series: dict, basket: dict) -> None:
        """AI 센티먼트 1M 이력을 저장 sequence 로 바꿔 끼우고, AI 트레이드 판정 daily snapshot 을 기록·backfill 한다."""
        from ..config.registry import get_instruments
        from ..engines.ai_regime import load_ai_regime_config
        from ..history.calculators import AiInputs
        from ..history.integrate import sync_ai_regime, sync_sentiment
        key = f"{settings.data_mode.value}:{settings.scenario}"
        with self._lock:
            m = self.manager(settings)
            dv = getattr(regime.sentiment, "_day_values", None) if regime.sentiment is not None else None
            if dv is not None:  # 센티먼트 backfill 은 가볍다(날짜당 입력 재계산) — 응답에 들어가야 하므로 바로 채운다
                sync_sentiment(m, regime, cfg_all=load_ai_regime_config(settings.config_dir), dv=dv, bench_dates=dv.cal, as_of=snapshot.as_of, config_dir=settings.config_dir)
            inputs = AiInputs(instruments=get_instruments().instruments, series_by_id=series, basket_series=basket, events=snapshot.events, mode=snapshot.mode,
                              zscore_window=settings.zscore_window, config_dir=settings.config_dir)
            sync_ai_regime(m, regime, inputs=inputs, as_of=snapshot.as_of, backfill=False)  # 오늘 값 기록만 — 과거 backfill(날짜당 AI 엔진 1회)은 /history/ai_regime 때
            self._pending[(key, "ai_regime")] = lambda: sync_ai_regime(m, regime, inputs=inputs, as_of=snapshot.as_of)

    def attach_regime(self, settings: Settings, kind: str, regime, snapshot, series: dict) -> None:
        from ..config.registry import get_instruments
        from ..history.calculators import RegimeInputs
        from ..history.integrate import sync_oil, sync_rates
        inputs = RegimeInputs(instruments=get_instruments().instruments, series_by_id=series, events=snapshot.events, mode=snapshot.mode, zscore_window=settings.zscore_window, config_dir=settings.config_dir)
        key = f"{settings.data_mode.value}:{settings.scenario}"; tab = f"{kind}_regime"; fn = sync_rates if kind == "rates" else sync_oil
        with self._lock:
            m = self.manager(settings)
            fn(m, regime, inputs=inputs, as_of=snapshot.as_of, backfill=False)
            self._pending[(key, tab)] = lambda: fn(m, regime, inputs=inputs, as_of=snapshot.as_of)

    def attach_memory(self, settings: Settings, investment, snapshot) -> None:
        from ..config.registry import get_instruments, get_universe
        from ..history.calculators import MemoryInputs
        from ..history.integrate import sync_memory
        u = get_universe(settings.config_dir)
        by_id = {s.id: s.as_instrument() for s in u.stocks}; by_id.update({a.id: a.as_instrument() for a in u.alternative}); by_id.update(get_instruments().by_id())
        key = f"{settings.data_mode.value}:{settings.scenario}"
        inputs = MemoryInputs(series_by_id=dict(getattr(investment, "_series_by_id", {}) or {}), instruments_by_id=by_id, zscore_window=settings.zscore_window, config_dir=settings.config_dir)
        with self._lock:
            m = self.manager(settings)
            sync_memory(m, investment, inputs=inputs, as_of=snapshot.as_of, backfill=False)
            self._pending[(key, "memory_cycle")] = lambda: sync_memory(m, investment, inputs=inputs, as_of=snapshot.as_of)

    PRODUCERS = {"market_regime": "market", "ai_sentiment": "ai", "ai_regime": "ai", "rates_regime": "rates", "oil_regime": "oil", "memory_cycle": "memory"}

    def get(self, settings: Settings, tab_id: str):
        """저장된 sequence 만 조립한다. 그 탭의 오늘 값을 만드는 서비스를 먼저 한 번 돌려 LIVE/RECORDED 가 들어 있게 한다."""
        from ..history.integrate import history_of
        if tab_id not in self.PRODUCERS:
            raise HTTPException(status_code=404, detail=f"알 수 없는 history tab '{tab_id}'. 사용 가능: {sorted(self.PRODUCERS)}")
        snapshot = _service.get(settings)
        producer = self.PRODUCERS[tab_id]
        try:
            if producer == "market":
                _state_history_service.get(settings)
            elif producer == "ai":
                _ai_regime_service.get(settings)
            elif producer == "rates":
                _rates_regime_service.get(settings)
            elif producer == "oil":
                _oil_regime_service.get(settings)
            elif producer == "memory":
                _investment.get(settings)
        except Exception:
            logger.exception("%s 의 오늘 값을 만들지 못했다 — 저장된 기록만 돌려준다", tab_id)
        key = f"{settings.data_mode.value}:{settings.scenario}"
        with self._lock:
            job = self._pending.pop((key, tab_id), None)
            if job is not None:
                try:
                    job()  # 빈 과거 날짜만 1회 계산(BACKFILLED). 이미 있는 날짜는 건드리지 않는다
                except Exception:
                    logger.exception("%s backfill 실패 — 저장된 기록만 돌려준다", tab_id)
            return history_of(self.manager(settings), tab_id, as_of=snapshot.as_of, config_dir=settings.config_dir)

    def clear(self) -> None:
        with self._lock:
            self._mock = None
            self._override = None
            self._persistent = None
            self._pending.clear()


_history_service = HistoryService()


def get_history_service() -> HistoryService:
    return _history_service


class ScenarioCheckService:
    """시나리오 점검 — 스냅샷 as_of 별로 캐시. 시장 z 는 캐시된 원시 시계열로 다시 만들고,
    대체·종목 z 는 Investment 캐시가 있을 때만 보탠다(없으면 그 계열은 결측으로 남는다)."""

    def __init__(self, base: SnapshotService, investment: InvestmentService) -> None:
        self._base = base
        self._investment = investment
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[object, object]] = {}

    def get(self, settings: Settings):
        from ..adapters.market.scenario import load_scenario
        from ..config.registry import get_instruments
        from ..engines.normalize import build_snapshot
        from ..engines.scenario_check import check_scenarios, extra_z_from_investment

        snapshot = self._base.get(settings)
        key = f"{settings.data_mode.value}:{settings.scenario}"
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] == snapshot.as_of:
                return hit[1]
        series = self._base.series(settings)
        instruments = get_instruments().instruments
        market = build_snapshot(instruments, series, mode=snapshot.mode, as_of=snapshot.as_of,
                                zscore_window=settings.zscore_window, correlations=False)
        inv_key = key
        with self._investment._lock:
            inv_hit = self._investment._cache.get(inv_key)
        extra = extra_z_from_investment(inv_hit[0]) if inv_hit else {}
        scenarios = [load_scenario(settings.mock_dir, n) for n in available_scenarios(settings.mock_dir)]
        result = check_scenarios(scenarios, market, snapshot.market_state, snapshot.themes,
                                 {i.id: i for i in instruments}, extra_z=extra)
        with self._lock:
            self._cache[key] = (snapshot.as_of, result)
        return result

    def market_and_extra(self, settings: Settings):
        """시장 z 스냅샷과 Investment 층의 대체·종목 z. 시나리오 점검과 유가 원인 판별이 같이 쓴다."""
        from ..config.registry import get_instruments
        from ..engines.normalize import build_snapshot
        from ..engines.scenario_check import extra_z_from_investment

        snapshot = self._base.get(settings)
        series = self._base.series(settings)
        instruments = get_instruments().instruments
        market = build_snapshot(instruments, series, mode=snapshot.mode, as_of=snapshot.as_of,
                                zscore_window=settings.zscore_window, correlations=False)
        key = f"{settings.data_mode.value}:{settings.scenario}"
        with self._investment._lock:
            inv_hit = self._investment._cache.get(key)
        inv = inv_hit[0] if inv_hit else None
        extra = extra_z_from_investment(inv) if inv else {}
        names = {p.id: p.label for p in getattr(inv, "alternative", []) or []} if inv else {}
        return snapshot, market, instruments, extra, names

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


_scenario_check_service = ScenarioCheckService(_service, get_investment_service())


def get_scenario_check_service() -> ScenarioCheckService:
    return _scenario_check_service


class OilRegimeService:
    """유가 시장 원인 판별 — 스냅샷 as_of 별 캐시."""

    def __init__(self, checks: ScenarioCheckService) -> None:
        self._checks = checks
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[object, object]] = {}

    def get(self, settings: Settings):
        from ..engines.oil_regime import build_oil_regime

        key = f"{settings.data_mode.value}:{settings.scenario}"
        snapshot, market, instruments, extra, names = self._checks.market_and_extra(settings)
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] == snapshot.as_of:
                return hit[1]
        result = build_oil_regime(market, snapshot.themes, snapshot.divergences, {i.id: i for i in instruments}, extra_z=extra, extra_names=names)
        with self._lock:
            self._cache[key] = (snapshot.as_of, result)
        try:
            get_history_service().attach_regime(settings, "oil", result, snapshot, self._checks._base.series(settings))
        except Exception:
            logger.exception("유가 daily snapshot 기록 실패 — 화면은 그대로 진행한다")
        return result

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


_oil_regime_service = OilRegimeService(_scenario_check_service)


def get_oil_regime_service() -> OilRegimeService:
    return _oil_regime_service


class RatesRegimeService:
    """금리·물가 원인 판별 — 스냅샷 as_of 별 캐시. 유가 판별과 같은 입력(시장 z + 대체 z + 테마)을 쓴다."""

    def __init__(self, checks: ScenarioCheckService) -> None:
        self._checks = checks
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[object, object]] = {}
        #: MARKET READ(LLM) — 스냅샷 as_of 별 결과. 생성은 백그라운드에서 돌고, 그동안 화면은 규칙 기반 문장 + '생성 중' 을 그린다
        self._reads: dict[str, tuple[object, object]] = {}
        self._pending: set[str] = set()

    def _with_read(self, settings: Settings, key: str, snapshot, market, instruments, result):
        """GET 을 LLM 응답만큼 붙잡지 않는다 — 준비된 해석이 있으면 붙이고, 없으면 생성을 한 번 걸어 두고 규칙 기반 문장을 돌려준다."""
        from ..ai.rates_read import apply_read

        if getattr(result, "top", None) is None:
            return result
        if settings.data_mode is DataMode.MOCK:
            return apply_read(result, out=None, status="skipped", reason="MOCK 시나리오 — 실데이터가 아니라 AI 해석을 만들지 않는다")
        if not settings.llm_enabled:
            return apply_read(result, out=None, status="fallback", reason="LLM 비활성 — 키 없음 또는 설정 off")
        with self._lock:
            hit = self._reads.get(key)
            if hit and hit[0] == snapshot.as_of:
                return hit[1]
            start = key not in self._pending
            if start:
                self._pending.add(key)
        if start:
            series = self._checks._base.series(settings)
            threading.Thread(target=self._generate, args=(settings, key, snapshot, market, instruments, series, result), daemon=True,
                             name="rates-market-read").start()
        return apply_read(result, out=None, status="pending", reason="AI 해석 생성 중 — 준비되면 다음 갱신에 바뀐다")

    def _generate(self, settings: Settings, key: str, snapshot, market, instruments, series, result) -> None:
        from ..ai.client import build_client
        from ..ai.rates_read import apply_read, attach_market_read

        try:
            out, _ctx = attach_market_read(result, client=build_client(settings), market=market, series=series, news=snapshot.events,
                                           instrument_kinds={i.id: i.series_kind for i in instruments}, as_of=snapshot.as_of)
        except Exception:
            logger.exception("MARKET READ 생성 실패 — 규칙 기반 문장 유지")
            out = apply_read(result, out=None, status="fallback", reason="AI 해석 생성 중 오류")
        with self._lock:
            self._reads[key] = (snapshot.as_of, out)
            self._pending.discard(key)

    def get(self, settings: Settings):
        from ..engines.rates_regime import build_rates_regime

        key = f"{settings.data_mode.value}:{settings.scenario}"
        snapshot, market, instruments, extra, names = self._checks.market_and_extra(settings)
        with self._lock:
            hit = self._cache.get(key)
        if hit and hit[0] == snapshot.as_of:
            return self._with_read(settings, key, snapshot, market, instruments, hit[1])
        result = build_rates_regime(market, snapshot.themes, {i.id: i for i in instruments}, extra_z=extra, extra_names=names)
        # POLICY & MACRO EVENTS(2026-10-12) — 확인된 실제 결정·지표라 MOCK 시나리오에는 붙이지 않는다. 실패해도 금리 화면은 그대로.
        if settings.data_mode is not DataMode.MOCK:
            try:
                from ..engines.policy_events import build_policy_events, load_events_file

                ev = build_policy_events(load_events_file(snapshot.as_of.date()), self._checks._base.series(settings), result, as_of=snapshot.as_of)
                if ev is not None:
                    result = result.model_copy(update={"events": ev})
            except Exception:
                logger.exception("POLICY & MACRO EVENTS 구성 실패 — 금리 화면은 이벤트 없이 진행한다")
        with self._lock:
            self._cache[key] = (snapshot.as_of, result)
        try:
            get_history_service().attach_regime(settings, "rates", result, snapshot, self._checks._base.series(settings))
        except Exception:
            logger.exception("금리·물가 daily snapshot 기록 실패 — 화면은 그대로 진행한다")
        return self._with_read(settings, key, snapshot, market, instruments, result)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._reads.clear()
            self._pending.clear()


_rates_regime_service = RatesRegimeService(_scenario_check_service)


class AiRegimeService:
    """AI Trade Intelligence — 바스켓 계열은 알트 어댑터(Yahoo·저장소, MOCK 은 시나리오)로 받고 스냅샷 as_of 별로 캐시한다."""

    def __init__(self, checks: ScenarioCheckService, base: SnapshotService) -> None:
        self._checks = checks
        self._base = base
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[object, object]] = {}
        self._basket: dict[str, tuple[object, dict]] = {}

    def basket_series(self, settings: Settings, as_of) -> dict:
        from ..adapters.registry import build_alt_adapter
        from ..engines.ai_regime import basket_instruments
        from ..models.intelligence import AltInstrument, SourceSpec

        key = f"{settings.data_mode.value}:{settings.scenario}"
        with self._lock:
            hit = self._basket.get(key)
            if hit and hit[0] == as_of:
                return dict(hit[1])
        specs = [AltInstrument(id=str(m["id"]), name=str(m.get("name", m["id"])), group="ai", asset_class="equity", unit="price",  # type: ignore[arg-type]
                               sources=[SourceSpec(provider="yahoo", symbol=str(m["symbol"]))], source_type="EXCHANGE")
                 for m in basket_instruments(settings.config_dir)]
        adapter = build_alt_adapter(settings, store_path=None)
        bars = max(settings.history_bars, 120)
        if settings.data_mode is DataMode.MOCK:
            series = adapter.fetch_series([], specs, [], bars=bars, as_of=as_of)
        else:
            series = adapter.fetch_series([a.as_instrument() for a in specs], {a.id: a.sources for a in specs}, bars=bars, as_of=as_of)
        with self._lock:
            self._basket[key] = (as_of, dict(series))
        return dict(series)

    def get(self, settings: Settings):
        from ..engines.ai_regime import build_ai_regime

        key = f"{settings.data_mode.value}:{settings.scenario}"
        snapshot, market, instruments, extra, names = self._checks.market_and_extra(settings)
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] == snapshot.as_of:
                return hit[1]
        basket = self.basket_series(settings, snapshot.as_of)
        series = self._base.series(settings)
        t = snapshot.thermometer
        with self._checks._investment._lock:
            inv_hit = self._checks._investment._cache.get(key)
        inv = inv_hit[0] if inv_hit else None  # Investment 층(메모리·HBM 대체데이터, 컨센서스)이 아직 없으면 그 부분은 결측으로 남는다
        result = build_ai_regime(market, series, basket, snapshot.themes, snapshot.events, {i.id: i for i in instruments},
                                 market_label=snapshot.market_state.primary_label.value, market_confidence=snapshot.market_state.confidence,
                                 thermometer=None if t is None else t.composite, band=None if t is None else t.band,
                                 extra_z=extra, extra_names=names, investment=inv, as_of=snapshot.as_of, config_dir=settings.config_dir)
        try:
            get_history_service().attach_ai(settings, result, snapshot, series, basket)  # 1M 센티먼트 이력 = 저장 sequence · AI 판정 daily snapshot 기록
        except Exception:
            logger.exception("AI daily snapshot 기록 실패 — 화면은 그대로 진행한다")
        with self._lock:
            self._cache[key] = (snapshot.as_of, result)
        return result

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._basket.clear()


_ai_regime_service = AiRegimeService(_scenario_check_service, _service)


def get_ai_regime_service() -> AiRegimeService:
    return _ai_regime_service


class CockpitService:
    """실시간 메인 탭 — 기존 층을 모아 우선순위만 매긴다. 어느 층이 없어도(AI 바스켓 수집 실패 등) 나머지로 만든다."""

    def __init__(self, checks: ScenarioCheckService, history: StateHistoryService, ai: AiRegimeService, rates: RatesRegimeService, oil: OilRegimeService) -> None:
        self._checks, self._history, self._ai, self._rates, self._oil = checks, history, ai, rates, oil
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[object, object]] = {}

    def get(self, settings: Settings):
        from ..engines.cockpit import build_cockpit

        key = f"{settings.data_mode.value}:{settings.scenario}"
        snapshot, market, instruments, extra, names = self._checks.market_and_extra(settings)
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] == snapshot.as_of:
                return hit[1]
        with self._checks._investment._lock:
            inv_hit = self._checks._investment._cache.get(key)
        inv = inv_hit[0] if inv_hit else None
        def _try(fn):
            try:
                return fn()
            except Exception:  # 한 층이 죽어도 메인 탭은 떠야 한다
                logger.exception("cockpit 보조 층 실패")
                return None
        history = _try(lambda: self._history.get(settings))
        ai = _try(lambda: self._ai.get(settings)); rates = _try(lambda: self._rates.get(settings)); oil = _try(lambda: self._oil.get(settings))
        obs = _try(lambda: self._history._base.state_observations(settings)) or []
        stored_days = len({o.as_of.date() for o in obs}) if obs else 0
        result = build_cockpit(snapshot, market, {i.id: i for i in instruments}, history=history, investment=inv, ai_regime=ai, rates_regime=rates, oil_regime=oil,
                               extra_z=extra, extra_names=names, observations=obs, stored_days=stored_days, config_dir=settings.config_dir)
        with self._lock:
            self._cache[key] = (snapshot.as_of, result)
        return result

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


_cockpit_service = CockpitService(_scenario_check_service, _state_history_service, _ai_regime_service, _rates_regime_service, _oil_regime_service)


def get_cockpit_service() -> CockpitService:
    return _cockpit_service


class AnalystViewService:
    """
    STOCK RADAR 의 ANALYST VIEW. radar 종목만(최대 max_stocks) 조회한다. 저장된(수기·캐시) 코멘트는 바로 돌려주고,
    TTL 이 지난 종목은 provider(LLM 웹검색)가 있을 때만 백그라운드 스레드로 다시 찾는다 — 화면은 기다리지 않는다.
    provider 가 없거나 실패하면 이 층만 비고 radar 는 그대로다. 키 값은 어디에도 남기지 않는다.
    """

    def __init__(self, cockpit: CockpitService) -> None:
        from pathlib import Path as _P

        from ..adapters.analyst_view import AnalystViewStore
        from ..engines.cockpit import load_cockpit_config

        cfg = load_cockpit_config().get("analyst_view", {})
        root = _P(__file__).resolve().parents[1]
        self._cfg = cfg
        self._store = AnalystViewStore(root / str(cfg.get("cache_path", "data/analyst_views/cache.json")), root / str(cfg.get("manual_dir", "data/analyst_views/manual")))
        self._cockpit = cockpit
        self._inflight: set[str] = set()
        self._lock = threading.Lock()
        self._provider = None

    def provider(self, settings: Settings):
        if self._provider is None:
            from ..adapters.analyst_view import LlmAnalystSearch
            from ..ai.client import build_client
            try:
                self._provider = LlmAnalystSearch(build_client(settings), max_uses=int(self._cfg.get("search_max_uses", 3)))
            except Exception:
                logger.exception("analyst search provider 생성 실패 — 저장된 코멘트만 쓴다")
                self._provider = LlmAnalystSearch(None)
        return self._provider

    def get(self, settings: Settings, stock_ids: list[str] | None = None):
        from ..models.analyst_view import AnalystViews
        from ..adapters.analyst_view import ttl_expired

        cockpit = self._cockpit.get(settings)
        ids = [str(i) for i in (stock_ids or [r.id for r in cockpit.radar])][: int(self._cfg.get("max_stocks", 8))]
        names = {r.id: r.name for r in cockpit.radar}
        as_of = cockpit.as_of
        max_age = int(self._cfg.get("max_age_days", 30))
        views = self._store.best(ids, as_of=as_of, max_age_days=max_age)
        prov = self.provider(settings)
        pending: list[str] = []
        if prov.available:
            now = utcnow()
            stale = [i for i in ids if ttl_expired(self._store.retrieved_at(i), ttl_hours=float(self._cfg.get("cache_ttl_hours", 12)), now=now)
                     and (i not in views or views[i].age_days > int(self._cfg.get("fresh_days", 7)))]
            with self._lock:
                todo = [i for i in stale if i not in self._inflight]
                self._inflight.update(todo)
            if todo:
                threading.Thread(target=self._refresh, args=(settings, todo, names, as_of, max_age), daemon=True).start()
            pending = sorted(self._inflight)
        provider = "llm_web" if prov.available else ("disabled" if not settings.llm_enabled else "unavailable")
        return AnalystViews(as_of=as_of, views=[views[i] for i in ids if i in views], requested=ids, pending=pending, missing=[i for i in ids if i not in views and i not in pending],
                            provider=provider, note=("웹에서 이름·증권사·날짜·URL·맥락이 모두 확인된 코멘트만. 없는 종목은 줄을 숨긴다. 요약은 paraphrase 이고 시스템 판단과 섞지 않는다. "
                                                     + ("검색 provider 없음 — 저장된 코멘트만." if not prov.available else f"TTL {self._cfg.get('cache_ttl_hours', 12)}h 캐시.")))

    def _refresh(self, settings: Settings, ids: list[str], names: dict[str, str], as_of, max_age: int) -> None:
        from ..config.registry import get_instruments  # noqa: F401  (aliases 는 AI 설정에서)
        try:
            from ..engines.ai_regime import load_ai_regime_config as load_ai_config
            aliases = {str(m["id"]): [str(a) for a in m.get("aliases", [])] for m in (load_ai_config(settings.config_dir).get("instruments") or []) if isinstance(m, dict)}
        except Exception:
            aliases = {}
        prov = self.provider(settings)
        for sid in ids:
            try:
                v = prov.search(sid, names.get(sid, sid), aliases.get(sid, []), as_of=as_of, max_age_days=max_age)
                if v is not None:
                    self._store.put([v.model_dump(mode="json")])
                else:
                    # 못 찾은 것도 retrieved_at 만 기록해 TTL 동안 재검색하지 않는다 (코멘트는 만들지 않는다)
                    self._store.put([{"stock_id": sid, "retrieved_at": utcnow().isoformat(), "retrieved_by": "llm_web"}])
            except Exception:
                logger.exception("analyst view 검색 실패 %s", sid)
            finally:
                with self._lock:
                    self._inflight.discard(sid)

    def clear(self) -> None:
        with self._lock:
            self._inflight.clear()


_analyst_view_service = AnalystViewService(_cockpit_service)


def get_analyst_view_service() -> AnalystViewService:
    return _analyst_view_service


def get_rates_regime_service() -> RatesRegimeService:
    return _rates_regime_service
