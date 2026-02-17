"""
[JS-T008] tests.unit.test_pdp
PDP 정책 엔진 + 감사 로그 단위 테스트

version: 1.0.0
created: 2026-02-17
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jedisos.core.config import SecurityConfig
from jedisos.core.exceptions import SecurityError
from jedisos.security.audit import AuditLogger
from jedisos.security.pdp import PolicyDecisionPoint


@pytest.fixture
def default_config():
    """기본 보안 설정."""
    return SecurityConfig(
        max_requests_per_minute=30,
        allowed_tools=[],
        blocked_tools=["shell_exec", "file_delete"],
    )


@pytest.fixture
def strict_config():
    """엄격한 보안 설정 (화이트리스트)."""
    return SecurityConfig(
        max_requests_per_minute=5,
        allowed_tools=["echo", "memory_recall", "memory_retain"],
        blocked_tools=["shell_exec"],
    )


@pytest.fixture
def pdp(default_config):
    return PolicyDecisionPoint(default_config)


@pytest.fixture
def strict_pdp(strict_config):
    return PolicyDecisionPoint(strict_config)


@pytest.fixture
def audit():
    return AuditLogger(max_entries=100)


class TestPDPBlockedTools:  # [JS-T008.1]
    def test_blocked_tool_denied(self, pdp):
        """블랙리스트 도구는 차단."""
        allowed, reason = pdp.check_tool_access("shell_exec")
        assert allowed is False
        assert "차단 목록" in reason

    def test_blocked_file_delete(self, pdp):
        allowed, _reason = pdp.check_tool_access("file_delete")
        assert allowed is False

    def test_allowed_tool_passes(self, pdp):
        """블랙리스트에 없는 도구는 허용."""
        allowed, reason = pdp.check_tool_access("echo")
        assert allowed is True
        assert reason == "허용"

    def test_memory_tool_passes(self, pdp):
        allowed, _ = pdp.check_tool_access("memory_recall")
        assert allowed is True


class TestPDPAllowedTools:  # [JS-T008.2]
    def test_whitelisted_tool_passes(self, strict_pdp):
        """화이트리스트 도구는 허용."""
        allowed, _ = strict_pdp.check_tool_access("echo")
        assert allowed is True

    def test_non_whitelisted_tool_denied(self, strict_pdp):
        """화이트리스트에 없는 도구는 차단."""
        allowed, reason = strict_pdp.check_tool_access("unknown_tool")
        assert allowed is False
        assert "허용 목록에 없습니다" in reason

    def test_blocked_overrides_allowed(self, strict_pdp):
        """블랙리스트가 화이트리스트보다 우선."""
        allowed, reason = strict_pdp.check_tool_access("shell_exec")
        assert allowed is False
        assert "차단 목록" in reason


class TestPDPRateLimit:  # [JS-T008.3]
    def test_within_rate_limit(self, strict_pdp):
        """속도 제한 내 요청은 허용."""
        for _ in range(5):
            allowed, _ = strict_pdp.check_tool_access("echo", user_id="user1")
            assert allowed is True

    def test_exceed_rate_limit(self, strict_pdp):
        """속도 제한 초과 시 차단."""
        for _ in range(5):
            strict_pdp.check_tool_access("echo", user_id="user1")

        allowed, reason = strict_pdp.check_tool_access("echo", user_id="user1")
        assert allowed is False
        assert "속도 제한" in reason

    def test_different_users_separate_limits(self, strict_pdp):
        """사용자별로 독립적인 속도 제한."""
        for _ in range(5):
            strict_pdp.check_tool_access("echo", user_id="user1")

        # user1은 제한 초과, user2는 아직 여유
        allowed1, _ = strict_pdp.check_tool_access("echo", user_id="user1")
        allowed2, _ = strict_pdp.check_tool_access("echo", user_id="user2")
        assert allowed1 is False
        assert allowed2 is True


class TestPDPEnforce:  # [JS-T008.4]
    def test_enforce_allowed(self, pdp):
        """허용된 도구는 예외 없이 통과."""
        pdp.enforce_tool_access("echo")  # 예외 없음

    def test_enforce_blocked_raises(self, pdp):
        """차단된 도구는 SecurityError 발생."""
        with pytest.raises(SecurityError, match="차단 목록"):
            pdp.enforce_tool_access("shell_exec")


class TestPDPDynamicPolicy:  # [JS-T008.5]
    def test_add_blocked_tool(self, pdp):
        """런타임에 블랙리스트에 도구 추가."""
        allowed, _ = pdp.check_tool_access("dangerous_tool")
        assert allowed is True

        pdp.add_blocked_tool("dangerous_tool")

        allowed, _ = pdp.check_tool_access("dangerous_tool")
        assert allowed is False

    def test_remove_blocked_tool(self, pdp):
        """블랙리스트에서 도구 제거."""
        allowed, _ = pdp.check_tool_access("shell_exec")
        assert allowed is False

        pdp.remove_blocked_tool("shell_exec")

        allowed, _ = pdp.check_tool_access("shell_exec")
        assert allowed is True

    def test_get_policy_summary(self, pdp):
        summary = pdp.get_policy_summary()
        assert "blocked_tools" in summary
        assert "shell_exec" in summary["blocked_tools"]
        assert summary["max_requests_per_minute"] == 30


class TestAuditLogger:  # [JS-T008.6]
    def test_log_tool_call_allowed(self, audit):
        audit.log_tool_call(tool_name="echo", user_id="user1", allowed=True)
        assert audit.entry_count == 1

    def test_log_tool_call_denied(self, audit):
        audit.log_tool_call(tool_name="shell_exec", user_id="user1", allowed=False, reason="차단됨")
        entries = audit.get_denied_entries()
        assert len(entries) == 1
        assert entries[0]["tool"] == "shell_exec"

    def test_log_security_event(self, audit):
        audit.log_security_event("login_attempt", user_id="user1", details={"ip": "127.0.0.1"})
        assert audit.entry_count == 1

    def test_log_agent_action(self, audit):
        audit.log_agent_action("task_completed", agent_name="worker1", user_id="user1")
        assert audit.entry_count == 1

    def test_get_recent(self, audit):
        for i in range(10):
            audit.log_tool_call(tool_name=f"tool_{i}", allowed=True)
        recent = audit.get_recent(5)
        assert len(recent) == 5

    def test_get_by_user(self, audit):
        audit.log_tool_call(tool_name="echo", user_id="alice", allowed=True)
        audit.log_tool_call(tool_name="echo", user_id="bob", allowed=True)
        audit.log_tool_call(tool_name="recall", user_id="alice", allowed=True)

        alice_entries = audit.get_by_user("alice")
        assert len(alice_entries) == 2

    def test_max_entries_limit(self):
        audit = AuditLogger(max_entries=5)
        for i in range(10):
            audit.log_tool_call(tool_name=f"tool_{i}", allowed=True)
        assert audit.entry_count == 5

    def test_clear(self, audit):
        audit.log_tool_call(tool_name="echo", allowed=True)
        audit.clear()
        assert audit.entry_count == 0


class TestAgentWithPDP:  # [JS-T008.7]
    """에이전트가 PDP를 통해 도구 호출을 제어하는지 테스트."""

    @pytest.mark.asyncio
    async def test_agent_blocks_tool_via_pdp(self):
        """PDP가 차단한 도구는 에이전트에서 실행되지 않음."""
        from jedisos.agents.react import ReActAgent
        from jedisos.core.config import HindsightConfig, LLMConfig
        from jedisos.llm.router import LLMRouter
        from jedisos.memory.hindsight import HindsightMemory

        memory = HindsightMemory(HindsightConfig(api_url="http://fake:8888"))
        llm = LLMRouter(LLMConfig(models=["gpt-5.2"], config_file="nonexistent.yaml"))
        config = SecurityConfig(blocked_tools=["dangerous_tool"])
        pdp = PolicyDecisionPoint(config)
        audit = AuditLogger()

        mock_executor = AsyncMock(return_value={"result": "ok"})
        agent = ReActAgent(
            memory=memory,
            llm=llm,
            tool_executor=mock_executor,
            pdp=pdp,
            audit=audit,
        )

        # 차단된 도구 호출
        result = await agent._call_tool("dangerous_tool", {})
        assert "error" in result
        mock_executor.assert_not_called()

        # 감사 로그에 기록
        denied = audit.get_denied_entries()
        assert len(denied) == 1

    @pytest.mark.asyncio
    async def test_agent_allows_tool_via_pdp(self):
        """PDP가 허용한 도구는 정상 실행."""
        from jedisos.agents.react import ReActAgent
        from jedisos.core.config import HindsightConfig, LLMConfig
        from jedisos.llm.router import LLMRouter
        from jedisos.memory.hindsight import HindsightMemory

        memory = HindsightMemory(HindsightConfig(api_url="http://fake:8888"))
        llm = LLMRouter(LLMConfig(models=["gpt-5.2"], config_file="nonexistent.yaml"))
        config = SecurityConfig(blocked_tools=["shell_exec"])
        pdp = PolicyDecisionPoint(config)
        audit = AuditLogger()

        mock_executor = AsyncMock(return_value={"result": "echo result"})
        agent = ReActAgent(
            memory=memory,
            llm=llm,
            tool_executor=mock_executor,
            pdp=pdp,
            audit=audit,
        )

        result = await agent._call_tool("echo", {"message": "test"})
        assert result == {"result": "echo result"}
        mock_executor.assert_called_once()

        # 감사 로그에 허용 기록
        assert audit.entry_count == 1
        assert audit.get_denied_entries() == []

    @pytest.mark.asyncio
    async def test_agent_full_flow_with_pdp(self):
        """PDP + 감사 로그가 포함된 전체 에이전트 플로우."""
        from jedisos.agents.react import ReActAgent
        from jedisos.core.config import HindsightConfig, LLMConfig
        from jedisos.llm.router import LLMRouter
        from jedisos.memory.hindsight import HindsightMemory

        memory = HindsightMemory(HindsightConfig(api_url="http://fake:8888"))
        llm = LLMRouter(LLMConfig(models=["gpt-5.2"], config_file="nonexistent.yaml"))
        config = SecurityConfig(blocked_tools=["shell_exec"])
        pdp = PolicyDecisionPoint(config)
        audit = AuditLogger()

        mock_executor = AsyncMock(return_value={"result": "ok"})
        agent = ReActAgent(
            memory=memory,
            llm=llm,
            tool_executor=mock_executor,
            pdp=pdp,
            audit=audit,
        )

        # 도구 호출이 포함된 LLM 응답
        tool_resp = MagicMock()
        tool_resp.model_dump.return_value = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "echo", "arguments": '{"msg": "hi"}'},
                            }
                        ],
                    }
                }
            ],
            "model": "gpt-5.2",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }
        final_resp = MagicMock()
        final_resp.model_dump.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "답변"}}],
            "model": "gpt-5.2",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }

        call_count = 0

        async def mock_acompletion(**kwargs):
            nonlocal call_count
            call_count += 1
            return tool_resp if call_count == 1 else final_resp

        with (
            patch.object(memory, "recall", new_callable=AsyncMock, return_value={}),
            patch.object(memory, "retain", new_callable=AsyncMock, return_value={}),
            patch("jedisos.llm.router.litellm.acompletion", side_effect=mock_acompletion),
        ):
            result = await agent.run("테스트")
            assert isinstance(result, str)
            assert audit.entry_count >= 1
