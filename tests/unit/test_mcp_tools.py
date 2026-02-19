"""
[JS-T007] tests.unit.test_mcp_tools
MCP 서버 + 클라이언트 + 에이전트 도구 실행 단위 테스트

version: 1.0.0
created: 2026-02-17
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jedisos.core.config import LLMConfig, MemoryConfig
from jedisos.llm.router import LLMRouter
from jedisos.mcp.client import MCPClientManager
from jedisos.mcp.server import create_mcp_server
from jedisos.memory.zvec_memory import ZvecMemory


def _make_llm_response(content: str = "답변", tool_calls: list | None = None) -> MagicMock:
    """mock LLM 응답 생성."""
    response = MagicMock()
    msg: dict = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    response.model_dump.return_value = {
        "choices": [{"message": msg}],
        "model": "gpt-5.2",
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }
    return response


@pytest.fixture
def mock_memory(tmp_path):
    config = MemoryConfig(data_dir=str(tmp_path / "data"), bank_id="test-bank")
    return ZvecMemory(config=config)


@pytest.fixture
def mock_llm():
    config = LLMConfig(models=["gpt-5.2"], config_file="nonexistent.yaml")
    return LLMRouter(config=config)


class TestMCPServerCreation:  # [JS-T007.1]
    def test_create_server_with_memory(self, mock_memory):
        server = create_mcp_server(memory=mock_memory, name="TestServer")
        assert server is not None

    def test_create_server_without_memory(self):
        server = create_mcp_server(memory=None, name="NoMemoryServer")
        assert server is not None

    def test_create_server_custom_version(self, mock_memory):
        server = create_mcp_server(memory=mock_memory, version="2.0.0")
        assert server is not None


class TestMCPServerTools:  # [JS-T007.2]
    @pytest.mark.asyncio
    async def test_server_has_memory_tools(self, mock_memory):
        """메모리 도구가 등록되었는지 확인."""
        from fastmcp import Client

        server = create_mcp_server(memory=mock_memory)
        async with Client(server) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}
            assert "memory_retain" in tool_names
            assert "memory_recall" in tool_names
            assert "memory_reflect" in tool_names

    @pytest.mark.asyncio
    async def test_server_has_utility_tools(self, mock_memory):
        """유틸리티 도구가 등록되었는지 확인."""
        from fastmcp import Client

        server = create_mcp_server(memory=mock_memory)
        async with Client(server) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}
            assert "system_health" in tool_names
            assert "echo" in tool_names

    @pytest.mark.asyncio
    async def test_echo_tool(self, mock_memory):
        """echo 도구 호출 테스트."""
        from fastmcp import Client

        server = create_mcp_server(memory=mock_memory)
        async with Client(server) as client:
            result = await client.call_tool("echo", {"message": "테스트 메시지"})
            assert not result.is_error

    @pytest.mark.asyncio
    async def test_system_health_tool(self, mock_memory):
        """system_health 도구 호출 테스트."""
        from fastmcp import Client

        server = create_mcp_server(memory=mock_memory)
        async with Client(server) as client:
            result = await client.call_tool("system_health", {})
            assert not result.is_error

    @pytest.mark.asyncio
    async def test_server_without_memory_has_no_memory_tools(self):
        """메모리 없이 생성 시 메모리 도구가 없는지 확인."""
        from fastmcp import Client

        server = create_mcp_server(memory=None)
        async with Client(server) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}
            assert "memory_retain" not in tool_names
            assert "system_health" in tool_names


class TestMCPClientManager:  # [JS-T007.3]
    @pytest.fixture
    def manager(self):
        return MCPClientManager()

    def test_init_empty(self, manager):
        assert manager.connected_servers == []
        assert manager.registered_servers == []

    @pytest.mark.asyncio
    async def test_register_server(self, manager):
        await manager.register_server("test", "http://localhost:8001/mcp")
        assert "test" in manager.registered_servers

    @pytest.mark.asyncio
    async def test_connect_unregistered_fails(self, manager):
        result = await manager.connect("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_call_tool_disconnected(self, manager):
        result = await manager.call_tool("nonexistent", "echo", {"message": "test"})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_disconnect_server(self, manager):
        await manager.register_server("test", "http://localhost:8001/mcp")
        await manager.disconnect("test")
        assert "test" not in manager.connected_servers

    @pytest.mark.asyncio
    async def test_disconnect_all(self, manager):
        await manager.register_server("s1", "http://localhost:8001/mcp")
        await manager.register_server("s2", "http://localhost:8002/mcp")
        await manager.disconnect_all()
        assert manager.connected_servers == []

    @pytest.mark.asyncio
    async def test_list_tools_disconnected(self, manager):
        result = await manager.list_tools("nonexistent")
        assert result == []


class TestMCPClientWithServer:  # [JS-T007.4]
    """In-process 클라이언트로 서버와 통신 테스트."""

    @pytest.mark.asyncio
    async def test_client_calls_server_tool(self, mock_memory):
        """클라이언트가 서버의 도구를 호출할 수 있는지 테스트."""
        from fastmcp import Client

        server = create_mcp_server(memory=mock_memory)

        async with Client(server) as client:
            result = await client.call_tool("echo", {"message": "hello"})
            assert not result.is_error

    @pytest.mark.asyncio
    async def test_client_list_tools(self, mock_memory):
        """클라이언트가 서버의 도구 목록을 조회할 수 있는지 테스트."""
        from fastmcp import Client

        server = create_mcp_server(memory=mock_memory)

        async with Client(server) as client:
            tools = await client.list_tools()
            assert (
                len(tools) >= 5
            )  # memory_retain, memory_recall, memory_reflect, system_health, echo


class TestAgentToolExecution:  # [JS-T007.5]
    """에이전트가 MCP 도구를 호출하는 플로우 테스트."""

    @pytest.mark.asyncio
    async def test_agent_with_tool_executor(self, mock_memory, mock_llm):
        """tool_executor를 통해 도구가 실행되는지 테스트."""
        from jedisos.agents.react import ReActAgent

        mock_executor = AsyncMock(return_value={"result": "도구 실행 결과"})
        agent = ReActAgent(
            memory=mock_memory,
            llm=mock_llm,
            tool_executor=mock_executor,
        )

        # 도구 호출이 포함된 LLM 응답
        tool_call_response = _make_llm_response(
            content="",
            tool_calls=[
                {
                    "id": "call_001",
                    "type": "function",
                    "function": {
                        "name": "echo",
                        "arguments": '{"message": "test"}',
                    },
                }
            ],
        )
        # 도구 결과를 받은 후 최종 응답
        final_response = _make_llm_response("최종 에이전트 답변")

        call_count = 0

        async def mock_acompletion(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return tool_call_response
            return final_response

        with (
            patch.object(mock_memory, "recall", new_callable=AsyncMock, return_value={}),
            patch.object(mock_memory, "retain", new_callable=AsyncMock, return_value={}),
            patch("jedisos.llm.router.litellm.acompletion", side_effect=mock_acompletion),
        ):
            result = await agent.run("도구를 사용해서 답해줘")
            assert isinstance(result, str)
            mock_executor.assert_called_once_with("echo", {"message": "test"})

    @pytest.mark.asyncio
    async def test_agent_without_tool_executor(self, mock_memory, mock_llm):
        """tool_executor 없이 도구 호출 시 에러 반환."""
        from jedisos.agents.react import ReActAgent

        agent = ReActAgent(memory=mock_memory, llm=mock_llm)

        tool_call_response = _make_llm_response(
            content="",
            tool_calls=[
                {
                    "id": "call_002",
                    "type": "function",
                    "function": {
                        "name": "unknown_tool",
                        "arguments": "{}",
                    },
                }
            ],
        )
        final_response = _make_llm_response("에러 처리 후 답변")

        call_count = 0

        async def mock_acompletion(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return tool_call_response
            return final_response

        with (
            patch.object(mock_memory, "recall", new_callable=AsyncMock, return_value={}),
            patch.object(mock_memory, "retain", new_callable=AsyncMock, return_value={}),
            patch("jedisos.llm.router.litellm.acompletion", side_effect=mock_acompletion),
        ):
            result = await agent.run("도구 테스트")
            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_agent_tool_executor_error(self, mock_memory, mock_llm):
        """tool_executor 예외 발생 시 에러 처리."""
        from jedisos.agents.react import ReActAgent

        mock_executor = AsyncMock(side_effect=Exception("도구 오류"))
        agent = ReActAgent(
            memory=mock_memory,
            llm=mock_llm,
            tool_executor=mock_executor,
        )

        tool_call_response = _make_llm_response(
            content="",
            tool_calls=[
                {
                    "id": "call_003",
                    "type": "function",
                    "function": {
                        "name": "failing_tool",
                        "arguments": "{}",
                    },
                }
            ],
        )
        final_response = _make_llm_response("오류 후 답변")

        call_count = 0

        async def mock_acompletion(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return tool_call_response
            return final_response

        with (
            patch.object(mock_memory, "recall", new_callable=AsyncMock, return_value={}),
            patch.object(mock_memory, "retain", new_callable=AsyncMock, return_value={}),
            patch("jedisos.llm.router.litellm.acompletion", side_effect=mock_acompletion),
        ):
            result = await agent.run("실패하는 도구 테스트")
            assert isinstance(result, str)


class TestMCPMemoryToolExecution:  # [JS-T007.6]
    """MCP 메모리 도구가 에이전트에서 동작하는 통합 테스트."""

    @pytest.mark.asyncio
    async def test_mcp_memory_tools_via_wrapper(self, mock_memory):
        """HindsightMCPWrapper를 통해 메모리 도구가 동작하는지 확인."""
        from jedisos.memory.mcp_wrapper import HindsightMCPWrapper

        wrapper = HindsightMCPWrapper(mock_memory)

        retain_result = {"status": "retained", "bank_id": "test-bank", "content_length": 7}

        with patch.object(
            mock_memory, "retain", new_callable=AsyncMock, return_value=retain_result
        ):
            result = await wrapper.execute("memory_retain", {"content": "테스트 저장"})
            assert result["status"] == "retained"

    @pytest.mark.asyncio
    async def test_agent_with_mcp_wrapper_executor(self, mock_memory, mock_llm):
        """에이전트가 MCP wrapper를 tool_executor로 사용."""
        from jedisos.agents.react import ReActAgent
        from jedisos.memory.mcp_wrapper import HindsightMCPWrapper

        wrapper = HindsightMCPWrapper(mock_memory)

        agent = ReActAgent(
            memory=mock_memory,
            llm=mock_llm,
            tool_executor=wrapper.execute,
        )

        tool_call_response = _make_llm_response(
            content="",
            tool_calls=[
                {
                    "id": "call_mem_1",
                    "type": "function",
                    "function": {
                        "name": "memory_recall",
                        "arguments": '{"query": "이전 대화"}',
                    },
                }
            ],
        )
        final_response = _make_llm_response("메모리 기반 답변")

        call_count = 0

        async def mock_acompletion(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return tool_call_response
            return final_response

        recall_result = {
            "context": "이전에 파이썬 개발자라고 했습니다",
            "memories": [],
            "query": "이전 대화",
            "bank_id": "test-bank",
        }

        with (
            patch.object(mock_memory, "recall", new_callable=AsyncMock, return_value=recall_result),
            patch.object(mock_memory, "retain", new_callable=AsyncMock, return_value={}),
            patch("jedisos.llm.router.litellm.acompletion", side_effect=mock_acompletion),
        ):
            result = await agent.run("이전에 뭐라고 했지?")
            assert isinstance(result, str)
