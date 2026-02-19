"""
[JS-D002] jedisos.mcp.client
MCP 클라이언트 매니저 - 외부 MCP 서버 연결 관리

version: 1.1.0
created: 2026-02-17
modified: 2026-02-20
dependencies: fastmcp>=2.14.5,<3.0
"""

from __future__ import annotations

from typing import Any

import structlog
from fastmcp import Client

logger = structlog.get_logger()

# 서버 타입 상수
SERVER_TYPE_REMOTE = "remote"
SERVER_TYPE_SUBPROCESS = "subprocess"


class MCPClientManager:  # [JS-D002.1]
    """여러 외부 MCP 서버를 관리하는 클라이언트 매니저.

    Tier 2 MCP 서버(Google Calendar, GitHub 등)의 연결을 관리하고
    에이전트가 외부 도구를 호출할 수 있도록 중개합니다.

    서버 타입:
        - remote: HTTP URL로 접속 (이미 실행 중인 서버)
        - subprocess: command/args로 프로세스를 직접 실행 (npx, uvx, python 등)
    """

    def __init__(self) -> None:
        self._clients: dict[str, Client] = {}
        self._server_configs: dict[str, dict[str, Any]] = {}
        self._connected: set[str] = set()
        self._subprocess_servers: set[str] = set()  # subprocess로 실행된 서버 추적

    async def register_server(  # [JS-D002.2]
        self,
        name: str,
        url: str = "",
        *,
        server_type: str = SERVER_TYPE_REMOTE,
        command: str = "",
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        """MCP 서버를 등록합니다.

        Args:
            name: 서버 식별자
            url: 서버 URL (remote 타입용, 예: http://localhost:8001/mcp)
            server_type: 서버 타입 ("remote" 또는 "subprocess")
            command: 실행 명령어 (subprocess 타입용, 예: "npx", "uvx", "python")
            args: 명령어 인자 (subprocess 타입용, 예: ["-y", "@mcp/server-fetch"])
            env: 환경변수 (subprocess 타입용)
        """
        self._server_configs[name] = {
            "url": url,
            "server_type": server_type,
            "command": command,
            "args": args or [],
            "env": env or {},
            **kwargs,
        }
        logger.info(
            "mcp_server_registered",
            name=name,
            server_type=server_type,
            url=url or None,
            command=command or None,
        )

    async def connect(self, name: str) -> bool:  # [JS-D002.3]
        """등록된 MCP 서버에 연결합니다.

        remote 타입: Client(url) 생성만 함 (호출 시 async with로 연결)
        subprocess 타입: Client 생성 + __aenter__로 프로세스 실행 (persistent)

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
        server_type = config.get("server_type", SERVER_TYPE_REMOTE)

        try:
            if server_type == SERVER_TYPE_SUBPROCESS:
                client = self._create_subprocess_client(config)
                # subprocess: 프로세스 시작 + 연결 유지
                await client.__aenter__()
                self._subprocess_servers.add(name)
            else:
                client = Client(config["url"])

            self._clients[name] = client
            self._connected.add(name)
            logger.info("mcp_server_connected", name=name, server_type=server_type)
            return True
        except Exception as e:
            logger.error(
                "mcp_server_connect_failed", name=name, server_type=server_type, error=str(e)
            )
            return False

    @staticmethod
    def _create_subprocess_client(config: dict[str, Any]) -> Client:  # [JS-D002.8]
        """subprocess 타입 서버용 FastMCP Client를 생성합니다.

        FastMCP Client는 mcpServers 형식의 config dict를 받습니다.
        서버가 1개일 때 FastMCP는 이름 프리픽스 없이 직접 연결합니다.
        """
        command = config.get("command", "")
        args = config.get("args", [])
        env = config.get("env") or None

        server_entry: dict[str, Any] = {
            "command": command,
            "args": args,
        }
        if env:
            server_entry["env"] = env

        return Client({"mcpServers": {"_subprocess": server_entry}})

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

        remote 타입: 호출마다 async with로 연결/해제
        subprocess 타입: 이미 실행 중인 세션에서 직접 호출

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
            if server_name in self._subprocess_servers:
                # subprocess: persistent 세션으로 직접 호출
                result = await client.call_tool(tool_name, arguments or {})
            else:
                # remote: 호출마다 연결
                async with client:
                    result = await client.call_tool(tool_name, arguments or {})

            return self._parse_tool_result(result, server_name, tool_name)

        except Exception as e:
            logger.error("mcp_tool_call_failed", server=server_name, tool=tool_name, error=str(e))
            return {"error": f"도구 호출 실패: {e}"}

    async def list_tools(self, server_name: str) -> list[dict[str, Any]]:  # [JS-D002.6]
        """MCP 서버에서 사용 가능한 도구 목록을 조회합니다."""
        if server_name not in self._clients:
            return []

        client = self._clients[server_name]
        try:
            if server_name in self._subprocess_servers:
                tools = await client.list_tools()
            else:
                async with client:
                    tools = await client.list_tools()

            return [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": t.inputSchema
                    if hasattr(t, "inputSchema") and t.inputSchema
                    else {"type": "object", "properties": {}},
                }
                for t in tools
            ]
        except Exception as e:
            logger.error("mcp_list_tools_failed", server=server_name, error=str(e))
            return []

    async def disconnect(self, name: str) -> None:  # [JS-D002.7]
        """MCP 서버 연결을 해제합니다.

        subprocess 타입: __aexit__로 프로세스 종료
        """
        client = self._clients.pop(name, None)

        # subprocess 서버: 프로세스 종료
        if name in self._subprocess_servers and client is not None:
            try:
                await client.__aexit__(None, None, None)
            except Exception as e:
                logger.warning("mcp_subprocess_exit_error", name=name, error=str(e))
            self._subprocess_servers.discard(name)

        self._connected.discard(name)
        logger.info("mcp_server_disconnected", name=name)

    async def disconnect_all(self) -> None:
        """모든 MCP 서버 연결을 해제합니다."""
        names = list(self._clients.keys())
        for name in names:
            await self.disconnect(name)

    @staticmethod
    def _parse_tool_result(  # [JS-D002.9]
        result: Any,
        server_name: str,
        tool_name: str,
    ) -> dict[str, Any]:
        """MCP 도구 호출 결과를 파싱합니다."""
        if hasattr(result, "is_error") and result.is_error:
            error_text = result.content[0].text if result.content else "알 수 없는 오류"
            logger.warning("mcp_tool_error", server=server_name, tool=tool_name, error=error_text)
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

    @property
    def connected_servers(self) -> list[str]:
        """연결된 서버 이름 목록."""
        return list(self._connected)

    @property
    def registered_servers(self) -> list[str]:
        """등록된 서버 이름 목록."""
        return list(self._server_configs.keys())

    def get_server_type(self, name: str) -> str:  # [JS-D002.10]
        """서버 타입을 반환합니다."""
        config = self._server_configs.get(name, {})
        return config.get("server_type", SERVER_TYPE_REMOTE)
