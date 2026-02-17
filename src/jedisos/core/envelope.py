"""
[JS-A001] jedisos.core.envelope
Envelope 메시지 계약 - 에이전트 간 통신의 기본 단위

version: 1.0.0
created: 2026-02-16
modified: 2026-02-16
dependencies: pydantic>=2.12, uuid6>=2025.0
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from uuid6 import uuid7

from jedisos.core.types import ChannelType, EnvelopeState


class Envelope(BaseModel):  # [JS-A001.1]
    """에이전트 간 메시지 표준 계약.

    UUIDv7 기반 ID로 시간순 정렬 가능.
    상태 머신으로 메시지 수명주기 추적.
    """

    id: str = Field(default_factory=lambda: str(uuid7()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    channel: ChannelType
    user_id: str
    user_name: str = ""
    content: str
    state: EnvelopeState = EnvelopeState.CREATED
    metadata: dict[str, Any] = Field(default_factory=dict)
    response: str = ""
    error: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    memory_context: list[dict[str, Any]] = Field(default_factory=list)

    def transition(self, new_state: EnvelopeState) -> None:  # [JS-A001.2]
        """상태 전환. 유효하지 않은 전환은 ValueError."""
        valid = {
            EnvelopeState.CREATED: {EnvelopeState.AUTHORIZED, EnvelopeState.DENIED},
            EnvelopeState.AUTHORIZED: {EnvelopeState.PROCESSING},
            EnvelopeState.PROCESSING: {
                EnvelopeState.TOOL_CALLING,
                EnvelopeState.COMPLETED,
                EnvelopeState.FAILED,
            },
            EnvelopeState.TOOL_CALLING: {
                EnvelopeState.PROCESSING,
                EnvelopeState.COMPLETED,
                EnvelopeState.FAILED,
            },
        }
        allowed = valid.get(self.state, set())
        if new_state not in allowed:
            raise ValueError(
                f"[JS-A001.2] 잘못된 상태 전환: {self.state} → {new_state}. 허용: {allowed}"
            )
        self.state = new_state
