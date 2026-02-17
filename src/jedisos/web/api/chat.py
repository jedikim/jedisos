"""
[JS-W002] jedisos.web.api.chat
WebSocket 기반 실시간 채팅 API

version: 1.0.0
created: 2026-02-18
modified: 2026-02-18
dependencies: fastapi>=0.115
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = structlog.get_logger()

router = APIRouter()


class ChatRequest(BaseModel):  # [JS-W002.1]
    """채팅 요청 모델."""

    message: str
    bank_id: str = "web-default"
    model: str | None = None


class ChatResponse(BaseModel):  # [JS-W002.2]
    """채팅 응답 모델."""

    response: str
    bank_id: str
    model: str | None = None


class ConnectionManager:  # [JS-W002.3]
    """WebSocket 연결 관리자."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("websocket_connected", total=len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.remove(websocket)
        logger.info("websocket_disconnected", total=len(self.active_connections))

    @property
    def connection_count(self) -> int:
        return len(self.active_connections)


manager = ConnectionManager()


@router.websocket("/ws")  # [JS-W002.4]
async def websocket_chat(websocket: WebSocket) -> None:
    """WebSocket 채팅 엔드포인트.

    클라이언트가 JSON 메시지를 보내면 에이전트 응답을 반환합니다.
    형식: {"message": "안녕", "bank_id": "web-default"}
    """
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            bank_id = data.get("bank_id", "web-default")

            if not message:
                await websocket.send_json({"error": "빈 메시지입니다."})
                continue

            logger.info("websocket_message", text_len=len(message), bank_id=bank_id)

            try:
                response = await _run_agent(message, bank_id)
                await websocket.send_json({"response": response, "bank_id": bank_id})
            except Exception as e:
                logger.error("websocket_agent_error", error=str(e))
                await websocket.send_json({"error": f"처리 실패: {e}"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@router.post("/send", response_model=ChatResponse)  # [JS-W002.5]
async def send_message(request: ChatRequest) -> ChatResponse:
    """HTTP POST 채팅 엔드포인트 (WebSocket 대안)."""
    logger.info("chat_send", text_len=len(request.message), bank_id=request.bank_id)

    response = await _run_agent(request.message, request.bank_id, request.model)
    return ChatResponse(response=response, bank_id=request.bank_id)


@router.get("/connections")  # [JS-W002.6]
async def get_connections() -> dict[str, Any]:
    """현재 WebSocket 연결 수를 반환합니다."""
    return {"active_connections": manager.connection_count}


async def _run_agent(message: str, bank_id: str, model: str | None = None) -> str:
    """에이전트를 실행합니다."""
    from jedisos.web.app import get_app_state

    state = get_app_state()
    memory = state.get("memory")
    llm = state.get("llm")

    if not memory or not llm:
        return "서버가 아직 초기화되지 않았습니다."

    from jedisos.agents.react import ReActAgent

    agent = ReActAgent(memory=memory, llm=llm)
    return await agent.run(message, bank_id=bank_id)
