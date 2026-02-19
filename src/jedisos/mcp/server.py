"""
[JS-D001] jedisos.mcp.server
FastMCP 기반 JediSOS 도구 서버

version: 1.0.0
created: 2026-02-17
modified: 2026-02-17
dependencies: fastmcp>=2.14.5,<3.0
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import structlog
from fastmcp import FastMCP

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from jedisos.memory.zvec_memory import ZvecMemory

logger = structlog.get_logger()


def create_mcp_server(  # [JS-D001.1]
    memory: ZvecMemory | None = None,
    name: str = "JediSOS",
    version: str = "1.0.0",
) -> FastMCP:
    """JediSOS MCP 서버를 생성합니다.

    Args:
        memory: 메모리 인스턴스 (None이면 메모리 도구 비활성화)
        name: 서버 이름
        version: 서버 버전

    Returns:
        설정된 FastMCP 서버 인스턴스
    """

    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        """서버 생명주기 관리."""
        logger.info("mcp_server_starting", name=name)
        yield {"memory": memory}
        logger.info("mcp_server_stopping", name=name)
        if memory:
            await memory.close()

    mcp = FastMCP(
        name=name,
        version=version,
        instructions="JediSOS 개인 AI 비서 도구 서버",
        lifespan=lifespan,
    )

    _register_memory_tools(mcp, memory)
    _register_utility_tools(mcp)

    logger.info("mcp_server_created", name=name, has_memory=memory is not None)
    return mcp


def _register_memory_tools(mcp: FastMCP, memory: ZvecMemory | None) -> None:  # [JS-D001.2]
    """메모리 관련 MCP 도구를 등록합니다."""
    if not memory:
        return

    @mcp.tool(
        name="memory_retain",
        description="대화 내용을 메모리에 저장합니다.",
        tags={"memory", "write"},
    )
    async def memory_retain(
        content: str,
        context: str = "",
        bank_id: str = "",
    ) -> dict[str, Any]:
        """메모리에 내용을 저장합니다."""
        logger.info("mcp_memory_retain", content_len=len(content))
        return await memory.retain(content=content, context=context, bank_id=bank_id or None)

    @mcp.tool(
        name="memory_recall",
        description="쿼리로 관련 메모리를 검색합니다.",
        tags={"memory", "read"},
    )
    async def memory_recall(
        query: str,
        bank_id: str = "",
    ) -> dict[str, Any]:
        """메모리에서 관련 내용을 검색합니다."""
        logger.info("mcp_memory_recall", query_len=len(query))
        return await memory.recall(query=query, bank_id=bank_id or None)

    @mcp.tool(
        name="memory_reflect",
        description="메모리를 통합/정리합니다.",
        tags={"memory", "maintenance"},
    )
    async def memory_reflect(
        bank_id: str = "",
    ) -> dict[str, Any]:
        """메모리 통합/정리를 트리거합니다."""
        logger.info("mcp_memory_reflect")
        return await memory.reflect(bank_id=bank_id or None)


def _register_utility_tools(mcp: FastMCP) -> None:  # [JS-D001.3]
    """유틸리티 MCP 도구를 등록합니다."""

    @mcp.tool(
        name="system_health",
        description="JediSOS 시스템 상태를 확인합니다.",
        tags={"system"},
    )
    async def system_health() -> dict[str, Any]:
        """시스템 헬스체크."""
        return {"status": "ok", "service": "jedisos"}

    @mcp.tool(
        name="echo",
        description="입력 메시지를 그대로 반환합니다. (테스트용)",
        tags={"utility", "test"},
    )
    async def echo(message: str) -> str:
        """에코 도구 (테스트/디버깅용)."""
        return message
