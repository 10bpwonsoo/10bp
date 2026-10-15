"""
주기 실행기.

    python -m marketpulse.scheduler.runner --interval 60 --db data/snapshots.db

API 서버와 별도로 파이프라인을 계속 돌려 히스토리를 쌓는다. divergence 의
지속 기간과 alert 의 기준선은 틱이 쌓여야 의미가 생기므로, 데모 전에
이것을 몇 분 돌려 두면 화면이 첫 순간부터 채워진다.

APScheduler 같은 라이브러리를 쓰지 않는다. 필요한 것이 '일정 간격으로
한 함수를 부르고 SIGINT 에 깨끗이 멈추는 것' 뿐이라, 의존성을 하나
늘리는 것보다 표준 라이브러리로 두는 편이 데모가 죽을 경로를 줄인다.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from pathlib import Path

from ..adapters.base import AdapterError
from ..config.settings import Settings, get_settings
from ..engines.orchestrator import (
    WEEK_AGO_TARGET,
    WEEK_AGO_TOLERANCE,
    run_pipeline_detailed,
)
from ..models.common import DataMode, utcnow
from ..storage.repository import SnapshotRepository
from ..storage.sqlite_repo import SqliteSnapshotRepository

logger = logging.getLogger("marketpulse.scheduler")

DEFAULT_INTERVAL_SEC = 60.0
DEFAULT_KEEP = 500


def stream_key(settings: Settings) -> str:
    return f"{settings.data_mode.value}:{settings.scenario}"


def run_once(
    settings: Settings, repo: SnapshotRepository, *, keep: int = DEFAULT_KEEP
) -> str:
    """한 틱 실행하고 저장한다. 요약 한 줄을 돌려준다."""
    key = stream_key(settings)
    history = repo.recent(key, limit=12)
    pending = repo.latest_pending(key)
    week_ago = repo.at_or_before(
        key, utcnow() - WEEK_AGO_TARGET, max_distance=WEEK_AGO_TOLERANCE
    )

    result = run_pipeline_detailed(
        settings, history=history, pending_divergences=pending, week_ago=week_ago
    )
    repo.save(key, result.snapshot, result.pending)
    repo.prune(key, keep)
    # Daily snapshot history — 오늘은 LIVE 로 갱신되다가 finalize_time(KST) 이후 틱에서 RECORDED 로 잠긴다. 과거 날짜는 건드리지 않는다.
    try:
        from ..config.registry import get_instruments
        from ..history import DailySnapshotManager, JsonDirStore, SqliteDailyStore
        from ..history.calculators import MarketInputs
        from ..history.integrate import sync_market
        store = SqliteDailyStore(settings.history_db) if settings.history_db else JsonDirStore(settings.history_dir)
        manager = DailySnapshotManager(store, namespace="" if settings.data_mode is not DataMode.MOCK else f"mock-{settings.scenario}-", config_dir=settings.config_dir)
        sync_market(manager, inputs=MarketInputs(instruments=get_instruments().instruments, series_by_id=result.series_by_id, events=result.snapshot.events, mode=result.snapshot.mode,
                                                 zscore_window=settings.zscore_window, config_dir=settings.config_dir), snapshot=result.snapshot, as_of=result.snapshot.as_of)
        store.close()
    except Exception:
        logger.exception("daily snapshot 기록 실패 — 틱은 저장됐다")

    snap = result.snapshot
    return (
        f"{snap.as_of.isoformat()}  state={snap.market_state.primary_label.value}"
        f"  themes={len(snap.themes)}  divergences={len(snap.divergences)}"
        f"(+{len(result.pending)} 확인중)  alerts={len(snap.alerts)}"
    )


def loop(
    settings: Settings,
    repo: SnapshotRepository,
    *,
    interval: float,
    stop: threading.Event,
    max_ticks: int | None = None,
) -> int:
    """stop 이 설정될 때까지 반복한다. 실행한 틱 수를 돌려준다."""
    ticks = 0
    while not stop.is_set():
        started = time.monotonic()
        try:
            logger.info("%s", run_once(settings, repo))
        except AdapterError as exc:
            logger.error("어댑터 오류: %s", exc)
        except Exception:
            # 한 틱의 실패가 루프를 죽이면 안 된다.
            logger.exception("틱 실행 실패. 다음 주기에 다시 시도한다.")

        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break

        elapsed = time.monotonic() - started
        stop.wait(max(0.0, interval - elapsed))
    return ticks


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="marketpulse.scheduler", description="Market Pulse AI 주기 실행기"
    )
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC, help="초 단위 주기")
    p.add_argument("--db", default="data/snapshots.db", help="SQLite 파일 경로")
    p.add_argument("--scenario", help="MOCK 시나리오 이름")
    p.add_argument("--ticks", type=int, help="이 횟수만 실행하고 종료")
    p.add_argument("--keep", type=int, default=DEFAULT_KEEP, help="스트림당 보관할 스냅샷 수")
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s"
    )
    args = build_parser().parse_args(argv)

    settings = get_settings()
    if args.scenario:
        settings = settings.model_copy(update={"scenario": args.scenario})

    repo = SqliteSnapshotRepository(Path(args.db))
    stop = threading.Event()

    def handle(signum: int, _frame: object) -> None:
        logger.info("신호 %s 수신. 현재 틱을 마치고 멈춘다.", signum)
        stop.set()

    signal.signal(signal.SIGINT, handle)
    signal.signal(signal.SIGTERM, handle)

    mode = settings.data_mode.value
    scenario = settings.scenario if settings.data_mode is DataMode.MOCK else "-"
    logger.info(
        "시작: mode=%s scenario=%s interval=%.0fs db=%s",
        mode, scenario, args.interval, args.db,
    )
    try:
        ticks = loop(
            settings, repo, interval=args.interval, stop=stop, max_ticks=args.ticks
        )
    finally:
        repo.close()
    logger.info("종료: %d틱 실행", ticks)
    return 0


if __name__ == "__main__":
    sys.exit(main())
