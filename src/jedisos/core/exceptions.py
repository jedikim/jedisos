"""
[JS-A003] jedisos.core.exceptions
커스텀 예외 계층 구조

version: 1.0.0
created: 2026-02-16
modified: 2026-02-16
"""


class JedisosError(Exception):  # [JS-A003.1]
    """JediSOS 기본 예외. 모든 커스텀 예외의 부모."""


class ConfigError(JedisosError):  # [JS-A003.2]
    """설정 관련 에러."""


class HindsightMemoryError(JedisosError):  # [JS-A003.3]
    """Hindsight 메모리 관련 에러."""


class LLMError(JedisosError):  # [JS-A003.4]
    """LLM 호출 관련 에러."""


class MCPError(JedisosError):  # [JS-A003.5]
    """MCP 도구 관련 에러."""


class ChannelError(JedisosError):  # [JS-A003.6]
    """채널 어댑터 관련 에러."""


class SecurityError(JedisosError):  # [JS-A003.7]
    """보안/권한 관련 에러."""


class AgentError(JedisosError):  # [JS-A003.8]
    """에이전트 실행 관련 에러."""
