"""
[JS-E003] jedisos.agents.worker
워커 에이전트 - 특화된 작업 수행

version: 1.0.0
created: 2026-02-16
modified: 2026-02-17
dependencies: langgraph>=1.0.8
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from jedisos.agents.react import ReActAgent
from jedisos.core.types import AgentRole

if TYPE_CHECKING:
    from jedisos.llm.router import LLMRouter
    from jedisos.memory.zvec_memory import ZvecMemory

logger = structlog.get_logger()


class WorkerAgent:  # [JS-E003.1]
    """특화된 작업을 수행하는 워커 에이전트.

    ReActAgent를 래핑하여 특정 도메인에 맞는
    시스템 프롬프트와 도구를 설정합니다.
    """

    def __init__(
        self,
        name: str,
        memory: ZvecMemory,
        llm: LLMRouter,
        tools: list[Any] | None = None,
        system_prompt: str = "",
    ) -> None:
        self.name = name
        self.role = AgentRole.WORKER
        self._agent = ReActAgent(
            memory=memory,
            llm=llm,
            tools=tools,
            identity_prompt=system_prompt or f"당신은 '{name}' 전문 워커 에이전트입니다.",
        )
        logger.info("worker_init", name=name)

    async def run(self, task: str, bank_id: str = "") -> str:  # [JS-E003.2]
        """워커 작업 실행."""
        logger.info("worker_run", name=self.name, task_len=len(task))
        return await self._agent.run(task, bank_id=bank_id)
