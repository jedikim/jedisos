"""
[JS-T009] tests.unit.test_channels
텔레그램 채널 어댑터 단위 테스트 (mock 기반)

version: 1.0.0
created: 2026-02-18
note: 디스코드/슬랙은 추후 구현 예정
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jedisos.channels.telegram import TelegramChannel
from jedisos.core.config import HindsightConfig, LLMConfig, SecurityConfig
from jedisos.core.envelope import Envelope
from jedisos.core.exceptions import ChannelError
from jedisos.core.types import ChannelType, EnvelopeState
from jedisos.llm.router import LLMRouter
from jedisos.memory.hindsight import HindsightMemory
from jedisos.security.audit import AuditLogger
from jedisos.security.pdp import PolicyDecisionPoint


@pytest.fixture
def mock_agent():
    """mock ReActAgent."""
    from jedisos.agents.react import ReActAgent

    memory = HindsightMemory(HindsightConfig(api_url="http://fake:8888"))
    llm = LLMRouter(LLMConfig(models=["gpt-5.2"], config_file="nonexistent.yaml"))
    return ReActAgent(memory=memory, llm=llm)


@pytest.fixture
def pdp():
    config = SecurityConfig(blocked_tools=["shell_exec"])
    return PolicyDecisionPoint(config)


@pytest.fixture
def audit():
    return AuditLogger()


@pytest.fixture
def channel(mock_agent, pdp, audit):
    return TelegramChannel(
        token="fake-token-123",
        agent=mock_agent,
        pdp=pdp,
        audit=audit,
    )


def _make_update(user_id: int = 12345, first_name: str = "테스터", text: str = "안녕") -> MagicMock:
    """mock telegram.Update 생성."""
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.first_name = first_name
    update.effective_user.username = "tester"
    update.message.text = text
    update.message.reply_text = AsyncMock()
    return update


class TestTelegramChannelInit:  # [JS-T009.1]
    def test_init_success(self, mock_agent):
        channel = TelegramChannel(token="test-token", agent=mock_agent)
        assert channel.token == "test-token"

    def test_init_no_token_raises(self, mock_agent):
        with pytest.raises(ChannelError, match="TELEGRAM_BOT_TOKEN"):
            TelegramChannel(token="", agent=mock_agent)

    def test_init_with_pdp_and_audit(self, channel):
        assert channel.pdp is not None
        assert channel.audit is not None

    def test_get_channel_info(self, channel):
        info = channel.get_channel_info()
        assert info["type"] == "telegram"
        assert info["has_pdp"] is True
        assert info["has_audit"] is True


class TestEnvelopeCreation:  # [JS-T009.2]
    def test_create_envelope_from_telegram(self, channel):
        """텔레그램 메시지를 올바른 Envelope로 변환."""
        envelope = channel._create_envelope(
            user_id="12345",
            user_name="테스터",
            content="안녕하세요",
        )
        assert envelope.channel == ChannelType.TELEGRAM
        assert envelope.user_id == "12345"
        assert envelope.user_name == "테스터"
        assert envelope.content == "안녕하세요"
        assert envelope.state == EnvelopeState.CREATED
        assert envelope.metadata["platform"] == "telegram"

    def test_envelope_has_uuid7_id(self, channel):
        envelope = channel._create_envelope("1", "user", "test")
        assert len(envelope.id) > 0

    def test_envelope_has_timestamp(self, channel):
        envelope = channel._create_envelope("1", "user", "test")
        assert envelope.created_at is not None


class TestProcessEnvelope:  # [JS-T009.3]
    @pytest.mark.asyncio
    async def test_process_success(self, channel):
        """정상 메시지 처리 플로우."""
        mock_resp = MagicMock()
        mock_resp.model_dump.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "에이전트 답변"}}],
            "model": "gpt-5.2",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }

        with (
            patch.object(channel.agent.memory, "recall", new_callable=AsyncMock, return_value={}),
            patch.object(channel.agent.memory, "retain", new_callable=AsyncMock, return_value={}),
            patch(
                "jedisos.llm.router.litellm.acompletion",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ),
        ):
            envelope = channel._create_envelope("12345", "테스터", "안녕")
            response = await channel._process_envelope(envelope)
            assert isinstance(response, str)
            assert envelope.state == EnvelopeState.COMPLETED

    @pytest.mark.asyncio
    async def test_process_agent_failure(self, channel):
        """에이전트 실행 실패 시 FAILED 상태 + ChannelError."""
        with (
            patch.object(
                channel.agent.memory,
                "recall",
                new_callable=AsyncMock,
                side_effect=Exception("LLM 오류"),
            ),
            patch.object(channel.agent.memory, "retain", new_callable=AsyncMock, return_value={}),
            patch(
                "jedisos.llm.router.litellm.acompletion",
                new_callable=AsyncMock,
                side_effect=Exception("API 오류"),
            ),
        ):
            envelope = channel._create_envelope("12345", "테스터", "테스트")
            with pytest.raises(ChannelError, match="에이전트 처리 실패"):
                await channel._process_envelope(envelope)
            assert envelope.state == EnvelopeState.FAILED

    @pytest.mark.asyncio
    async def test_process_pdp_denied(self):
        """PDP가 차단하면 DENIED 상태."""
        from jedisos.agents.react import ReActAgent

        memory = HindsightMemory(HindsightConfig(api_url="http://fake:8888"))
        llm = LLMRouter(LLMConfig(models=["gpt-5.2"], config_file="nonexistent.yaml"))
        agent = ReActAgent(memory=memory, llm=llm)

        # channel_message를 블랙리스트에 추가
        config = SecurityConfig(blocked_tools=["channel_message"])
        pdp = PolicyDecisionPoint(config)
        audit = AuditLogger()

        ch = TelegramChannel(token="test", agent=agent, pdp=pdp, audit=audit)
        envelope = ch._create_envelope("12345", "테스터", "테스트")
        response = await ch._process_envelope(envelope)

        assert envelope.state == EnvelopeState.DENIED
        assert "거부" in response
        assert audit.get_denied_entries() == []  # PDP 차단은 security_event로 기록
        # security event 기록 확인
        assert audit.entry_count >= 1


class TestHandleMessage:  # [JS-T009.4]
    @pytest.mark.asyncio
    async def test_handle_message_sends_reply(self, channel):
        """메시지 처리 후 reply_text 호출."""
        update = _make_update(text="질문입니다")
        context = MagicMock()

        mock_resp = MagicMock()
        mock_resp.model_dump.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "답변"}}],
            "model": "gpt-5.2",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }

        with (
            patch.object(channel.agent.memory, "recall", new_callable=AsyncMock, return_value={}),
            patch.object(channel.agent.memory, "retain", new_callable=AsyncMock, return_value={}),
            patch(
                "jedisos.llm.router.litellm.acompletion",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ),
        ):
            await channel._handle_message(update, context)
            update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_message_no_user(self, channel):
        """effective_user가 None이면 무시."""
        update = MagicMock()
        update.effective_user = None
        context = MagicMock()

        await channel._handle_message(update, context)
        # 예외 없이 종료


class TestHandleStart:  # [JS-T009.5]
    @pytest.mark.asyncio
    async def test_start_sends_greeting(self, channel):
        update = _make_update()
        context = MagicMock()

        await channel._handle_start(update, context)
        update.message.reply_text.assert_called_once()
        call_text = update.message.reply_text.call_args[0][0]
        assert "JediSOS" in call_text

    @pytest.mark.asyncio
    async def test_start_logs_audit(self, channel):
        update = _make_update()
        context = MagicMock()

        await channel._handle_start(update, context)
        assert channel.audit.entry_count >= 1


class TestHandleHelp:  # [JS-T009.6]
    @pytest.mark.asyncio
    async def test_help_sends_usage(self, channel):
        update = _make_update()
        context = MagicMock()

        await channel._handle_help(update, context)
        update.message.reply_text.assert_called_once()
        call_text = update.message.reply_text.call_args[0][0]
        assert "도움말" in call_text


class TestBuildApp:  # [JS-T009.7]
    def test_build_app_returns_application(self, channel):
        app = channel.build_app()
        assert app is not None
        assert channel._app is not None


class TestEnvelopeStateTransitions:  # [JS-T009.8]
    """텔레그램 메시지 처리 시 Envelope 상태 전환 검증."""

    def test_happy_path_states(self):
        """CREATED → AUTHORIZED → PROCESSING → COMPLETED."""
        envelope = Envelope(
            channel=ChannelType.TELEGRAM,
            user_id="123",
            content="test",
        )
        assert envelope.state == EnvelopeState.CREATED

        envelope.transition(EnvelopeState.AUTHORIZED)
        assert envelope.state == EnvelopeState.AUTHORIZED

        envelope.transition(EnvelopeState.PROCESSING)
        assert envelope.state == EnvelopeState.PROCESSING

        envelope.transition(EnvelopeState.COMPLETED)
        assert envelope.state == EnvelopeState.COMPLETED

    def test_denied_path(self):
        """CREATED → DENIED."""
        envelope = Envelope(
            channel=ChannelType.TELEGRAM,
            user_id="123",
            content="test",
        )
        envelope.transition(EnvelopeState.DENIED)
        assert envelope.state == EnvelopeState.DENIED

    def test_failed_path(self):
        """CREATED → AUTHORIZED → PROCESSING → FAILED."""
        envelope = Envelope(
            channel=ChannelType.TELEGRAM,
            user_id="123",
            content="test",
        )
        envelope.transition(EnvelopeState.AUTHORIZED)
        envelope.transition(EnvelopeState.PROCESSING)
        envelope.transition(EnvelopeState.FAILED)
        assert envelope.state == EnvelopeState.FAILED
