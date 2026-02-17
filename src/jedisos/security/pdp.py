"""
[JS-G001] jedisos.security.pdp
Policy Decision Point - 도구 호출 허용/차단 정책 엔진

version: 1.0.0
created: 2026-02-17
modified: 2026-02-17
dependencies: pydantic-settings>=2.13
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any

import structlog

from jedisos.core.exceptions import SecurityError

if TYPE_CHECKING:
    from jedisos.core.config import SecurityConfig
    from jedisos.core.types import PolicyDecision

logger = structlog.get_logger()


class PolicyDecisionPoint:  # [JS-G001.1]
    """도구 호출에 대한 허용/차단 정책을 결정합니다.

    SecurityConfig 기반으로:
    - allowed_tools: 화이트리스트 (빈 리스트 = 모두 허용)
    - blocked_tools: 블랙리스트 (항상 차단)
    - max_requests_per_minute: 속도 제한
    """

    def __init__(self, config: SecurityConfig) -> None:
        self.config = config
        self._request_counts: dict[str, list[float]] = defaultdict(list)
        logger.info(
            "pdp_init",
            allowed_tools=config.allowed_tools,
            blocked_tools=config.blocked_tools,
            rate_limit=config.max_requests_per_minute,
        )

    def check_tool_access(  # [JS-G001.2]
        self,
        tool_name: str,
        user_id: str = "",
        channel: str = "",
    ) -> PolicyDecision:
        """도구 호출 허용 여부를 판단합니다.

        Args:
            tool_name: 호출할 도구 이름
            user_id: 사용자 식별자
            channel: 채널 식별자

        Returns:
            (allowed, reason) 튜플
        """
        # 1. 블랙리스트 체크
        if tool_name in self.config.blocked_tools:
            reason = f"도구 '{tool_name}'은(는) 차단 목록에 있습니다."
            logger.warning("pdp_blocked", tool=tool_name, user_id=user_id, reason=reason)
            return False, reason

        # 2. 화이트리스트 체크 (빈 리스트면 모두 허용)
        if self.config.allowed_tools and tool_name not in self.config.allowed_tools:
            reason = f"도구 '{tool_name}'은(는) 허용 목록에 없습니다."
            logger.warning("pdp_not_allowed", tool=tool_name, user_id=user_id, reason=reason)
            return False, reason

        # 3. 속도 제한 체크
        rate_key = user_id or "anonymous"
        if not self._check_rate_limit(rate_key):
            reason = f"속도 제한 초과 (최대 {self.config.max_requests_per_minute}회/분)"
            logger.warning("pdp_rate_limited", user_id=rate_key, reason=reason)
            return False, reason

        logger.info("pdp_allowed", tool=tool_name, user_id=user_id)
        return True, "허용"

    def _check_rate_limit(self, key: str) -> bool:  # [JS-G001.3]
        """분당 요청 수를 체크합니다."""
        now = time.monotonic()
        window = 60.0

        # 오래된 요청 제거
        self._request_counts[key] = [t for t in self._request_counts[key] if now - t < window]

        if len(self._request_counts[key]) >= self.config.max_requests_per_minute:
            return False

        self._request_counts[key].append(now)
        return True

    def enforce_tool_access(  # [JS-G001.4]
        self,
        tool_name: str,
        user_id: str = "",
        channel: str = "",
    ) -> None:
        """도구 접근을 강제합니다. 차단 시 SecurityError를 발생시킵니다."""
        allowed, reason = self.check_tool_access(tool_name, user_id, channel)
        if not allowed:
            raise SecurityError(reason)

    def add_blocked_tool(self, tool_name: str) -> None:  # [JS-G001.5]
        """블랙리스트에 도구를 추가합니다."""
        if tool_name not in self.config.blocked_tools:
            self.config.blocked_tools.append(tool_name)
            logger.info("pdp_tool_blocked", tool=tool_name)

    def remove_blocked_tool(self, tool_name: str) -> None:  # [JS-G001.6]
        """블랙리스트에서 도구를 제거합니다."""
        if tool_name in self.config.blocked_tools:
            self.config.blocked_tools.remove(tool_name)
            logger.info("pdp_tool_unblocked", tool=tool_name)

    def get_policy_summary(self) -> dict[str, Any]:  # [JS-G001.7]
        """현재 정책 요약을 반환합니다."""
        return {
            "allowed_tools": list(self.config.allowed_tools),
            "blocked_tools": list(self.config.blocked_tools),
            "max_requests_per_minute": self.config.max_requests_per_minute,
        }
