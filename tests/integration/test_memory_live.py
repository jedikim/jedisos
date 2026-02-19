"""
[JS-T003] tests.integration.test_memory_live
ZvecMemory 실제 연동 테스트

version: 1.1.0
created: 2026-02-16
modified: 2026-02-19
"""

import pytest

from jedisos.core.config import MemoryConfig
from jedisos.memory.zvec_memory import ZvecMemory


@pytest.fixture
async def live_memory(tmp_path):
    config = MemoryConfig(data_dir=str(tmp_path / "data"), bank_id="test-live")
    mem = ZvecMemory(config=config)
    yield mem
    await mem.close()


@pytest.mark.integration
class TestMemoryLive:
    @pytest.mark.asyncio
    async def test_health_check(self, live_memory):
        """메모리 시스템이 정상인지 확인."""
        assert await live_memory.health_check() is True

    @pytest.mark.asyncio
    async def test_retain_and_recall(self, live_memory):
        """저장 후 검색이 되는지 확인."""
        await live_memory.retain(
            "JediSOS 테스트: Alice는 Google에서 일하는 엔지니어입니다.",
            context="user",
        )
        result = await live_memory.recall("Alice는 어디서 일하나요?")
        assert result is not None
