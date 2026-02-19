"""
[JS-E001] jedisos.agents.react
LangGraph 기반 ReAct 에이전트

version: 1.1.0
created: 2026-02-16
modified: 2026-02-18
dependencies: langgraph>=1.0.8, litellm>=1.81.12
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Annotated, Any, TypedDict

import structlog
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from jedisos.llm.router import LLMRouter
    from jedisos.memory.zvec_memory import ZvecMemory
    from jedisos.security.audit import AuditLogger
    from jedisos.security.pdp import PolicyDecisionPoint

logger = structlog.get_logger()

MAX_TOOL_CALLS = 10

# 의도별 도구 필터링 — 불필요한 도구를 제공하면 LLM이 도구를 남용함
# "chat"/"question" → 메모리 도구 + 동적 스킬만 (스킬 관리 도구 제외)
_SKILL_MGMT_TOOLS = frozenset({"create_skill", "list_skills", "delete_skill", "upgrade_skill"})
_MEMORY_ONLY_INTENTS = frozenset({"chat", "question"})

# 백그라운드 태스크 참조 (GC 방지)
_background_tasks: set[asyncio.Task[None]] = set()

# LangGraph 메시지 타입 → OpenAI 역할 매핑
_ROLE_MAP = {"human": "user", "ai": "assistant", "system": "system", "tool": "tool"}


def _extract_msg_role_content(msg: Any) -> tuple[str, str]:  # [JS-E001.0]
    """메시지에서 role과 content를 추출합니다. 객체/dict 형식 모두 지원."""
    if hasattr(msg, "type"):
        role = _ROLE_MAP.get(msg.type, msg.type)
        content = msg.content if hasattr(msg, "content") else ""
    elif isinstance(msg, dict):
        raw_role = msg.get("role", "unknown")
        role = _ROLE_MAP.get(raw_role, raw_role)
        content = msg.get("content", "")
    else:
        role = "unknown"
        content = str(msg)
    return role, content or ""


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
        memory: ZvecMemory,
        llm: LLMRouter,
        tools: list[Any] | None = None,
        identity_prompt: str = "",
        tool_executor: Any | None = None,
        pdp: PolicyDecisionPoint | None = None,
        audit: AuditLogger | None = None,
    ) -> None:
        self.memory = memory
        self.llm = llm
        self.tools = tools or []
        self.identity_prompt = identity_prompt
        self.tool_executor = tool_executor
        self.pdp = pdp
        self.audit = audit
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
        """관련 메모리 검색. 최근 사용자 메시지를 기반으로 검색. 3초 타임아웃."""
        query_parts: list[str] = []
        for msg in reversed(state["messages"]):
            role, content = _extract_msg_role_content(msg)
            if role == "user" and content:
                query_parts.append(content)
                if len(query_parts) >= 2:
                    break

        query = " ".join(reversed(query_parts)) if query_parts else ""
        if not query:
            return {"memory_context": ""}

        try:
            result = await asyncio.wait_for(
                self.memory.recall(query, bank_id=state.get("bank_id")), timeout=3.0
            )
            context = result.get("context", "") if isinstance(result, dict) else str(result)
        except TimeoutError:
            logger.warning("recall_timeout", bank_id=state.get("bank_id"))
            context = ""
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
                role = _ROLE_MAP.get(msg.type, msg.type)
                msg_dict: dict[str, Any] = {"role": role, "content": msg.content}
                # tool_calls가 있으면 OpenAI 형식으로 변환하여 포함
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    msg_dict["tool_calls"] = [
                        self._to_openai_tool_call(tc) for tc in msg.tool_calls
                    ]
                # tool 응답이면 tool_call_id 포함
                if hasattr(msg, "tool_call_id") and msg.tool_call_id:
                    msg_dict["tool_call_id"] = msg.tool_call_id
                messages.append(msg_dict)
            else:
                # dict 형태도 역할 매핑 + tool_calls 형식 변환
                if isinstance(msg, dict):
                    if msg.get("role") in _ROLE_MAP:
                        msg = {**msg, "role": _ROLE_MAP[msg["role"]]}
                    if msg.get("tool_calls"):
                        msg = {
                            **msg,
                            "tool_calls": [
                                self._to_openai_tool_call(tc) for tc in msg["tool_calls"]
                            ],
                        }
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
        """도구 실행. tool_executor 또는 내장 도구 핸들러를 통해 실행."""
        count = state.get("tool_call_count", 0)
        last = state["messages"][-1]
        tool_calls = getattr(last, "tool_calls", None) or (
            last.get("tool_calls") if isinstance(last, dict) else None
        )

        if not tool_calls:
            return {"tool_call_count": count + 1}

        tool_results: list[dict[str, Any]] = []
        for tc in tool_calls:
            tool_name, tool_id, args = self._parse_tool_call(tc)
            result = await self._call_tool(tool_name, args)

            tool_results.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": json.dumps(result, ensure_ascii=False)
                    if isinstance(result, dict)
                    else str(result),
                }
            )
            logger.info(
                "tool_executed",
                tool=tool_name,
                call_id=tool_id,
                args_keys=list(args.keys()),
                result_ok=result.get("ok") if isinstance(result, dict) else None,
            )

        return {"messages": tool_results, "tool_call_count": count + 1}

    @staticmethod
    def _to_openai_tool_call(tc: Any) -> dict[str, Any]:  # [JS-E001.5a]
        """LangGraph tool_call을 OpenAI 형식으로 변환합니다.

        LangGraph: {"name": ..., "args": {...}, "id": ..., "type": "tool_call"}
        OpenAI:    {"id": ..., "type": "function", "function": {"name": ..., "arguments": "..."}}
        """
        if isinstance(tc, dict):
            name = tc.get("name", "")
            args = tc.get("args", {})
            tool_id = tc.get("id", "")
            # 이미 OpenAI 형식이면 그대로 반환
            if "function" in tc:
                return tc
        else:
            name = getattr(tc, "name", "")
            args = getattr(tc, "args", {})
            tool_id = getattr(tc, "id", "")
            if hasattr(tc, "function"):
                return {
                    "id": tool_id,
                    "type": "function",
                    "function": {
                        "name": getattr(tc.function, "name", ""),
                        "arguments": getattr(tc.function, "arguments", "{}"),
                    },
                }

        args_str = json.dumps(args, ensure_ascii=False) if isinstance(args, dict) else str(args)
        return {
            "id": tool_id,
            "type": "function",
            "function": {"name": name, "arguments": args_str},
        }

    @staticmethod
    def _parse_tool_call(tc: Any) -> tuple[str, str, dict[str, Any]]:  # [JS-E001.7b]
        """도구 호출을 파싱합니다. OpenAI/LangGraph 형식 모두 지원."""
        if isinstance(tc, dict):
            # LangGraph ToolCall 형식: {"name": ..., "args": ..., "id": ...}
            if "name" in tc and "args" in tc:
                return tc["name"], tc.get("id", ""), tc.get("args", {})
            # OpenAI 형식: {"id": ..., "function": {"name": ..., "arguments": ...}}
            func = tc.get("function", {})
            raw_args = func.get("arguments", "{}")
            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            return func.get("name", ""), tc.get("id", ""), args

        # 객체 형식 (LangGraph ToolCall 또는 OpenAI)
        name = getattr(tc, "name", "")
        tool_id = getattr(tc, "id", "")
        args = getattr(tc, "args", None)
        if args is not None:
            return name, tool_id, args if isinstance(args, dict) else {}

        # OpenAI 객체: function.name, function.arguments
        func = getattr(tc, "function", None)
        if func:
            name = getattr(func, "name", "")
            raw_args = getattr(func, "arguments", "{}")
            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            return name, tool_id, args

        return name, tool_id, {}

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:  # [JS-E001.7a]
        """단일 도구를 호출합니다. PDP 검사 후 tool_executor에 위임."""
        # PDP 정책 검사
        if self.pdp:
            allowed, reason = self.pdp.check_tool_access(name)
            if self.audit:
                self.audit.log_tool_call(tool_name=name, allowed=allowed, reason=reason)
            if not allowed:
                return {"error": reason}
        elif self.audit:
            self.audit.log_tool_call(tool_name=name, allowed=True, reason="PDP 미설정")

        if self.tool_executor:
            try:
                return await self.tool_executor(name, arguments)
            except Exception as e:
                logger.error("tool_execution_failed", tool=name, error=str(e))
                return {"error": str(e)}
        return {"error": f"도구 '{name}'의 실행기가 설정되지 않았습니다."}

    async def _retain_memory(self, state: AgentState) -> dict:  # [JS-E001.8]
        """대화 내용을 메모리에 저장 (백그라운드, 현재 턴만)."""
        # 마지막 user+assistant 턴만 저장 (눈덩이 방지)
        parts: list[str] = []
        for msg in reversed(state["messages"]):
            role, content = _extract_msg_role_content(msg)
            if role in ("user", "assistant") and content:
                parts.append(f"{role}: {content}")
                if role == "user":
                    break
        conversation = "\n".join(reversed(parts))

        async def _bg_retain() -> None:
            try:
                await self.memory.retain(conversation, bank_id=state.get("bank_id"))
            except Exception as e:
                logger.warning("retain_failed_continuing", error=str(e))

        task = asyncio.create_task(_bg_retain())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        return {}

    async def run(  # [JS-E001.9]
        self,
        user_message: str,
        bank_id: str = "",
        history: list[dict[str, str]] | None = None,
    ) -> str:
        """에이전트 실행 (편의 메서드)."""
        messages: list[dict[str, str]] = []
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        initial_state: AgentState = {
            "messages": messages,
            "memory_context": "",
            "bank_id": bank_id or "jedisos-default",
            "tool_call_count": 0,
        }
        result = await self.graph.ainvoke(initial_state)
        last = result["messages"][-1]
        return last.content if hasattr(last, "content") else str(last)

    async def run_stream(  # [JS-E001.10]
        self,
        user_message: str,
        bank_id: str = "",
        history: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[str]:
        """스트리밍 에이전트 실행. 토큰 단위로 yield합니다.

        도구 호출이 필요한 경우 도구 실행 후 최종 응답을 스트리밍합니다.
        recall에 3초 타임아웃을 적용하여 응답 지연을 최소화합니다.
        """
        bid = bank_id or "jedisos-default"

        # 1. recall_memory (3초 타임아웃 — 느린 recall이 응답을 막지 않도록)
        messages: list[dict[str, str]] = []
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        query_parts = [user_message]
        if history:
            for msg in reversed(history):
                if msg.get("role") == "user" and msg.get("content"):
                    query_parts.append(msg["content"])
                    if len(query_parts) >= 2:
                        break

        query = " ".join(reversed(query_parts))
        memory_context = ""
        try:
            result = await asyncio.wait_for(self.memory.recall(query, bank_id=bid), timeout=3.0)
            memory_context = result.get("context", "") if isinstance(result, dict) else str(result)
        except TimeoutError:
            logger.warning("recall_timeout", bank_id=bid)
        except Exception as e:
            logger.warning("recall_failed_continuing", error=str(e))

        # 2. 시스템 프롬프트 구성
        system_parts: list[str] = []
        if self.identity_prompt:
            system_parts.append(self.identity_prompt)
        if memory_context:
            system_parts.append(f"관련 기억:\n{memory_context}")

        llm_messages: list[dict[str, Any]] = []
        if system_parts:
            llm_messages.append({"role": "system", "content": "\n\n".join(system_parts)})
        for msg in messages:
            role = _ROLE_MAP.get(msg.get("role", ""), msg.get("role", ""))
            llm_messages.append({"role": role, "content": msg.get("content", "")})

        # 2.5. 의도 분류 (소형 모델 — 저렴/빠름)
        llm_role = "chat"
        intent = "chat"
        try:
            raw_intent = await self.llm.complete_text(
                prompt=f"사용자: {user_message}",
                system=(
                    "사용자 메시지의 의도를 한 단어로만 분류하세요. "
                    "선택지: chat, question, remember, skill_request, complex\n"
                    "한 단어만 답하세요."
                ),
                role="classify",
                max_tokens=10,
                temperature=0.0,
            )
            intent = raw_intent.strip().lower().split()[0] if raw_intent else "chat"
            if intent == "complex":
                llm_role = "reason"
            elif intent == "skill_request":
                llm_role = "code"
            logger.info("intent_classified", intent=intent, llm_role=llm_role)
        except Exception as e:
            logger.debug("intent_classify_failed", error=str(e))

        # 2.6. 의도별 도구 필터링 — 불필요한 도구 호출 방지 (47초→6초)
        if self.tools:
            if intent in _MEMORY_ONLY_INTENTS:
                # chat/question → 스킬 관리 도구 제외, 메모리 + 동적 스킬만
                filtered = [
                    t
                    for t in self.tools
                    if t.to_dict().get("function", {}).get("name") not in _SKILL_MGMT_TOOLS
                ]
                tool_defs = [t.to_dict() for t in filtered] if filtered else None
            else:
                tool_defs = [t.to_dict() for t in self.tools]
        else:
            tool_defs = None

        # 3. 스트리밍 LLM 호출
        #    - 텍스트 응답: 토큰 즉시 yield (실시간 스트리밍)
        #    - 도구 호출: 델타 누적 → 실행 → 다시 스트리밍 호출
        content = ""
        tool_call_count = 0

        while True:
            text_buf = ""
            tool_calls_map: dict[int, dict[str, str]] = {}
            has_tool_calls = False

            async for chunk in self.llm.stream(llm_messages, tools=tool_defs, role=llm_role):
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})

                # 텍스트 토큰 → 즉시 yield
                token = delta.get("content", "")
                if token:
                    text_buf += token
                    content += token
                    yield token

                # 도구 호출 델타 → 누적
                if delta.get("tool_calls"):
                    has_tool_calls = True
                    for tc_delta in delta["tool_calls"]:
                        idx = tc_delta.get("index", 0)
                        if idx not in tool_calls_map:
                            tool_calls_map[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc_delta.get("id"):
                            tool_calls_map[idx]["id"] = tc_delta["id"]
                        func = tc_delta.get("function", {})
                        if func.get("name"):
                            tool_calls_map[idx]["name"] = func["name"]
                        if func.get("arguments"):
                            tool_calls_map[idx]["arguments"] += func["arguments"]

            # 도구 호출 없음 → 텍스트 스트리밍 완료, 루프 종료
            if not has_tool_calls or tool_call_count >= MAX_TOOL_CALLS:
                break

            # 도구 호출 처리
            tool_call_count += 1
            tool_calls = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in tool_calls_map.values()
            ]

            assistant_msg: dict[str, Any] = {"role": "assistant", "content": text_buf or ""}
            assistant_msg["tool_calls"] = tool_calls
            llm_messages.append(assistant_msg)

            for tc in tool_calls:
                tool_name, tool_id, args = self._parse_tool_call(tc)
                tool_result = await self._call_tool(tool_name, args)
                llm_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": json.dumps(tool_result, ensure_ascii=False)
                        if isinstance(tool_result, dict)
                        else str(tool_result),
                    }
                )
                logger.info("tool_executed", tool=tool_name, call_id=tool_id)

        # 4. retain_memory (백그라운드) — 현재 턴만 저장 (눈덩이 방지)
        retain_parts = [f"user: {user_message}"]
        if content:
            retain_parts.append(f"assistant: {content}")
        full_conversation = "\n".join(retain_parts)

        async def _bg_retain() -> None:
            try:
                await self.memory.retain(full_conversation, bank_id=bid)
            except Exception as e:
                logger.warning("retain_failed_continuing", error=str(e))

        task = asyncio.create_task(_bg_retain())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
