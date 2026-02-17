# LangGraph 사용법 가이드

> JediSOS에서 LangGraph를 활용한 멀티-에이전트 워크플로우 구축을 위한 완전 가이드
> LangGraph v1.0.8 기준

---

## 1. 핵심 개념

LangGraph는 **상태 기반 그래프** 패러다임으로 복잡한 에이전트 워크플로우를 구축한다.

### 1.1 StateGraph = 노드 + 엣지 + 공유 상태

```
    ┌─────────┐
    │  START  │
    └────┬────┘
         │
    ┌────▼──────┐
    │  node_a   │  State (shared)
    │ ─────────▶│  {"messages": [...],
    │ ◀─────────│   "count": 5, ...}
    └────┬──────┘
         │
    ┌────▼──────┐
    │  node_b   │
    └────┬──────┘
         │
    ┌────▼────┐
    │   END    │
    └──────────┘
```

**핵심 원리:**
- **노드(Node)**: 상태를 읽고 부분 상태를 반환하는 함수 `State → Partial<State>`
- **엣지(Edge)**: 노드 간 제어 흐름 연결
- **상태(State)**: 모든 노드가 공유하는 dict (TypedDict 형식 권장)
- **리듀서(Reducer)**: 상태 업데이트 시 병합 규칙 정의

### 1.2 노드 시그니처: 부분 상태만 반환

```python
def my_node(state: State) -> dict:
    """노드는 State 전체를 읽지만, 변경된 부분만 반환"""
    return {"updated_field": "new_value"}  # 반환값이 병합됨

# LangGraph의 병합 로직:
# new_state = {**old_state, **node_return}  # 복잡한 리듀서는 다름
```

### 1.3 리듀서 패턴: Annotated

여러 노드가 같은 채널에 쓸 때 병합 방식을 정의한다:

```python
from typing import Annotated
import operator
from langgraph.graph import add_messages

class State(TypedDict):
    messages: Annotated[list, add_messages]        # 메시지 누적
    count: int                                      # LastValue (기본)
    items: Annotated[list, operator.add]           # 리스트 연결
    config: Annotated[dict, lambda a, b: {**a, **b}]  # 커스텀 병합
```

| 리듀서 | 동작 | 예시 |
|------|------|------|
| `add_messages` | 메시지 ID 기반 중복 제거 + 추가 | 채팅 히스토리 |
| `operator.add` | 리스트 연결 | `[a] + [b]` |
| `operator.or_` | 비트 OR 연결 | 플래그 누적 |
| LastValue (기본) | 덮어쓰기 | 최신값만 유지 |
| 커스텀 함수 | 사용자 정의 병합 | dict merge 등 |

---

## 2. State 정의

### 2.1 TypedDict 방식 (권장)

```python
from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph import add_messages
import operator

class State(TypedDict):
    """LangGraph 상태 정의"""
    messages: Annotated[list, add_messages]      # 리듀서: 메시지 누적
    memory_context: str                           # 기억 검색 결과
    bank_id: str                                  # 사용자 ID (Hindsight 뱅크)
    tool_call_count: int                          # 도구 호출 횟수
    reasoning: str                                # 에이전트 추론 과정
```

**TypedDict의 장점:**
- 타입 체킹 (mypy 호환)
- IDE 자동완성
- 런타임 성능 우수
- 리듀서 인라인 정의 가능

### 2.2 JediSOS AgentState 예시

```python
from typing import Annotated
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages

class AgentState(TypedDict):
    """JediSOS 에이전트 상태"""
    # 메시지 관리
    messages: Annotated[list[BaseMessage], add_messages]

    # 메모리 연동
    memory_context: str            # recall 결과
    bank_id: str                   # Hindsight 뱅크 ID

    # 실행 제어
    tool_call_count: int           # 도구 호출 횟수 (무한 루프 방지)
    max_iterations: int            # 최대 반복 횟수

    # 중간 결과 저장
    reasoning: str | None          # 추론 프로세스
    next_action: str               # "recall" | "reason" | "tools" | "retain" | "end"

    # 메타데이터
    user_id: str                   # 요청자 ID
    conversation_id: str           # 대화 세션 ID
    timestamp: str                 # 작업 시작 시간
```

### 2.3 리듀서 종류

```python
# 1. add_messages (LangGraph 전용, 메시지 최적화)
messages: Annotated[list[BaseMessage], add_messages]
# 특징: ID 기반 중복 제거, RemoveMessage 지원, langchain BaseMessage 최적화

# 2. operator.add (리스트 연결)
items: Annotated[list, operator.add]
# [a] + [b] = [a, b]

# 3. LastValue (기본값, 덮어쓰기)
status: str  # 또는 status: Annotated[str, operator.setitem]
# 최신값만 유지, 이전값은 버려짐

# 4. 커스텀 함수
def merge_dicts(a: dict, b: dict) -> dict:
    result = a.copy() if a else {}
    if b:
        result.update(b)
    return result

config: Annotated[dict, merge_dicts]

# 5. operator.or_ (플래그/세트)
flags: Annotated[set, operator.or_]
# {a} | {b} = {a, b}
```

---

## 3. 그래프 구성

### 3.1 노드 추가: add_node()

```python
from langgraph.graph import StateGraph, START, END

builder = StateGraph(State)

# 방법 1: 함수명 자동 추론
def recall_node(state: State) -> dict:
    """기억 검색 노드"""
    return {"memory_context": "..."}

builder.add_node(recall_node)  # 노드명 = "recall_node"

# 방법 2: 명시적 이름
builder.add_node("recall", recall_node)

# 방법 3: 람다 (간단한 경우)
builder.add_node("increment", lambda s: {"count": s.get("count", 0) + 1})

# 방법 4: 재시도 정책 포함
from langgraph.types import RetryPolicy

builder.add_node(
    "api_call",
    api_node,
    retry_policy=RetryPolicy(
        initial_interval=0.5,
        backoff_factor=2.0,
        max_attempts=3,
        retry_on=TimeoutError
    )
)
```

### 3.2 엣지 추가: add_edge()

```python
# 선형 흐름
builder.add_edge(START, "recall")          # 시작 → recall 노드
builder.add_edge("recall", "reason")       # recall → reason 노드
builder.add_edge("reason", "tools")        # reason → tools 노드
builder.add_edge("tools", "recall")        # 루프: tools → recall
builder.add_edge("reason", END)            # reason → 종료

# 또는 체인 방식
builder.add_edge(START, "recall")
builder.add_edge("recall", "reason")
builder.add_edge("reason", END)
```

### 3.3 조건부 엣지: add_conditional_edges()

```python
# 라우팅 함수
def route_after_reason(state: State) -> str:
    """추론 결과에 따라 다음 노드 결정"""
    last_msg = state["messages"][-1]

    # LLM이 도구를 호출했는가?
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "tools"      # 도구 노드로
    else:
        return "retain"     # 기억 저장 노드로

# 조건부 엣지 등록
builder.add_conditional_edges(
    source="reason",                    # 어디서 나가는가
    path=route_after_reason,            # 라우팅 함수
    path_map={
        "tools": "tools",               # 반환값 → 노드명 매핑
        "retain": "retain",
    }
)

# 또는 직접 NodeEnd/END 사용
def route_to_end(state: State) -> str:
    if state["tool_call_count"] > 5:
        return END  # 루프 종료
    return "reason"

builder.add_conditional_edges("tools", route_to_end)
```

### 3.4 동적 라우팅: Send

```python
from langgraph.types import Send

def scatter_node(state: State):
    """여러 노드에 병렬 전송"""
    items = state["items"]
    return [
        Send("process", {"item": item})
        for item in items
    ]

def process_node(state: State) -> dict:
    """개별 아이템 처리"""
    return {"results": [state["item"] * 2]}

builder.add_node("scatter", scatter_node)
builder.add_node("process", process_node)
builder.add_conditional_edges(START, scatter_node)  # START에서 scatter로
builder.add_edge("process", "gather")               # 모두 gather로 수렴
```

### 3.5 그래프 컴파일: compile()

```python
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import AsyncPostgresSaver

# 개발용: 메모리 체크포인터
checkpointer = InMemorySaver()
graph = builder.compile(
    checkpointer=checkpointer,
    interrupt_before=["approval_node"],    # 이 노드 실행 전 중단
    interrupt_after=["reason"],            # 이 노드 실행 후 중단
    debug=True                             # 디버그 출력
)

# 프로덕션용: PostgreSQL 체크포인터
async def setup_graph():
    async with await AsyncPostgresSaver.acreate_pool(
        "postgresql://user:pass@localhost/langgraph_db"
    ) as checkpointer:
        await checkpointer.asetup()  # 테이블 자동 생성

        graph = builder.compile(checkpointer=checkpointer)
        return graph
```

**compile() 시그니처:**
```python
def compile(
    self,
    checkpointer: Checkpointer = None,
    *,
    cache: BaseCache | None = None,
    store: BaseStore | None = None,
    interrupt_before: All | list[str] | None = None,
    interrupt_after: All | list[str] | None = None,
    debug: bool = False,
    name: str | None = None,
) -> CompiledStateGraph:
```

---

## 4. Prebuilt 컴포넌트

### 4.1 ToolNode: 도구 실행

```python
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool

@tool
def search_memory(query: str) -> str:
    """과거 기억에서 정보를 검색한다"""
    return f"Found info about: {query}"

@tool
def save_note(note: str) -> str:
    """메모를 저장한다"""
    return f"Saved: {note}"

# ToolNode 생성
tools = [search_memory, save_note]
tool_node = ToolNode(tools)

# 그래프에 추가
builder.add_node("tools", tool_node)
```

**ToolNode 시그니처:**
```python
class ToolNode(Generic[StateT, ContextT]):
    def __init__(
        self,
        tools: Sequence[BaseTool],
        name: str = "tools",
        *,
        on_error: Callable[[Exception], str] | None = None,
        tags: Sequence[str] | None = None,
    ) -> None:
```

### 4.2 tools_condition: 도구 호출 라우팅

```python
from langgraph.prebuilt import tools_condition
from langgraph.graph import END

def agent_node(state: State) -> dict:
    """LLM 추론 노드"""
    response = llm.invoke(state["messages"])
    return {"messages": [response]}

# 자동으로 tool_calls 확인하여 라우팅
builder.add_node("agent", agent_node)
builder.add_node("tools", tool_node)

builder.add_edge(START, "agent")
builder.add_conditional_edges(
    "agent",
    tools_condition,  # 도구 호출 있으면 "tools", 없으면 END
    {
        "tools": "tools",
        END: END,
    }
)
builder.add_edge("tools", "agent")  # 도구 실행 후 다시 에이전트로
```

**tools_condition 로직:**
```python
def tools_condition(state: dict) -> str:
    """마지막 메시지에 tool_calls가 있는가?"""
    msg = state["messages"][-1]
    if hasattr(msg, "tool_calls") and msg.tool_calls:
        return "tools"
    return END
```

### 4.3 InjectedState: 도구에서 상태 접근

```python
from langgraph.prebuilt import InjectedState
from langchain_core.tools import tool
from typing import Annotated

@tool
def save_to_memory(content: str, state: Annotated[dict, InjectedState]) -> str:
    """현재 상태에 접근하는 도구"""
    user_id = state["user_id"]
    return f"Saved to {user_id}'s memory: {content}"

# 도구 호출 시 state가 자동으로 주입됨
```

### 4.4 InjectedStore: 영속 저장소 접근

```python
from langgraph.prebuilt import InjectedStore
from typing import Annotated

@tool
def persist_data(key: str, value: str, store: Annotated[dict, InjectedStore]) -> str:
    """그래프 전체에서 공유하는 저장소"""
    store.put("user_data", key, value)
    return f"Stored {key}"

# compile 시 store 전달
graph = builder.compile(
    checkpointer=checkpointer,
    store=my_store  # 모든 도구가 접근 가능
)
```

### 4.5 create_react_agent: 고수준 빌더

```python
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI

model = ChatOpenAI(model="gpt-4-turbo", temperature=0)
tools = [search_memory, save_note, api_call]

# 자동으로 ReAct 에이전트 생성 (노드 + 엣지 + 라우팅)
graph = create_react_agent(
    model=model,
    tools=tools,
    max_iterations=10,         # 무한 루프 방지
    state_schema=AgentState,   # 커스텀 상태 (옵션)
    messages_method="messages" # 상태의 메시지 키
)

# 바로 invoke 가능!
result = graph.invoke({"messages": [HumanMessage(content="Hello")]})
```

---

## 5. 체크포인팅 (상태 영속성)

### 5.1 InMemorySaver: 개발용

```python
from langgraph.checkpoint.memory import InMemorySaver

checkpointer = InMemorySaver()

# compile 시 전달
graph = builder.compile(checkpointer=checkpointer)

# 스레드별로 상태 유지
config = {"configurable": {"thread_id": "user-123"}}

# 첫 실행
result1 = graph.invoke(
    {"messages": [HumanMessage(content="Hello")]},
    config
)

# 두 번째 실행: 이전 상태 계속됨
result2 = graph.invoke(
    {"messages": [HumanMessage(content="Next")]},
    config
)
# 상태에 "Hello"에 대한 응답이 계속 존재
```

**특징:**
- 프로세스 메모리만 사용 (휘발성)
- 빠르지만 재부팅 시 손실
- 단일 프로세스에서만 작동
- **프로덕션 금지**

### 5.2 AsyncPostgresSaver: 프로덕션

```python
from langgraph.checkpoint.postgres import AsyncPostgresSaver
import asyncio

async def main():
    # 1. 연결 풀 생성
    pool = await AsyncPostgresSaver.acreate_pool(
        "postgresql://jedi:password@db.internal:5432/langgraph_prod",
        max_size=50,  # 동시 연결 수
    )

    # 2. 테이블 생성/마이그레이션
    checkpointer = pool
    await checkpointer.asetup()

    # 3. 그래프 컴파일
    graph = builder.compile(checkpointer=checkpointer)

    # 4. 사용
    config = {"configurable": {"thread_id": "user-456"}}
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Query")]},
        config
    )

    # 5. 정리 (선택)
    # await pool.aclose()  # 또는 with 문 사용

asyncio.run(main())
```

**또는 context manager 사용:**

```python
async def main():
    async with await AsyncPostgresSaver.acreate_pool(
        "postgresql://jedi:password@db.internal/langgraph"
    ) as checkpointer:
        await checkpointer.asetup()
        graph = builder.compile(checkpointer=checkpointer)
        result = await graph.ainvoke(state, config)
        # 자동으로 정리됨
```

### 5.3 thread_id 개념

```python
# 각 사용자/대화마다 고유한 thread_id
import uuid

# 방식 1: UUID
thread_id = str(uuid.uuid4())

# 방식 2: 사용자 + 세션
user_id = "user-123"
session_id = "session-456"
thread_id = f"{user_id}:{session_id}"

# 방식 3: 사용자별 고정 (장기 메모리)
thread_id = f"user-{user_id}"

# 방식 4: 타임스탬프 기반
from datetime import datetime
thread_id = f"conv-{datetime.now().isoformat()}"

# 사용
config = {"configurable": {"thread_id": thread_id}}
result = graph.invoke(state, config)
```

**같은 thread_id로 호출하면:**
- 이전 체크포인트에서 상태 복원
- 메시지 히스토리 누적
- 도구 호출 기록 유지

### 5.4 checkpoint_ns: 네임스페이스 격리

```python
# 같은 thread_id라도 다른 ns는 독립적
config1 = {
    "configurable": {
        "thread_id": "shared-id",
        "checkpoint_ns": "user:123:project:456",  # 경로 형식
    }
}

config2 = {
    "configurable": {
        "thread_id": "shared-id",
        "checkpoint_ns": "user:789:project:456",  # 다른 네임스페이스
    }
}

# 같은 thread_id지만 다른 상태 유지
result1 = graph.invoke(state, config1)
result2 = graph.invoke(state, config2)  # config1과 독립적
```

### 5.5 체크포인트 나열 및 재개

```python
# 모든 체크포인트 나열
config = {"configurable": {"thread_id": "user-123"}}

for checkpoint_tuple in checkpointer.list(config):
    print(f"Step {checkpoint_tuple.metadata['step']}: {checkpoint_tuple.checkpoint['ts']}")

# 특정 체크포인트에서 재개
config_with_id = {
    "configurable": {
        "thread_id": "user-123",
        "checkpoint_id": "abc-123-def",  # 특정 시점
    }
}

result = graph.invoke(new_input, config_with_id)
# 그 시점부터 계속 실행됨
```

---

## 6. Async 패턴

### 6.1 ainvoke: 단일 비동기 실행

```python
import asyncio
from langchain_core.messages import HumanMessage

async def main():
    # compile 이후
    config = {"configurable": {"thread_id": "async-user"}}

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Hello")]},
        config
    )

    print(result["messages"][-1].content)

asyncio.run(main())
```

### 6.2 astream: 스트리밍 (7가지 모드)

```python
async def stream_execution():
    async for chunk in graph.astream(
        {"messages": [HumanMessage(content="Query")]},
        config,
        stream_mode="updates",  # 또는 "values", "messages" 등
    ):
        print(f"Update: {chunk}")

asyncio.run(stream_execution())
```

### 6.3 astream_events: 이벤트 기반 스트리밍

```python
async def stream_events():
    async for event in graph.astream_events(
        {"messages": [HumanMessage(content="Query")]},
        config,
        version="v2",
    ):
        event_type = event["event"]

        if event_type == "on_chain_start":
            print(f"시작: {event['name']}")
        elif event_type == "on_chain_end":
            print(f"종료: {event['name']}")
        elif event_type == "on_llm_stream":
            # 토큰 스트리밍
            print(event["data"]["chunk"].content, end="", flush=True)
        elif event_type == "on_tool_start":
            print(f"도구 실행: {event['name']}")

asyncio.run(stream_events())
```

---

## 7. 스트리밍

### 7.1 StreamMode 종류

| 모드 | 설명 | 출력 예 |
|------|------|--------|
| `updates` | 각 노드의 변경사항만 | `{"reason": {"next_action": "tools"}}` |
| `values` | 각 노드 후 전체 상태 | `{"messages": [...], "count": 5}` |
| `messages` | LLM 토큰 스트리밍 | `(token, metadata)` |
| `checkpoints` | 각 체크포인트 스냅샷 | `{"values": {...}, "next": [...]}` |
| `tasks` | 태스크 시작/종료 | `{"type": "task_end", "task": {...}}` |
| `debug` | checkpoints + tasks | 모든 정보 |
| `custom` | 사용자 정의 데이터 | StreamWriter로 내보낸 것 |

### 7.2 기본 스트리밍

```python
# 동기 버전
for chunk in graph.stream(
    {"messages": [HumanMessage(content="Hello")]},
    config,
    stream_mode="updates",
):
    print(chunk)
    # {"recall": {"memory_context": "..."}}
    # {"reason": {"next_action": "tools"}}
    # {"tools": {"tool_call_result": "..."}}
```

### 7.3 복수 모드 동시 스트리밍

```python
# 여러 모드를 동시에 받기
for chunk in graph.stream(
    state,
    config,
    stream_mode=["updates", "messages"],  # 리스트
):
    mode, data = chunk
    if mode == "updates":
        print(f"Update: {data}")
    elif mode == "messages":
        print(f"Token: {data[0]}")
```

### 7.4 JediSOS 웹소켓 연동 예시

```python
# FastAPI + WebSocket
from fastapi import WebSocket, FastAPI
import asyncio
import json

app = FastAPI()

@app.websocket("/ws/agent/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()

    try:
        while True:
            # 클라이언트에서 메시지 수신
            data = await websocket.receive_json()
            user_input = data["message"]

            # 그래프 스트리밍 시작
            config = {
                "configurable": {
                    "thread_id": f"{user_id}-session",
                }
            }

            async for chunk in graph.astream(
                {"messages": [HumanMessage(content=user_input)]},
                config,
                stream_mode="updates",
            ):
                # 각 노드 업데이트를 클라이언트에 전송
                await websocket.send_json({
                    "type": "update",
                    "data": chunk
                })

            # 최종 결과 전송
            await websocket.send_json({
                "type": "complete",
                "data": "done"
            })

    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        await websocket.close()
```

---

## 8. 에러 처리

### 8.1 RetryPolicy: 자동 재시도

```python
from langgraph.types import RetryPolicy

# 기본 설정
retry_policy = RetryPolicy(
    initial_interval=0.5,      # 첫 재시도까지 0.5초
    backoff_factor=2.0,        # 매번 2배 증가
    max_interval=128.0,        # 최대 128초
    max_attempts=3,            # 최대 3번 시도
    jitter=True,               # 지터 추가 (thundering herd 방지)
    retry_on=Exception,        # 모든 Exception 재시도
)

# 노드에 적용
builder.add_node(
    "api_call",
    api_node,
    retry_policy=retry_policy
)
```

### 8.2 조건부 재시도

```python
# 특정 에러만 재시도
retry_on_timeout = RetryPolicy(
    max_attempts=5,
    retry_on=TimeoutError  # TimeoutError만 재시도
)

retry_on_network = RetryPolicy(
    max_attempts=3,
    retry_on=lambda e: isinstance(e, (ConnectionError, TimeoutError))
)

# 또는 예외 타입 리스트
retry_on_multi = RetryPolicy(
    max_attempts=3,
    retry_on=[TimeoutError, ConnectionError, RuntimeError]
)
```

### 8.3 복수 재시도 정책

```python
# 예외 타입별로 다른 정책
policies = [
    RetryPolicy(
        max_attempts=5,
        initial_interval=0.1,
        retry_on=TimeoutError,  # 타임아웃은 많이 재시도
    ),
    RetryPolicy(
        max_attempts=1,
        retry_on=ValueError,     # ValueError는 한 번만
    ),
]

builder.add_node("sensitive", sensitive_node, retry_policy=policies)
# 첫 번째 일치하는 정책이 적용됨
```

### 8.4 노드 내 에러 처리

```python
def safe_node(state: State) -> dict:
    try:
        result = risky_operation(state)
    except ValueError as e:
        # 폴백
        result = default_operation(state)
    except Exception as e:
        # 로깅 후 재시도 정책에 위임
        logger.error(f"Unexpected error: {e}")
        raise  # RetryPolicy가 자동 재시도

    return {"result": result}

builder.add_node("safe", safe_node)
```

### 8.5 그래프 수준 에러 처리

```python
from langgraph.errors import GraphInterrupt

try:
    result = graph.invoke(state, config)
except GraphInterrupt as e:
    # 사용자 인터럽트
    print(f"Interrupted: {e.interrupts}")
except Exception as e:
    # 다른 에러
    print(f"Execution failed: {e}")
    # 나중에 같은 thread_id로 재시도 가능
    result = graph.invoke(new_input, config)  # 마지막 체크포인트에서 재개
```

---

## 9. Human-in-the-Loop

### 9.1 interrupt 함수

```python
from langgraph.types import interrupt

def approval_node(state: State) -> dict:
    """사용자 승인을 요청하는 노드"""
    action = state["next_action"]

    # 실행을 일시 중단하고 사용자 입력을 기다림
    approval = interrupt(
        value={
            "type": "approval_request",
            "action": action,
            "message": f"Do you approve this action: {action}?"
        }
    )

    # 중단 이후, 사용자가 Command(resume=...)로 재개할 때
    # interrupt의 반환값이 approval이 됨

    if approval.get("approved"):
        return {"approved": True}
    else:
        return {"approved": False, "reason": approval.get("reason")}

builder.add_node("approval", approval_node)
```

### 9.2 interrupt_before / interrupt_after

```python
# compile 시에 자동 중단점 설정
graph = builder.compile(
    checkpointer=checkpointer,
    interrupt_before=["approval_node"],      # 실행 전 중단
    interrupt_after=["tool_execution"],      # 실행 후 중단
)

# 또는 모든 노드
graph = builder.compile(
    checkpointer=checkpointer,
    interrupt_before="*",  # 모든 노드 전에 중단
)

# 사용 흐름
config = {"configurable": {"thread_id": "user-123"}}

# 첫 호출: approval_node 직전에 중단
for event in graph.stream(state, config):
    if "__interrupt__" in event:
        interrupts = event["__interrupt__"]
        print(f"Awaiting input: {interrupts[0].value}")
        break

# 사용자 응답 받은 후
from langgraph.types import Command

user_response = {"approved": True}
resume_command = Command(resume=user_response)

# 중단점에서 재개
for event in graph.stream(resume_command, config):
    print(event)
```

### 9.3 Command로 복잡한 제어

```python
def decision_node(state: State) -> dict | Command:
    """상태 업데이트 + 특정 노드로 이동"""

    if condition1:
        # 상태 업데이트 + 특정 노드로 이동
        return Command(
            update={"status": "processing"},
            goto="tools",  # 이 노드로 직접 이동
        )
    elif condition2:
        # 부모 그래프로 명령 전파
        return Command(
            update={"status": "delegating"},
            graph=Command.PARENT,  # 부모 그래프로
        )
    else:
        # 일반 반환
        return {"status": "continuing"}

# 또는 여러 노드에 병렬 전송
from langgraph.types import Send

def parallel_split(state: State) -> list[Command]:
    items = state["items"]
    return [
        Command(
            goto="process",
            update={"current_item": item}
        )
        for item in items
    ]
```

### 9.4 JediSOS MCP 설치 확인 시나리오

```python
async def mcp_setup_workflow(user_id: str) -> dict:
    """MCP 설치 여부 확인 후 처리"""

    config = {"configurable": {"thread_id": user_id}}

    async def check_mcp_node(state: State) -> dict:
        """MCP 서버 상태 확인"""
        try:
            response = await mcp_client.get_tools()
            return {"mcp_available": True, "tools": response}
        except ConnectionError:
            return {"mcp_available": False}

    async def request_mcp_setup(state: State) -> dict:
        """MCP 설치 요청"""
        if not state["mcp_available"]:
            setup_url = interrupt(
                value={
                    "type": "setup_required",
                    "message": "MCP Server not detected. Please install.",
                    "instructions": "curl -X POST http://localhost:3001/install"
                }
            )

            # 사용자가 Command(resume={"installed": True})로 응답할 때까지 대기
            return {"mcp_setup_requested": True}
        return {"mcp_setup_requested": False}

    builder.add_node("check_mcp", check_mcp_node)
    builder.add_node("request_setup", request_mcp_setup)
    builder.add_edge(START, "check_mcp")

    builder.add_conditional_edges(
        "check_mcp",
        lambda s: "request_setup" if not s["mcp_available"] else END
    )

    graph = builder.compile(checkpointer=checkpointer)

    result = await graph.ainvoke({"messages": []}, config)
    return result
```

---

## 10. 서브그래프

### 10.1 기본 서브그래프

```python
# 서브그래프 정의
def create_subgraph():
    sub_builder = StateGraph(State)

    def process_node(state: State) -> dict:
        return {"count": state["count"] * 2}

    sub_builder.add_node("process", process_node)
    sub_builder.set_entry_point("process")
    sub_builder.set_finish_point("process")

    return sub_builder.compile()

# 부모 그래프에서 사용
parent_builder = StateGraph(State)
subgraph = create_subgraph()

parent_builder.add_node("subgraph", subgraph)  # 컴파일된 그래프를 노드로
parent_builder.add_edge(START, "subgraph")
parent_builder.add_edge("subgraph", END)

parent_graph = parent_builder.compile()
```

### 10.2 상태 매핑 (다른 상태 스키마)

```python
class SubState(TypedDict):
    value: int
    result: int

class ParentState(TypedDict):
    items: list[int]
    results: list[int]

# 서브그래프
def create_sub():
    builder = StateGraph(SubState)

    def process(state: SubState) -> dict:
        return {"result": state["value"] ** 2}

    builder.add_node("process", process)
    builder.set_entry_point("process")
    builder.set_finish_point("process")

    return builder.compile()

# 부모에서 상태 변환
def parent_to_sub(parent_state: ParentState):
    """부모 상태 → 서브 상태"""
    return {"value": parent_state["items"][0]}

def sub_to_parent(parent_state: ParentState, sub_result: SubState):
    """서브 결과 → 부모 상태"""
    return {"results": [sub_result["result"]]}

parent_builder = StateGraph(ParentState)
subgraph = create_sub()

parent_builder.add_node(
    "subgraph",
    subgraph,
    # 상태 매핑은 내부적으로 처리 (수동 래핑 필요한 경우도 있음)
)
parent_builder.add_edge(START, "subgraph")
parent_builder.add_edge("subgraph", END)
```

---

## 11. JediSOS 통합 패턴

### 11.1 ReAct 에이전트: 완전 구현

```python
from langgraph.graph import StateGraph, START, END, add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import RetryPolicy
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
import asyncio

# ============ 1. State 정의 ============
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    memory_context: str
    bank_id: str
    tool_call_count: int
    max_iterations: int

# ============ 2. 도구 정의 ============
@tool
async def search_knowledge(query: str) -> str:
    """기술 지식 검색"""
    return f"Found info about {query}"

@tool
async def call_api(endpoint: str, params: dict) -> str:
    """외부 API 호출"""
    return f"API call to {endpoint}: {params}"

tools = [search_knowledge, call_api]

# ============ 3. 노드 함수 ============
async def recall_node(state: AgentState) -> dict:
    """Step 1: 관련 기억 검색"""
    query = state["messages"][-1].content
    # Hindsight recall 호출
    memories = await hindsight.arecall(
        bank_id=state["bank_id"],
        query=query,
        budget="mid"
    )
    context = "\n".join([f"- {m.text}" for m in memories])

    return {"memory_context": context}

async def reason_node(state: AgentState) -> dict:
    """Step 2: LLM 추론 (도구 호출 여부 결정)"""
    model = ChatOpenAI(model="gpt-4-turbo", temperature=0)

    # 기억을 프롬프트에 주입
    messages = state["messages"].copy()
    if state["memory_context"]:
        messages.insert(-1, AIMessage(
            content=f"Related memories:\n{state['memory_context']}"
        ))

    response = model.invoke(messages)

    return {
        "messages": [response],
        "tool_call_count": (
            state.get("tool_call_count", 0) +
            (1 if hasattr(response, "tool_calls") and response.tool_calls else 0)
        )
    }

# ============ 4. 그래프 구성 ============
def create_jedi_agent(bank_id: str, max_iterations: int = 10):
    builder = StateGraph(AgentState)

    # 노드 추가
    builder.add_node("recall", recall_node)
    builder.add_node("reason", reason_node)
    builder.add_node("tools", ToolNode(tools))

    # 엣지
    builder.add_edge(START, "recall")
    builder.add_edge("recall", "reason")

    # 조건부: 도구 호출 여부
    def should_continue(state: AgentState) -> str:
        if state["tool_call_count"] >= state.get("max_iterations", 10):
            return END

        last_msg = state["messages"][-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            return "tools"
        return END

    builder.add_conditional_edges("reason", should_continue)
    builder.add_edge("tools", "reason")  # 도구 후 다시 추론

    # 컴파일
    checkpointer = InMemorySaver()
    graph = builder.compile(checkpointer=checkpointer)

    return graph

# ============ 5. 실행 ============
async def main():
    graph = create_jedi_agent(bank_id="jedi", max_iterations=5)

    config = {"configurable": {"thread_id": "conv-001"}}

    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="What's my tech stack preference?")],
            "bank_id": "jedi",
            "memory_context": "",
            "tool_call_count": 0,
            "max_iterations": 5,
        },
        config
    )

    print(result["messages"][-1].content)

asyncio.run(main())
```

### 11.2 슈퍼바이저 + 워커 패턴

```python
# 여러 전문 에이전트 + 슈퍼바이저
def create_supervisor_graph():
    """마스터 에이전트가 여러 워커를 지휘"""

    # 워커 에이전트들
    research_agent = create_agent("research", tools=research_tools)
    code_agent = create_agent("code", tools=code_tools)
    writing_agent = create_agent("writing", tools=writing_tools)

    # 슈퍼바이저 정의
    class SupervisorState(TypedDict):
        messages: Annotated[list, add_messages]
        next: str  # "research" | "code" | "writing" | "gather" | END

    def supervisor_node(state: SupervisorState) -> dict:
        """어느 워커에게 일을 할당할지 결정"""
        response = llm.invoke(
            f"Delegate this task: {state['messages'][-1].content}"
        )
        # response에서 next_worker를 추출
        return {"next": determine_worker(response)}

    # 워커 결과 취합
    def gather_node(state: SupervisorState) -> dict:
        """모든 워커 결과를 최종 답변으로"""
        return {"messages": [final_answer]}

    builder = StateGraph(SupervisorState)

    builder.add_node("supervisor", supervisor_node)
    builder.add_node("research", research_agent)
    builder.add_node("code", code_agent)
    builder.add_node("writing", writing_agent)
    builder.add_node("gather", gather_node)

    builder.add_edge(START, "supervisor")

    builder.add_conditional_edges(
        "supervisor",
        lambda s: s["next"],
        {
            "research": "research",
            "code": "code",
            "writing": "writing",
            "gather": "gather",
        }
    )

    builder.add_edge("research", "gather")
    builder.add_edge("code", "gather")
    builder.add_edge("writing", "gather")
    builder.add_edge("gather", END)

    return builder.compile(checkpointer=InMemorySaver())

graph = create_supervisor_graph()
```

### 11.3 LiteLLM 연동

```python
# LiteLLM로 다중 모델 지원
from litellm import completion

async def reason_with_litellm(state: AgentState) -> dict:
    """LiteLLM을 통한 모델 호출"""

    response = await completion(
        model="gpt-4-turbo",  # 또는 "claude-3-opus", "llama-2" 등
        messages=state["messages"],
        tools=[tool.to_dict() for tool in tools],
        temperature=0,
        timeout=30,
    )

    return {"messages": [response]}

# 또는 model 파라미터화
class AgentConfig(TypedDict):
    model: str  # "gpt-4-turbo" | "claude-opus" | "llama"

def create_configurable_agent(config: AgentConfig):
    async def reason_node(state: AgentState) -> dict:
        response = await completion(
            model=config["model"],
            messages=state["messages"],
        )
        return {"messages": [response]}

    # 나머지 그래프 구성...
```

### 11.4 Hindsight + LangGraph 연동

```python
async def full_memory_cycle(state: AgentState) -> dict:
    """메모리 회수 → 추론 → 도구 → 메모리 저장"""

    # 1. RECALL: 기억 검색
    if not state.get("memory_context"):
        memories = await hindsight.arecall(
            bank_id=state["bank_id"],
            query=state["messages"][-1].content,
            budget="mid",
            max_tokens=4096,
        )
        memory_text = "\n".join([m.text for m in memories])
        state["memory_context"] = memory_text

    # 2. REASON: LLM 추론 (메모리 포함)
    model = ChatOpenAI(model="gpt-4-turbo")
    messages_with_memory = [
        *state["messages"][:-1],
        AIMessage(content=f"Memory context:\n{state['memory_context']}"),
        state["messages"][-1],
    ]
    response = model.invoke(messages_with_memory)

    # 3. (TOOLS: 도구 호출 - 별도 노드)

    # 4. RETAIN: 이 대화를 기억으로 저장
    await hindsight.aretain(
        bank_id=state["bank_id"],
        content=f"User: {state['messages'][-1].content}\nAssistant: {response.content}",
        context="conversation",
        tags=["conversation", "jedisos"],
        timestamp=datetime.now().isoformat(),
    )

    return {
        "messages": [response],
        "memory_context": state["memory_context"],
    }

# 그래프에 추가
builder.add_node("memory_cycle", full_memory_cycle)
```

---

## 12. 주의사항 및 팁

### 12.1 compile() 후에만 실행 가능

```python
builder = StateGraph(State)
builder.add_node("node1", func1)
builder.add_edge(START, "node1")

# ❌ 에러: compile 전에 호출
# result = builder.invoke(input_data)

# ✅ 올바른 방법
graph = builder.compile()
result = graph.invoke(input_data)
```

### 12.2 add_messages 리듀서: ID 기반 중복 제거

```python
# add_messages는 message ID를 기반으로 중복 제거
from langchain_core.messages import HumanMessage, AIMessage

msg1 = HumanMessage(content="Hello", id="msg-1")
msg2 = AIMessage(content="Hi", id="msg-2")
msg1_updated = HumanMessage(content="Hello updated", id="msg-1")

# 첫 상태
state = {"messages": [msg1]}

# msg2 추가
state = {"messages": [msg1, msg2]}  # add_messages로 병합

# msg1 업데이트 (같은 ID)
state = {"messages": [msg1_updated, msg2]}  # msg1이 교체됨, msg2는 유지

# ID가 없으면 자동 생성
msg3 = AIMessage(content="Hello")  # id 없음
# add_messages가 UUID 할당
```

### 12.3 프로덕션은 반드시 PostgresSaver

```python
# ❌ 프로덕션에서 메모리 체크포인터 금지
# checkpointer = InMemorySaver()  # 프로세스 재부팅 시 손실!

# ✅ 프로덕션: PostgreSQL 사용
async with await AsyncPostgresSaver.acreate_pool(
    "postgresql://user:pass@prod-db:5432/langgraph"
) as checkpointer:
    graph = builder.compile(checkpointer=checkpointer)
    # 영속성 보장
```

### 12.4 MemorySaver는 데이터 소실

```python
# InMemorySaver의 한계
checkpointer = InMemorySaver()

# 프로세스 1에서 저장
graph = builder.compile(checkpointer=checkpointer)
graph.invoke(state, {"configurable": {"thread_id": "user-1"}})

# 프로세스 2에서 같은 thread_id 로드 불가능
# → 새로운 InMemorySaver 인스턴스이므로 데이터 없음!

# 멀티 프로세스/마이크로서비스 환경에서는
# 반드시 중앙 데이터베이스 (PostgreSQL, Redis 등) 사용
```

### 12.5 상태 업데이트는 부분만 반환

```python
def bad_node(state: State) -> dict:
    # ❌ 나머지 필드를 None으로 오버라이드
    return {"count": 5}  # 다른 필드는 상태에 유지됨 (리듀서 규칙 따름)

def good_node(state: State) -> dict:
    # ✅ 변경된 것만 반환
    return {
        "count": state["count"] + 1,
        "messages": [new_message],  # add_messages로 누적
    }
```

### 12.6 리듀서 오버라이드: Overwrite

```python
from langgraph.types import Overwrite

def clear_node(state: State) -> dict:
    """리듀서를 무시하고 값 덮어쓰기"""
    return {
        "items": Overwrite([])  # operator.add를 무시하고 완전 교체
    }
```

### 12.7 타입 안전성

```python
# Mypy와 호환되는 타입 힌팅
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    count: int

def typed_node(state: AgentState) -> dict[str, list | int]:
    """명시적 타입"""
    return {
        "messages": [msg],
        "count": state["count"] + 1,
    }

builder: StateGraph[AgentState, None, AgentState, AgentState] = StateGraph(AgentState)
builder.add_node("node", typed_node)
```

### 12.8 디버깅: 시각화

```python
# 그래프 구조 시각화
mermaid_diagram = graph.get_graph().draw_mermaid()
print(mermaid_diagram)

# ASCII 다이어그램
print(graph.get_graph().draw_ascii())

# PNG로 저장
graph.get_graph().draw_mermaid_png("graph.png")
```

### 12.9 성능 최적화

```python
# 1. 병렬 실행: Send를 사용한 산재
def scatter(state: State):
    from langgraph.types import Send
    return [Send("worker", {"task": item}) for item in state["tasks"]]

# 2. Async 노드로 I/O 병렬화
async def parallel_api_calls(state: State) -> dict:
    results = await asyncio.gather(
        fetch_api(url1),
        fetch_api(url2),
        fetch_api(url3),
    )
    return {"api_results": results}

# 3. 배치 처리
results = graph.batch(
    [input1, input2, input3],
    [config1, config2, config3],
)

# 4. 스트리밍: 부분 결과 즉시 반환
async for chunk in graph.astream(state, config, stream_mode="updates"):
    # UI에 즉시 업데이트 표시
    update_ui(chunk)
```

### 12.10 일반적인 실수

```python
# ❌ 실수 1: invoke 전 compile 잊기
builder.add_node("n", func)
result = builder.invoke(state)  # TypeError

# ❌ 실수 2: 노드에서 전체 상태 반환
def bad(s): return {"messages": [...], "count": 5, "other": ""}
# 더 많은 필드가 있으면 암묵적으로 누락됨

# ❌ 실수 3: thread_id 없이 체크포인팅
config = {"configurable": {}}  # thread_id 누락
graph.invoke(state, config)  # 체크포인팅 안 됨

# ❌ 실수 4: 비동기 함수를 동기 노드로 등록
async def async_func(s): ...
builder.add_node("async", async_func)  # 조용히 실패

# ✅ 비동기는 ainvoke 사용
await graph.ainvoke(state, config)
```

---

## 참고

| 개념 | 위치 | 설명 |
|------|------|------|
| StateGraph | langgraph.graph | 그래프 구축 |
| add_messages | langgraph.graph | 메시지 병합 |
| ToolNode | langgraph.prebuilt | 도구 실행 |
| InMemorySaver | langgraph.checkpoint.memory | 메모리 저장 |
| AsyncPostgresSaver | langgraph.checkpoint.postgres | DB 저장 |
| Command, Send | langgraph.types | 고급 제어 |
| interrupt | langgraph.types | Human-in-the-loop |
| RetryPolicy | langgraph.types | 재시도 정책 |

**참고 자료:**
- [LangGraph 공식 문서](https://langchain-ai.github.io/langgraph/)
- [GitHub](https://github.com/langchain-ai/langgraph)
- [LangChain 문서](https://docs.langchain.com/)

---

**최종 업데이트:** 2026년 2월 17일
**LangGraph 버전:** 1.0.8
**Python 버전:** 3.10+
