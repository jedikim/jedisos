"""
[JS-W003] jedisos.web.api.settings
설정 관리 API - .env, llm_config.yaml, MCP 설정 편집

version: 1.0.0
created: 2026-02-18
modified: 2026-02-18
dependencies: fastapi>=0.115
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = structlog.get_logger()

router = APIRouter()

# 설정 파일 기본 경로 (Docker: JEDISOS_DATA_DIR=/data, JEDISOS_CONFIG_DIR=/config)
_DATA_DIR = Path(os.environ.get("JEDISOS_DATA_DIR", "."))
_CONFIG_DIR = Path(os.environ.get("JEDISOS_CONFIG_DIR", str(_DATA_DIR / "config")))
_ENV_PATH = _DATA_DIR / ".env"

# [JS-W003.8] 웹 UI에서 수정 가능한 환경변수 키 목록
_ALLOWED_ENV_KEYS: set[str] = {
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "SECURITY_MAX_REQUESTS_PER_MINUTE",
    "DEBUG",
    "LOG_LEVEL",
    # 채널 봇 토큰
    "TELEGRAM_BOT_TOKEN",
    "DISCORD_BOT_TOKEN",
    "SLACK_BOT_TOKEN",
    "SLACK_APP_TOKEN",
}


class LLMSettingsUpdate(BaseModel):  # [JS-W003.1]
    """LLM 설정 업데이트 모델."""

    models: list[str] | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    timeout: int | None = None


class RoleModelsUpdate(BaseModel):  # [JS-W003.9]
    """역할별 모델 매핑 업데이트 모델."""

    roles: dict[str, list[str]]


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
    known_keys = sorted(_ALLOWED_ENV_KEYS)
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
    if update.key not in _ALLOWED_ENV_KEYS:
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


@router.get("/llm/roles")  # [JS-W003.10]
async def get_model_roles() -> dict[str, Any]:
    """현재 역할별 모델 매핑을 반환합니다."""
    from jedisos.web.app import get_app_state

    state = get_app_state()
    llm = state.get("llm")
    if not llm:
        return {"roles": {}, "fallback_models": []}

    roles: dict[str, list[str]] = {}
    for role in ("reason", "code", "chat", "classify", "extract"):
        roles[role] = llm.models_for(role)

    return {
        "roles": roles,
        "fallback_models": llm.models,
    }


@router.put("/llm/roles")  # [JS-W003.11]
async def update_model_roles(update: RoleModelsUpdate) -> dict[str, str]:
    """역할별 모델 매핑을 수동으로 업데이트합니다."""
    import yaml

    from jedisos.web.app import get_app_state

    state = get_app_state()
    llm = state.get("llm")
    if not llm:
        raise HTTPException(status_code=503, detail="LLM 라우터가 초기화되지 않았습니다")

    valid_roles = {"reason", "code", "chat", "classify", "extract"}
    for role in update.roles:
        if role not in valid_roles:
            raise HTTPException(status_code=400, detail=f"잘못된 역할: {role}")

    llm.set_role_models(update.roles)

    # model_roles.yaml에 캐시 저장
    cache_path = _DATA_DIR / "model_roles.yaml"
    try:
        cache_path.write_text(
            yaml.dump(update.roles, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("model_roles_cache_save_failed", error=str(e))

    logger.info("model_roles_updated_manually", roles=update.roles)
    return {"status": "updated"}


@router.post("/llm/reconfigure")  # [JS-W003.12]
async def reconfigure_models() -> dict[str, Any]:
    """모델 자동 구성을 다시 실행합니다 (캐시 삭제 후)."""
    from jedisos.web.app import get_app_state

    state = get_app_state()
    llm = state.get("llm")
    if not llm:
        raise HTTPException(status_code=503, detail="LLM 라우터가 초기화되지 않았습니다")

    # 캐시 삭제
    cache_path = _DATA_DIR / "model_roles.yaml"
    if cache_path.exists():
        cache_path.unlink()

    try:
        from jedisos.llm.auto_config import auto_configure_roles

        role_mapping = await auto_configure_roles(llm, data_dir=str(_DATA_DIR))
        llm.set_role_models(role_mapping)
        logger.info("model_roles_reconfigured", mapping=role_mapping)
        return {"status": "reconfigured", "roles": role_mapping}
    except Exception as e:
        logger.error("model_roles_reconfigure_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"자동 구성 실패: {e}") from e
