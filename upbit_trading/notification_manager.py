"""
알림 관리 모듈
- 알림 유형별 포맷팅 (매매 시그널, 주문 체결, 손익, 일일 리포트, 에러/경고)
- 마크다운 포맷으로 가독성 높은 메시지 구성
- 이모지 활용한 시각적 표현
"""

import logging
from datetime import datetime
from typing import Optional

from .telegram_bot import TelegramBot

logger = logging.getLogger(__name__)


def _fmt_price(price: float) -> str:
    """가격 포맷팅 (KRW)"""
    if price >= 1:
        return f"{price:,.0f}"
    return f"{price:.4f}"


def _fmt_pct(pct: float) -> str:
    """퍼센트 포맷팅 (+/- 부호 포함)"""
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


def _pct_emoji(pct: float) -> str:
    """수익률에 따른 이모지"""
    if pct >= 5:
        return "🚀"
    elif pct >= 1:
        return "📈"
    elif pct >= 0:
        return "➡️"
    elif pct >= -3:
        return "📉"
    else:
        return "🔻"


class NotificationManager:
    """알림 매니저 - 유형별 메시지 포맷팅 및 전송"""

    def __init__(self, bot: TelegramBot):
        self.bot = bot

    # ──────────────────────────────────
    # 1. 매매 시그널 알림
    # ──────────────────────────────────
    async def notify_signal(
        self,
        ticker: str,
        side: str,
        current_price: float,
        indicators: Optional[dict] = None,
        strategy_name: str = "",
        reason: str = "",
    ) -> bool:
        """매매 시그널 발생 알림

        Args:
            ticker: 종목 코드 (e.g. KRW-BTC)
            side: "BUY" 또는 "SELL"
            current_price: 현재가
            indicators: 지표 딕셔너리 (e.g. {"RSI": 28.5, "MACD": -0.002})
            strategy_name: 전략 이름
            reason: 시그널 발생 사유
        """
        emoji = "🟢 매수" if side.upper() == "BUY" else "🔴 매도"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            f"📊 매매 시그널 발생",
            f"{'─' * 24}",
            f"{emoji} 시그널",
            f"종목: {ticker}",
            f"현재가: {_fmt_price(current_price)} KRW",
        ]

        if strategy_name:
            lines.append(f"전략: {strategy_name}")
        if reason:
            lines.append(f"사유: {reason}")

        if indicators:
            lines.append(f"{'─' * 24}")
            lines.append("주요 지표:")
            for name, value in indicators.items():
                if isinstance(value, float):
                    lines.append(f"  {name}: {value:.4f}")
                else:
                    lines.append(f"  {name}: {value}")

        lines.append(f"{'─' * 24}")
        lines.append(f"시간: {now}")

        return await self.bot.send_plain("\n".join(lines))

    # ──────────────────────────────────
    # 2. 주문 체결 알림
    # ──────────────────────────────────
    async def notify_order_filled(
        self,
        ticker: str,
        side: str,
        filled_price: float,
        volume: float,
        total_amount: float,
        order_id: str = "",
        fee: float = 0.0,
    ) -> bool:
        """주문 체결 알림

        Args:
            ticker: 종목 코드
            side: "BUY" 또는 "SELL"
            filled_price: 체결가
            volume: 체결 수량
            total_amount: 총 체결 금액
            order_id: 주문 UUID
            fee: 수수료
        """
        emoji = "✅ 매수 체결" if side.upper() == "BUY" else "💰 매도 체결"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            f"{emoji}",
            f"{'─' * 24}",
            f"종목: {ticker}",
            f"체결가: {_fmt_price(filled_price)} KRW",
            f"수량: {volume:.8f}",
            f"총금액: {_fmt_price(total_amount)} KRW",
        ]

        if fee > 0:
            lines.append(f"수수료: {_fmt_price(fee)} KRW")
        if order_id:
            lines.append(f"주문ID: {order_id}")

        lines.append(f"{'─' * 24}")
        lines.append(f"시간: {now}")

        return await self.bot.send_plain("\n".join(lines))

    # ──────────────────────────────────
    # 3. 손익 알림
    # ──────────────────────────────────
    async def notify_profit(
        self,
        ticker: str,
        profit_rate: float,
        realized_profit: float,
        entry_price: float = 0.0,
        exit_price: float = 0.0,
    ) -> bool:
        """손익 알림

        Args:
            ticker: 종목 코드
            profit_rate: 수익률 (%)
            realized_profit: 실현 손익 (KRW)
            entry_price: 진입가
            exit_price: 청산가
        """
        emoji = _pct_emoji(profit_rate)
        result = "수익" if profit_rate >= 0 else "손실"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            f"{emoji} 매매 {result} 확정",
            f"{'─' * 24}",
            f"종목: {ticker}",
            f"수익률: {_fmt_pct(profit_rate)}",
            f"실현손익: {_fmt_price(abs(realized_profit))} KRW {'이익' if realized_profit >= 0 else '손실'}",
        ]

        if entry_price > 0:
            lines.append(f"진입가: {_fmt_price(entry_price)} KRW")
        if exit_price > 0:
            lines.append(f"청산가: {_fmt_price(exit_price)} KRW")

        lines.append(f"{'─' * 24}")
        lines.append(f"시간: {now}")

        return await self.bot.send_plain("\n".join(lines))

    # ──────────────────────────────────
    # 4. 일일 리포트
    # ──────────────────────────────────
    async def notify_daily_report(
        self,
        total_balance: float,
        available_balance: float,
        locked_balance: float,
        daily_profit_rate: float,
        daily_profit_amount: float,
        total_profit_rate: float,
        positions: list[dict],
        trade_count: int = 0,
    ) -> bool:
        """일일 리포트 알림

        Args:
            total_balance: 총 자산 (KRW)
            available_balance: 가용 잔고
            locked_balance: 투자 중 금액
            daily_profit_rate: 일일 수익률 (%)
            daily_profit_amount: 일일 손익 금액 (KRW)
            total_profit_rate: 누적 수익률 (%)
            positions: 보유 포지션 리스트 [{"ticker", "avg_price", "current_price", "profit_rate", "amount"}]
            trade_count: 당일 거래 횟수
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        daily_emoji = _pct_emoji(daily_profit_rate)

        lines = [
            f"📋 일일 리포트",
            f"{'─' * 24}",
            f"시간: {now}",
            "",
            f"💰 자산 현황",
            f"  총 자산: {_fmt_price(total_balance)} KRW",
            f"  가용 잔고: {_fmt_price(available_balance)} KRW",
            f"  투자 중: {_fmt_price(locked_balance)} KRW",
            "",
            f"{daily_emoji} 일일 수익률: {_fmt_pct(daily_profit_rate)}",
            f"  일일 손익: {_fmt_price(abs(daily_profit_amount))} KRW {'이익' if daily_profit_amount >= 0 else '손실'}",
            f"  누적 수익률: {_fmt_pct(total_profit_rate)}",
            f"  당일 거래: {trade_count}건",
        ]

        if positions:
            lines.append("")
            lines.append(f"📌 보유 포지션 ({len(positions)}개)")
            lines.append(f"{'─' * 24}")

            for pos in positions:
                p_emoji = _pct_emoji(pos.get("profit_rate", 0))
                lines.append(
                    f"  {p_emoji} {pos['ticker']}"
                )
                lines.append(
                    f"    평단: {_fmt_price(pos.get('avg_price', 0))} "
                    f"→ 현재: {_fmt_price(pos.get('current_price', 0))}"
                )
                lines.append(
                    f"    수익률: {_fmt_pct(pos.get('profit_rate', 0))} "
                    f"| 평가액: {_fmt_price(pos.get('amount', 0))} KRW"
                )
        else:
            lines.append("")
            lines.append("📌 보유 포지션 없음")

        return await self.bot.send_plain("\n".join(lines))

    # ──────────────────────────────────
    # 5. 에러/경고 알림
    # ──────────────────────────────────
    async def notify_error(
        self,
        error_type: str,
        message: str,
        detail: str = "",
    ) -> bool:
        """에러/경고 알림

        Args:
            error_type: 에러 유형 ("API_ERROR", "STRATEGY_ERROR", "SYSTEM_ERROR", "WARNING")
            message: 에러 메시지
            detail: 상세 정보
        """
        type_map = {
            "API_ERROR": "🔌 API 에러",
            "STRATEGY_ERROR": "📊 전략 이상",
            "SYSTEM_ERROR": "⚠️ 시스템 에러",
            "WARNING": "⚡ 경고",
        }
        title = type_map.get(error_type.upper(), f"❗ {error_type}")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            title,
            f"{'─' * 24}",
            f"{message}",
        ]

        if detail:
            lines.append(f"상세: {detail}")

        lines.append(f"{'─' * 24}")
        lines.append(f"시간: {now}")

        return await self.bot.send_plain("\n".join(lines))

    # ──────────────────────────────────
    # 유틸리티: 시스템 시작/종료
    # ──────────────────────────────────
    async def notify_system_start(self, strategy_name: str = "", version: str = ""):
        """시스템 시작 알림"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "🟢 자동매매 시스템 시작",
            f"{'─' * 24}",
            f"시간: {now}",
        ]
        if strategy_name:
            lines.append(f"전략: {strategy_name}")
        if version:
            lines.append(f"버전: {version}")

        return await self.bot.send_plain("\n".join(lines))

    async def notify_system_stop(self, reason: str = ""):
        """시스템 종료 알림"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "🔴 자동매매 시스템 종료",
            f"{'─' * 24}",
            f"시간: {now}",
        ]
        if reason:
            lines.append(f"사유: {reason}")

        return await self.bot.send_plain("\n".join(lines))
