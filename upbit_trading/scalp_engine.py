"""스캘핑 엔진 - 12초 주기 두 전략 통합 구동

ScalpEngine은 기존 TradingEngine(60초 주기)과 독립적으로 동작하며,
HistoricalLowBreakout과 BoxRange 두 전략을 동시에 실행한다.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, date
from typing import Callable, List, Optional

from .config import ScalpEngineConfig
from .data_collector import UpbitCollector
from .rate_limiter import UpbitRateLimiter
from .risk_manager import RiskManager
from .strategies import Signal
from .strategy_box_range import BoxRangeStrategy
from .strategy_historical_low import HistoricalLowBreakoutStrategy
from .trader import UpbitTrader
from .trading_engine import EngineState

logger = logging.getLogger(__name__)


class ScalpEngine:
    """12초 주기 스캘핑 엔진

    Args:
        trader: Upbit 매매 실행기 (기존 모듈 재사용)
        risk_manager: 리스크 관리자 (기존 모듈 재사용)
        config: 스캘핑 엔진 설정
    """

    def __init__(
        self,
        trader: Optional[UpbitTrader] = None,
        risk_manager: Optional[RiskManager] = None,
        config: Optional[ScalpEngineConfig] = None,
    ):
        self.cfg = config or ScalpEngineConfig()
        self.trader = trader or UpbitTrader()
        self.risk_manager = risk_manager or RiskManager()

        # 공유 인프라
        self._limiter = UpbitRateLimiter(max_per_sec=self.cfg.api_rate_limit)
        self._collector = UpbitCollector()

        # 전략 초기화
        self.strategy_hist = HistoricalLowBreakoutStrategy(
            trader=self.trader,
            collector=self._collector,
            rate_limiter=self._limiter,
            config=self.cfg,
        )
        self.strategy_box = BoxRangeStrategy(
            trader=self.trader,
            collector=self._collector,
            rate_limiter=self._limiter,
            config=self.cfg,
        )

        # 스레드 제어
        self._state = EngineState.STOPPED
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._cycle_count = 0
        self._last_date: Optional[date] = None

        # 콜백
        self._on_signal_callbacks: List[Callable] = []
        self._on_order_callbacks: List[Callable] = []

    # ── 엔진 시작/중지 ──────────────────────────

    def start(self):
        """스캘핑 엔진을 시작한다."""
        if self._state == EngineState.RUNNING:
            logger.warning("[ScalpEngine] 이미 실행 중")
            return

        self._stop_event.clear()
        self._state = EngineState.RUNNING
        self._thread = threading.Thread(target=self._main_loop, daemon=True, name="ScalpEngine")
        self._thread.start()
        logger.info("[ScalpEngine] 시작 (주기=%d초)", self.cfg.cycle_seconds)

    def stop(self):
        """스캘핑 엔진을 중지한다."""
        if self._state == EngineState.STOPPED:
            return

        self._state = EngineState.STOPPED
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=30)
        logger.info("[ScalpEngine] 중지 완료")

    def pause(self):
        """일시 중지"""
        self._state = EngineState.PAUSED
        logger.info("[ScalpEngine] 일시 중지")

    def resume(self):
        """재개"""
        self._state = EngineState.RUNNING
        logger.info("[ScalpEngine] 재개")

    # ── 메인 루프 ───────────────────────────────

    def _main_loop(self):
        """12초 주기 메인 루프"""
        logger.info("[ScalpEngine] 메인 루프 시작")

        while not self._stop_event.is_set():
            try:
                if self._state == EngineState.RUNNING:
                    self._check_daily_reset()
                    if self.risk_manager.is_trading_allowed:
                        self._execute_cycle()
                    else:
                        logger.debug("[ScalpEngine] 리스크 매니저에 의해 매매 중지")
            except Exception as e:
                logger.error("[ScalpEngine] 사이클 실행 오류: %s", e, exc_info=True)

            self._stop_event.wait(timeout=self.cfg.cycle_seconds)

        logger.info("[ScalpEngine] 메인 루프 종료")

    def _check_daily_reset(self):
        """날짜 변경 시 일일 카운터를 리셋한다."""
        today = date.today()
        if self._last_date != today:
            self._last_date = today
            self.strategy_hist.tracker.reset_daily_counts()
            self.strategy_box.tracker.reset_daily_counts()
            logger.info("[ScalpEngine] 일일 카운터 리셋")

    def _execute_cycle(self):
        """단일 사이클 실행"""
        self._cycle_count += 1

        # ── 전략 1: 역사적 전저점 급등 매수 ──
        self._run_historical_low()

        # ── 전략 2: 박스권 매매 ──
        self._run_box_range()

    # ── 전략 1 실행 ─────────────────────────────

    def _run_historical_low(self):
        """전략 1: 후보 스캔 + 진입 + 청산"""
        # 스캔 윈도우에서만 후보 갱신
        if self.strategy_hist.is_scan_window():
            if not self.strategy_hist._candidates:
                self.strategy_hist.scan_for_candidates()

            # 후보 종목에 대해 진입 체크
            for ticker in list(self.strategy_hist._candidates):
                if not self.strategy_hist.tracker.can_open(ticker):
                    continue

                signal = self.strategy_hist.check_entry_signal(ticker)
                if signal and signal.signal == Signal.BUY:
                    self._fire_signal(signal)
                    # 리스크 체크
                    balance = self.trader.get_balance("KRW")
                    positions = self._get_positions_for_risk()
                    allowed, reason = self.risk_manager.check_buy_allowed(
                        ticker, self.cfg.hist_invest_amount, balance, positions,
                    )
                    if allowed:
                        if self.strategy_hist.execute_buy(ticker):
                            self._fire_order(ticker, "BUY", self.cfg.hist_invest_amount)
                    else:
                        logger.info("[ScalpEngine] 전략1 매수 거부: %s - %s", ticker, reason)

        # 보유 포지션 청산 체크 (스캔 윈도우 관계없이 항상)
        exit_signals = self.strategy_hist.check_exit_signals()
        for signal in exit_signals:
            ticker = signal.metadata.get("ticker", "")
            if ticker:
                self._fire_signal(signal)
                limit_price = signal.metadata.get("limit_price", 0.0)
                if self.strategy_hist.execute_sell(ticker, reason=signal.reason, limit_price=limit_price):
                    self._fire_order(ticker, "SELL", 0)
                    # 손익 기록
                    pos = self.strategy_hist.tracker._closed_history[-1] if self.strategy_hist.tracker._closed_history else None
                    if pos and "profit_krw" in pos.metadata:
                        self.risk_manager.record_trade_result(pos.metadata["profit_krw"])

    # ── 전략 2 실행 ─────────────────────────────

    def _run_box_range(self):
        """전략 2: 박스 갱신 + 진입 + 청산"""
        # 박스 범위 갱신 (5분마다)
        if self.strategy_box.needs_refresh():
            self.strategy_box.refresh_box_ranges()

        # 진입 스캔
        entry_signals = self.strategy_box.scan_for_entries()
        for signal in entry_signals:
            ticker = signal.metadata.get("ticker", "")
            if not ticker:
                continue

            self._fire_signal(signal)
            balance = self.trader.get_balance("KRW")
            positions = self._get_positions_for_risk()
            allowed, reason = self.risk_manager.check_buy_allowed(
                ticker, self.cfg.box_invest_amount, balance, positions,
            )
            if allowed:
                if self.strategy_box.execute_buy(ticker):
                    self._fire_order(ticker, "BUY", self.cfg.box_invest_amount)
            else:
                logger.info("[ScalpEngine] 전략2 매수 거부: %s - %s", ticker, reason)

        # 청산 체크
        exit_signals = self.strategy_box.check_exit_signals()
        for signal in exit_signals:
            ticker = signal.metadata.get("ticker", "")
            if ticker:
                self._fire_signal(signal)
                if self.strategy_box.execute_sell(ticker, reason=signal.reason):
                    self._fire_order(ticker, "SELL", 0)
                    pos = self.strategy_box.tracker._closed_history[-1] if self.strategy_box.tracker._closed_history else None
                    if pos and "profit_krw" in pos.metadata:
                        self.risk_manager.record_trade_result(pos.metadata["profit_krw"])

    # ── 헬퍼 ────────────────────────────────────

    def _get_positions_for_risk(self) -> dict:
        """리스크 매니저용 보유 포지션 dict 생성"""
        positions: dict[str, float] = {}
        for ticker, pos in self.strategy_hist.tracker.active_positions.items():
            positions[ticker] = pos.invest_amount
        for ticker, pos in self.strategy_box.tracker.active_positions.items():
            positions[ticker] = positions.get(ticker, 0) + pos.invest_amount
        return positions

    # ── 콜백 ────────────────────────────────────

    def on_signal(self, callback: Callable):
        """시그널 콜백 등록: callback(signal: TradeSignal)"""
        self._on_signal_callbacks.append(callback)

    def on_order(self, callback: Callable):
        """주문 콜백 등록: callback(ticker, side, amount)"""
        self._on_order_callbacks.append(callback)

    def _fire_signal(self, signal):
        for cb in self._on_signal_callbacks:
            try:
                cb(signal)
            except Exception as e:
                logger.error("[ScalpEngine] 시그널 콜백 오류: %s", e)

    def _fire_order(self, ticker: str, side: str, amount: float):
        for cb in self._on_order_callbacks:
            try:
                cb(ticker, side, amount)
            except Exception as e:
                logger.error("[ScalpEngine] 주문 콜백 오류: %s", e)

    # ── 상태 조회 ───────────────────────────────

    @property
    def state(self) -> EngineState:
        return self._state

    def get_status(self) -> dict:
        return {
            "engine": "ScalpEngine",
            "state": self._state.value,
            "cycle_count": self._cycle_count,
            "cycle_seconds": self.cfg.cycle_seconds,
            "strategy_1": self.strategy_hist.get_status(),
            "strategy_2": self.strategy_box.get_status(),
            "rate_limiter_available": self._limiter.available,
        }
