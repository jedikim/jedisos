"""
[JS-D002] jedisos.mcp.client
MCP 클라이언트 매니저 - 외부 MCP 서버 연결 관리

version: 1.0.0
created: 2026-02-17
modified: 2026-02-17
dependencies: fastmcp>=2.14.5,<3.0
"""

from __future__ import annotations

from typing import Any

import structlog
from fastmcp import Client

logger = structlog.get_logger()


class MCPClientManager:  # [JS-D002.1]
    """여러 외부 MCP 서버를 관리하는 클라이언트 매니저.

    Tier 2 MCP 서버(Google Calendar, GitHub 등)의 연결을 관리하고
    에이전트가 외부 도구를 호출할 수 있도록 중개합니다.
    """

    def __init__(self) -> None:
        self._clients: dict[str, Client] = {}
        self._server_configs: dict[str, dict[str, Any]] = {}
        self._connected: set[str] = set()

    async def register_server(  # [JS-D002.2]
        self,
        name: str,
        url: str,
        **kwargs: Any,
    ) -> None:
        """MCP 서버를 등록합니다.

        Args:
            name: 서버 식별자
            url: 서버 URL (예: http://localhost:8001/mcp)
        """
        self._server_configs[name] = {"url": url, **kwargs}
        logger.info("mcp_server_registered", name=name, url=url)

    async def connect(self, name: str) -> bool:  # [JS-D002.3]
        """등록된 MCP 서버에 연결합니다.

        Args:
            name: 서버 식별자

        Returns:
            연결 성공 여부
        """
        if name not in self._server_configs:
            logger.error("mcp_server_not_registered", name=name)
            return False

        if name in self._connected:
            return True

        config = self._server_configs[name]
        try:
            client = Client(config["url"])
            self._clients[name] = client
            self._connected.add(name)
            logger.info("mcp_server_connected", name=name)
            return True
        except Exception as e:
            logger.error("mcp_server_connect_failed", name=name, error=str(e))
            return False

    async def connect_all(self) -> dict[str, bool]:  # [JS-D002.4]
        """등록된 모든 MCP 서버에 연결합니다.

        Returns:
            서버별 연결 성공 여부
        """
        results: dict[str, bool] = {}
        for name in self._server_configs:
            results[name] = await self.connect(name)
        return results

    async def call_tool(  # [JS-D002.5]
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """MCP 서버의 도구를 호출합니다.

        Args:
            server_name: 서버 식별자
            tool_name: 도구 이름
            arguments: 도구 인자

        Returns:
            도구 실행 결과
        """
        if server_name not in self._clients:
            return {"error": f"서버 '{server_name}'에 연결되지 않았습니다."}

        client = self._clients[server_name]
        try:
            async with client:
                result = await client.call_tool(tool_name, arguments or {})

            if hasattr(result, "is_error") and result.is_error:
                error_text = result.content[0].text if result.content else "알 수 없는 오류"
                logger.warning(
                    "mcp_tool_error", server=server_name, tool=tool_name, error=error_text
                )
                return {"error": error_text}

            data = None
            if hasattr(result, "structured_content") and result.structured_content:
                data = result.structured_content
            elif hasattr(result, "data"):
                data = result.data
            elif hasattr(result, "content") and result.content:
                data = result.content[0].text if result.content else None

            logger.info("mcp_tool_called", server=server_name, tool=tool_name)
            return {"success": True, "data": data}

        except Exception as e:
            logger.error("mcp_tool_call_failed", server=server_name, tool=tool_name, error=str(e))
            return {"error": f"도구 호출 실패: {e}"}

    async def list_tools(self, server_name: str) -> list[dict[str, Any]]:  # [JS-D002.6]
        """MCP 서버에서 사용 가능한 도구 목록을 조회합니다."""
        if server_name not in self._clients:
            return []

        client = self._clients[server_name]
        try:
            async with client:
                tools = await client.list_tools()
            return [{"name": t.name, "description": t.description or ""} for t in tools]
        except Exception as e:
            logger.error("mcp_list_tools_failed", server=server_name, error=str(e))
            return []

    async def disconnect(self, name: str) -> None:  # [JS-D002.7]
        """MCP 서버 연결을 해제합니다."""
        self._clients.pop(name, None)
        self._connected.discard(name)
        logger.info("mcp_server_disconnected", name=name)

    async def disconnect_all(self) -> None:
        """모든 MCP 서버 연결을 해제합니다."""
        names = list(self._clients.keys())
        for name in names:
            await self.disconnect(name)

    @property
    def connected_servers(self) -> list[str]:
        """연결된 서버 이름 목록."""
        return list(self._connected)

    @property
    def registered_servers(self) -> list[str]:
        """등록된 서버 이름 목록."""
        return list(self._server_configs.keys())
