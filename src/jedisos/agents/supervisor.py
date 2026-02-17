"""
[JS-E002] jedisos.agents.supervisor
슈퍼바이저 에이전트 - 워커 에이전트 조율

version: 1.0.0
created: 2026-02-16
modified: 2026-02-17
dependencies: langgraph>=1.0.8
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from jedisos.core.types import AgentRole

if TYPE_CHECKING:
    from jedisos.agents.react import ReActAgent

logger = structlog.get_logger()


class SupervisorAgent:  # [JS-E002.1]
    """멀티에이전트 슈퍼바이저.

    복잡한 작업을 워커 에이전트에 분배하고 결과를 통합합니다.
    """

    def __init__(
        self,
        main_agent: ReActAgent,
        workers: dict[str, ReActAgent] | None = None,
    ) -> None:
        self.main_agent = main_agent
        self.workers = workers or {}
        self.role = AgentRole.SUPERVISOR
        logger.info("supervisor_init", worker_count=len(self.workers))

    def register_worker(self, name: str, worker: ReActAgent) -> None:  # [JS-E002.2]
        """워커 에이전트를 등록합니다."""
        self.workers[name] = worker
        logger.info("worker_registered", name=name)

    async def run(self, user_message: str, bank_id: str = "") -> str:  # [JS-E002.3]
        """슈퍼바이저 실행.

        현재는 메인 에이전트에 위임합니다.
        향후 작업 분배 로직을 추가합니다.
        """
        logger.info("supervisor_run", message_len=len(user_message))
        return await self.main_agent.run(user_message, bank_id=bank_id)

    async def delegate(  # [JS-E002.4]
        self,
        worker_name: str,
        task: str,
        bank_id: str = "",
    ) -> str:
        """특정 워커에게 작업을 위임합니다."""
        worker = self.workers.get(worker_name)
        if not worker:
            return (
                f"워커 '{worker_name}'을 찾을 수 없습니다. 등록된 워커: {list(self.workers.keys())}"
            )

        logger.info("task_delegated", worker=worker_name, task_len=len(task))
        return await worker.run(task, bank_id=bank_id)

    @property
    def worker_names(self) -> list[str]:
        """등록된 워커 이름 목록."""
        return list(self.workers.keys())
