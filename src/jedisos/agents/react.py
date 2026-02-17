"""
[JS-E001] jedisos.agents.react
LangGraph 기반 ReAct 에이전트

version: 1.0.0
created: 2026-02-16
modified: 2026-02-17
dependencies: langgraph>=1.0.8, litellm>=1.81.12
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, TypedDict

import structlog
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

if TYPE_CHECKING:
    from jedisos.llm.router import LLMRouter
    from jedisos.memory.hindsight import HindsightMemory

logger = structlog.get_logger()

MAX_TOOL_CALLS = 10


class AgentState(TypedDict):  # [JS-E001.1]
    """ReAct 에이전트 상태."""

    messages: Annotated[list, add_messages]
    memory_context: str
    bank_id: str
    tool_call_count: int


class ReActAgent:  # [JS-E001.2]
    """LangGraph StateGraph 기반 ReAct 에이전트.

    recall → reason → act → observe → retain 루프를 실행합니다.
    """

    def __init__(
        self,
        memory: HindsightMemory,
        llm: LLMRouter,
        tools: list[Any] | None = None,
        identity_prompt: str = "",
    ) -> None:
        self.memory = memory
        self.llm = llm
        self.tools = tools or []
        self.identity_prompt = identity_prompt
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:  # [JS-E001.3]
        """LangGraph StateGraph 구성."""
        builder = StateGraph(AgentState)

        builder.add_node("recall_memory", self._recall_memory)
        builder.add_node("llm_reason", self._llm_reason)
        builder.add_node("execute_tools", self._execute_tools)
        builder.add_node("retain_memory", self._retain_memory)

        builder.add_edge(START, "recall_memory")
        builder.add_edge("recall_memory", "llm_reason")
        builder.add_conditional_edges(
            "llm_reason",
            self._should_continue,
            {"execute_tools": "execute_tools", "retain_memory": "retain_memory"},
        )
        builder.add_edge("execute_tools", "llm_reason")
        builder.add_edge("retain_memory", END)

        return builder.compile()

    async def _recall_memory(self, state: AgentState) -> dict:  # [JS-E001.4]
        """관련 메모리 검색."""
        last_msg = state["messages"][-1]
        query = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

        try:
            result = await self.memory.recall(query, bank_id=state.get("bank_id"))
            context = str(result) if result else ""
        except Exception as e:
            logger.warning("recall_failed_continuing", error=str(e))
            context = ""

        return {"memory_context": context}

    async def _llm_reason(self, state: AgentState) -> dict:  # [JS-E001.5]
        """LLM으로 추론."""
        system_parts: list[str] = []
        if self.identity_prompt:
            system_parts.append(self.identity_prompt)
        if state.get("memory_context"):
            system_parts.append(f"관련 기억:\n{state['memory_context']}")

        messages: list[dict[str, Any]] = []
        if system_parts:
            messages.append({"role": "system", "content": "\n\n".join(system_parts)})

        for msg in state["messages"]:
            if hasattr(msg, "type"):
                messages.append({"role": msg.type, "content": msg.content})
            else:
                messages.append(msg)

        tool_defs = [t.to_dict() for t in self.tools] if self.tools else None
        response = await self.llm.complete(messages, tools=tool_defs)

        choice = response["choices"][0]["message"]
        return {"messages": [choice]}

    def _should_continue(self, state: AgentState) -> str:  # [JS-E001.6]
        """도구 호출 여부 판단."""
        last = state["messages"][-1]
        tool_calls = getattr(last, "tool_calls", None) or (
            last.get("tool_calls") if isinstance(last, dict) else None
        )

        count = state.get("tool_call_count", 0)
        if tool_calls and count < MAX_TOOL_CALLS:
            return "execute_tools"
        return "retain_memory"

    async def _execute_tools(self, state: AgentState) -> dict:  # [JS-E001.7]
        """도구 실행. 실제 구현은 Phase 5에서 MCP 연동 후 완성."""
        count = state.get("tool_call_count", 0)
        return {"tool_call_count": count + 1}

    async def _retain_memory(self, state: AgentState) -> dict:  # [JS-E001.8]
        """대화 내용을 메모리에 저장."""
        conversation = "\n".join(
            f"{m.type if hasattr(m, 'type') else 'unknown'}: "
            f"{m.content if hasattr(m, 'content') else str(m)}"
            for m in state["messages"]
        )
        try:
            await self.memory.retain(conversation, bank_id=state.get("bank_id"))
        except Exception as e:
            logger.warning("retain_failed_continuing", error=str(e))
        return {}

    async def run(self, user_message: str, bank_id: str = "") -> str:  # [JS-E001.9]
        """에이전트 실행 (편의 메서드)."""
        initial_state: AgentState = {
            "messages": [{"role": "user", "content": user_message}],
            "memory_context": "",
            "bank_id": bank_id or "jedisos-default",
            "tool_call_count": 0,
        }
        result = await self.graph.ainvoke(initial_state)
        last = result["messages"][-1]
        return last.content if hasattr(last, "content") else str(last)
