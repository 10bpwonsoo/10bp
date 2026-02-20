"""전략 2: 박스권 매매 (BoxRange)

동작 흐름:
  1. 거래대금 상위 10개 코인의 최근 5시간 분봉으로 박스(고가/저가) 계산
  2. 박스 폭 2~8% 범위인 코인만 대상
  3. 현재가가 박스 하단 20% 구간 → 매수
  4. 현재가가 박스 상단 80% 구간 → 매도
  5. 24시간 보유 후 상단 미도달 시 → +구간이면 즉시 수익실현
  6. 박스 범위 5분마다 갱신
  7. 안전장치: -5% 손절, 코인당 하루 5회 제한
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, TYPE_CHECKING

from .position_tracker import PositionTracker
from .strategies import Signal, TradeSignal

if TYPE_CHECKING:
    from .config import ScalpEngineConfig
    from .data_collector import UpbitCollector
    from .rate_limiter import UpbitRateLimiter
    from .trader import UpbitTrader

logger = logging.getLogger(__name__)


@dataclass
class BoxRange:
    """종목별 박스 범위"""
    ticker: str
    high: float            # 박스 상단
    low: float             # 박스 하단
    range_pct: float       # 박스 폭 (%)
    updated_at: datetime = None

    def __post_init__(self):
        if self.updated_at is None:
            self.updated_at = datetime.now()

    @property
    def buy_threshold(self) -> float:
        """매수 기준가 (하단 20% 지점)"""
        return self.low + (self.high - self.low) * 0.20

    @property
    def sell_threshold(self) -> float:
        """매도 기준가 (상단 80% 지점)"""
        return self.low + (self.high - self.low) * 0.80

    def position_in_box(self, price: float) -> float:
        """현재가의 박스 내 위치 (0.0=하단, 1.0=상단)"""
        if self.high <= self.low:
            return 0.5
        return (price - self.low) / (self.high - self.low)


class BoxRangeStrategy:
    """박스권 하단 매수, 상단 매도 전략
    24시간 보유 후 상단 미도달 시 수익구간에서 매도"""

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
            strategy_name="BoxRange",
            max_positions=config.box_max_positions,
        )
        self._boxes: Dict[str, BoxRange] = {}      # ticker -> BoxRange
        self._target_tickers: List[str] = []        # 거래대금 상위 종목
        self._last_refresh: Optional[datetime] = None

    # ── 박스 범위 갱신 ──────────────────────────

    def needs_refresh(self) -> bool:
        """박스 범위 갱신이 필요한지 확인"""
        if self._last_refresh is None:
            return True
        elapsed = (datetime.now() - self._last_refresh).total_seconds()
        return elapsed >= self.cfg.box_refresh_minutes * 60

    def refresh_box_ranges(self):
        """거래대금 상위 코인의 박스 범위를 갱신한다."""
        logger.info("[BoxRange] 박스 범위 갱신 시작")

        # 1. 거래대금 상위 종목 조회
        try:
            self.limiter.acquire()
            markets_df = self.collector.fetch_markets("KRW")
        except Exception as e:
            logger.error("[BoxRange] 마켓 조회 실패: %s", e)
            return

        market_list = markets_df["market"].tolist()

        try:
            self.limiter.acquire()
            tickers_df = self.collector.fetch_tickers(market_list)
        except Exception as e:
            logger.error("[BoxRange] 시세 조회 실패: %s", e)
            return

        if tickers_df.empty:
            return

        # 거래대금 기준 정렬 → 상위 N개
        tickers_df = tickers_df.sort_values("acc_trade_price_24h", ascending=False)
        top_tickers = tickers_df["market"].head(self.cfg.box_top_n).tolist()
        self._target_tickers = top_tickers

        # 2. 각 종목의 5시간(300분) 분봉으로 박스 계산
        #    Upbit 분봉 API 최대 200개 → 5분봉 * 200 = 1000분 커버 가능
        #    300분 = 5분봉 60개로 조회
        new_boxes: Dict[str, BoxRange] = {}
        candle_count = self.cfg.box_window_minutes // 5  # 5분봉 개수
        for ticker in top_tickers:
            try:
                self.limiter.acquire()
                minute_df = self.collector.fetch_minute_ohlcv(
                    ticker, unit=5, count=candle_count,
                )
            except Exception as e:
                logger.debug("[BoxRange] %s 분봉 조회 실패: %s", ticker, e)
                continue

            if minute_df.empty or len(minute_df) < 10:
                continue

            box_high = minute_df["high_price"].max()
            box_low = minute_df["low_price"].min()

            if box_low <= 0:
                continue

            range_pct = (box_high - box_low) / box_low

            # 박스 폭 필터 (2~8%)
            if self.cfg.box_min_range_pct <= range_pct <= self.cfg.box_max_range_pct:
                new_boxes[ticker] = BoxRange(
                    ticker=ticker,
                    high=box_high,
                    low=box_low,
                    range_pct=range_pct,
                )
                logger.info(
                    "[BoxRange] %s | 박스=[%.0f ~ %.0f] | 폭=%.2f%%",
                    ticker, box_low, box_high, range_pct * 100,
                )

        self._boxes = new_boxes
        self._last_refresh = datetime.now()
        logger.info("[BoxRange] 유효 박스 %d개 갱신 완료", len(new_boxes))

    # ── 진입 스캔 ───────────────────────────────

    def scan_for_entries(self) -> List[TradeSignal]:
        """박스 하단 매수 조건을 스캔한다.

        Returns:
            매수 시그널 리스트
        """
        signals = []

        for ticker, box in self._boxes.items():
            if not self.tracker.can_open(ticker):
                continue

            # 일일 매매 횟수 제한
            if self.tracker.get_daily_trade_count(ticker) >= self.cfg.box_daily_max_trades:
                continue

            current_price = self.trader.get_current_price(ticker)
            if current_price is None:
                continue

            position = box.position_in_box(current_price)

            # 박스 하단 20% 구간 → 매수
            if position <= self.cfg.box_buy_zone_pct:
                signals.append(TradeSignal(
                    signal=Signal.BUY,
                    strategy_name="BoxRange",
                    confidence=1.0 - position,  # 하단에 가까울수록 높은 신뢰도
                    reason=f"박스 하단 진입 (위치={position:.1%}, 가격={current_price:,.0f})",
                    metadata={
                        "ticker": ticker,
                        "box_position": position,
                        "box_high": box.high,
                        "box_low": box.low,
                        "current_price": current_price,
                    },
                ))
                logger.info(
                    "[BoxRange] 매수 시그널: %s | 현재가=%.0f | 박스위치=%.1f%% | 매수구간=%.0f 이하",
                    ticker, current_price, position * 100, box.buy_threshold,
                )

        return signals

    # ── 청산 체크 ───────────────────────────────

    def check_exit_signals(self) -> List[TradeSignal]:
        """보유 포지션의 청산 조건을 확인한다.

        Returns:
            매도 시그널 리스트
        """
        signals = []

        for ticker, pos in list(self.tracker.active_positions.items()):
            signal = self._check_single_exit(ticker, pos)
            if signal:
                signals.append(signal)

        return signals

    def _check_single_exit(self, ticker: str, pos) -> Optional[TradeSignal]:
        """개별 포지션 청산 조건 확인

        우선순위:
          1. -5% 손절
          2. 박스 상단 80% 도달 → 익절
          3. 24시간 보유 후 상단 미도달 → 수익구간이면 수익실현, 아니면 강제 청산
        """
        current_price = self.trader.get_current_price(ticker)
        if current_price is None:
            return None

        pos.metadata["current_price"] = current_price

        # 1. 손절 (-5%)
        profit_rate = 0.0
        if pos.entry_price > 0:
            profit_rate = (current_price - pos.entry_price) / pos.entry_price
            if profit_rate <= self.cfg.box_stop_loss:
                return TradeSignal(
                    signal=Signal.SELL,
                    strategy_name="BoxRange",
                    confidence=1.0,
                    reason=f"손절: {profit_rate:.2%} <= {self.cfg.box_stop_loss:.2%}",
                    metadata={"ticker": ticker, "exit_type": "stop_loss"},
                )

        # 2. 박스 상단 80% → 매도
        box = self._boxes.get(ticker)
        if box:
            position = box.position_in_box(current_price)
            if position >= self.cfg.box_sell_zone_pct:
                return TradeSignal(
                    signal=Signal.SELL,
                    strategy_name="BoxRange",
                    confidence=position,
                    reason=f"박스 상단 도달 (위치={position:.1%}, 가격={current_price:,.0f})",
                    metadata={"ticker": ticker, "exit_type": "box_top"},
                )

        # 3. 24시간 보유 후 상단 미도달
        hold_hours = pos.hold_minutes / 60.0
        if hold_hours >= self.cfg.box_max_hold_hours:
            if profit_rate > 0:
                # 수익 구간 → 즉시 수익실현
                return TradeSignal(
                    signal=Signal.SELL,
                    strategy_name="BoxRange",
                    confidence=0.9,
                    reason=(
                        f"24시간 보유 수익실현: 보유={hold_hours:.1f}시간, "
                        f"수익률={profit_rate:+.2%}"
                    ),
                    metadata={"ticker": ticker, "exit_type": "timeout_profit"},
                )
            else:
                # 손실 구간이지만 24시간 초과 → 강제 청산
                return TradeSignal(
                    signal=Signal.SELL,
                    strategy_name="BoxRange",
                    confidence=1.0,
                    reason=(
                        f"24시간 보유 강제 청산: 보유={hold_hours:.1f}시간, "
                        f"수익률={profit_rate:+.2%}"
                    ),
                    metadata={"ticker": ticker, "exit_type": "timeout_force"},
                )

        return None

    # ── 매매 실행 ────────────────────────────────

    def execute_buy(self, ticker: str) -> bool:
        """시장가 매수를 실행한다."""
        amount = self.cfg.box_invest_amount

        result = self.trader.buy_market_order(ticker, amount)
        if result is None:
            logger.error("[BoxRange] 매수 실패: %s", ticker)
            return False

        order_uuid = result.get("uuid", "")
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

    def execute_sell(self, ticker: str, reason: str = "") -> bool:
        """시장가 매도를 실행한다."""
        pos = self.tracker.get_position(ticker)
        if pos is None:
            return False

        currency = ticker.split("-")[1] if "-" in ticker else ticker
        holding = self.trader.get_holding_amount(currency)

        if holding <= 0:
            logger.warning("[BoxRange] 보유 수량 없음: %s", ticker)
            self.tracker.close_position(ticker, reason="보유 없음")
            return False

        result = self.trader.sell_market_order(ticker, holding)
        if result is None:
            logger.error("[BoxRange] 매도 실패: %s", ticker)
            return False

        current_price = self.trader.get_current_price(ticker) or 0.0
        self.tracker.close_position(ticker, exit_price=current_price, reason=reason)
        return True

    def get_status(self) -> dict:
        return {
            "strategy": "BoxRange",
            "target_tickers": self._target_tickers,
            "active_boxes": {
                k: {"high": v.high, "low": v.low, "range": f"{v.range_pct:.2%}"}
                for k, v in self._boxes.items()
            },
            "last_refresh": self._last_refresh.isoformat() if self._last_refresh else None,
            "positions": self.tracker.get_status(),
        }
