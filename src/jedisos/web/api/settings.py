"""
[JS-W003] jedisos.web.api.settings
설정 관리 API - .env, llm_config.yaml, MCP 설정 편집

version: 1.0.0
created: 2026-02-18
modified: 2026-02-18
dependencies: fastapi>=0.115
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = structlog.get_logger()

router = APIRouter()

# 설정 파일 기본 경로
_CONFIG_DIR = Path("config")
_ENV_PATH = Path(".env")


class LLMSettingsUpdate(BaseModel):  # [JS-W003.1]
    """LLM 설정 업데이트 모델."""

    models: list[str] | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    timeout: int | None = None


class EnvUpdate(BaseModel):  # [JS-W003.2]
    """환경변수 업데이트 모델."""

    key: str
    value: str


@router.get("/llm")  # [JS-W003.3]
async def get_llm_settings() -> dict[str, Any]:
    """현재 LLM 설정을 반환합니다."""
    from jedisos.web.app import get_app_state

    state = get_app_state()
    config = state.get("config")
    if not config:
        return {"models": [], "temperature": 0.7, "max_tokens": 8192, "timeout": 60}

    return {
        "models": list(config.llm.models),
        "temperature": config.llm.temperature,
        "max_tokens": config.llm.max_tokens,
        "timeout": config.llm.timeout,
    }


@router.put("/llm")  # [JS-W003.4]
async def update_llm_settings(settings: LLMSettingsUpdate) -> dict[str, str]:
    """LLM 설정을 업데이트합니다. llm_config.yaml에 저장."""
    config_path = _CONFIG_DIR / "llm_config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # 현재 설정 로드
    current = await get_llm_settings()

    if settings.models is not None:
        current["models"] = settings.models
    if settings.temperature is not None:
        current["temperature"] = settings.temperature
    if settings.max_tokens is not None:
        current["max_tokens"] = settings.max_tokens
    if settings.timeout is not None:
        current["timeout"] = settings.timeout

    # YAML로 저장
    lines = ["# JediSOS LLM 설정\n", "models:\n"]
    for m in current["models"]:
        lines.append(f"  - {m}\n")
    lines.append(f"\ntemperature: {current['temperature']}\n")
    lines.append(f"max_tokens: {current['max_tokens']}\n")
    lines.append(f"timeout: {current['timeout']}\n")

    config_path.write_text("".join(lines))
    logger.info("llm_settings_updated", models=current["models"])
    return {"status": "updated"}


@router.get("/security")  # [JS-W003.5]
async def get_security_settings() -> dict[str, Any]:
    """보안 설정을 반환합니다."""
    from jedisos.web.app import get_app_state

    state = get_app_state()
    pdp = state.get("pdp")
    if not pdp:
        return {"blocked_tools": [], "allowed_tools": [], "max_requests_per_minute": 30}

    return pdp.get_policy_summary()


@router.get("/env")  # [JS-W003.6]
async def get_env_keys() -> dict[str, Any]:
    """설정 가능한 환경변수 키 목록을 반환합니다.

    값은 보안상 반환하지 않습니다.
    """
    known_keys = [
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "HINDSIGHT_API_URL",
        "SECURITY_MAX_REQUESTS_PER_MINUTE",
        "DEBUG",
        "LOG_LEVEL",
    ]
    # 실제 설정된 키 확인
    configured = []
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key = line.split("=", 1)[0].strip()
                has_value = bool(line.split("=", 1)[1].strip())
                configured.append({"key": key, "configured": has_value})

    return {"known_keys": known_keys, "configured": configured}


@router.put("/env")  # [JS-W003.7]
async def update_env_var(update: EnvUpdate) -> dict[str, str]:
    """환경변수를 .env 파일에 업데이트합니다."""
    # 허용된 키만
    allowed = {
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "HINDSIGHT_API_URL",
        "SECURITY_MAX_REQUESTS_PER_MINUTE",
        "DEBUG",
        "LOG_LEVEL",
    }
    if update.key not in allowed:
        raise HTTPException(status_code=400, detail=f"허용되지 않는 키입니다: {update.key}")

    # .env 파일 업데이트
    lines: list[str] = []
    found = False
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text().splitlines():
            if line.strip().startswith(f"{update.key}="):
                lines.append(f"{update.key}={update.value}")
                found = True
            else:
                lines.append(line)

    if not found:
        lines.append(f"{update.key}={update.value}")

    _ENV_PATH.write_text("\n".join(lines) + "\n")
    logger.info("env_var_updated", key=update.key)
    return {"status": "updated", "key": update.key}
