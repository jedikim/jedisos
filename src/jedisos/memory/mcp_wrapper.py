"""
[JS-B003] jedisos.memory.mcp_wrapper
메모리 MCP 래퍼 - FastMCP 기반 도구 서버

version: 1.0.0
created: 2026-02-16
modified: 2026-02-16
dependencies: fastmcp>=2.14.5
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from jedisos.memory.zvec_memory import ZvecMemory

logger = structlog.get_logger()


class HindsightMCPWrapper:  # [JS-B003.1]
    """메모리를 MCP 도구로 노출하는 래퍼.

    에이전트가 MCP 프로토콜을 통해 메모리 연산을 호출할 수 있도록 합니다.
    """

    def __init__(self, memory: ZvecMemory) -> None:
        self.memory = memory

    def get_tools(self) -> list[dict[str, Any]]:  # [JS-B003.2]
        """MCP 도구 정의를 반환합니다."""
        return [
            {
                "name": "memory_retain",
                "description": "대화 내용을 메모리에 저장합니다.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "저장할 내용"},
                        "context": {"type": "string", "description": "추가 컨텍스트"},
                    },
                    "required": ["content"],
                },
            },
            {
                "name": "memory_recall",
                "description": "쿼리로 관련 메모리를 검색합니다.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "검색 쿼리"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "memory_reflect",
                "description": "메모리를 통합/정리합니다.",
                "parameters": {"type": "object", "properties": {}},
            },
        ]

    async def execute(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:  # [JS-B003.3]
        """MCP 도구 호출을 실행합니다."""
        handlers = {
            "memory_retain": self._handle_retain,
            "memory_recall": self._handle_recall,
            "memory_reflect": self._handle_reflect,
        }
        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}

        logger.info("mcp_tool_execute", tool=tool_name)
        return await handler(arguments)

    async def _handle_retain(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self.memory.retain(
            content=args["content"],
            context=args.get("context", ""),
        )

    async def _handle_recall(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self.memory.recall(query=args["query"])

    async def _handle_reflect(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self.memory.reflect()
