"""
[JS-M004] jedisos.marketplace.models
패키지 메타데이터 모델 - 6종 패키지 유형 정의

version: 1.0.0
created: 2026-02-18
modified: 2026-02-18
dependencies: pydantic>=2.12
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path  # noqa: TC003 - Pydantic needs Path at runtime

from pydantic import BaseModel, Field

# 허용 라이선스 목록  [JS-M004.1]
ALLOWED_LICENSES: set[str] = {"MIT", "Apache-2.0", "BSD-3-Clause"}


class PackageType(StrEnum):  # [JS-M004.2]
    """패키지 유형 (6종)."""

    SKILL = "skill"
    MCP_SERVER = "mcp_server"
    PROMPT_PACK = "prompt_pack"
    WORKFLOW = "workflow"
    IDENTITY_PACK = "identity_pack"
    BUNDLE = "bundle"

    @property
    def dir_name(self) -> str:  # [JS-M004.3]
        """tools/ 하위 디렉토리 이름."""
        mapping = {
            "skill": "skills",
            "mcp_server": "mcp-servers",
            "prompt_pack": "prompts",
            "workflow": "workflows",
            "identity_pack": "identities",
            "bundle": "bundles",
        }
        return mapping[self.value]


class PackageMeta(BaseModel):  # [JS-M004.4]
    """패키지 메타데이터 (jedisos-package.yaml 내용)."""

    name: str
    version: str
    description: str
    type: PackageType = PackageType.SKILL
    license: str = "MIT"
    author: str = "anonymous"
    tags: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class PackageInfo(BaseModel):  # [JS-M004.5]
    """설치된 패키지 정보 (메타 + 디렉토리 경로)."""

    meta: PackageMeta
    directory: Path

    model_config = {"arbitrary_types_allowed": True}
