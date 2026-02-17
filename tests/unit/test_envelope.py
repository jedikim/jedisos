"""
[JS-T001] tests.unit.test_envelope
Envelope 단위 테스트

version: 1.0.0
created: 2026-02-16
"""

import pytest

from jedisos.core.envelope import Envelope
from jedisos.core.types import ChannelType, EnvelopeState


class TestEnvelopeCreation:  # [JS-T001.1]
    """Envelope 생성 테스트."""

    def test_create_with_defaults(self):
        env = Envelope(
            channel=ChannelType.CLI,
            user_id="user1",
            content="hello",
        )
        assert env.state == EnvelopeState.CREATED
        assert env.id  # UUIDv7이 생성되어야 함
        assert env.content == "hello"

    def test_uuid7_is_unique(self):
        env1 = Envelope(channel=ChannelType.CLI, user_id="u", content="a")
        env2 = Envelope(channel=ChannelType.CLI, user_id="u", content="b")
        assert env1.id != env2.id

    def test_uuid7_is_time_sortable(self):
        env1 = Envelope(channel=ChannelType.CLI, user_id="u", content="a")
        env2 = Envelope(channel=ChannelType.CLI, user_id="u", content="b")
        assert env1.id < env2.id  # UUIDv7은 시간순 정렬


class TestEnvelopeStateMachine:  # [JS-T001.2]
    """상태 전환 테스트."""

    def test_valid_transition_created_to_authorized(self, sample_envelope):
        sample_envelope.transition(EnvelopeState.AUTHORIZED)
        assert sample_envelope.state == EnvelopeState.AUTHORIZED

    def test_valid_transition_created_to_denied(self, sample_envelope):
        sample_envelope.transition(EnvelopeState.DENIED)
        assert sample_envelope.state == EnvelopeState.DENIED

    def test_invalid_transition_raises(self, sample_envelope):
        with pytest.raises(ValueError, match="잘못된 상태 전환"):
            sample_envelope.transition(EnvelopeState.COMPLETED)

    def test_full_happy_path(self, sample_envelope):
        sample_envelope.transition(EnvelopeState.AUTHORIZED)
        sample_envelope.transition(EnvelopeState.PROCESSING)
        sample_envelope.transition(EnvelopeState.TOOL_CALLING)
        sample_envelope.transition(EnvelopeState.PROCESSING)
        sample_envelope.transition(EnvelopeState.COMPLETED)
        assert sample_envelope.state == EnvelopeState.COMPLETED
