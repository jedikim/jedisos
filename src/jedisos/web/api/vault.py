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

    try:
        resp = await vault_client._send({"op": "setup", "data": request.password})
    except Exception as e:
        logger.error("vault_setup_error", error=str(e))
        return {"ok": False, "error": f"SecVault 연결 실패: {e}"}

    if resp.get("ok"):
        state["vault_status"] = "unlocked"
        logger.info("vault_setup_success")
        return {"ok": True, "status": "unlocked"}

    error_msg = resp.get("error", "알 수 없는 오류")
    logger.warning("vault_setup_failed", error=error_msg)
    return {"ok": False, "error": error_msg}


@router.post("/unlock")  # [JS-W007.4]
async def vault_unlock(request: VaultPasswordRequest) -> dict:
    """SecVault 잠금을 해제합니다."""
    from jedisos.web.app import get_app_state

    state = get_app_state()
    vault_client = state.get("vault_client")
    if vault_client is None:
        return {"ok": False, "error": "SecVault가 초기화되지 않았습니다."}

    try:
        resp = await vault_client._send({"op": "unlock", "data": request.password})
    except Exception as e:
        logger.error("vault_unlock_error", error=str(e))
        return {"ok": False, "error": f"SecVault 연결 실패: {e}"}

    if resp.get("ok"):
        state["vault_status"] = "unlocked"
        logger.info("vault_unlock_success")
        return {"ok": True, "status": "unlocked"}

    error_msg = resp.get("error", "비밀번호가 틀립니다.")
    logger.warning("vault_unlock_failed", error=error_msg)
    return {"ok": False, "error": error_msg}
