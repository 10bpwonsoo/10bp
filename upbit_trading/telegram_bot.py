"""
텔레그램 봇 모듈
- python-telegram-bot 라이브러리를 활용한 텔레그램 봇 초기화 및 메시지 전송
- 에러 핸들링 및 재시도 로직
"""

import asyncio
import logging
from typing import Optional

import telegram
from telegram import Bot
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)


class TelegramBot:
    """텔레그램 봇 래퍼 클래스"""

    def __init__(self, token: str, chat_id: str, max_retries: int = 3, retry_delay: float = 5.0):
        self.token = token
        self.chat_id = chat_id
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._bot: Optional[Bot] = None

    @property
    def bot(self) -> Bot:
        if self._bot is None:
            self._bot = Bot(token=self.token)
        return self._bot

    async def initialize(self):
        """봇 초기화 및 연결 테스트"""
        try:
            me = await self.bot.get_me()
            logger.info(f"텔레그램 봇 연결 성공: @{me.username}")
            return True
        except Exception as e:
            logger.error(f"텔레그램 봇 초기화 실패: {e}")
            return False

    async def send_message(
        self,
        text: str,
        chat_id: Optional[str] = None,
        parse_mode: str = "Markdown",
        disable_preview: bool = True,
    ) -> bool:
        """메시지 전송 (재시도 로직 포함)

        Args:
            text: 전송할 메시지 텍스트
            chat_id: 대상 채팅 ID (None이면 기본 chat_id 사용)
            parse_mode: 파싱 모드 ("Markdown", "HTML", None)
            disable_preview: 링크 미리보기 비활성화 여부
        """
        target_chat_id = chat_id or self.chat_id
        if not target_chat_id:
            logger.error("chat_id가 설정되지 않았습니다.")
            return False

        # 텔레그램 메시지 길이 제한 (4096자)
        messages = self._split_message(text, max_length=4000)

        for msg in messages:
            success = await self._send_with_retry(
                msg, target_chat_id, parse_mode, disable_preview
            )
            if not success:
                return False
            if len(messages) > 1:
                await asyncio.sleep(0.5)

        return True

    async def send_html(self, text: str, chat_id: Optional[str] = None) -> bool:
        """HTML 형식 메시지 전송"""
        return await self.send_message(text, chat_id=chat_id, parse_mode="HTML")

    async def send_plain(self, text: str, chat_id: Optional[str] = None) -> bool:
        """일반 텍스트 메시지 전송"""
        return await self.send_message(text, chat_id=chat_id, parse_mode=None)

    async def _send_with_retry(
        self,
        text: str,
        chat_id: str,
        parse_mode: Optional[str],
        disable_preview: bool,
    ) -> bool:
        """재시도 로직이 포함된 메시지 전송"""
        pm = None
        if parse_mode == "Markdown":
            pm = ParseMode.MARKDOWN_V2
        elif parse_mode == "HTML":
            pm = ParseMode.HTML

        for attempt in range(1, self.max_retries + 1):
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=pm,
                    disable_web_page_preview=disable_preview,
                )
                return True
            except telegram.error.RetryAfter as e:
                wait = e.retry_after
                logger.warning(f"Rate limit. {wait}초 대기 후 재시도...")
                await asyncio.sleep(wait)
            except telegram.error.BadRequest as e:
                if "parse" in str(e).lower():
                    logger.warning(f"파싱 에러, 일반 텍스트로 재전송: {e}")
                    try:
                        await self.bot.send_message(
                            chat_id=chat_id,
                            text=text,
                            parse_mode=None,
                            disable_web_page_preview=disable_preview,
                        )
                        return True
                    except Exception as e2:
                        logger.error(f"일반 텍스트 전송도 실패: {e2}")
                        return False
                else:
                    logger.error(f"BadRequest: {e}")
                    return False
            except Exception as e:
                logger.error(f"전송 시도 {attempt}/{self.max_retries} 실패: {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay * attempt)

        logger.error("최대 재시도 횟수 초과")
        return False

    @staticmethod
    def _split_message(text: str, max_length: int = 4000) -> list[str]:
        """긴 메시지를 텔레그램 제한에 맞게 분할"""
        if len(text) <= max_length:
            return [text]

        parts = []
        lines = text.split("\n")
        current = ""

        for line in lines:
            if len(current) + len(line) + 1 > max_length:
                if current:
                    parts.append(current)
                current = line
            else:
                current = f"{current}\n{line}" if current else line

        if current:
            parts.append(current)

        return parts if parts else [text[:max_length]]
