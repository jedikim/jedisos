"""
[JS-W005] jedisos.web.api.monitoring
상태 모니터링 + 감사 로그 API

version: 1.0.0
created: 2026-02-18
modified: 2026-02-18
dependencies: fastapi>=0.115
"""

from __future__ import annotations

import sys
from typing import Any

import structlog
from fastapi import APIRouter

from jedisos import __version__

logger = structlog.get_logger()

router = APIRouter()


@router.get("/status")  # [JS-W005.1]
async def get_status() -> dict[str, Any]:
    """시스템 상태를 반환합니다."""
    from jedisos.web.app import get_app_state

    state = get_app_state()
    memory = state.get("memory")
    llm = state.get("llm")

    # 메모리 시스템 상태
    memory_ok = False
    if memory:
        try:
            memory_ok = await memory.health_check()
        except Exception:
            memory_ok = False

    return {
        "version": __version__,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "services": {
            "memory": "ok" if memory_ok else "offline",
            "llm": "configured" if llm else "not_configured",
        },
        "models": list(llm.models) if llm else [],
    }


@router.get("/audit")  # [JS-W005.2]
async def get_audit_log(limit: int = 50) -> dict[str, Any]:
    """감사 로그를 반환합니다."""
    from jedisos.web.app import get_app_state

    state = get_app_state()
    audit = state.get("audit")

    if not audit:
        return {"entries": [], "total": 0}

    entries = audit.get_recent(limit)
    return {"entries": entries, "total": audit.entry_count}


@router.get("/audit/denied")  # [JS-W005.3]
async def get_denied_log() -> dict[str, Any]:
    """차단된 요청 로그를 반환합니다."""
    from jedisos.web.app import get_app_state

    state = get_app_state()
    audit = state.get("audit")

    if not audit:
        return {"entries": [], "total": 0}

    entries = audit.get_denied_entries()
    return {"entries": entries, "total": len(entries)}


@router.get("/policy")  # [JS-W005.4]
async def get_policy() -> dict[str, Any]:
    """현재 보안 정책을 반환합니다."""
    from jedisos.web.app import get_app_state

    state = get_app_state()
    pdp = state.get("pdp")

    if not pdp:
        return {"blocked_tools": [], "allowed_tools": [], "max_requests_per_minute": 0}

    return pdp.get_policy_summary()
