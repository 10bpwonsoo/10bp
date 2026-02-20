"""전략 1: 역사적 전저점 급등 매수 (HistoricalLowBreakout)

동작 흐름:
  1. 오전 8:50~9:10 (일봉 마감 부근) 전 KRW 코인 스캔
  2. 과거 60일 저가 대비 5% 이내인 코인 필터링
  3. 해당 코인 중 현재 1분봉 거래량 > 평균의 3배 → 즉시 매수
  4. 매수 후 12초마다 1분봉 모니터링
  5. 최근 4분봉 고점을 돌파 못하면 → 1틱 아래 지정가 매도
  6. 안전장치: 최대 30분 보유, -5% 손절
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

from .position_tracker import PositionTracker
from .strategies import Signal, TradeSignal

if TYPE_CHECKING:
    from .config import ScalpEngineConfig
    from .data_collector import UpbitCollector
    from .rate_limiter import UpbitRateLimiter
    from .trader import UpbitTrader

logger = logging.getLogger(__name__)


def _get_tick_size(price: float) -> float:
    """Upbit 호가 단위(틱 사이즈)를 반환한다."""
    if price >= 2_000_000:
        return 1_000
    elif price >= 1_000_000:
        return 500
    elif price >= 500_000:
        return 100
    elif price >= 100_000:
        return 50
    elif price >= 10_000:
        return 10
    elif price >= 1_000:
        return 5
    elif price >= 100:
        return 1
    elif price >= 10:
        return 0.1
    else:
        return 0.01


class HistoricalLowBreakoutStrategy:
    """역사적 전저점 근접 + 거래량 급등 시 매수,
    4분 고점 돌파 실패 시 1틱 아래 지정가 매도"""

    def __init__(
        self,
        trader: UpbitTrader,
        collector: UpbitCollector,
        rate_limiter: UpbitRateLimiter,
        config: ScalpEngineConfig,
    ):
        self.trader = trader
        self.collector = collector
        self.limiter = rate_limiter
        self.cfg = config
        self.tracker = PositionTracker(
            strategy_name="HistoricalLow",
            max_positions=config.hist_max_positions,
        )
        self._candidates: List[str] = []  # 스캔된 후보 종목

    # ── 진입 스캔 (8:50~9:10에만 실행) ───────────

    def is_scan_window(self) -> bool:
        """현재 시각이 스캔 윈도우 내인지 확인"""
        now = datetime.now()
        start = now.replace(
            hour=self.cfg.hist_scan_start_hour,
            minute=self.cfg.hist_scan_start_minute,
            second=0, microsecond=0,
        )
        end = now.replace(
            hour=self.cfg.hist_scan_end_hour,
            minute=self.cfg.hist_scan_end_minute,
            second=0, microsecond=0,
        )
        return start <= now <= end

    def scan_for_candidates(self) -> List[str]:
        """전 KRW 코인을 스캔하여 전저점 근접 종목을 선별한다.

        Returns:
            후보 종목 리스트 (예: ["KRW-XRP", "KRW-ADA"])
        """
        if not self.is_scan_window():
            return self._candidates

        logger.info("[HistoricalLow] 전저점 후보 스캔 시작")
        candidates = []

        try:
            self.limiter.acquire()
            markets_df = self.collector.fetch_markets("KRW")
        except Exception as e:
            logger.error("[HistoricalLow] 마켓 조회 실패: %s", e)
            return self._candidates

        for _, row in markets_df.iterrows():
            ticker = row["market"]

            if not self.tracker.can_open(ticker):
                continue

            try:
                self.limiter.acquire()
                daily_df = self.collector.fetch_daily_ohlcv(
                    ticker, count=self.cfg.hist_lookback_days,
                )
            except Exception as e:
                logger.debug("[HistoricalLow] %s 일봉 조회 실패: %s", ticker, e)
                continue

            if daily_df.empty or len(daily_df) < 10:
                continue

            # 과거 60일 저가
            historical_low = daily_df["low_price"].min()
            current_price = daily_df["close_price"].iloc[0]  # 가장 최근

            if historical_low <= 0 or current_price <= 0:
                continue

            proximity = (current_price - historical_low) / historical_low

            if proximity <= self.cfg.hist_low_proximity_pct:
                candidates.append(ticker)
                logger.info(
                    "[HistoricalLow] 후보: %s | 현재가=%.0f | 저점=%.0f | 근접도=%.2f%%",
                    ticker, current_price, historical_low, proximity * 100,
                )

        self._candidates = candidates
        logger.info("[HistoricalLow] 후보 %d개 선별: %s", len(candidates), candidates)
        return candidates

    def check_entry_signal(self, ticker: str) -> Optional[TradeSignal]:
        """후보 종목에 대해 거래량 급등 여부를 확인한다.

        Returns:
            TradeSignal(BUY) 또는 None
        """
        if ticker not in self._candidates:
            return None
        if not self.tracker.can_open(ticker):
            return None

        try:
            self.limiter.acquire()
            minute_df = self.collector.fetch_minute_ohlcv(ticker, unit=1, count=30)
        except Exception as e:
            logger.debug("[HistoricalLow] %s 분봉 조회 실패: %s", ticker, e)
            return None

        if minute_df.empty or len(minute_df) < 10:
            return None

        # 현재 1분봉 (인덱스 0이 가장 최근)
        current_volume = minute_df["volume"].iloc[0]
        avg_volume = minute_df["volume"].iloc[1:].mean()

        if avg_volume <= 0:
            return None

        volume_ratio = current_volume / avg_volume

        if volume_ratio >= self.cfg.hist_volume_surge:
            logger.info(
                "[HistoricalLow] 거래량 급등: %s | 현재=%.2f | 평균=%.2f | 배율=%.1fx",
                ticker, current_volume, avg_volume, volume_ratio,
            )
            return TradeSignal(
                signal=Signal.BUY,
                strategy_name="HistoricalLow",
                confidence=min(volume_ratio / 10.0, 1.0),
                reason=f"전저점 근접 + 거래량 {volume_ratio:.1f}배 급등",
                metadata={
                    "volume_ratio": volume_ratio,
                    "current_volume": current_volume,
                    "avg_volume": avg_volume,
                },
            )
        return None

    # ── 청산 체크 (매 사이클) ────────────────────

    def check_exit_signals(self) -> List[TradeSignal]:
        """보유 중인 포지션의 청산 조건을 확인한다.

        Returns:
            청산이 필요한 TradeSignal 리스트
        """
        signals = []

        for ticker, pos in list(self.tracker.active_positions.items()):
            signal = self._check_single_exit(ticker, pos)
            if signal:
                signals.append(signal)

        return signals

    def _check_single_exit(self, ticker: str, pos) -> Optional[TradeSignal]:
        """개별 포지션 청산 조건 확인

        1. -5% 손절 → 시장가 매도
        2. 최대 보유 시간 초과 → 시장가 매도
        3. 최근 4분봉 고점 돌파 실패 → 고점 1틱 아래 지정가 매도
        """
        try:
            self.limiter.acquire()
            minute_df = self.collector.fetch_minute_ohlcv(ticker, unit=1, count=5)
        except Exception as e:
            logger.debug("[HistoricalLow] %s 분봉 조회 실패: %s", ticker, e)
            return None

        if minute_df.empty or len(minute_df) < 2:
            return None

        current_price = minute_df["close_price"].iloc[0]
        pos.metadata["current_price"] = current_price

        # 1. 손절 체크 (-5%)
        if pos.entry_price > 0:
            profit_rate = (current_price - pos.entry_price) / pos.entry_price
            if profit_rate <= self.cfg.hist_stop_loss:
                return TradeSignal(
                    signal=Signal.SELL,
                    strategy_name="HistoricalLow",
                    confidence=1.0,
                    reason=f"손절: {profit_rate:.2%} <= {self.cfg.hist_stop_loss:.2%}",
                    metadata={"ticker": ticker, "exit_type": "stop_loss"},
                )

        # 2. 최대 보유 시간 초과
        if pos.hold_minutes >= self.cfg.hist_max_hold_minutes:
            return TradeSignal(
                signal=Signal.SELL,
                strategy_name="HistoricalLow",
                confidence=1.0,
                reason=f"최대 보유 시간 초과: {pos.hold_minutes:.0f}분 >= {self.cfg.hist_max_hold_minutes}분",
                metadata={"ticker": ticker, "exit_type": "timeout"},
            )

        # 3. 최근 4분봉 고점 돌파 실패 → 1틱 아래 지정가 매도
        #    minute_df: 인덱스 0=현재, 1~4=이전 4개 분봉
        if len(minute_df) >= 5:
            # 이전 4분봉(인덱스 1~4)의 고점
            recent_4min_high = minute_df["high_price"].iloc[1:5].max()
            current_high = minute_df["high_price"].iloc[0]

            if current_high < recent_4min_high:
                tick = _get_tick_size(recent_4min_high)
                limit_price = recent_4min_high - tick
                return TradeSignal(
                    signal=Signal.SELL,
                    strategy_name="HistoricalLow",
                    confidence=0.8,
                    reason=(
                        f"4분 고점 돌파 실패: 현재고가={current_high:,.0f} < "
                        f"4분고점={recent_4min_high:,.0f} → "
                        f"지정가={limit_price:,.0f}"
                    ),
                    metadata={
                        "ticker": ticker,
                        "exit_type": "high_breakout_fail",
                        "limit_price": limit_price,
                        "recent_4min_high": recent_4min_high,
                    },
                )

        return None

    # ── 매매 실행 ────────────────────────────────

    def execute_buy(self, ticker: str) -> bool:
        """시장가 매수를 실행한다."""
        amount = self.cfg.hist_invest_amount

        result = self.trader.buy_market_order(ticker, amount)
        if result is None:
            logger.error("[HistoricalLow] 매수 실패: %s", ticker)
            return False

        order_uuid = result.get("uuid", "")

        # 현재가로 대략적 수량 추정
        current_price = self.trader.get_current_price(ticker)
        volume = amount / current_price if current_price and current_price > 0 else 0.0

        self.tracker.open_position(
            ticker=ticker,
            entry_price=current_price or 0.0,
            volume=volume,
            invest_amount=amount,
            order_uuid=order_uuid,
        )
        return True

    def execute_sell(self, ticker: str, reason: str = "", limit_price: float = 0.0) -> bool:
        """매도를 실행한다.

        Args:
            ticker: 마켓 코드
            reason: 매도 사유
            limit_price: 지정가 (0이면 시장가 매도)
        """
        pos = self.tracker.get_position(ticker)
        if pos is None:
            return False

        # 실제 보유 수량 조회
        currency = ticker.split("-")[1] if "-" in ticker else ticker
        holding = self.trader.get_holding_amount(currency)

        if holding <= 0:
            logger.warning("[HistoricalLow] 보유 수량 없음: %s", ticker)
            self.tracker.close_position(ticker, reason="보유 없음")
            return False

        if limit_price > 0:
            # 지정가 매도 (4분 고점 돌파 실패)
            result = self.trader.sell_limit_order(ticker, limit_price, holding)
            if result is None:
                logger.error("[HistoricalLow] 지정가 매도 실패: %s @ %.0f", ticker, limit_price)
                return False
            logger.info(
                "[HistoricalLow] 지정가 매도 접수: %s | 가격=%.0f | 수량=%.8f | 사유=%s",
                ticker, limit_price, holding, reason,
            )
            exit_price = limit_price
        else:
            # 시장가 매도 (손절, 타임아웃)
            result = self.trader.sell_market_order(ticker, holding)
            if result is None:
                logger.error("[HistoricalLow] 시장가 매도 실패: %s", ticker)
                return False
            exit_price = self.trader.get_current_price(ticker) or 0.0

        self.tracker.close_position(ticker, exit_price=exit_price, reason=reason)
        return True

    def get_status(self) -> dict:
        return {
            "strategy": "HistoricalLow",
            "candidates": self._candidates,
            "scan_window": self.is_scan_window(),
            "positions": self.tracker.get_status(),
        }
