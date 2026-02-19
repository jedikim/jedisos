"""
[JS-W007] jedisos.web.api.vault
SecVault REST API - 마스터 비밀번호 설정/해제/상태 조회

version: 1.0.0
created: 2026-02-19
modified: 2026-02-19
dependencies: fastapi>=0.115
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter
from pydantic import BaseModel

logger = structlog.get_logger()

router = APIRouter()


class VaultPasswordRequest(BaseModel):  # [JS-W007.1]
    """비밀번호 요청 모델."""

    password: str


@router.get("/status")  # [JS-W007.2]
async def vault_status() -> dict:
    """SecVault 상태를 반환합니다."""
    from jedisos.web.app import get_app_state

    state = get_app_state()
    vault_client = state.get("vault_client")
    if vault_client is None:
        return {"status": "unavailable"}

    try:
        result = await vault_client.status()
        return {"status": result.get("status", "unknown")}
    except Exception as e:
        logger.warning("vault_status_failed", error=str(e))
        return {"status": "error", "error": str(e)}


@router.post("/setup")  # [JS-W007.3]
async def vault_setup(request: VaultPasswordRequest) -> dict:
    """SecVault 마스터 비밀번호를 최초 설정합니다."""
    from jedisos.web.app import get_app_state

    state = get_app_state()
    vault_client = state.get("vault_client")
    if vault_client is None:
        return {"ok": False, "error": "SecVault가 초기화되지 않았습니다."}

    ok = await vault_client.setup(request.password)
    if ok:
        state["vault_status"] = "unlocked"
        return {"ok": True, "status": "unlocked"}
    return {"ok": False, "error": "비밀번호 설정에 실패했습니다. (8자 이상)"}


@router.post("/unlock")  # [JS-W007.4]
async def vault_unlock(request: VaultPasswordRequest) -> dict:
    """SecVault 잠금을 해제합니다."""
    from jedisos.web.app import get_app_state

    state = get_app_state()
    vault_client = state.get("vault_client")
    if vault_client is None:
        return {"ok": False, "error": "SecVault가 초기화되지 않았습니다."}

    ok = await vault_client.unlock(request.password)
    if ok:
        state["vault_status"] = "unlocked"
        return {"ok": True, "status": "unlocked"}
    return {"ok": False, "error": "비밀번호가 틀립니다."}
