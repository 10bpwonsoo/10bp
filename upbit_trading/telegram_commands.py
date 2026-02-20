"""
텔레그램 명령어 핸들러 모듈
- /start, /status, /balance, /positions, /profit
- /strategy, /pause, /resume, /report
- config, db_manager, trader 모듈과 연동
"""

import logging
from datetime import datetime
from typing import Optional

import pyupbit
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from .telegram_bot import TelegramBot
from .notification_manager import NotificationManager
from .config import TelegramConfig

logger = logging.getLogger(__name__)


def _fmt_price(price: float) -> str:
    if price >= 1:
        return f"{price:,.0f}"
    return f"{price:.4f}"


def _fmt_pct(pct: float) -> str:
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


class TelegramCommandHandler:
    """텔레그램 명령어 처리 클래스

    Args:
        bot: TelegramBot 인스턴스
        notification_manager: NotificationManager 인스턴스
        config: AppConfig 인스턴스 (config.py)
        db_manager: DBManager 인스턴스 (db_manager.py)
        trader: UpbitTrader 인스턴스 (trader.py)
        engine: TradingEngine 인스턴스 (trading_engine.py)
    """

    def __init__(
        self,
        bot: TelegramBot,
        notification_manager: NotificationManager,
        config=None,
        db_manager=None,
        trader=None,
        engine=None,
    ):
        self.bot = bot
        self.notification = notification_manager
        self.config = config
        self.db_manager = db_manager
        self.trader = trader  # UpbitTrader 인스턴스
        self.engine = engine  # TradingEngine 인스턴스
        self._paused = False
        self._authorized_chat_ids: set[str] = set()
        if bot.chat_id:
            self._authorized_chat_ids.add(str(bot.chat_id))

    @property
    def is_paused(self) -> bool:
        return self._paused

    def _is_authorized(self, update: Update) -> bool:
        """인가된 채팅인지 확인"""
        chat_id = str(update.effective_chat.id)
        return chat_id in self._authorized_chat_ids

    async def _check_auth(self, update: Update) -> bool:
        if not self._is_authorized(update):
            await update.message.reply_text("⛔ 권한이 없습니다.")
            return False
        return True

    # ──────────────────────────────────
    # /start - 봇 시작 안내
    # ──────────────────────────────────
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = (
            "🤖 Upbit 자동매매 봇\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "\n"
            "📌 사용 가능한 명령어:\n"
            "/status   - 현재 봇 상태\n"
            "/balance  - 잔고 조회\n"
            "/positions - 보유 포지션\n"
            "/profit   - 수익률 조회\n"
            "/strategy - 전략 상태\n"
            "/pause    - 매매 일시 중지\n"
            "/resume   - 매매 재개\n"
            "/report   - 수동 리포트\n"
            "\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "자동매매가 실행 중이면 시그널 및 체결 알림이 자동 전송됩니다."
        )
        await update.message.reply_text(msg)

    # ──────────────────────────────────
    # /status - 봇 상태 조회
    # ──────────────────────────────────
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # TradingEngine이 연결된 경우 엔진 상태 사용
        if self.engine and hasattr(self.engine, "get_status"):
            engine_status = self.engine.get_status()
            state = engine_status.get("state", "UNKNOWN")
        elif self._paused:
            state = "PAUSED"
        elif self.trader:
            state = "RUNNING"
        else:
            state = "STOPPED"

        state_emoji = {"RUNNING": "🟢", "PAUSED": "🟡", "STOPPED": "🔴"}.get(state, "⚪")

        lines = [
            "📊 봇 상태",
            "━━━━━━━━━━━━━━━━━━━━",
            f"상태: {state_emoji} {state}",
        ]

        if self.trader:
            lines.append("API: ✅ 연결됨")
        else:
            lines.append("API: ❌ 미연결")

        if self.db_manager:
            lines.append("DB: ✅ 연결됨")
        else:
            lines.append("DB: ❌ 미연결")

        if self.engine and hasattr(self.engine, "get_status"):
            engine_status = self.engine.get_status()
            lines.append(f"대상 종목: {len(engine_status.get('target_tickers', []))}개")
            lines.append(f"전략 수: {engine_status.get('strategy_count', 0)}개")

        lines.extend([
            "━━━━━━━━━━━━━━━━━━━━",
            f"조회 시간: {now}",
        ])

        await update.message.reply_text("\n".join(lines))

    # ──────────────────────────────────
    # /balance - 잔고 조회
    # ──────────────────────────────────
    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not self.trader:
            await update.message.reply_text(f"💰 잔고 조회 불가 (트레이더 미연결)\n조회 시간: {now}")
            return

        try:
            # UpbitTrader.get_balances() -> list of dicts
            balances = self.trader.get_balances()
            krw_balance = 0.0
            invested = 0.0

            for item in balances:
                currency = item.get("currency", "")
                balance_val = float(item.get("balance", 0))
                locked = float(item.get("locked", 0))
                avg_price = float(item.get("avg_buy_price", 0))

                if currency == "KRW":
                    krw_balance = balance_val + locked
                else:
                    invested += (balance_val + locked) * avg_price

            total = krw_balance + invested

            msg = (
                f"💰 잔고 현황\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"총 자산: {_fmt_price(total)} KRW\n"
                f"가용 잔고: {_fmt_price(krw_balance)} KRW\n"
                f"투자 중: {_fmt_price(invested)} KRW\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"조회 시간: {now}"
            )
        except Exception as e:
            logger.error(f"잔고 조회 실패: {e}")
            msg = f"❌ 잔고 조회 실패: {e}\n조회 시간: {now}"

        await update.message.reply_text(msg)

    # ──────────────────────────────────
    # /positions - 보유 포지션
    # ──────────────────────────────────
    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not self.trader:
            await update.message.reply_text(f"📌 포지션 조회 불가 (트레이더 미연결)\n조회 시간: {now}")
            return

        try:
            balances = self.trader.get_balances()
            positions = []

            for item in balances:
                currency = item.get("currency", "")
                if currency == "KRW":
                    continue

                balance_val = float(item.get("balance", 0))
                if balance_val <= 0:
                    continue

                avg_price = float(item.get("avg_buy_price", 0))
                ticker = f"KRW-{currency}"
                current_price = self.trader.get_current_price(ticker) or 0

                profit_rate = 0.0
                if avg_price > 0 and current_price > 0:
                    profit_rate = ((current_price - avg_price) / avg_price) * 100

                amount = balance_val * current_price

                positions.append({
                    "ticker": ticker,
                    "avg_price": avg_price,
                    "current_price": current_price,
                    "profit_rate": profit_rate,
                    "amount": amount,
                    "volume": balance_val,
                })

            if not positions:
                await update.message.reply_text(f"📌 보유 포지션 없음\n조회 시간: {now}")
                return

            lines = [
                f"📌 보유 포지션 ({len(positions)}개)",
                "━━━━━━━━━━━━━━━━━━━━",
            ]
            for pos in positions:
                emoji = "📈" if pos["profit_rate"] >= 0 else "📉"
                lines.append(f"{emoji} {pos['ticker']}")
                lines.append(
                    f"  평단: {_fmt_price(pos['avg_price'])} → 현재: {_fmt_price(pos['current_price'])}"
                )
                lines.append(
                    f"  수익률: {_fmt_pct(pos['profit_rate'])} | 평가액: {_fmt_price(pos['amount'])} KRW"
                )
                lines.append(f"  수량: {pos['volume']:.8f}")
                lines.append("")

            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"조회 시간: {now}")
            await update.message.reply_text("\n".join(lines))

        except Exception as e:
            logger.error(f"포지션 조회 실패: {e}")
            await update.message.reply_text(f"❌ 포지션 조회 실패: {e}\n조회 시간: {now}")

    # ──────────────────────────────────
    # /profit - 수익률 조회 (일/주/월)
    # ──────────────────────────────────
    async def cmd_profit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not self.trader:
            await update.message.reply_text(f"📊 수익률 조회 불가 (트레이더 미연결)\n조회 시간: {now}")
            return

        try:
            # 현재 보유 자산 기반 미실현 손익 계산
            balances = self.trader.get_balances()
            total_invested = 0.0
            total_current = 0.0

            for item in balances:
                currency = item.get("currency", "")
                if currency == "KRW":
                    continue

                balance_val = float(item.get("balance", 0))
                if balance_val <= 0:
                    continue

                avg_price = float(item.get("avg_buy_price", 0))
                ticker = f"KRW-{currency}"
                current_price = self.trader.get_current_price(ticker) or 0

                total_invested += balance_val * avg_price
                total_current += balance_val * current_price

            unrealized_pnl = total_current - total_invested
            unrealized_rate = ((total_current / total_invested) - 1) * 100 if total_invested > 0 else 0

            lines = [
                "📊 수익률 현황",
                "━━━━━━━━━━━━━━━━━━━━",
                f"미실현 손익",
                f"  투자 원금: {_fmt_price(total_invested)} KRW",
                f"  현재 평가: {_fmt_price(total_current)} KRW",
                f"  미실현 손익: {_fmt_price(abs(unrealized_pnl))} KRW {'이익' if unrealized_pnl >= 0 else '손실'}",
                f"  수익률: {_fmt_pct(unrealized_rate)}",
                "━━━━━━━━━━━━━━━━━━━━",
                f"조회 시간: {now}",
            ]
            await update.message.reply_text("\n".join(lines))

        except Exception as e:
            logger.error(f"수익률 조회 실패: {e}")
            await update.message.reply_text(f"❌ 수익률 조회 실패: {e}\n조회 시간: {now}")

    # ──────────────────────────────────
    # /strategy - 현재 전략 상태 및 시그널
    # ──────────────────────────────────
    async def cmd_strategy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # trader에 전략 정보가 있으면 표시
        if self.trader and hasattr(self.trader, "get_strategy_status"):
            status = self.trader.get_strategy_status()
            name = status.get("name", "-")
            params = status.get("parameters", {})
            signals = status.get("recent_signals", [])

            lines = [
                "📊 전략 상태",
                "━━━━━━━━━━━━━━━━━━━━",
                f"전략: {name}",
            ]

            if params:
                lines.append("파라미터:")
                for k, v in params.items():
                    lines.append(f"  {k}: {v}")

            if signals:
                lines.append("")
                lines.append("최근 시그널:")
                for sig in signals[-5:]:
                    side = sig.get("side", "?")
                    ticker = sig.get("ticker", "?")
                    ts = sig.get("timestamp", "?")
                    emoji = "🟢" if side == "BUY" else "🔴"
                    lines.append(f"  {emoji} {side} {ticker} ({ts})")

            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"조회 시간: {now}")
            await update.message.reply_text("\n".join(lines))
        else:
            lines = [
                "📊 전략 상태",
                "━━━━━━━━━━━━━━━━━━━━",
                f"매매 상태: {'⏸ 일시중지' if self._paused else '▶️ 활성'}",
                "━━━━━━━━━━━━━━━━━━━━",
                f"조회 시간: {now}",
            ]
            await update.message.reply_text("\n".join(lines))

    # ──────────────────────────────────
    # /pause - 매매 일시 중지
    # ──────────────────────────────────
    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return

        self._paused = True
        if self.engine and hasattr(self.engine, "pause"):
            self.engine.pause()
        await update.message.reply_text("⏸ 매매가 일시 중지되었습니다.")
        logger.info("사용자 명령으로 매매 일시 중지")

    # ──────────────────────────────────
    # /resume - 매매 재개
    # ──────────────────────────────────
    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return

        self._paused = False
        if self.engine and hasattr(self.engine, "resume"):
            self.engine.resume()
        await update.message.reply_text("▶️ 매매가 재개되었습니다.")
        logger.info("사용자 명령으로 매매 재개")

    # ──────────────────────────────────
    # /report - 수동 리포트 생성
    # ──────────────────────────────────
    async def cmd_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_auth(update):
            return

        await update.message.reply_text("📋 리포트 생성 중...")

        if not self.trader:
            await update.message.reply_text("📋 리포트 생성 불가 (트레이더 미연결)")
            return

        try:
            balances = self.trader.get_balances()
            krw_balance = 0.0
            invested = 0.0
            positions = []

            for item in balances:
                currency = item.get("currency", "")
                balance_val = float(item.get("balance", 0))
                locked = float(item.get("locked", 0))
                avg_price = float(item.get("avg_buy_price", 0))

                if currency == "KRW":
                    krw_balance = balance_val + locked
                    continue

                if balance_val <= 0:
                    continue

                ticker = f"KRW-{currency}"
                current_price = self.trader.get_current_price(ticker) or 0
                profit_rate = ((current_price / avg_price) - 1) * 100 if avg_price > 0 else 0
                amount = balance_val * current_price
                invested += balance_val * avg_price

                positions.append({
                    "ticker": ticker,
                    "avg_price": avg_price,
                    "current_price": current_price,
                    "profit_rate": profit_rate,
                    "amount": amount,
                })

            total_current_value = sum(p["amount"] for p in positions)
            total_balance = krw_balance + total_current_value
            total_profit_rate = ((total_current_value / invested) - 1) * 100 if invested > 0 else 0

            await self.notification.notify_daily_report(
                total_balance=total_balance,
                available_balance=krw_balance,
                locked_balance=total_current_value,
                daily_profit_rate=total_profit_rate,
                daily_profit_amount=total_current_value - invested,
                total_profit_rate=total_profit_rate,
                positions=positions,
            )

        except Exception as e:
            logger.error(f"리포트 생성 실패: {e}")
            await update.message.reply_text(f"❌ 리포트 생성 실패: {e}")

    # ──────────────────────────────────
    # 핸들러 등록
    # ──────────────────────────────────
    def register_handlers(self, application: Application):
        """Application에 모든 명령어 핸들러를 등록"""
        handlers = [
            ("start", self.cmd_start),
            ("help", self.cmd_start),
            ("status", self.cmd_status),
            ("balance", self.cmd_balance),
            ("positions", self.cmd_positions),
            ("profit", self.cmd_profit),
            ("strategy", self.cmd_strategy),
            ("pause", self.cmd_pause),
            ("resume", self.cmd_resume),
            ("report", self.cmd_report),
        ]

        for command, handler in handlers:
            application.add_handler(CommandHandler(command, handler))

        logger.info(f"텔레그램 명령어 핸들러 {len(handlers)}개 등록 완료")


def create_telegram_application(
    config=None,
    db_manager=None,
    trader=None,
    engine=None,
) -> tuple[Application, TelegramBot, NotificationManager, TelegramCommandHandler]:
    """텔레그램 Application 생성 및 초기화

    Args:
        config: AppConfig 인스턴스 (config.py의 config 전역 변수)
        db_manager: DBManager 인스턴스
        trader: UpbitTrader 인스턴스
        engine: TradingEngine 인스턴스

    Returns:
        (Application, TelegramBot, NotificationManager, TelegramCommandHandler) 튜플
    """
    if config is None:
        from .config import config as app_config
        config = app_config

    token = config.telegram.token
    chat_id = config.telegram.chat_id

    if not token:
        raise ValueError("TELEGRAM_TOKEN이 설정되지 않았습니다. .env 파일 또는 환경변수를 확인하세요.")

    bot = TelegramBot(token=token, chat_id=chat_id)
    notification = NotificationManager(bot)
    cmd_handler = TelegramCommandHandler(
        bot=bot,
        notification_manager=notification,
        config=config,
        db_manager=db_manager,
        trader=trader,
        engine=engine,
    )

    application = (
        Application.builder()
        .token(token)
        .get_updates_read_timeout(30)
        .get_updates_write_timeout(30)
        .get_updates_connect_timeout(30)
        .build()
    )

    cmd_handler.register_handlers(application)

    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"텔레그램 봇 에러: {context.error}")
        if isinstance(context.error, Exception):
            await notification.notify_error(
                "SYSTEM_ERROR",
                "텔레그램 봇 에러 발생",
                str(context.error),
            )

    application.add_error_handler(error_handler)

    return application, bot, notification, cmd_handler
