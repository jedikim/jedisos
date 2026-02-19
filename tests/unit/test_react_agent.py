"""
[JS-T005] tests.unit.test_react_agent
ReAct 에이전트 + 슈퍼바이저 + 워커 단위 테스트 (mock 기반)

version: 1.0.0
created: 2026-02-17
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jedisos.agents.react import MAX_TOOL_CALLS, AgentState, ReActAgent
from jedisos.agents.supervisor import SupervisorAgent
from jedisos.agents.worker import WorkerAgent
from jedisos.core.config import LLMConfig, MemoryConfig
from jedisos.core.types import AgentRole
from jedisos.memory.zvec_memory import ZvecMemory


def _make_llm_response(content: str = "안녕하세요!") -> MagicMock:
    """mock LLM 응답 생성."""
    response = MagicMock()
    response.model_dump.return_value = {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "model": "gpt-5.2",
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }
    return response


@pytest.fixture
def mock_memory(tmp_path):
    """ZvecMemory with tmp_path."""
    config = MemoryConfig(data_dir=str(tmp_path / "data"), bank_id="test-bank")
    return ZvecMemory(config=config)


@pytest.fixture
def mock_llm():
    """mock LLMRouter."""
    from jedisos.llm.router import LLMRouter

    config = LLMConfig(models=["gpt-5.2"], config_file="nonexistent.yaml")
    return LLMRouter(config=config)


@pytest.fixture
def react_agent(mock_memory, mock_llm):
    """테스트용 ReActAgent."""
    return ReActAgent(
        memory=mock_memory,
        llm=mock_llm,
        tools=[],
        identity_prompt="테스트 에이전트입니다.",
    )


class TestAgentState:  # [JS-T005.1]
    def test_agent_state_fields(self):
        state: AgentState = {
            "messages": [],
            "memory_context": "",
            "bank_id": "test-bank",
            "tool_call_count": 0,
        }
        assert state["messages"] == []
        assert state["bank_id"] == "test-bank"
        assert state["tool_call_count"] == 0


class TestReActAgentInit:  # [JS-T005.2]
    def test_agent_init(self, react_agent):
        assert react_agent.memory is not None
        assert react_agent.llm is not None
        assert react_agent.tools == []
        assert react_agent.identity_prompt == "테스트 에이전트입니다."
        assert react_agent.graph is not None

    def test_agent_init_no_identity(self, mock_memory, mock_llm):
        agent = ReActAgent(memory=mock_memory, llm=mock_llm)
        assert agent.identity_prompt == ""


class TestRecallMemory:  # [JS-T005.3]
    @pytest.mark.asyncio
    async def test_recall_success(self, react_agent):
        """recall 성공 시 memory_context가 설정되는지 확인."""
        state: AgentState = {
            "messages": [MagicMock(type="human", content="안녕하세요")],
            "memory_context": "",
            "bank_id": "test-bank",
            "tool_call_count": 0,
        }
        with patch.object(
            react_agent.memory,
            "recall",
            new_callable=AsyncMock,
            return_value={"response": "기억 내용"},
        ):
            result = await react_agent._recall_memory(state)
            assert result["memory_context"] != ""

    @pytest.mark.asyncio
    async def test_recall_failure_continues(self, react_agent):
        """recall 실패해도 빈 context로 진행."""
        state: AgentState = {
            "messages": [MagicMock(content="안녕하세요")],
            "memory_context": "",
            "bank_id": "test-bank",
            "tool_call_count": 0,
        }
        with patch.object(
            react_agent.memory,
            "recall",
            new_callable=AsyncMock,
            side_effect=Exception("connection error"),
        ):
            result = await react_agent._recall_memory(state)
            assert result["memory_context"] == ""

    @pytest.mark.asyncio
    async def test_recall_with_dict_message(self, react_agent):
        """dict 형태 메시지도 처리."""
        state: AgentState = {
            "messages": [{"role": "user", "content": "테스트"}],
            "memory_context": "",
            "bank_id": "test-bank",
            "tool_call_count": 0,
        }
        with patch.object(
            react_agent.memory, "recall", new_callable=AsyncMock, return_value={"response": "ok"}
        ):
            result = await react_agent._recall_memory(state)
            assert "memory_context" in result


class TestLLMReason:  # [JS-T005.4]
    @pytest.mark.asyncio
    async def test_llm_reason_success(self, react_agent):
        """LLM 추론 정상 동작."""
        mock_resp = _make_llm_response("답변입니다")
        state: AgentState = {
            "messages": [MagicMock(type="user", content="질문")],
            "memory_context": "관련 기억",
            "bank_id": "test-bank",
            "tool_call_count": 0,
        }
        with patch(
            "jedisos.llm.router.litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await react_agent._llm_reason(state)
            assert "messages" in result
            assert len(result["messages"]) == 1

    @pytest.mark.asyncio
    async def test_llm_reason_without_memory_context(self, react_agent):
        """memory_context 없어도 정상 동작."""
        mock_resp = _make_llm_response("답변")
        state: AgentState = {
            "messages": [MagicMock(type="user", content="질문")],
            "memory_context": "",
            "bank_id": "test-bank",
            "tool_call_count": 0,
        }
        with patch(
            "jedisos.llm.router.litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await react_agent._llm_reason(state)
            assert "messages" in result


class TestShouldContinue:  # [JS-T005.5]
    def test_no_tool_calls_returns_retain(self, react_agent):
        """도구 호출 없으면 retain_memory로."""
        state: AgentState = {
            "messages": [MagicMock(tool_calls=None)],
            "memory_context": "",
            "bank_id": "test-bank",
            "tool_call_count": 0,
        }
        assert react_agent._should_continue(state) == "retain_memory"

    def test_with_tool_calls_returns_execute(self, react_agent):
        """도구 호출 있으면 execute_tools로."""
        msg = MagicMock()
        msg.tool_calls = [{"id": "call_1", "function": {"name": "test"}}]
        state: AgentState = {
            "messages": [msg],
            "memory_context": "",
            "bank_id": "test-bank",
            "tool_call_count": 0,
        }
        assert react_agent._should_continue(state) == "execute_tools"

    def test_max_tool_calls_returns_retain(self, react_agent):
        """최대 도구 호출 수 초과 시 retain_memory로."""
        msg = MagicMock()
        msg.tool_calls = [{"id": "call_1"}]
        state: AgentState = {
            "messages": [msg],
            "memory_context": "",
            "bank_id": "test-bank",
            "tool_call_count": MAX_TOOL_CALLS,
        }
        assert react_agent._should_continue(state) == "retain_memory"

    def test_dict_message_with_tool_calls(self, react_agent):
        """dict 메시지의 tool_calls 처리."""
        state: AgentState = {
            "messages": [{"role": "assistant", "tool_calls": [{"id": "call_1"}]}],
            "memory_context": "",
            "bank_id": "test-bank",
            "tool_call_count": 0,
        }
        assert react_agent._should_continue(state) == "execute_tools"

    def test_dict_message_without_tool_calls(self, react_agent):
        """dict 메시지에 tool_calls 없으면 retain."""
        state: AgentState = {
            "messages": [{"role": "assistant", "content": "답변"}],
            "memory_context": "",
            "bank_id": "test-bank",
            "tool_call_count": 0,
        }
        assert react_agent._should_continue(state) == "retain_memory"


class TestExecuteTools:  # [JS-T005.6]
    @pytest.mark.asyncio
    async def test_execute_tools_increments_count(self, react_agent):
        """도구 호출 없는 메시지일 때 카운트만 증가."""
        state: AgentState = {
            "messages": [MagicMock(tool_calls=None)],
            "memory_context": "",
            "bank_id": "test-bank",
            "tool_call_count": 3,
        }
        result = await react_agent._execute_tools(state)
        assert result["tool_call_count"] == 4


class TestRetainMemory:  # [JS-T005.7]
    @pytest.mark.asyncio
    async def test_retain_success(self, react_agent):
        """대화 내용 메모리 저장."""
        state: AgentState = {
            "messages": [
                MagicMock(type="user", content="질문"),
                MagicMock(type="assistant", content="답변"),
            ],
            "memory_context": "",
            "bank_id": "test-bank",
            "tool_call_count": 0,
        }
        with patch.object(
            react_agent.memory, "retain", new_callable=AsyncMock, return_value={"id": "mem_1"}
        ):
            result = await react_agent._retain_memory(state)
            assert result == {}

    @pytest.mark.asyncio
    async def test_retain_failure_continues(self, react_agent):
        """retain 실패해도 에러 없이 진행."""
        state: AgentState = {
            "messages": [MagicMock(type="user", content="질문")],
            "memory_context": "",
            "bank_id": "test-bank",
            "tool_call_count": 0,
        }
        with patch.object(
            react_agent.memory,
            "retain",
            new_callable=AsyncMock,
            side_effect=Exception("retain error"),
        ):
            result = await react_agent._retain_memory(state)
            assert result == {}


class TestReActAgentRun:  # [JS-T005.8]
    @pytest.mark.asyncio
    async def test_run_end_to_end(self, react_agent):
        """전체 에이전트 실행 플로우 테스트."""
        mock_resp = _make_llm_response("에이전트 답변입니다")

        with (
            patch.object(
                react_agent.memory,
                "recall",
                new_callable=AsyncMock,
                return_value={"response": "기억"},
            ),
            patch.object(
                react_agent.memory, "retain", new_callable=AsyncMock, return_value={"id": "m1"}
            ),
            patch(
                "jedisos.llm.router.litellm.acompletion",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ),
        ):
            result = await react_agent.run("안녕하세요")
            assert isinstance(result, str)
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_run_with_bank_id(self, react_agent):
        """bank_id 지정하여 실행."""
        mock_resp = _make_llm_response("뱅크 답변")

        with (
            patch.object(react_agent.memory, "recall", new_callable=AsyncMock, return_value={}),
            patch.object(react_agent.memory, "retain", new_callable=AsyncMock, return_value={}),
            patch(
                "jedisos.llm.router.litellm.acompletion",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ),
        ):
            result = await react_agent.run("테스트", bank_id="custom-bank")
            assert isinstance(result, str)


class TestSupervisorAgent:  # [JS-T005.9]
    @pytest.fixture
    def supervisor(self, react_agent):
        return SupervisorAgent(main_agent=react_agent)

    def test_supervisor_init(self, supervisor):
        assert supervisor.role == AgentRole.SUPERVISOR
        assert supervisor.workers == {}

    def test_register_worker(self, supervisor, react_agent):
        supervisor.register_worker("test_worker", react_agent)
        assert "test_worker" in supervisor.workers
        assert supervisor.worker_names == ["test_worker"]

    @pytest.mark.asyncio
    async def test_supervisor_run(self, supervisor):
        """슈퍼바이저 실행 (메인 에이전트에 위임)."""
        mock_resp = _make_llm_response("슈퍼바이저 답변")
        with (
            patch.object(
                supervisor.main_agent.memory, "recall", new_callable=AsyncMock, return_value={}
            ),
            patch.object(
                supervisor.main_agent.memory, "retain", new_callable=AsyncMock, return_value={}
            ),
            patch(
                "jedisos.llm.router.litellm.acompletion",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ),
        ):
            result = await supervisor.run("슈퍼바이저 테스트")
            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_delegate_to_worker(self, supervisor, react_agent):
        """워커에게 작업 위임."""
        supervisor.register_worker("analyzer", react_agent)
        mock_resp = _make_llm_response("분석 결과")
        with (
            patch.object(react_agent.memory, "recall", new_callable=AsyncMock, return_value={}),
            patch.object(react_agent.memory, "retain", new_callable=AsyncMock, return_value={}),
            patch(
                "jedisos.llm.router.litellm.acompletion",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ),
        ):
            result = await supervisor.delegate("analyzer", "데이터 분석해줘")
            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_delegate_unknown_worker(self, supervisor):
        """존재하지 않는 워커에 위임 시 에러 메시지."""
        result = await supervisor.delegate("nonexistent", "작업")
        assert "찾을 수 없습니다" in result

    def test_worker_names_empty(self, supervisor):
        assert supervisor.worker_names == []


class TestWorkerAgent:  # [JS-T005.10]
    def test_worker_init(self, mock_memory, mock_llm):
        worker = WorkerAgent(name="analyzer", memory=mock_memory, llm=mock_llm)
        assert worker.name == "analyzer"
        assert worker.role == AgentRole.WORKER

    def test_worker_custom_prompt(self, mock_memory, mock_llm):
        worker = WorkerAgent(
            name="coder",
            memory=mock_memory,
            llm=mock_llm,
            system_prompt="코딩 전문 에이전트입니다.",
        )
        assert worker._agent.identity_prompt == "코딩 전문 에이전트입니다."

    def test_worker_default_prompt(self, mock_memory, mock_llm):
        worker = WorkerAgent(name="helper", memory=mock_memory, llm=mock_llm)
        assert "helper" in worker._agent.identity_prompt

    @pytest.mark.asyncio
    async def test_worker_run(self, mock_memory, mock_llm):
        worker = WorkerAgent(name="tester", memory=mock_memory, llm=mock_llm)
        mock_resp = _make_llm_response("워커 답변")
        with (
            patch.object(mock_memory, "recall", new_callable=AsyncMock, return_value={}),
            patch.object(mock_memory, "retain", new_callable=AsyncMock, return_value={}),
            patch(
                "jedisos.llm.router.litellm.acompletion",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ),
        ):
            result = await worker.run("테스트 작업")
            assert isinstance(result, str)
