"""
[JS-T007] tests.unit.test_mcp_tools
MCP 서버 + 클라이언트 + 에이전트 도구 실행 + 런타임 연결 단위 테스트

version: 1.1.0
created: 2026-02-17
modified: 2026-02-20
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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


class TestMCPClientListToolsSchema:  # [JS-T007.7]
    """list_tools()가 inputSchema를 포함하는지 테스트."""

    @pytest.mark.asyncio
    async def test_list_tools_includes_parameters(self, mock_memory):
        """도구 목록에 parameters 필드가 포함되는지 확인."""
        from fastmcp import Client

        server = create_mcp_server(memory=mock_memory)
        manager = MCPClientManager()

        # in-process 서버를 client에 직접 연결
        manager._clients["test"] = Client(server)
        manager._connected.add("test")

        tools = await manager.list_tools("test")
        assert len(tools) > 0
        for tool in tools:
            assert "parameters" in tool
            assert "type" in tool["parameters"]


class TestMCPRuntimeIntegration:  # [JS-T007.8]
    """_register_builtin_tools의 MCP 연동 테스트."""

    @pytest.fixture
    def mock_mcp_manager(self):
        """Mock MCPClientManager."""
        mgr = MagicMock(spec=MCPClientManager)
        mgr.connected_servers = ["test_server"]
        mgr.list_tools = AsyncMock(
            return_value=[
                {
                    "name": "fetch",
                    "description": "Fetch a URL",
                    "parameters": {
                        "type": "object",
                        "properties": {"url": {"type": "string"}},
                        "required": ["url"],
                    },
                },
            ]
        )
        mgr.call_tool = AsyncMock(return_value={"success": True, "data": "fetched"})
        mgr.register_server = AsyncMock()
        mgr.connect = AsyncMock(return_value=True)
        return mgr

    @pytest.mark.asyncio
    async def test_mcp_tools_included_in_defs(self, mock_memory, mock_llm, mock_mcp_manager):
        """MCP 도구가 tool definitions에 포함되는지 확인."""
        from jedisos.web.app import _register_builtin_tools

        wrapped_tools, _ = await _register_builtin_tools(mock_memory, mock_llm, mock_mcp_manager)
        tool_names = [t.to_dict()["function"]["name"] for t in wrapped_tools]
        assert "mcp_test_server_fetch" in tool_names

    @pytest.mark.asyncio
    async def test_mcp_tool_routing(self, mock_memory, mock_llm, mock_mcp_manager):
        """tool_executor가 MCP 도구를 올바르게 라우팅하는지 확인."""
        from jedisos.web.app import _register_builtin_tools

        _, tool_executor = await _register_builtin_tools(mock_memory, mock_llm, mock_mcp_manager)
        result = await tool_executor("mcp_test_server_fetch", {"url": "http://example.com"})
        assert result == {"success": True, "data": "fetched"}
        mock_mcp_manager.call_tool.assert_called_once_with(
            "test_server", "fetch", {"url": "http://example.com"}
        )

    @pytest.mark.asyncio
    async def test_mcp_tool_routing_error(self, mock_memory, mock_llm, mock_mcp_manager):
        """MCP 도구 호출 실패 시 에러 반환."""
        mock_mcp_manager.call_tool = AsyncMock(side_effect=Exception("connection refused"))

        from jedisos.web.app import _register_builtin_tools

        _, tool_executor = await _register_builtin_tools(mock_memory, mock_llm, mock_mcp_manager)
        result = await tool_executor("mcp_test_server_fetch", {"url": "http://fail.com"})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_add_mcp_server_tool(self, mock_memory, mock_llm, mock_mcp_manager, tmp_path):
        """add_mcp_server 내장 도구가 서버를 등록하는지 확인."""
        from jedisos.web.app import _register_builtin_tools

        # MCP config 경로를 tmp_path로 설정
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "mcp_servers.json"
        config_file.write_text(json.dumps({"servers": []}))

        with patch("jedisos.web.api.mcp._MCP_CONFIG_PATH", config_file):
            _, tool_executor = await _register_builtin_tools(
                mock_memory, mock_llm, mock_mcp_manager
            )
            result = await tool_executor(
                "add_mcp_server",
                {"name": "new_srv", "url": "http://localhost:9000/mcp", "description": "Test"},
            )

        assert result["status"] == "registered"
        assert result["connected"] is True
        assert result["name"] == "new_srv"
        mock_mcp_manager.register_server.assert_called_with(
            "new_srv",
            url="http://localhost:9000/mcp",
            server_type="remote",
            command="",
            args=[],
            env={},
        )
        mock_mcp_manager.connect.assert_called_with("new_srv")

    @pytest.mark.asyncio
    async def test_add_mcp_server_duplicate(
        self, mock_memory, mock_llm, mock_mcp_manager, tmp_path
    ):
        """이미 등록된 서버를 추가하면 에러 반환."""
        from jedisos.web.app import _register_builtin_tools

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "mcp_servers.json"
        config_file.write_text(
            json.dumps({"servers": [{"name": "existing", "url": "http://x", "enabled": True}]})
        )

        with patch("jedisos.web.api.mcp._MCP_CONFIG_PATH", config_file):
            _, tool_executor = await _register_builtin_tools(
                mock_memory, mock_llm, mock_mcp_manager
            )
            result = await tool_executor("add_mcp_server", {"name": "existing", "url": "http://y"})

        assert "error" in result

    @pytest.mark.asyncio
    async def test_add_mcp_server_missing_name(self, mock_memory, mock_llm, mock_mcp_manager):
        """이름 누락 시 에러 반환."""
        from jedisos.web.app import _register_builtin_tools

        _, tool_executor = await _register_builtin_tools(mock_memory, mock_llm, mock_mcp_manager)
        result = await tool_executor("add_mcp_server", {"name": "", "url": "http://x"})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_add_mcp_server_remote_missing_url(self, mock_memory, mock_llm, mock_mcp_manager):
        """remote 타입에서 URL 누락 시 에러 반환."""
        from jedisos.web.app import _register_builtin_tools

        _, tool_executor = await _register_builtin_tools(mock_memory, mock_llm, mock_mcp_manager)
        result = await tool_executor(
            "add_mcp_server", {"name": "test", "server_type": "remote", "url": ""}
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_add_mcp_server_subprocess(
        self, mock_memory, mock_llm, mock_mcp_manager, tmp_path
    ):
        """subprocess 타입으로 MCP 서버를 등록+연결하는지 확인."""
        from jedisos.web.app import _register_builtin_tools

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "mcp_servers.json"
        config_file.write_text(json.dumps({"servers": []}))

        with patch("jedisos.web.api.mcp._MCP_CONFIG_PATH", config_file):
            _, tool_executor = await _register_builtin_tools(
                mock_memory, mock_llm, mock_mcp_manager
            )
            result = await tool_executor(
                "add_mcp_server",
                {
                    "name": "fetch_srv",
                    "server_type": "subprocess",
                    "command": "npx",
                    "args": ["-y", "@mcp/server-fetch"],
                    "description": "Fetch server",
                },
            )

        assert result["status"] == "registered"
        assert result["connected"] is True
        mock_mcp_manager.register_server.assert_called_with(
            "fetch_srv",
            url="",
            server_type="subprocess",
            command="npx",
            args=["-y", "@mcp/server-fetch"],
            env={},
        )

        # config에 저장 확인
        saved = json.loads(config_file.read_text())
        srv = saved["servers"][0]
        assert srv["server_type"] == "subprocess"
        assert srv["command"] == "npx"

    @pytest.mark.asyncio
    async def test_add_mcp_server_subprocess_missing_command(
        self, mock_memory, mock_llm, mock_mcp_manager
    ):
        """subprocess 타입에서 command 누락 시 에러 반환."""
        from jedisos.web.app import _register_builtin_tools

        _, tool_executor = await _register_builtin_tools(mock_memory, mock_llm, mock_mcp_manager)
        result = await tool_executor(
            "add_mcp_server", {"name": "test", "server_type": "subprocess", "command": ""}
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_no_mcp_manager_returns_only_builtin(self, mock_memory, mock_llm):
        """mcp_manager=None이면 MCP 도구가 없어야 함."""
        from jedisos.web.app import _register_builtin_tools

        wrapped_tools, _ = await _register_builtin_tools(mock_memory, mock_llm, None)
        tool_names = [t.to_dict()["function"]["name"] for t in wrapped_tools]
        assert not any(n.startswith("mcp_") for n in tool_names)
        assert "add_mcp_server" in tool_names  # 내장 도구는 항상 존재


class TestMCPSubprocessClient:  # [JS-T007.9]
    """MCPClientManager subprocess 서버 라이프사이클 테스트."""

    @pytest.fixture
    def manager(self):
        return MCPClientManager()

    @pytest.mark.asyncio
    async def test_register_subprocess_server(self, manager):
        """subprocess 서버 등록."""
        await manager.register_server(
            "fetch",
            server_type="subprocess",
            command="npx",
            args=["-y", "@mcp/server-fetch"],
        )
        assert "fetch" in manager.registered_servers
        assert manager.get_server_type("fetch") == "subprocess"

    @pytest.mark.asyncio
    async def test_register_remote_server_default(self, manager):
        """기본 타입은 remote."""
        await manager.register_server("test", url="http://localhost:8001/mcp")
        assert manager.get_server_type("test") == "remote"

    @pytest.mark.asyncio
    async def test_subprocess_connect_calls_aenter(self, manager):
        """subprocess connect가 Client.__aenter__를 호출하는지 확인."""
        await manager.register_server(
            "test_sub",
            server_type="subprocess",
            command="echo",
            args=["hello"],
        )

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "jedisos.mcp.client.MCPClientManager._create_subprocess_client",
            return_value=mock_client,
        ):
            result = await manager.connect("test_sub")

        assert result is True
        assert "test_sub" in manager.connected_servers
        mock_client.__aenter__.assert_called_once()

    @pytest.mark.asyncio
    async def test_subprocess_disconnect_calls_aexit(self, manager):
        """subprocess disconnect가 Client.__aexit__를 호출하는지 확인."""
        mock_client = MagicMock()
        mock_client.__aexit__ = AsyncMock(return_value=None)

        manager._clients["test_sub"] = mock_client
        manager._connected.add("test_sub")
        manager._subprocess_servers.add("test_sub")

        await manager.disconnect("test_sub")

        mock_client.__aexit__.assert_called_once_with(None, None, None)
        assert "test_sub" not in manager.connected_servers

    @pytest.mark.asyncio
    async def test_subprocess_call_tool_direct(self, manager):
        """subprocess 서버는 async with 없이 직접 call_tool."""
        mock_result = MagicMock(spec=[])  # spec=[]로 자동 속성 생성 방지
        mock_result.is_error = False
        mock_result.content = [MagicMock(text="result data")]

        mock_client = MagicMock()
        mock_client.call_tool = AsyncMock(return_value=mock_result)

        manager._clients["sub_srv"] = mock_client
        manager._connected.add("sub_srv")
        manager._subprocess_servers.add("sub_srv")

        result = await manager.call_tool("sub_srv", "echo", {"message": "hi"})
        assert result["success"] is True
        assert result["data"] == "result data"
        # async with가 아닌 직접 호출이므로 __aenter__는 호출되지 않아야 함
        mock_client.__aenter__ = MagicMock()
        mock_client.__aenter__.assert_not_called()

    @pytest.mark.asyncio
    async def test_subprocess_list_tools_direct(self, manager):
        """subprocess 서버는 async with 없이 직접 list_tools."""
        mock_tool = MagicMock()
        mock_tool.name = "echo"
        mock_tool.description = "Echo a message"
        mock_tool.inputSchema = {"type": "object", "properties": {"message": {"type": "string"}}}

        mock_client = MagicMock()
        mock_client.list_tools = AsyncMock(return_value=[mock_tool])

        manager._clients["sub_srv"] = mock_client
        manager._connected.add("sub_srv")
        manager._subprocess_servers.add("sub_srv")

        tools = await manager.list_tools("sub_srv")
        assert len(tools) == 1
        assert tools[0]["name"] == "echo"
        assert tools[0]["parameters"]["type"] == "object"

    @pytest.mark.asyncio
    async def test_create_subprocess_client(self):
        """_create_subprocess_client가 올바른 config로 Client를 생성하는지."""
        config = {
            "command": "npx",
            "args": ["-y", "@mcp/server-fetch"],
            "env": {"API_KEY": "test123"},
        }
        client = MCPClientManager._create_subprocess_client(config)
        from fastmcp import Client as _Client

        assert isinstance(client, _Client)


class TestMCPRegistrySearch:  # [JS-T007.10]
    """MCP 서버 검색 기능 테스트."""

    @pytest.mark.asyncio
    async def test_search_curated_by_name(self):
        """큐레이티드 리스트에서 이름으로 검색."""
        from jedisos.mcp.registry import search_curated

        results = await search_curated("fetch")
        assert len(results) >= 1
        assert any(r["name"] == "fetch" for r in results)

    @pytest.mark.asyncio
    async def test_search_curated_by_tag(self):
        """큐레이티드 리스트에서 태그로 검색."""
        from jedisos.mcp.registry import search_curated

        results = await search_curated("database")
        assert len(results) >= 1
        names = [r["name"] for r in results]
        assert "sqlite" in names or "postgres" in names

    @pytest.mark.asyncio
    async def test_search_curated_no_match(self):
        """큐레이티드에 없는 검색어는 빈 결과."""
        from jedisos.mcp.registry import search_curated

        results = await search_curated("xyznonexistent123")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_curated_has_command(self):
        """큐레이티드 결과에 command/args가 포함되어 있어 바로 실행 가능."""
        from jedisos.mcp.registry import search_curated

        results = await search_curated("github")
        assert len(results) >= 1
        srv = results[0]
        assert "command" in srv
        assert "args" in srv
        assert srv["command"] in ("npx", "uvx", "python")

    @pytest.mark.asyncio
    async def test_search_npm_mock(self):
        """npm 검색 (mock)."""
        from jedisos.mcp.registry import search_npm

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "objects": [
                {
                    "package": {
                        "name": "@modelcontextprotocol/server-weather",
                        "description": "Weather MCP server",
                        "version": "1.0.0",
                        "keywords": ["mcp", "weather"],
                        "links": {"npm": "https://npmjs.com/package/@mcp/server-weather"},
                    }
                }
            ]
        }

        with patch("jedisos.mcp.registry.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            results = await search_npm("weather")

        assert len(results) == 1
        assert results[0]["name"] == "server-weather"
        assert results[0]["command"] == "npx"
        assert results[0]["source"] == "npm"

    @pytest.mark.asyncio
    async def test_search_npm_error_returns_empty(self):
        """npm API 오류 시 빈 결과 반환 (에러 아님)."""
        from jedisos.mcp.registry import search_npm

        with patch("jedisos.mcp.registry.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            results = await search_npm("weather")

        assert results == []

    @pytest.mark.asyncio
    async def test_search_all_registry(self):
        """search_all(source='registry')가 통합 결과를 반환."""
        from jedisos.mcp.registry import search_all

        with (
            patch("jedisos.mcp.registry.search_npm", new_callable=AsyncMock, return_value=[]),
            patch("jedisos.mcp.registry.search_pypi", new_callable=AsyncMock, return_value=[]),
        ):
            result = await search_all("fetch", source="registry")

        assert "curated" in result
        assert "npm" in result
        assert "pypi" in result
        assert "total" in result
        assert len(result["curated"]) >= 1  # fetch는 큐레이티드에 있음

    @pytest.mark.asyncio
    async def test_search_all_mcp_so(self):
        """search_all(source='mcp_so')가 mcp.so 결과를 반환."""
        from jedisos.mcp.registry import search_all

        mock_results = [{"name": "weather-srv", "source": "mcp.so"}]
        with patch(
            "jedisos.mcp.registry.search_mcp_so",
            new_callable=AsyncMock,
            return_value=mock_results,
        ):
            result = await search_all("weather", source="mcp_so")

        assert result["source"] == "mcp.so"
        assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_search_tool_in_builtin_tools(self, mock_memory, mock_llm):
        """search_mcp_servers가 내장 도구에 포함되어 있는지 확인."""
        from jedisos.web.app import _register_builtin_tools

        wrapped_tools, _ = await _register_builtin_tools(mock_memory, mock_llm, None)
        tool_names = [t.to_dict()["function"]["name"] for t in wrapped_tools]
        assert "search_mcp_servers" in tool_names

    @pytest.mark.asyncio
    async def test_search_tool_executor(self, mock_memory, mock_llm):
        """tool_executor에서 search_mcp_servers 호출."""
        from jedisos.web.app import _register_builtin_tools

        _, tool_executor = await _register_builtin_tools(mock_memory, mock_llm, None)

        with (
            patch("jedisos.mcp.registry.search_npm", new_callable=AsyncMock, return_value=[]),
            patch("jedisos.mcp.registry.search_pypi", new_callable=AsyncMock, return_value=[]),
        ):
            result = await tool_executor("search_mcp_servers", {"query": "fetch"})

        assert "curated" in result
        assert result["total"] >= 1

    @pytest.mark.asyncio
    async def test_search_tool_empty_query(self, mock_memory, mock_llm):
        """빈 검색어는 에러 반환."""
        from jedisos.web.app import _register_builtin_tools

        _, tool_executor = await _register_builtin_tools(mock_memory, mock_llm, None)
        result = await tool_executor("search_mcp_servers", {"query": ""})
        assert "error" in result
