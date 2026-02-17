"""
[JS-T002] tests.unit.test_memory_mock
HindsightMemory 단위 테스트 (mock 기반)

version: 1.0.0
created: 2026-02-16
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from jedisos.core.config import HindsightConfig
from jedisos.core.exceptions import HindsightMemoryError
from jedisos.memory.hindsight import HindsightMemory
from jedisos.memory.identity import AgentIdentity
from jedisos.memory.mcp_wrapper import HindsightMCPWrapper


def _make_response(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    """httpx.Response는 동기 메서드이므로 MagicMock 사용."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    return resp


def _make_error_response(status_code: int, message: str) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        message, request=MagicMock(), response=resp
    )
    return resp


@pytest.fixture
def memory():
    config = HindsightConfig(api_url="http://fake:8888", bank_id="test-bank")
    return HindsightMemory(config=config)


class TestRetain:  # [JS-T002.1]
    @pytest.mark.asyncio
    async def test_retain_success(self, memory):
        mock_resp = _make_response(200, {"id": "mem_001"})
        with patch.object(memory._client, "post", new_callable=AsyncMock, return_value=mock_resp):
            result = await memory.retain("Alice는 엔지니어입니다")
            assert result["id"] == "mem_001"

    @pytest.mark.asyncio
    async def test_retain_failure_raises(self, memory):
        mock_resp = _make_error_response(500, "Server Error")
        with (
            patch.object(memory._client, "post", new_callable=AsyncMock, return_value=mock_resp),
            pytest.raises(HindsightMemoryError, match="Retain 실패"),
        ):
            await memory.retain("test")


class TestRecall:  # [JS-T002.2]
    @pytest.mark.asyncio
    async def test_recall_success(self, memory):
        mock_resp = _make_response(200, {"response": "Alice는 Google에서 일합니다."})
        with patch.object(memory._client, "post", new_callable=AsyncMock, return_value=mock_resp):
            result = await memory.recall("Alice는 어디서 일하나요?")
            assert "response" in result

    @pytest.mark.asyncio
    async def test_recall_failure_raises(self, memory):
        mock_resp = _make_error_response(404, "Not Found")
        with (
            patch.object(memory._client, "post", new_callable=AsyncMock, return_value=mock_resp),
            pytest.raises(HindsightMemoryError, match="Recall 실패"),
        ):
            await memory.recall("test")


class TestHealthCheck:  # [JS-T002.3]
    @pytest.mark.asyncio
    async def test_health_check_success(self, memory):
        mock_resp = _make_response(200)
        with patch.object(memory._client, "get", new_callable=AsyncMock, return_value=mock_resp):
            assert await memory.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, memory):
        with patch.object(
            memory._client, "get", side_effect=httpx.ConnectError("Connection refused")
        ):
            assert await memory.health_check() is False


class TestIdentity:  # [JS-T002.4]
    def test_default_identity(self):
        identity = AgentIdentity()
        prompt = identity.to_system_prompt()
        assert prompt.startswith("당신의 정체성:")
        assert "JediSOS" in prompt

    def test_custom_identity(self, tmp_path):
        custom = tmp_path / "IDENTITY.md"
        custom.write_text("# Custom Agent\n커스텀 에이전트입니다.", encoding="utf-8")
        identity = AgentIdentity(identity_path=custom)
        prompt = identity.to_system_prompt()
        assert "커스텀 에이전트" in prompt


class TestMCPWrapper:  # [JS-T002.5]
    @pytest.mark.asyncio
    async def test_mcp_wrapper_get_tools(self, memory):
        wrapper = HindsightMCPWrapper(memory)
        tools = wrapper.get_tools()
        assert len(tools) == 3
        names = {t["name"] for t in tools}
        assert names == {"memory_retain", "memory_recall", "memory_reflect"}

    @pytest.mark.asyncio
    async def test_mcp_wrapper_execute_retain(self, memory):
        wrapper = HindsightMCPWrapper(memory)
        mock_resp = _make_response(200, {"id": "mem_002"})
        with patch.object(memory._client, "post", new_callable=AsyncMock, return_value=mock_resp):
            result = await wrapper.execute("memory_retain", {"content": "test memory"})
            assert result["id"] == "mem_002"

    @pytest.mark.asyncio
    async def test_mcp_wrapper_unknown_tool(self, memory):
        wrapper = HindsightMCPWrapper(memory)
        result = await wrapper.execute("unknown_tool", {})
        assert "error" in result
