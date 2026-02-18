"""
[JS-F001] jedisos.channels.telegram
텔레그램 봇 채널 어댑터 - python-telegram-bot>=22.6 기반

version: 1.1.0
created: 2026-02-18
modified: 2026-02-18
dependencies: python-telegram-bot>=22.6
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING, Any

import structlog
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from jedisos.core.envelope import Envelope
from jedisos.core.exceptions import ChannelError
from jedisos.core.types import ChannelType, EnvelopeState

if TYPE_CHECKING:
    from telegram import Update

    from jedisos.agents.react import ReActAgent
    from jedisos.security.audit import AuditLogger
    from jedisos.security.pdp import PolicyDecisionPoint

logger = structlog.get_logger()

# 사용자별 대화 히스토리 (최근 20턴)
_MAX_HISTORY = 20
_telegram_history: dict[str, list[dict[str, str]]] = defaultdict(list)


def _md_to_telegram_html(text: str) -> str:  # [JS-F001.10]
    """마크다운 텍스트를 텔레그램 HTML로 변환합니다.

    **bold** → <b>bold</b>, *italic* → <i>italic</i>,
    `code` → <code>code</code>, ```block``` → <pre>block</pre>

    Args:
        text: 마크다운 텍스트

    Returns:
        텔레그램 HTML 포맷 문자열
    """
    # HTML 특수문자 이스케이프 먼저
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # 코드 블록 (```...```)
    text = re.sub(r"```(?:\w*\n)?(.*?)```", r"<pre>\1</pre>", text, flags=re.DOTALL)
    # 인라인 코드 (`...`)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    # 볼드 (**...**)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # 이탤릭 (*...*)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", text)
    return text


class TelegramChannel:  # [JS-F001.1]
    """텔레그램 봇 채널 어댑터.

    메시지 수신 → Envelope 생성 → PDP 검사 → 에이전트 실행 → 응답 전송
    """

    def __init__(
        self,
        token: str,
        agent: ReActAgent,
        pdp: PolicyDecisionPoint | None = None,
        audit: AuditLogger | None = None,
    ) -> None:
        if not token:
            raise ChannelError("TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.")

        self.token = token
        self.agent = agent
        self.pdp = pdp
        self.audit = audit
        self._app: Application | None = None
        logger.info("telegram_channel_init")

    def build_app(self) -> Application:  # [JS-F001.2]
        """텔레그램 봇 애플리케이션을 빌드합니다."""
        builder = Application.builder().token(self.token)
        self._app = builder.build()

        self._app.add_handler(CommandHandler("start", self._handle_start))
        self._app.add_handler(CommandHandler("help", self._handle_help))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

        logger.info("telegram_app_built")
        return self._app

    async def _handle_start(  # [JS-F001.3]
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """/start 명령 처리."""
        user = update.effective_user
        if not user or not update.message:
            return

        logger.info("telegram_start", user_id=str(user.id), user_name=user.first_name)

        if self.audit:
            self.audit.log_agent_action(
                action="channel_start",
                agent_name="telegram",
                user_id=str(user.id),
                details={"user_name": user.first_name},
            )

        await update.message.reply_text(
            f"안녕하세요, {user.first_name}님! JediSOS 개인 AI 비서입니다.\n"
            "메시지를 보내주세요. 무엇이든 도와드리겠습니다."
        )

    async def _handle_help(  # [JS-F001.4]
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """/help 명령 처리."""
        if not update.message:
            return

        await update.message.reply_text(
            "JediSOS 사용법:\n"
            "- 일반 메시지를 보내면 AI가 답변합니다.\n"
            "- /start - 시작 인사\n"
            "- /help - 도움말"
        )

    async def _handle_message(  # [JS-F001.5]
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """텍스트 메시지 처리. Envelope 기반 파이프라인."""
        user = update.effective_user
        if not user or not update.message or not update.message.text:
            return

        user_id = str(user.id)
        user_name = user.first_name or user.username or "Unknown"
        content = update.message.text

        logger.info(
            "telegram_message_received",
            user_id=user_id,
            user_name=user_name,
            text_len=len(content),
        )

        envelope = self._create_envelope(user_id, user_name, content)

        try:
            response = await self._process_envelope(envelope)
            # 대화 히스토리에 추가
            history = _telegram_history[user_id]
            history.append({"role": "user", "content": content})
            history.append({"role": "assistant", "content": response})
            while len(history) > _MAX_HISTORY * 2:
                history.pop(0)
            await update.message.reply_text(_md_to_telegram_html(response), parse_mode="HTML")
        except ChannelError as e:
            logger.error("telegram_processing_failed", user_id=user_id, error=str(e))
            await update.message.reply_text("죄송합니다, 처리 중 오류가 발생했습니다.")

    def _create_envelope(  # [JS-F001.6]
        self,
        user_id: str,
        user_name: str,
        content: str,
    ) -> Envelope:
        """텔레그램 메시지를 Envelope로 변환합니다."""
        return Envelope(
            channel=ChannelType.TELEGRAM,
            user_id=user_id,
            user_name=user_name,
            content=content,
            metadata={"platform": "telegram"},
        )

    async def _process_envelope(self, envelope: Envelope) -> str:  # [JS-F001.7]
        """Envelope 기반 파이프라인: PDP 검사 → 에이전트 실행."""
        # 1. PDP 보안 검사
        if self.pdp:
            allowed, reason = self.pdp.check_tool_access(
                tool_name="channel_message",
                user_id=envelope.user_id,
                channel="telegram",
            )
            if not allowed:
                envelope.transition(EnvelopeState.DENIED)
                envelope.error = reason
                if self.audit:
                    self.audit.log_security_event(
                        "message_denied",
                        user_id=envelope.user_id,
                        details={"reason": reason, "channel": "telegram"},
                    )
                return f"접근이 거부되었습니다: {reason}"

        envelope.transition(EnvelopeState.AUTHORIZED)

        # 2. 에이전트 실행 (대화 히스토리 포함)
        envelope.transition(EnvelopeState.PROCESSING)
        try:
            bank_id = f"telegram-{envelope.user_id}"
            history = _telegram_history.get(envelope.user_id, [])
            response = await self.agent.run(envelope.content, bank_id=bank_id, history=history)
            envelope.response = response
            envelope.transition(EnvelopeState.COMPLETED)

            if self.audit:
                self.audit.log_agent_action(
                    action="message_processed",
                    agent_name="telegram",
                    user_id=envelope.user_id,
                    details={"response_len": len(response)},
                )

            return response
        except Exception as e:
            envelope.transition(EnvelopeState.FAILED)
            envelope.error = str(e)
            logger.error("telegram_agent_failed", user_id=envelope.user_id, error=str(e))
            raise ChannelError(f"에이전트 처리 실패: {e}") from e

    async def run_polling(self) -> None:  # [JS-F001.8]
        """폴링 모드로 봇을 실행합니다."""
        if not self._app:
            self.build_app()

        logger.info("telegram_polling_start")
        assert self._app is not None
        await self._app.run_polling()

    def get_channel_info(self) -> dict[str, Any]:  # [JS-F001.9]
        """채널 정보를 반환합니다."""
        return {
            "type": "telegram",
            "has_pdp": self.pdp is not None,
            "has_audit": self.audit is not None,
        }
