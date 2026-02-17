"""
[JS-W001] jedisos.web.app
FastAPI 메인 애플리케이션 + 라우터 등록

version: 1.0.0
created: 2026-02-18
modified: 2026-02-18
dependencies: fastapi>=0.115, uvicorn>=0.34
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from jedisos import __version__

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = structlog.get_logger()

# 앱 상태 (lifespan에서 초기화)
_app_state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:  # [JS-W001.1]
    """앱 시작/종료 시 리소스를 관리합니다."""
    logger.info("web_app_starting", version=__version__)

    # 시작 시 초기화
    from jedisos.core.config import HindsightConfig, JedisosConfig, LLMConfig, SecurityConfig
    from jedisos.llm.router import LLMRouter
    from jedisos.memory.hindsight import HindsightMemory
    from jedisos.security.audit import AuditLogger
    from jedisos.security.pdp import PolicyDecisionPoint

    config = JedisosConfig()
    memory = HindsightMemory(HindsightConfig())
    llm = LLMRouter(LLMConfig())
    pdp = PolicyDecisionPoint(SecurityConfig())
    audit = AuditLogger()

    _app_state["config"] = config
    _app_state["memory"] = memory
    _app_state["llm"] = llm
    _app_state["pdp"] = pdp
    _app_state["audit"] = audit

    logger.info("web_app_ready")
    yield

    # 종료 시 정리
    _app_state.clear()
    logger.info("web_app_shutdown")


def get_app_state() -> dict[str, Any]:  # [JS-W001.2]
    """앱 공유 상태를 반환합니다."""
    return _app_state


def create_app() -> FastAPI:  # [JS-W001.3]
    """FastAPI 앱을 생성하고 라우터를 등록합니다."""
    app = FastAPI(
        title="JediSOS",
        description="AI Agent System with Hindsight Memory",
        version=__version__,
        lifespan=lifespan,
    )

    # CORS 설정 (로컬 개발용)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 라우터 등록
    from jedisos.web.api.chat import router as chat_router
    from jedisos.web.api.mcp import router as mcp_router
    from jedisos.web.api.monitoring import router as monitoring_router
    from jedisos.web.api.settings import router as settings_router
    from jedisos.web.setup_wizard import router as wizard_router

    app.include_router(chat_router, prefix="/api/chat", tags=["chat"])
    app.include_router(settings_router, prefix="/api/settings", tags=["settings"])
    app.include_router(mcp_router, prefix="/api/mcp", tags=["mcp"])
    app.include_router(monitoring_router, prefix="/api/monitoring", tags=["monitoring"])
    app.include_router(wizard_router, prefix="/api/setup", tags=["setup"])

    @app.get("/health")
    async def health_check() -> JSONResponse:  # [JS-W001.4]
        """헬스 체크 엔드포인트."""
        return JSONResponse({"status": "ok", "version": __version__})

    logger.info("web_app_created")
    return app


def run_server(host: str = "0.0.0.0", port: int = 8080) -> None:  # [JS-W001.5]  # nosec B104
    """uvicorn으로 서버를 실행합니다."""
    import uvicorn

    logger.info("web_server_starting", host=host, port=port)
    uvicorn.run(
        "jedisos.web.app:create_app",
        factory=True,
        host=host,
        port=port,
        log_level="info",
    )
