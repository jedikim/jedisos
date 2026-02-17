"""
[JS-T000] tests.conftest
공통 테스트 픽스처

version: 1.0.0
created: 2026-02-16
"""

import pytest

from jedisos.core.config import JedisosConfig
from jedisos.core.envelope import Envelope
from jedisos.core.types import ChannelType


@pytest.fixture
def config() -> JedisosConfig:
    """테스트용 설정."""
    return JedisosConfig(debug=True, log_level="DEBUG")


@pytest.fixture
def sample_envelope() -> Envelope:
    """테스트용 Envelope."""
    return Envelope(
        channel=ChannelType.CLI,
        user_id="test_user_001",
        user_name="테스터",
        content="안녕하세요, 테스트 메시지입니다.",
    )
