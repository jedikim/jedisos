"""
[JS-B002] jedisos.memory.identity
에이전트 정체성 관리 - IDENTITY.md 기반

version: 1.0.0
created: 2026-02-16
modified: 2026-02-16
"""

from __future__ import annotations

from pathlib import Path

import structlog

logger = structlog.get_logger()

DEFAULT_IDENTITY = """
# JediSOS Agent Identity

## 이름
JediSOS

## 역할
사용자를 돕는 AI 어시스턴트

## 성격
정확하고, 친절하며, 한국어와 영어를 모두 지원합니다.

## 규칙
1. 사실만 말합니다. 모르면 모른다고 합니다.
2. 도구를 활용하여 정확한 정보를 제공합니다.
3. 이전 대화를 기억하고 활용합니다.
""".strip()


class AgentIdentity:  # [JS-B002.1]
    """에이전트 정체성 로더."""

    def __init__(self, identity_path: str | Path | None = None) -> None:
        self.path = Path(identity_path) if identity_path else None
        self._content: str | None = None

    def load(self) -> str:  # [JS-B002.2]
        """정체성 문서를 로드합니다."""
        if self._content:
            return self._content

        if self.path and self.path.exists():
            self._content = self.path.read_text(encoding="utf-8")
            logger.info("identity_loaded", path=str(self.path))
        else:
            self._content = DEFAULT_IDENTITY
            logger.info("identity_default_used")

        return self._content

    def to_system_prompt(self) -> str:  # [JS-B002.3]
        """시스템 프롬프트용으로 포맷합니다."""
        content = self.load()
        return f"당신의 정체성:\n\n{content}"
