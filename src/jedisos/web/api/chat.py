"""
[JS-W002] jedisos.web.api.chat
WebSocket 기반 실시간 채팅 API

version: 1.1.0
created: 2026-02-18
modified: 2026-02-18
dependencies: fastapi>=0.115
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = structlog.get_logger()

router = APIRouter()

# bank_id별 대화 히스토리 캐시 (최근 N턴 유지)
_MAX_HISTORY_TURNS = 20
_conversation_history: dict[str, list[dict[str, str]]] = defaultdict(list)


class ChatRequest(BaseModel):  # [JS-W002.1]
    """채팅 요청 모델."""

    message: str
    bank_id: str = "default"
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

    클라이언트가 JSON 메시지를 보내면 에이전트 응답을 스트리밍합니다.
    형식: {"message": "안녕", "bank_id": "default"}
    응답: {"type": "stream", "content": "토큰"} 또는
          {"type": "done", "response": "전체 응답", "bank_id": "..."}
    """
    await manager.connect(websocket)
    try:
        # SecVault 상태 전송
        await _send_vault_status(websocket)

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            # SecVault 비밀번호 설정/해제 처리
            if msg_type == "vault_setup":
                await _handle_vault_setup(websocket, data.get("password", ""))
                continue
            if msg_type == "vault_unlock":
                await _handle_vault_unlock(websocket, data.get("password", ""))
                continue

            message = data.get("message", "")
            bank_id = data.get("bank_id", "default")

            if not message:
                await websocket.send_json({"error": "빈 메시지입니다."})
                continue

            logger.info("websocket_message", text_len=len(message), bank_id=bank_id)

            try:
                agent = _get_or_create_agent()
                if agent is None:
                    await websocket.send_json({"error": "서버가 아직 초기화되지 않았습니다."})
                    continue

                history = _get_history(bank_id)
                _add_to_history(bank_id, "user", message)

                full_response = ""
                async for chunk in agent.run_stream(message, bank_id=bank_id, history=history):
                    full_response += chunk
                    await websocket.send_json({"type": "stream", "content": chunk})

                _add_to_history(bank_id, "assistant", full_response)
                await websocket.send_json(
                    {
                        "type": "done",
                        "response": full_response,
                        "bank_id": bank_id,
                    }
                )
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


def _get_history(bank_id: str) -> list[dict[str, str]]:  # [JS-W002.7]
    """bank_id별 대화 히스토리를 반환합니다."""
    return _conversation_history[bank_id]


def _add_to_history(bank_id: str, role: str, content: str) -> None:  # [JS-W002.8]
    """대화 히스토리에 메시지를 추가합니다."""
    history = _conversation_history[bank_id]
    history.append({"role": role, "content": content})
    # 최대 턴 수 초과 시 오래된 메시지 제거 (2개씩 = user+assistant)
    while len(history) > _MAX_HISTORY_TURNS * 2:
        history.pop(0)


def clear_all_history() -> None:  # [JS-W002.10]
    """모든 대화 히스토리를 초기화합니다. 스킬 추가/삭제 시 호출."""
    _conversation_history.clear()
    logger.info("conversation_history_cleared")


def _get_or_create_agent() -> Any:  # [JS-W002.9]
    """캐시된 에이전트를 반환하거나 새로 생성합니다."""
    from jedisos.web.app import get_app_state

    state = get_app_state()

    # 이미 캐시된 에이전트가 있으면 재사용
    cached = state.get("_cached_agent")
    if cached is not None:
        return cached

    memory = state.get("memory")
    llm = state.get("llm")
    if not memory or not llm:
        return None

    from jedisos.agents.react import ReActAgent
    from jedisos.llm.prompts import get_identity_prompt

    agent = ReActAgent(
        memory=memory,
        llm=llm,
        tools=state.get("builtin_tools", []),
        tool_executor=state.get("tool_executor"),
        identity_prompt=get_identity_prompt(),
        dspy_bridge=state.get("dspy_bridge"),
    )
    state["_cached_agent"] = agent
    logger.info("agent_cached", tool_count=len(agent.tools))
    return agent


async def _run_agent(message: str, bank_id: str, model: str | None = None) -> str:
    """에이전트를 실행합니다. 대화 히스토리를 포함합니다."""
    agent = _get_or_create_agent()
    if agent is None:
        return "서버가 아직 초기화되지 않았습니다."

    # 이전 대화 히스토리 포함
    history = _get_history(bank_id)
    _add_to_history(bank_id, "user", message)

    response = await agent.run(message, bank_id=bank_id, history=history)

    _add_to_history(bank_id, "assistant", response)
    return response


async def _send_vault_status(websocket: WebSocket) -> None:  # [JS-W002.11]
    """WebSocket 연결 시 SecVault 상태를 전송합니다."""
    from jedisos.web.app import get_app_state

    state = get_app_state()
    vault_client = state.get("vault_client")
    if vault_client is None:
        return

    try:
        status = await vault_client.status()
        await websocket.send_json(
            {
                "type": "vault_status",
                "status": status.get("status", "unknown"),
            }
        )
    except Exception as e:
        logger.warning("vault_status_send_failed", error=str(e))


async def _handle_vault_setup(websocket: WebSocket, password: str) -> None:  # [JS-W002.12]
    """SecVault 최초 비밀번호 설정을 처리합니다."""
    from jedisos.web.app import get_app_state

    state = get_app_state()
    vault_client = state.get("vault_client")
    if vault_client is None:
        await websocket.send_json(
            {"type": "vault_error", "error": "SecVault가 초기화되지 않았습니다."}
        )
        return

    ok = await vault_client.setup(password)
    if ok:
        state["vault_status"] = "unlocked"
        await websocket.send_json({"type": "vault_status", "status": "unlocked"})
    else:
        await websocket.send_json({"type": "vault_error", "error": "비밀번호 설정에 실패했습니다."})


async def _handle_vault_unlock(websocket: WebSocket, password: str) -> None:  # [JS-W002.13]
    """SecVault 잠금 해제를 처리합니다."""
    from jedisos.web.app import get_app_state

    state = get_app_state()
    vault_client = state.get("vault_client")
    if vault_client is None:
        await websocket.send_json(
            {"type": "vault_error", "error": "SecVault가 초기화되지 않았습니다."}
        )
        return

    ok = await vault_client.unlock(password)
    if ok:
        state["vault_status"] = "unlocked"
        await websocket.send_json({"type": "vault_status", "status": "unlocked"})
    else:
        await websocket.send_json({"type": "vault_error", "error": "비밀번호가 틀립니다."})
