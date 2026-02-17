"""
[JS-W006] jedisos.web.setup_wizard
첫 실행 Setup Wizard API

version: 1.0.0
created: 2026-02-18
modified: 2026-02-18
dependencies: fastapi>=0.115
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter
from pydantic import BaseModel

logger = structlog.get_logger()

router = APIRouter()

_ENV_PATH = Path(".env")


class SetupStatus(BaseModel):  # [JS-W006.1]
    """Setup 상태 모델."""

    is_first_run: bool
    has_api_key: bool
    has_llm_config: bool


class SetupRequest(BaseModel):  # [JS-W006.2]
    """Setup Wizard 요청 모델."""

    openai_api_key: str = ""
    google_api_key: str = ""
    models: list[str] | None = None


@router.get("/status")  # [JS-W006.3]
async def get_setup_status() -> SetupStatus:
    """Setup Wizard 진행 상태를 반환합니다."""
    is_first_run = True
    has_api_key = False

    if _ENV_PATH.exists():
        env_content = _ENV_PATH.read_text()
        if "JEDISOS_FIRST_RUN=false" in env_content:
            is_first_run = False
        # API 키 존재 여부
        for line in env_content.splitlines():
            if line.startswith("OPENAI_API_KEY=") and line.split("=", 1)[1].strip():
                has_api_key = True
                break
            if line.startswith("GOOGLE_API_KEY=") and line.split("=", 1)[1].strip():
                has_api_key = True
                break

    has_llm_config = Path("config/llm_config.yaml").exists()

    return SetupStatus(
        is_first_run=is_first_run,
        has_api_key=has_api_key,
        has_llm_config=has_llm_config,
    )


@router.post("/complete")  # [JS-W006.4]
async def complete_setup(request: SetupRequest) -> dict[str, str]:
    """Setup Wizard를 완료합니다.

    API 키를 저장하고, LLM 설정을 생성하고, first_run 플래그를 해제합니다.
    """
    # 1. .env 파일에 API 키 저장
    env_lines: list[str] = []
    if _ENV_PATH.exists():
        env_lines = _ENV_PATH.read_text().splitlines()

    env_lines = _update_env_line(env_lines, "OPENAI_API_KEY", request.openai_api_key)
    env_lines = _update_env_line(env_lines, "GOOGLE_API_KEY", request.google_api_key)
    env_lines = _update_env_line(env_lines, "JEDISOS_FIRST_RUN", "false")

    _ENV_PATH.write_text("\n".join(env_lines) + "\n")

    # 2. llm_config.yaml 생성
    models = request.models or ["gpt-5.2", "gemini/gemini-3-flash"]
    config_dir = Path("config")
    config_dir.mkdir(exist_ok=True)
    llm_config_path = config_dir / "llm_config.yaml"

    lines = ["# JediSOS LLM 설정\n", "models:\n"]
    for m in models:
        lines.append(f"  - {m}\n")
    lines.append("\ntemperature: 0.7\nmax_tokens: 8192\ntimeout: 60\n")
    llm_config_path.write_text("".join(lines))

    logger.info("setup_completed", models=models)
    return {"status": "completed"}


@router.get("/recommended-mcp")  # [JS-W006.5]
async def get_recommended_mcp() -> dict[str, Any]:
    """추천 MCP 서버 목록을 반환합니다."""
    return {
        "servers": [
            {
                "name": "hindsight-memory",
                "description": "Hindsight 메모리 도구 (retain/recall/reflect)",
                "category": "memory",
                "builtin": True,
            },
            {
                "name": "google-calendar",
                "description": "Google Calendar 연동 (OAuth 필요)",
                "category": "productivity",
                "builtin": False,
            },
            {
                "name": "gmail",
                "description": "Gmail 연동 (OAuth 필요)",
                "category": "communication",
                "builtin": False,
            },
        ]
    }


def _update_env_line(lines: list[str], key: str, value: str) -> list[str]:
    """환경변수 라인을 업데이트하거나 추가합니다."""
    updated = False
    result = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            result.append(f"{key}={value}")
            updated = True
        else:
            result.append(line)
    if not updated:
        result.append(f"{key}={value}")
    return result
