"""
[JS-T003] tests.integration.test_hindsight_live
Hindsight 실제 연동 테스트
docker compose -f docker-compose.dev.yml up -d 상태에서 실행

version: 1.0.0
created: 2026-02-16
"""

import pytest

from jedisos.core.config import HindsightConfig
from jedisos.memory.hindsight import HindsightMemory


@pytest.fixture
async def live_memory():
    config = HindsightConfig()  # .env에서 로드
    mem = HindsightMemory(config=config)
    yield mem
    await mem.close()


@pytest.mark.integration
class TestHindsightLive:
    @pytest.mark.asyncio
    async def test_health_check(self, live_memory):
        """Hindsight 서버가 살아있는지 확인."""
        assert await live_memory.health_check() is True

    @pytest.mark.asyncio
    async def test_retain_and_recall(self, live_memory):
        """저장 후 검색이 되는지 확인."""
        await live_memory.retain(
            "JediSOS 테스트: Alice는 Google에서 일하는 엔지니어입니다.",
            context="통합 테스트",
        )
        result = await live_memory.recall("Alice는 어디서 일하나요?")
        assert result is not None
