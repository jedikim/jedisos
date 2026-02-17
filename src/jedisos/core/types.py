"""
[JS-A004] jedisos.core.types
공통 타입 정의

version: 1.0.0
created: 2026-02-16
modified: 2026-02-16
dependencies: pydantic>=2.12, uuid6>=2025.0
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ChannelType(StrEnum):  # [JS-A004.1]
    """지원 채널 타입."""

    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    CLI = "cli"
    API = "api"


class EnvelopeState(StrEnum):  # [JS-A004.2]
    """Envelope 상태 머신."""

    CREATED = "created"
    AUTHORIZED = "authorized"
    DENIED = "denied"
    PROCESSING = "processing"
    TOOL_CALLING = "tool_calling"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentRole(StrEnum):  # [JS-A004.3]
    """에이전트 역할."""

    SUPERVISOR = "supervisor"
    WORKER = "worker"
    REVIEWER = "reviewer"


# 공통 타입 별칭
ToolResult = dict[str, Any]
MemoryContext = list[dict[str, Any]]
PolicyDecision = tuple[bool, str]  # (allowed, reason)
