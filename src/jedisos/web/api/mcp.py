"""
[JS-W004] jedisos.web.api.mcp
MCP 서버 관리 API - 검색, 설치, 삭제

version: 1.0.0
created: 2026-02-18
modified: 2026-02-18
dependencies: fastapi>=0.115
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = structlog.get_logger()

router = APIRouter()

_MCP_CONFIG_PATH = Path(os.environ.get("JEDISOS_DATA_DIR", ".")) / "config" / "mcp_servers.json"


class MCPServerInfo(BaseModel):  # [JS-W004.1]
    """MCP 서버 정보 모델."""

    name: str
    url: str = ""
    description: str = ""
    enabled: bool = True
    server_type: str = "remote"  # "remote" 또는 "subprocess"
    command: str = ""
    args: list[str] = []
    env: dict[str, str] = {}


class MCPServerInstall(BaseModel):  # [JS-W004.2]
    """MCP 서버 설치 요청."""

    name: str
    url: str = ""
    description: str = ""
    server_type: str = "remote"
    command: str = ""
    args: list[str] = []
    env: dict[str, str] = {}


def _load_mcp_config() -> dict[str, Any]:  # [JS-W004.3]
    """MCP 설정 파일을 로드합니다."""
    if _MCP_CONFIG_PATH.exists():
        return json.loads(_MCP_CONFIG_PATH.read_text())
    return {"servers": []}


def _save_mcp_config(config: dict[str, Any]) -> None:
    """MCP 설정 파일을 저장합니다."""
    _MCP_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _MCP_CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False))


@router.get("/servers")  # [JS-W004.4]
async def list_servers() -> dict[str, Any]:
    """설치된 MCP 서버 목록을 반환합니다."""
    config = _load_mcp_config()
    return {"servers": config.get("servers", []), "total": len(config.get("servers", []))}


@router.post("/servers")  # [JS-W004.5]
async def install_server(request: MCPServerInstall) -> dict[str, str]:
    """MCP 서버를 설치합니다."""
    config = _load_mcp_config()
    servers = config.get("servers", [])

    # 중복 체크
    for s in servers:
        if s["name"] == request.name:
            raise HTTPException(
                status_code=409, detail=f"서버 '{request.name}'이(가) 이미 설치되어 있습니다."
            )

    entry: dict[str, Any] = {
        "name": request.name,
        "url": request.url,
        "description": request.description,
        "enabled": True,
        "server_type": request.server_type,
    }
    if request.server_type == "subprocess":
        entry["command"] = request.command
        entry["args"] = request.args
        entry["env"] = request.env
    servers.append(entry)
    config["servers"] = servers
    _save_mcp_config(config)

    logger.info("mcp_server_installed", name=request.name)
    return {"status": "installed", "name": request.name}


@router.delete("/servers/{name}")  # [JS-W004.6]
async def uninstall_server(name: str) -> dict[str, str]:
    """MCP 서버를 삭제합니다."""
    config = _load_mcp_config()
    servers = config.get("servers", [])

    original_count = len(servers)
    servers = [s for s in servers if s["name"] != name]

    if len(servers) == original_count:
        raise HTTPException(status_code=404, detail=f"서버 '{name}'을(를) 찾을 수 없습니다.")

    config["servers"] = servers
    _save_mcp_config(config)

    logger.info("mcp_server_uninstalled", name=name)
    return {"status": "uninstalled", "name": name}


@router.put("/servers/{name}/toggle")  # [JS-W004.7]
async def toggle_server(name: str) -> dict[str, Any]:
    """MCP 서버 활성화/비활성화를 토글합니다."""
    config = _load_mcp_config()
    servers = config.get("servers", [])

    for s in servers:
        if s["name"] == name:
            s["enabled"] = not s.get("enabled", True)
            _save_mcp_config(config)
            logger.info("mcp_server_toggled", name=name, enabled=s["enabled"])
            return {"name": name, "enabled": s["enabled"]}

    raise HTTPException(status_code=404, detail=f"서버 '{name}'을(를) 찾을 수 없습니다.")
