"""
[JS-T006] tests.integration.test_agent_memory
에이전트 + 메모리 통합 테스트 (실제 Hindsight 필요)

version: 1.0.0
created: 2026-02-17
dependencies: Hindsight 서버가 localhost:8888에서 실행 중이어야 함
"""

import pytest

from jedisos.agents.react import ReActAgent
from jedisos.agents.supervisor import SupervisorAgent
from jedisos.agents.worker import WorkerAgent
from jedisos.core.config import LLMConfig, MemoryConfig
from jedisos.llm.router import LLMRouter
from jedisos.memory.zvec_memory import ZvecMemory


@pytest.fixture
async def live_memory(tmp_path):
    """실제 ZvecMemory 인스턴스."""
    config = MemoryConfig(data_dir=str(tmp_path / "data"), bank_id="test-agent-integration")
    memory = ZvecMemory(config=config)
    yield memory
    await memory.close()


@pytest.fixture
def llm():
    """LLM 라우터 (실제 API 호출)."""
    config = LLMConfig(config_file="llm_config.yaml")
    return LLMRouter(config=config)


@pytest.mark.integration
class TestAgentMemoryIntegration:  # [JS-T006.1]
    """에이전트가 메모리를 저장하고 이전 대화를 기억하는지 테스트."""

    @pytest.mark.asyncio
    async def test_agent_retains_and_recalls(self, live_memory, llm):
        """에이전트 실행 후 메모리에 대화가 저장되는지 확인."""
        health = await live_memory.health_check()
        if not health:
            pytest.skip("Hindsight 서버가 실행 중이 아닙니다")

        agent = ReActAgent(
            memory=live_memory,
            llm=llm,
            identity_prompt="당신은 JediSOS 테스트 에이전트입니다.",
        )

        result = await agent.run(
            "내 이름은 테스트유저이고 파이썬 개발자야",
            bank_id="test-agent-integration",
        )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_supervisor_with_memory(self, live_memory, llm):
        """슈퍼바이저가 메모리와 함께 동작하는지 확인."""
        health = await live_memory.health_check()
        if not health:
            pytest.skip("Hindsight 서버가 실행 중이 아닙니다")

        main_agent = ReActAgent(memory=live_memory, llm=llm)
        supervisor = SupervisorAgent(main_agent=main_agent)

        result = await supervisor.run(
            "안녕하세요, 슈퍼바이저 통합 테스트입니다",
            bank_id="test-agent-integration",
        )
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_worker_with_memory(self, live_memory, llm):
        """워커 에이전트가 메모리와 함께 동작하는지 확인."""
        health = await live_memory.health_check()
        if not health:
            pytest.skip("Hindsight 서버가 실행 중이 아닙니다")

        worker = WorkerAgent(
            name="test-worker",
            memory=live_memory,
            llm=llm,
            system_prompt="테스트 워커입니다.",
        )

        result = await worker.run(
            "간단한 인사를 해주세요",
            bank_id="test-agent-integration",
        )
        assert isinstance(result, str)
        assert len(result) > 0
