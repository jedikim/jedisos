"""
[JS-G002] jedisos.security.audit
감사 로그 - 도구 호출 및 보안 결정 기록

version: 1.0.0
created: 2026-02-17
modified: 2026-02-17
dependencies: structlog>=25.5.0
"""

from __future__ import annotations

import time
from typing import Any

import structlog

logger = structlog.get_logger()


class AuditLogger:  # [JS-G002.1]
    """도구 호출 및 보안 이벤트를 기록하는 감사 로거.

    structlog 기반으로 구조화된 감사 로그를 생성합니다.
    인메모리 로그도 유지하여 최근 이벤트 조회가 가능합니다.
    """

    def __init__(self, max_entries: int = 1000) -> None:
        self._entries: list[dict[str, Any]] = []
        self._max_entries = max_entries
        logger.info("audit_logger_init", max_entries=max_entries)

    def log_tool_call(  # [JS-G002.2]
        self,
        tool_name: str,
        user_id: str = "",
        channel: str = "",
        arguments: dict[str, Any] | None = None,
        allowed: bool = True,
        reason: str = "",
    ) -> None:
        """도구 호출을 기록합니다."""
        entry = {
            "event": "tool_call",
            "tool": tool_name,
            "user_id": user_id,
            "channel": channel,
            "allowed": allowed,
            "reason": reason,
            "timestamp": time.time(),
        }
        self._append(entry)

        if allowed:
            logger.info("audit_tool_allowed", tool=tool_name, user_id=user_id, channel=channel)
        else:
            logger.warning(
                "audit_tool_denied",
                tool=tool_name,
                user_id=user_id,
                reason=reason,
            )

    def log_security_event(  # [JS-G002.3]
        self,
        event_type: str,
        user_id: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        """보안 이벤트를 기록합니다."""
        entry = {
            "event": event_type,
            "user_id": user_id,
            "details": details or {},
            "timestamp": time.time(),
        }
        self._append(entry)
        logger.info("audit_security_event", event_type=event_type, user_id=user_id)

    def log_agent_action(  # [JS-G002.4]
        self,
        action: str,
        agent_name: str = "",
        user_id: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        """에이전트 행동을 기록합니다."""
        entry = {
            "event": "agent_action",
            "action": action,
            "agent": agent_name,
            "user_id": user_id,
            "details": details or {},
            "timestamp": time.time(),
        }
        self._append(entry)
        logger.info("audit_agent_action", action=action, agent=agent_name, user_id=user_id)

    def get_recent(self, count: int = 50) -> list[dict[str, Any]]:  # [JS-G002.5]
        """최근 감사 로그를 조회합니다."""
        return list(self._entries[-count:])

    def get_by_user(self, user_id: str) -> list[dict[str, Any]]:  # [JS-G002.6]
        """특정 사용자의 감사 로그를 조회합니다."""
        return [e for e in self._entries if e.get("user_id") == user_id]

    def get_denied_entries(self) -> list[dict[str, Any]]:  # [JS-G002.7]
        """차단된 도구 호출 로그를 조회합니다."""
        return [e for e in self._entries if e.get("event") == "tool_call" and not e.get("allowed")]

    def clear(self) -> None:
        """감사 로그를 초기화합니다."""
        self._entries.clear()

    @property
    def entry_count(self) -> int:
        """현재 로그 엔트리 수."""
        return len(self._entries)

    def _append(self, entry: dict[str, Any]) -> None:
        """엔트리를 추가하고 최대 크기를 유지합니다."""
        self._entries.append(entry)
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries :]
