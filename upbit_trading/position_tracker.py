"""전략별 포지션 상태 관리

스캘핑 전략에서 진입 → 모니터링 → 청산까지의 상태를 추적한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class PositionState(str, Enum):
    PENDING = "PENDING"        # 매수 주문 접수 대기
    HOLDING = "HOLDING"        # 보유 중 (모니터링)
    CLOSING = "CLOSING"        # 청산 주문 접수 중
    CLOSED = "CLOSED"          # 청산 완료


@dataclass
class Position:
    """개별 포지션 정보"""
    ticker: str
    strategy: str              # 전략 이름
    state: PositionState = PositionState.PENDING
    entry_price: float = 0.0   # 평균 매수가
    volume: float = 0.0        # 보유 수량
    invest_amount: float = 0.0 # 투입 금액 (KRW)
    entry_time: datetime = field(default_factory=datetime.now)
    order_uuid: str = ""       # 매수 주문 UUID
    prev_minute_volume: float = 0.0  # 이전 1분봉 거래량 (전략1 청산용)
    metadata: Dict = field(default_factory=dict)

    @property
    def hold_minutes(self) -> float:
        """보유 경과 시간 (분)"""
        return (datetime.now() - self.entry_time).total_seconds() / 60.0

    @property
    def profit_rate(self) -> float:
        """현재 수익률 (current_price 기준). metadata에 current_price가 있어야 한다."""
        current = self.metadata.get("current_price", 0)
        if self.entry_price <= 0 or current <= 0:
            return 0.0
        return (current - self.entry_price) / self.entry_price


class PositionTracker:
    """전략별 포지션 관리자

    Args:
        strategy_name: 이 트래커가 관리하는 전략 이름
        max_positions: 동시 보유 가능 최대 포지션 수
    """

    def __init__(self, strategy_name: str, max_positions: int = 5):
        self.strategy_name = strategy_name
        self.max_positions = max_positions
        self._positions: Dict[str, Position] = {}  # ticker -> Position
        self._closed_history: List[Position] = []
        self._daily_trade_counts: Dict[str, int] = {}  # ticker -> 당일 거래 횟수

    @property
    def active_positions(self) -> Dict[str, Position]:
        """HOLDING 상태인 포지션만 반환"""
        return {k: v for k, v in self._positions.items()
                if v.state in (PositionState.PENDING, PositionState.HOLDING)}

    @property
    def active_count(self) -> int:
        return len(self.active_positions)

    def can_open(self, ticker: str) -> bool:
        """새 포지션을 열 수 있는지 확인"""
        if self.active_count >= self.max_positions:
            return False
        if ticker in self.active_positions:
            return False
        return True

    def open_position(
        self,
        ticker: str,
        entry_price: float,
        volume: float,
        invest_amount: float,
        order_uuid: str = "",
    ) -> Position:
        """새 포지션을 등록한다."""
        pos = Position(
            ticker=ticker,
            strategy=self.strategy_name,
            state=PositionState.HOLDING,
            entry_price=entry_price,
            volume=volume,
            invest_amount=invest_amount,
            order_uuid=order_uuid,
        )
        self._positions[ticker] = pos
        self._daily_trade_counts[ticker] = self._daily_trade_counts.get(ticker, 0) + 1
        logger.info(
            "[%s] 포지션 오픈: %s | 가격=%.2f | 수량=%.8f | 금액=%s",
            self.strategy_name, ticker, entry_price, volume, f"{invest_amount:,.0f}",
        )
        return pos

    def close_position(self, ticker: str, exit_price: float = 0.0, reason: str = "") -> Optional[Position]:
        """포지션을 청산 처리한다."""
        pos = self._positions.get(ticker)
        if pos is None:
            return None

        pos.state = PositionState.CLOSED
        pos.metadata["exit_price"] = exit_price
        pos.metadata["exit_time"] = datetime.now().isoformat()
        pos.metadata["exit_reason"] = reason

        if exit_price > 0 and pos.entry_price > 0:
            profit_rate = (exit_price - pos.entry_price) / pos.entry_price
            profit_krw = pos.invest_amount * profit_rate
            pos.metadata["profit_rate"] = profit_rate
            pos.metadata["profit_krw"] = profit_krw
            logger.info(
                "[%s] 포지션 청산: %s | 수익률=%.2f%% | 손익=%s원 | 사유=%s",
                self.strategy_name, ticker, profit_rate * 100, f"{profit_krw:+,.0f}", reason,
            )
        else:
            logger.info("[%s] 포지션 청산: %s | 사유=%s", self.strategy_name, ticker, reason)

        self._closed_history.append(pos)
        del self._positions[ticker]
        return pos

    def get_position(self, ticker: str) -> Optional[Position]:
        """특정 종목의 활성 포지션을 반환한다."""
        return self._positions.get(ticker)

    def get_daily_trade_count(self, ticker: str) -> int:
        """특정 종목의 당일 거래 횟수"""
        return self._daily_trade_counts.get(ticker, 0)

    def reset_daily_counts(self):
        """일일 거래 횟수를 초기화한다."""
        self._daily_trade_counts.clear()

    def get_status(self) -> dict:
        """현재 트래커 상태 요약"""
        return {
            "strategy": self.strategy_name,
            "active_positions": self.active_count,
            "max_positions": self.max_positions,
            "tickers": list(self.active_positions.keys()),
            "closed_today": len(self._closed_history),
        }
