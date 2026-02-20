"""리스크 관리 모듈

최대 투자금 제한, 종목당 투자 비율, 손절/익절, 일일 손실 제한,
비정상 가격 변동 감지, 연속 손실 일시 중지 등의 리스크 관리 기능을 제공한다.
"""

import logging
from datetime import datetime, date
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RiskConfig:
    """리스크 관리 설정"""
    max_total_investment: float = 1_000_000      # 최대 총 투자금 (KRW)
    max_per_coin_ratio: float = 0.3              # 종목당 최대 투자 비율 (30%)
    min_order_amount: float = 5_000              # 최소 주문 금액 (KRW)
    stop_loss_rate: float = -0.05                # 손절 기준 (-5%)
    take_profit_rate: float = 0.10               # 익절 기준 (+10%)
    daily_max_loss: float = 100_000              # 일일 최대 손실 (KRW)
    daily_max_loss_rate: float = -0.10           # 일일 최대 손실률 (-10%)
    max_consecutive_losses: int = 3              # 연속 손실 허용 횟수
    consecutive_loss_pause_minutes: int = 60     # 연속 손실 시 일시 중지 시간 (분)
    price_spike_threshold: float = 0.15          # 비정상 가격 변동 감지 기준 (15%)
    max_open_positions: int = 10                 # 최대 동시 보유 종목 수
    max_single_order_ratio: float = 0.5          # 1회 주문 최대 비율 (잔고 대비 50%)


@dataclass
class DailyStats:
    """일일 매매 통계"""
    trade_date: date = field(default_factory=date.today)
    total_profit: float = 0.0           # 일일 총 수익 (KRW)
    total_loss: float = 0.0             # 일일 총 손실 (KRW)
    trade_count: int = 0                # 일일 거래 횟수
    win_count: int = 0                  # 승리 횟수
    loss_count: int = 0                 # 패배 횟수
    consecutive_losses: int = 0         # 현재 연속 손실 횟수

    @property
    def net_profit(self) -> float:
        return self.total_profit + self.total_loss

    @property
    def win_rate(self) -> float:
        if self.trade_count == 0:
            return 0.0
        return self.win_count / self.trade_count

    def reset_if_new_day(self):
        """날짜가 바뀌면 통계를 리셋한다."""
        today = date.today()
        if self.trade_date != today:
            self.trade_date = today
            self.total_profit = 0.0
            self.total_loss = 0.0
            self.trade_count = 0
            self.win_count = 0
            self.loss_count = 0
            # consecutive_losses는 날짜가 바뀌어도 유지


class RiskManager:
    """리스크 관리 클래스

    매매 전 리스크 체크, 손절/익절 판단, 일일 손실 관리 등을 수행한다.
    """

    def __init__(self, config: Optional[RiskConfig] = None):
        self.config = config or RiskConfig()
        self.daily_stats = DailyStats()
        self._paused_until: Optional[datetime] = None
        self._emergency_stop = False
        # 종목별 이전 가격 캐시 (비정상 변동 감지용)
        self._prev_prices: dict[str, float] = {}

    # ─── 매매 전 리스크 체크 ───

    def check_buy_allowed(
        self,
        ticker: str,
        order_amount: float,
        current_balance: float,
        current_positions: dict[str, float],
    ) -> tuple[bool, str]:
        """매수 주문 가능 여부를 판단한다.

        Args:
            ticker: 마켓 코드 (예: "KRW-BTC")
            order_amount: 주문 금액 (KRW)
            current_balance: 현재 KRW 잔고
            current_positions: 보유 포지션 {ticker: 평가금액}

        Returns:
            (허용 여부, 사유 메시지)
        """
        self.daily_stats.reset_if_new_day()

        # 긴급 중지 상태
        if self._emergency_stop:
            return False, "긴급 중지 상태입니다."

        # 일시 중지 체크
        if self._paused_until and datetime.now() < self._paused_until:
            remaining = (self._paused_until - datetime.now()).seconds // 60
            return False, f"연속 손실로 {remaining}분간 일시 중지 상태입니다."
        elif self._paused_until:
            self._paused_until = None

        # 최소 주문 금액 체크
        if order_amount < self.config.min_order_amount:
            return False, f"최소 주문 금액 미달: {order_amount:,.0f} < {self.config.min_order_amount:,.0f}"

        # 잔고 부족 체크
        if order_amount > current_balance:
            return False, f"잔고 부족: 주문 {order_amount:,.0f} > 잔고 {current_balance:,.0f}"

        # 1회 주문 최대 비율 체크
        max_single = current_balance * self.config.max_single_order_ratio
        if order_amount > max_single:
            return False, f"1회 주문 한도 초과: {order_amount:,.0f} > {max_single:,.0f} ({self.config.max_single_order_ratio:.0%})"

        # 총 투자금 한도 체크
        total_invested = sum(current_positions.values())
        if total_invested + order_amount > self.config.max_total_investment:
            return False, f"최대 투자금 초과: {total_invested + order_amount:,.0f} > {self.config.max_total_investment:,.0f}"

        # 종목당 투자 비율 체크
        existing = current_positions.get(ticker, 0)
        max_per_coin = self.config.max_total_investment * self.config.max_per_coin_ratio
        if existing + order_amount > max_per_coin:
            return False, f"종목당 투자 한도 초과 ({ticker}): {existing + order_amount:,.0f} > {max_per_coin:,.0f}"

        # 최대 보유 종목 수 체크
        active_positions = {k: v for k, v in current_positions.items() if v > 0}
        if ticker not in active_positions and len(active_positions) >= self.config.max_open_positions:
            return False, f"최대 보유 종목 수 초과: {len(active_positions)} >= {self.config.max_open_positions}"

        # 일일 최대 손실 체크
        if self.daily_stats.net_profit <= -abs(self.config.daily_max_loss):
            return False, f"일일 최대 손실 도달: {self.daily_stats.net_profit:,.0f}"

        return True, "매수 가능"

    def check_sell_allowed(self, ticker: str, volume: float, holding_volume: float) -> tuple[bool, str]:
        """매도 주문 가능 여부를 판단한다.

        Args:
            ticker: 마켓 코드
            volume: 매도 수량
            holding_volume: 보유 수량

        Returns:
            (허용 여부, 사유 메시지)
        """
        if self._emergency_stop:
            return False, "긴급 중지 상태입니다."

        if volume <= 0:
            return False, "매도 수량이 유효하지 않습니다."

        if volume > holding_volume:
            return False, f"보유 수량 초과: 매도 {volume} > 보유 {holding_volume}"

        return True, "매도 가능"

    # ─── 손절/익절 판단 ───

    def check_stop_loss(self, avg_buy_price: float, current_price: float) -> bool:
        """손절 조건 충족 여부를 판단한다.

        Returns:
            True면 손절 매도 필요
        """
        if avg_buy_price <= 0:
            return False
        change_rate = (current_price - avg_buy_price) / avg_buy_price
        if change_rate <= self.config.stop_loss_rate:
            logger.warning(f"손절 조건 충족: 수익률 {change_rate:.2%} <= {self.config.stop_loss_rate:.2%}")
            return True
        return False

    def check_take_profit(self, avg_buy_price: float, current_price: float) -> bool:
        """익절 조건 충족 여부를 판단한다.

        Returns:
            True면 익절 매도 필요
        """
        if avg_buy_price <= 0:
            return False
        change_rate = (current_price - avg_buy_price) / avg_buy_price
        if change_rate >= self.config.take_profit_rate:
            logger.info(f"익절 조건 충족: 수익률 {change_rate:.2%} >= {self.config.take_profit_rate:.2%}")
            return True
        return False

    # ─── 비정상 가격 변동 감지 ───

    def check_price_spike(self, ticker: str, current_price: float) -> bool:
        """비정상 가격 변동을 감지한다.

        Args:
            ticker: 마켓 코드
            current_price: 현재가

        Returns:
            True면 비정상 변동 감지 (매매 중지 권고)
        """
        prev_price = self._prev_prices.get(ticker)
        self._prev_prices[ticker] = current_price

        if prev_price is None or prev_price <= 0:
            return False

        change_rate = abs((current_price - prev_price) / prev_price)
        if change_rate >= self.config.price_spike_threshold:
            logger.warning(
                f"비정상 가격 변동 감지 ({ticker}): "
                f"{prev_price:,.0f} -> {current_price:,.0f} ({change_rate:.2%})"
            )
            return True
        return False

    # ─── 매매 결과 기록 ───

    def record_trade_result(self, profit: float):
        """매매 결과를 기록하고 리스크 상태를 업데이트한다.

        Args:
            profit: 실현 손익 (KRW). 양수=수익, 음수=손실
        """
        self.daily_stats.reset_if_new_day()
        self.daily_stats.trade_count += 1

        if profit >= 0:
            self.daily_stats.total_profit += profit
            self.daily_stats.win_count += 1
            self.daily_stats.consecutive_losses = 0
        else:
            self.daily_stats.total_loss += profit
            self.daily_stats.loss_count += 1
            self.daily_stats.consecutive_losses += 1

        logger.info(
            f"매매 결과 기록: 손익 {profit:+,.0f} KRW | "
            f"일일 순손익: {self.daily_stats.net_profit:+,.0f} KRW | "
            f"연속손실: {self.daily_stats.consecutive_losses}회"
        )

        # 연속 손실 체크
        if self.daily_stats.consecutive_losses >= self.config.max_consecutive_losses:
            from datetime import timedelta
            self._paused_until = datetime.now() + timedelta(
                minutes=self.config.consecutive_loss_pause_minutes
            )
            logger.warning(
                f"연속 {self.daily_stats.consecutive_losses}회 손실! "
                f"{self.config.consecutive_loss_pause_minutes}분간 매매 일시 중지"
            )

    # ─── 긴급 중지 ───

    def emergency_stop(self):
        """긴급 매매 중지를 활성화한다."""
        self._emergency_stop = True
        logger.critical("긴급 매매 중지 활성화!")

    def resume_trading(self):
        """매매를 재개한다."""
        self._emergency_stop = False
        self._paused_until = None
        logger.info("매매 재개")

    @property
    def is_trading_allowed(self) -> bool:
        """현재 매매 가능 상태인지 반환한다."""
        if self._emergency_stop:
            return False
        if self._paused_until and datetime.now() < self._paused_until:
            return False
        self.daily_stats.reset_if_new_day()
        if self.daily_stats.net_profit <= -abs(self.config.daily_max_loss):
            return False
        return True

    def get_status(self) -> dict:
        """현재 리스크 관리 상태를 반환한다."""
        self.daily_stats.reset_if_new_day()
        return {
            "emergency_stop": self._emergency_stop,
            "paused_until": self._paused_until.isoformat() if self._paused_until else None,
            "trading_allowed": self.is_trading_allowed,
            "daily_net_profit": self.daily_stats.net_profit,
            "daily_trade_count": self.daily_stats.trade_count,
            "daily_win_rate": self.daily_stats.win_rate,
            "consecutive_losses": self.daily_stats.consecutive_losses,
        }
