"""매매 엔진 (메인 루프)

전략 시그널 수신 -> 리스크 체크 -> 주문 실행 흐름을 관리한다.
스케줄러로 주기적 실행, 상태 관리, SQL Server 매매 결과 저장을 담당한다.
"""

import logging
import time
import threading
from enum import Enum
from datetime import datetime
from typing import Optional

import pyupbit

from .trader import UpbitTrader
from .risk_manager import RiskManager, RiskConfig

logger = logging.getLogger(__name__)


class EngineState(Enum):
    """엔진 상태"""
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"


class TradingEngine:
    """매매 엔진

    전략 시그널을 수신하고, 리스크 체크 후 주문을 실행하는 메인 루프를 관리한다.
    """

    def __init__(
        self,
        trader: Optional[UpbitTrader] = None,
        risk_manager: Optional[RiskManager] = None,
        risk_config: Optional[RiskConfig] = None,
        strategies: Optional[list] = None,
        target_tickers: Optional[list[str]] = None,
        interval_seconds: int = 60,
        db_manager=None,
    ):
        """
        Args:
            trader: UpbitTrader 인스턴스
            risk_manager: RiskManager 인스턴스
            risk_config: RiskConfig (risk_manager가 None일 때 사용)
            strategies: Strategy 인스턴스 리스트 (generate_signal(ticker, df) 메서드 필요)
            target_tickers: 매매 대상 마켓 코드 리스트 (예: ["KRW-BTC", "KRW-ETH"])
            interval_seconds: 매매 루프 실행 간격 (초)
            db_manager: DBManager 인스턴스 (매매 결과 저장용, 선택)
        """
        self.trader = trader or UpbitTrader()
        self.risk_manager = risk_manager or RiskManager(risk_config or RiskConfig())
        self.strategies = strategies or []
        self.target_tickers = target_tickers or []
        self.interval_seconds = interval_seconds
        self.db_manager = db_manager

        self._state = EngineState.STOPPED
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # 매매 결과 콜백 (텔레그램 알림 등)
        self._on_signal_callbacks: list = []
        self._on_order_callbacks: list = []

    # ─── 상태 관리 ───

    @property
    def state(self) -> EngineState:
        return self._state

    def start(self):
        """엔진을 시작한다."""
        if self._state == EngineState.RUNNING:
            logger.warning("엔진이 이미 실행 중입니다.")
            return

        logger.info("매매 엔진 시작")
        self._state = EngineState.RUNNING
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._main_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """엔진을 중지한다."""
        logger.info("매매 엔진 중지 요청")
        self._state = EngineState.STOPPED
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=30)

    def pause(self):
        """엔진을 일시 중지한다."""
        if self._state == EngineState.RUNNING:
            self._state = EngineState.PAUSED
            logger.info("매매 엔진 일시 중지")

    def resume(self):
        """엔진을 재개한다."""
        if self._state == EngineState.PAUSED:
            self._state = EngineState.RUNNING
            self.risk_manager.resume_trading()
            logger.info("매매 엔진 재개")

    # ─── 콜백 등록 ───

    def on_signal(self, callback):
        """시그널 발생 시 호출될 콜백을 등록한다.
        callback(ticker, signal, strategy_name, indicators)
        """
        self._on_signal_callbacks.append(callback)

    def on_order(self, callback):
        """주문 체결 시 호출될 콜백을 등록한다.
        callback(ticker, side, price, volume, result)
        """
        self._on_order_callbacks.append(callback)

    # ─── 메인 루프 ───

    def _main_loop(self):
        """매매 메인 루프"""
        logger.info(
            f"매매 루프 시작 | 대상: {self.target_tickers} | 간격: {self.interval_seconds}초"
        )

        while not self._stop_event.is_set():
            if self._state == EngineState.PAUSED:
                self._stop_event.wait(timeout=5)
                continue

            if self._state == EngineState.STOPPED:
                break

            try:
                self._execute_cycle()
            except Exception as e:
                logger.error(f"매매 사이클 실행 중 오류: {e}", exc_info=True)

            self._stop_event.wait(timeout=self.interval_seconds)

        logger.info("매매 루프 종료")

    def _execute_cycle(self):
        """단일 매매 사이클 실행"""
        if not self.risk_manager.is_trading_allowed:
            logger.info("리스크 관리에 의해 매매 일시 중지 상태")
            return

        # 현재 포트폴리오 상태 조회
        balance = self.trader.get_balance("KRW")
        positions = self._get_current_positions()

        for ticker in self.target_tickers:
            if self._stop_event.is_set() or self._state != EngineState.RUNNING:
                break

            try:
                self._process_ticker(ticker, balance, positions)
            except Exception as e:
                logger.error(f"{ticker} 처리 중 오류: {e}", exc_info=True)

            # API rate limit 방지
            time.sleep(0.2)

    def _process_ticker(self, ticker: str, balance: float, positions: dict):
        """개별 종목 매매 로직"""
        # 현재가 조회
        current_price = self.trader.get_current_price(ticker)
        if current_price is None:
            return

        # 비정상 가격 변동 감지
        if self.risk_manager.check_price_spike(ticker, current_price):
            logger.warning(f"{ticker} 비정상 가격 변동 감지 - 매매 스킵")
            return

        # 보유 중인 종목: 손절/익절 체크
        currency = ticker.split("-")[1] if "-" in ticker else ticker
        holding = self.trader.get_holding_amount(currency)

        if holding > 0:
            avg_price = self.trader.get_avg_buy_price(currency)
            self._check_stop_take(ticker, currency, current_price, avg_price, holding)

        # 전략 시그널 생성
        signal = self._get_consensus_signal(ticker)
        if signal is None:
            return

        # 시그널 처리
        if signal == "BUY" and holding == 0:
            self._execute_buy(ticker, balance, positions)
        elif signal == "SELL" and holding > 0:
            self._execute_sell(ticker, currency, holding)

    def _get_consensus_signal(self, ticker: str) -> Optional[str]:
        """모든 전략의 시그널을 종합하여 최종 시그널을 반환한다.

        Returns:
            "BUY", "SELL", "HOLD" 또는 None
        """
        if not self.strategies:
            return None

        signals = []
        for strategy in self.strategies:
            try:
                # 전략은 generate_signal(ticker) 메서드를 구현해야 한다
                sig = strategy.generate_signal(ticker)
                if sig:
                    signals.append(sig)

                    # 시그널 콜백 호출
                    strategy_name = getattr(strategy, "name", strategy.__class__.__name__)
                    indicators = getattr(strategy, "last_indicators", {})
                    for cb in self._on_signal_callbacks:
                        try:
                            cb(ticker, sig, strategy_name, indicators)
                        except Exception as e:
                            logger.error(f"시그널 콜백 오류: {e}")

            except Exception as e:
                logger.error(f"전략 시그널 생성 오류 ({strategy.__class__.__name__}): {e}")

        if not signals:
            return None

        # 과반수 투표로 결정
        buy_count = signals.count("BUY")
        sell_count = signals.count("SELL")
        total = len(signals)

        if buy_count > total / 2:
            return "BUY"
        elif sell_count > total / 2:
            return "SELL"
        return "HOLD"

    def _check_stop_take(
        self, ticker: str, currency: str, current_price: float,
        avg_price: float, holding: float
    ):
        """손절/익절 조건을 체크하고 필요 시 자동 매도한다."""
        if self.risk_manager.check_stop_loss(avg_price, current_price):
            logger.warning(f"[손절] {ticker} | 평균가: {avg_price:,.0f} -> 현재가: {current_price:,.0f}")
            self._execute_sell(ticker, currency, holding, reason="stop_loss")
        elif self.risk_manager.check_take_profit(avg_price, current_price):
            logger.info(f"[익절] {ticker} | 평균가: {avg_price:,.0f} -> 현재가: {current_price:,.0f}")
            self._execute_sell(ticker, currency, holding, reason="take_profit")

    def _execute_buy(self, ticker: str, balance: float, positions: dict):
        """매수를 실행한다."""
        # 투자 금액 계산 (잔고의 일정 비율)
        invest_amount = balance * 0.1  # 잔고의 10%를 기본으로 투자

        # 리스크 체크
        allowed, msg = self.risk_manager.check_buy_allowed(
            ticker, invest_amount, balance, positions
        )
        if not allowed:
            logger.info(f"[매수 거부] {ticker}: {msg}")
            return

        # 시장가 매수
        result = self.trader.buy_market_order(ticker, invest_amount)
        if result:
            logger.info(f"[매수 주문] {ticker} | 금액: {invest_amount:,.0f} KRW")
            self._save_trade_result(ticker, "buy", invest_amount, result)

            for cb in self._on_order_callbacks:
                try:
                    cb(ticker, "buy", invest_amount, 0, result)
                except Exception as e:
                    logger.error(f"주문 콜백 오류: {e}")

    def _execute_sell(self, ticker: str, currency: str, holding: float, reason: str = "signal"):
        """매도를 실행한다."""
        # 리스크 체크
        allowed, msg = self.risk_manager.check_sell_allowed(ticker, holding, holding)
        if not allowed:
            logger.info(f"[매도 거부] {ticker}: {msg}")
            return

        # 평균 매수가 조회 (손익 계산용)
        avg_price = self.trader.get_avg_buy_price(currency)
        current_price = self.trader.get_current_price(ticker)

        # 시장가 매도
        result = self.trader.sell_market_order(ticker, holding)
        if result:
            logger.info(f"[매도 주문] {ticker} | 수량: {holding} | 사유: {reason}")

            # 손익 계산 및 기록
            if avg_price > 0 and current_price:
                profit = (current_price - avg_price) * holding
                self.risk_manager.record_trade_result(profit)
                logger.info(f"[매도 결과] {ticker} | 손익: {profit:+,.0f} KRW")

            self._save_trade_result(ticker, "sell", 0, result, reason=reason)

            for cb in self._on_order_callbacks:
                try:
                    cb(ticker, "sell", current_price or 0, holding, result)
                except Exception as e:
                    logger.error(f"주문 콜백 오류: {e}")

    # ─── 포트폴리오 조회 ───

    def _get_current_positions(self) -> dict[str, float]:
        """현재 보유 포지션을 {ticker: 평가금액} 형태로 반환한다."""
        positions = {}
        balances = self.trader.get_balances()

        for item in balances:
            currency = item.get("currency", "")
            if currency == "KRW":
                continue
            balance_val = float(item.get("balance", 0))
            locked = float(item.get("locked", 0))
            total = balance_val + locked
            if total <= 0:
                continue

            ticker = f"KRW-{currency}"
            price = self.trader.get_current_price(ticker)
            if price:
                positions[ticker] = total * price

        return positions

    # ─── SQL Server 저장 ───

    def _save_trade_result(self, ticker: str, side: str, amount: float, result: dict, reason: str = ""):
        """매매 결과를 SQL Server에 저장한다."""
        if self.db_manager is None:
            return

        try:
            trade_record = {
                "ticker": ticker,
                "side": side,
                "amount": amount,
                "order_uuid": result.get("uuid", ""),
                "ord_type": result.get("ord_type", ""),
                "state": result.get("state", ""),
                "reason": reason,
                "created_at": result.get("created_at", datetime.now().isoformat()),
                "recorded_at": datetime.now().isoformat(),
            }

            if hasattr(self.db_manager, "insert_trade_history"):
                self.db_manager.insert_trade_history(trade_record)
                logger.debug(f"매매 결과 DB 저장 완료: {ticker} {side}")
        except Exception as e:
            logger.error(f"매매 결과 DB 저장 실패: {e}")

    # ─── 상태 조회 ───

    def get_status(self) -> dict:
        """엔진 상태를 반환한다."""
        return {
            "state": self._state.value,
            "target_tickers": self.target_tickers,
            "strategy_count": len(self.strategies),
            "interval_seconds": self.interval_seconds,
            "risk_status": self.risk_manager.get_status(),
        }

    def get_portfolio_summary(self) -> dict:
        """포트폴리오 요약을 반환한다."""
        balance = self.trader.get_balance("KRW")
        positions = self._get_current_positions()
        total_invested = sum(positions.values())

        return {
            "krw_balance": balance,
            "total_invested": total_invested,
            "total_asset": balance + total_invested,
            "positions": positions,
            "position_count": len(positions),
        }
