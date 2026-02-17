# Hindsight 사용법 가이드

> JediSOS에서 Hindsight 메모리 엔진을 사용하는 방법을 정리한 문서
> hindsight-client v0.4.11 기준

---

## 1. 핵심 개념

Hindsight는 **3가지 핵심 동작**으로 작동한다:

| 동작 | 설명 | 비유 |
|------|------|------|
| **retain** | 기억 저장 | "이거 기억해둬" |
| **recall** | 기억 검색 (의미 기반) | "~에 대해 뭐 알아?" |
| **reflect** | 기억 기반 답변 생성 (LLM) | "~에 대해 생각해봐" |

### 1.1 Bank (메모리 뱅크)

모든 기억은 **bank** 단위로 격리된다. JediSOS에서는 사용자별로 1개의 bank를 사용한다.

```
bank_id = "jedi"          # 사용자 식별자
bank_id = "jedi-work"     # 업무용 분리도 가능
```

### 1.2 Fact Types (기억 유형)

Hindsight가 내부적으로 분류하는 기억 유형:

| 타입 | 설명 | 예시 |
|------|------|------|
| `world` | 세상에 대한 사실 | "파이썬 3.12에서 f-string이 중첩 가능해졌다" |
| `experience` | 경험/사건 | "2024년 3월에 서울에서 컨퍼런스 참석했다" |
| `opinion` | 의견/선호 | "나는 TypeScript보다 Python을 선호한다" |
| `observation` | 관찰/패턴 | "매주 월요일에 팀 회의가 있다" |

### 1.3 Budget (예산 레벨)

검색 깊이를 제어한다:

| 레벨 | 설명 | 비용 | 용도 |
|------|------|------|------|
| `low` | 빠른 검색, 최소 처리 | 낮음 | 간단한 질문, reflect 기본값 |
| `mid` | 균형 잡힌 검색 | 중간 | 일반 사용, recall 기본값 |
| `high` | 깊은 검색, 그래프 탐색 포함 | 높음 | 복잡한 분석, 관계 추적 |

---

## 2. 클라이언트 초기화

### 2.1 Sync 클라이언트

```python
from hindsight_client import Hindsight

# 로컬 Hindsight 서버 (Docker)
client = Hindsight(base_url="http://localhost:8888")

# API 키 인증 (프로덕션)
client = Hindsight(
    base_url="http://localhost:8888",
    api_key="your-api-key"
)

# Context manager 사용 (권장)
with Hindsight(base_url="http://localhost:8888") as client:
    result = client.recall(bank_id="jedi", query="내 취미가 뭐야?")
```

### 2.2 JediSOS에서의 Async 사용 (LangGraph 내부)

```python
from hindsight_client import Hindsight

# JediSOS의 HindsightClient 래퍼 내부
class HindsightClient:
    def __init__(self, base_url: str, api_key: str | None = None):
        self._client = Hindsight(base_url=base_url, api_key=api_key)

    async def remember(self, bank_id: str, content: str, **kwargs):
        """retain의 async 래퍼"""
        return await self._client.aretain(
            bank_id=bank_id,
            content=content,
            **kwargs
        )

    async def search(self, bank_id: str, query: str, **kwargs):
        """recall의 async 래퍼"""
        return await self._client.arecall(
            bank_id=bank_id,
            query=query,
            **kwargs
        )

    async def answer(self, bank_id: str, query: str, **kwargs):
        """reflect의 async 래퍼"""
        return await self._client.areflect(
            bank_id=bank_id,
            query=query,
            **kwargs
        )

    async def close(self):
        await self._client.aclose()
```

---

## 3. retain — 기억 저장

### 3.1 기본 사용법

```python
# 단일 기억 저장
result = client.retain(
    bank_id="jedi",
    content="오늘 팀 회의에서 Q2 로드맵을 확정했다. React에서 Next.js로 마이그레이션 결정."
)
print(result.success)      # True
print(result.items_count)  # 1
print(result.bank_id)      # "jedi"
```

### 3.2 풍부한 메타데이터와 함께

```python
from datetime import datetime

result = client.retain(
    bank_id="jedi",
    content="GPT-5.2가 출시되었다. 멀티모달 성능이 크게 향상되었고 가격은 기존 대비 30% 인하.",
    timestamp=datetime(2026, 1, 15, 10, 30),   # 이벤트 발생 시각
    context="기술 뉴스 모니터링",                  # 어떤 맥락에서 수집했는지
    document_id="tech-news-2026-01",             # 문서 그룹핑용 ID
    metadata={"source": "techcrunch", "category": "ai"},  # 사용자 정의 메타데이터
    entities=[                                    # 수동 엔티티 지정 (선택)
        {"text": "GPT-5.2", "type": "product"},
        {"text": "OpenAI", "type": "organization"}
    ],
    tags=["ai", "llm", "news"]                   # 필터링용 태그
)
```

### 3.3 배치 저장 (대량)

```python
# 여러 기억을 한번에 저장
items = [
    {
        "content": "아침에 코드 리뷰 3건 처리했다",
        "timestamp": datetime(2026, 2, 17, 9, 0),
        "context": "업무 일지",
        "tags": ["work", "code-review"]
    },
    {
        "content": "점심에 팀원들과 새 카페에 갔다. 아메리카노가 맛있었다.",
        "timestamp": datetime(2026, 2, 17, 12, 30),
        "context": "일상",
        "tags": ["daily", "food"]
    },
    {
        "content": "오후에 LangGraph 워크플로우 설계를 완료했다",
        "timestamp": datetime(2026, 2, 17, 16, 0),
        "context": "업무 일지",
        "tags": ["work", "langgraph"]
    }
]

result = client.retain_batch(
    bank_id="jedi",
    items=items,
    document_id="daily-log-2026-02-17",    # 전체 배치에 적용
    document_tags=["daily-log"]             # 전체 배치에 태그 추가
)
print(result.items_count)  # 3
```

### 3.4 비동기 저장 (대용량)

```python
# 백그라운드에서 비동기 처리 (대량 데이터 수집 시)
result = client.retain_batch(
    bank_id="jedi",
    items=large_items_list,    # 수백~수천 건
    retain_async=True          # 백그라운드 처리
)
print(result.operation_id)     # "op_abc123" — 나중에 상태 확인용
```

### 3.5 RetainResponse 구조

```python
RetainResponse:
    success: bool              # 저장 성공 여부
    bank_id: str               # 뱅크 ID
    items_count: int           # 저장된 항목 수
    async: bool                # 비동기 처리 여부
    operation_id: str | None   # 비동기 시 작업 ID
    usage: TokenUsage | None   # 토큰 사용량
```

---

## 4. recall — 기억 검색

recall은 **의미론적 유사도 검색**을 수행한다. 벡터 검색 + BM25 + 그래프 검색을 융합(fusion)한 결과를 반환한다.

### 4.1 기본 사용법

```python
# 의미 기반 검색
response = client.recall(
    bank_id="jedi",
    query="내가 좋아하는 프로그래밍 언어는?"
)

# 결과 순회
for r in response.results:
    print(f"[{r.type}] {r.text}")
    # [opinion] 나는 TypeScript보다 Python을 선호한다
    # [experience] 지난 주에 Rust로 CLI 도구를 만들었는데 재미있었다
```

### 4.2 타입 필터링

```python
# 경험만 검색
response = client.recall(
    bank_id="jedi",
    query="최근 회의",
    types=["experience"]       # world, experience, opinion, observation
)

# 의견만 검색
response = client.recall(
    bank_id="jedi",
    query="기술 스택 선호도",
    types=["opinion", "observation"]
)
```

### 4.3 태그 필터링

```python
# 업무 관련 기억만 검색
response = client.recall(
    bank_id="jedi",
    query="이번 주에 뭐 했어?",
    tags=["work"],
    tags_match="any"           # "any" | "all" | "any_strict" | "all_strict"
)
```

**tags_match 옵션:**

| 값 | 동작 | 태그 없는 기억 포함 |
|---|---|---|
| `any` (기본값) | OR 매칭 | O |
| `all` | AND 매칭 | O |
| `any_strict` | OR 매칭 | X |
| `all_strict` | AND 매칭 | X |

### 4.4 고급 옵션

```python
response = client.recall(
    bank_id="jedi",
    query="AI 관련 프로젝트들",
    max_tokens=8192,           # 결과 최대 토큰 (기본: 4096)
    budget="high",             # 깊은 검색 (그래프 탐색 포함)
    trace=True,                # 검색 과정 추적 (디버깅용)
    query_timestamp="2026-01-01T00:00:00",  # 이 시점 기준으로 검색
    include_entities=True,     # 관련 엔티티 정보 포함
    max_entity_tokens=500,     # 엔티티 최대 토큰
    include_chunks=True,       # 원본 청크 포함
    max_chunk_tokens=8192      # 청크 최대 토큰
)

# trace 확인 (디버깅)
if response.trace:
    print(response.trace)

# 엔티티 확인
if response.entities:
    for name, state in response.entities.items():
        print(f"엔티티: {name} → {state}")
```

### 4.5 RecallResponse 구조

```python
RecallResponse:
    results: list[RecallResult]                   # 검색 결과 목록
    trace: dict | None                            # 검색 추적 정보
    entities: dict[str, EntityStateResponse] | None  # 관련 엔티티
    chunks: dict[str, ChunkData] | None           # 원본 청크

RecallResult:
    id: str                    # 기억 고유 ID
    text: str                  # 기억 텍스트
    type: str | None           # world / experience / opinion / observation
    entities: list[str] | None # 관련 엔티티 이름들
    context: str | None        # 기억의 맥락
    occurred_start: str | None # 발생 시작 시각
    occurred_end: str | None   # 발생 종료 시각
    mentioned_at: str | None   # 언급된 시각
    document_id: str | None    # 소속 문서 ID
    metadata: dict | None      # 사용자 정의 메타데이터
    chunk_id: str | None       # 원본 청크 ID
    tags: list[str] | None     # 태그 목록
```

### 4.6 Async recall

```python
# LangGraph 노드 내부에서 (async)
results = await client.arecall(
    bank_id="jedi",
    query="최근 프로젝트 현황",
    budget="mid"
)
# arecall은 list[RecallResult]를 직접 반환 (RecallResponse가 아님!)
for r in results:
    print(r.text)
```

---

## 5. reflect — 기억 기반 답변 생성

reflect는 recall과 달리 **LLM이 기억을 기반으로 답변을 생성**한다. RAG와 유사하지만 Hindsight의 그래프 구조를 활용해 더 맥락있는 답변을 만든다.

### 5.1 기본 사용법

```python
# 기억 기반 답변 생성
answer = client.reflect(
    bank_id="jedi",
    query="내가 올해 가장 관심 가진 기술이 뭐야?"
)

print(answer.text)
# "올해 가장 관심을 가진 기술은 LangGraph와 MCP(Model Context Protocol)입니다.
#  1월에 LangGraph로 에이전트 워크플로우를 설계했고, 2월에는 MCP 서버를 구축하는
#  프로젝트를 시작했습니다. 특히 LangGraph의 상태 관리 패턴에 깊은 인상을 받았다고
#  여러 번 언급하셨습니다."
```

### 5.2 추가 컨텍스트 제공

```python
# 현재 대화 맥락을 함께 전달
answer = client.reflect(
    bank_id="jedi",
    query="이 프로젝트에서 내가 주의해야 할 점은?",
    context="현재 JediSOS 프로젝트를 개발 중. LangGraph + Hindsight + LiteLLM 조합.",
    budget="high"              # 깊은 분석
)
```

### 5.3 구조화된 출력 (JSON Schema)

```python
# 정해진 형식으로 답변 받기
answer = client.reflect(
    bank_id="jedi",
    query="내 기술 스택 선호도를 정리해줘",
    response_schema={
        "type": "object",
        "properties": {
            "preferred": {
                "type": "array",
                "items": {"type": "string"},
                "description": "선호하는 기술들"
            },
            "disliked": {
                "type": "array",
                "items": {"type": "string"},
                "description": "싫어하는 기술들"
            },
            "neutral": {
                "type": "array",
                "items": {"type": "string"},
                "description": "중립적인 기술들"
            }
        }
    }
)

print(answer.text)               # 마크다운 답변
print(answer.structured_output)  # {"preferred": ["Python", "LangGraph"], "disliked": [...], ...}
```

### 5.4 ReflectResponse 구조

```python
ReflectResponse:
    text: str                          # 마크다운 형식 답변
    based_on: ReflectBasedOn | None    # 답변에 사용된 기억들
    structured_output: dict | None     # response_schema 지정 시 구조화 결과
    usage: TokenUsage | None           # 토큰 사용량
    trace: ReflectTrace | None         # 추적 정보
```

### 5.5 Async reflect

```python
# LangGraph 노드 내부
answer = await client.areflect(
    bank_id="jedi",
    query="이번 달 일정 요약해줘",
    budget="mid",
    tags=["schedule", "work"],
    tags_match="any"
)
print(answer.text)
```

---

## 6. Bank 관리

### 6.1 Bank 생성

```python
# 새 뱅크 생성
profile = client.create_bank(
    bank_id="jedi",
    name="Jedi's Memory",
    mission="사용자의 기술 관심사, 프로젝트 진행 상황, 일상 패턴을 학습하고 기억한다.",
    disposition={
        "skepticism": 0.3,    # 0~1, 낮을수록 정보를 잘 받아들임
        "literalism": 0.7,    # 0~1, 높을수록 문자 그대로 해석
        "empathy": 0.8        # 0~1, 높을수록 감정적 뉘앙스 파악
    }
)
```

**mission** 은 Hindsight가 기억을 정리하고 mental model을 생성할 때 참고하는 지침이다. 잘 작성하면 기억 품질이 크게 올라간다.

### 6.2 Mission 업데이트

```python
# 미션만 별도 업데이트
client.set_mission(
    bank_id="jedi",
    mission="사용자의 AI 프로젝트(JediSOS), 기술 선호도, 업무 패턴을 학습한다. "
            "특히 의사결정 이력과 그 이유를 중점적으로 기억한다."
)
```

### 6.3 Bank 삭제

```python
# 주의: 모든 기억이 삭제됨!
client.delete_bank(bank_id="jedi-test")
```

---

## 7. Mental Models (지식 요약)

Mental Model은 특정 주제에 대한 **지속적으로 업데이트되는 요약문**이다. Hindsight가 축적된 기억을 바탕으로 생성하고, 새 기억이 쌓이면 자동 갱신할 수 있다.

### 7.1 생성

```python
# "사용자의 기술 스택"에 대한 mental model 생성
result = client.create_mental_model(
    bank_id="jedi",
    name="기술 스택 선호도",
    source_query="사용자가 선호하는 프로그래밍 언어, 프레임워크, 도구는 무엇인가?",
    tags=["tech", "preferences"],
    max_tokens=2000,
    trigger={"refresh_after_consolidation": True}  # 기억 정리 후 자동 갱신
)
print(result.operation_id)  # 백그라운드에서 생성됨
```

### 7.2 조회

```python
# 모든 mental model 목록
models = client.list_mental_models(bank_id="jedi")
for m in models.items:
    print(f"{m.name}: {m.id}")

# 특정 mental model 조회
model = client.get_mental_model(bank_id="jedi", mental_model_id="mm_abc123")
print(model.content)  # 생성된 요약 텍스트
```

### 7.3 갱신 / 수정 / 삭제

```python
# 수동 갱신 (최신 기억 반영)
client.refresh_mental_model(bank_id="jedi", mental_model_id="mm_abc123")

# 메타데이터 수정
client.update_mental_model(
    bank_id="jedi",
    mental_model_id="mm_abc123",
    name="기술 스택 선호도 (업데이트)",
    source_query="사용자가 2026년에 선호하는 기술 스택은?"
)

# 삭제
client.delete_mental_model(bank_id="jedi", mental_model_id="mm_abc123")
```

---

## 8. Directives (지시문)

Directive는 reflect 시 **강제로 적용되는 규칙**이다. LLM 응답의 톤, 형식, 제약 조건을 지정할 수 있다.

### 8.1 생성

```python
# 한국어 응답 지시
client.create_directive(
    bank_id="jedi",
    name="한국어 응답",
    content="항상 한국어로 답변하되, 기술 용어는 영어를 병기한다.",
    priority=10,       # 높을수록 먼저 적용
    is_active=True,
    tags=["language"]
)

# 간결한 응답 지시
client.create_directive(
    bank_id="jedi",
    name="간결한 답변",
    content="답변은 3문장 이내로 핵심만 전달한다. 불필요한 서론은 생략한다.",
    priority=5,
    is_active=True,
    tags=["style"]
)
```

### 8.2 조회 / 수정 / 삭제

```python
# 목록 조회
directives = client.list_directives(bank_id="jedi")
for d in directives.items:
    print(f"[{'ON' if d.is_active else 'OFF'}] {d.name} (priority={d.priority})")

# 비활성화
client.update_directive(
    bank_id="jedi",
    directive_id="dir_abc123",
    is_active=False
)

# 삭제
client.delete_directive(bank_id="jedi", directive_id="dir_abc123")
```

---

## 9. JediSOS에서의 통합 패턴

### 9.1 LangGraph 노드에서 사용

```python
from langgraph.graph import StateGraph
from hindsight_client import Hindsight

# 전역 클라이언트 (앱 시작 시 생성)
hindsight = Hindsight(
    base_url=os.getenv("HINDSIGHT_URL", "http://localhost:8888"),
    api_key=os.getenv("HINDSIGHT_API_KEY")
)

async def memory_recall_node(state: AgentState) -> AgentState:
    """기억 검색 노드"""
    query = state["messages"][-1].content
    bank_id = state["user_id"]

    # 관련 기억 검색
    results = await hindsight.arecall(
        bank_id=bank_id,
        query=query,
        budget="mid",
        max_tokens=4096
    )

    # 기억을 컨텍스트로 변환
    memory_context = "\n".join([
        f"- [{r.type}] {r.text}" for r in results
    ])

    return {**state, "memory_context": memory_context}

async def memory_retain_node(state: AgentState) -> AgentState:
    """대화 내용 기억 저장 노드"""
    # 사용자 메시지와 AI 응답을 함께 저장
    user_msg = state["messages"][-2].content
    ai_response = state["messages"][-1].content

    await hindsight.aretain(
        bank_id=state["user_id"],
        content=f"사용자: {user_msg}\n응답: {ai_response}",
        context="대화",
        tags=["conversation"]
    )

    return state
```

### 9.2 @tool 래퍼 (Tier 1 Skill)

```python
from langchain_core.tools import tool

@tool
async def remember(content: str, tags: list[str] | None = None) -> str:
    """사용자가 기억해달라고 한 내용을 저장한다."""
    result = await hindsight.aretain(
        bank_id=current_user_id(),
        content=content,
        tags=tags or []
    )
    return f"기억 저장 완료 ({result.items_count}건)"

@tool
async def search_memory(query: str, types: list[str] | None = None) -> str:
    """과거 기억에서 관련 정보를 검색한다."""
    results = await hindsight.arecall(
        bank_id=current_user_id(),
        query=query,
        types=types,
        budget="mid"
    )
    if not results:
        return "관련 기억을 찾지 못했습니다."
    return "\n".join([f"- {r.text}" for r in results])

@tool
async def ask_memory(question: str) -> str:
    """축적된 기억을 바탕으로 질문에 답변한다."""
    answer = await hindsight.areflect(
        bank_id=current_user_id(),
        query=question,
        budget="mid"
    )
    return answer.text
```

### 9.3 대화 흐름 예시

```
사용자: "저번 주에 뭐 했는지 알려줘"

1. LangGraph → memory_recall_node 실행
2. hindsight.arecall(query="저번 주에 뭐 했는지") 호출
3. Hindsight 내부:
   a. 벡터 검색 (pgvector cosine similarity)
   b. BM25 전문 검색
   c. 그래프 탐색 (temporal links, entity co-occurrences)
   d. 스코어 융합 (vector + BM25 + graph)
4. 결과를 LLM 컨텍스트에 주입
5. LLM이 기억 기반 답변 생성
6. memory_retain_node에서 이 대화 자체도 저장
```

---

## 10. recall vs reflect 사용 구분

| 상황 | 사용할 API | 이유 |
|------|-----------|------|
| LLM에 컨텍스트를 주입할 때 | `recall` | 원본 기억 텍스트가 필요 |
| 사용자에게 직접 답변할 때 | `reflect` | LLM이 기억을 해석해서 답변 |
| 기억 존재 여부만 확인할 때 | `recall` | 빠르고 비용 낮음 |
| 구조화된 데이터가 필요할 때 | `reflect` + `response_schema` | JSON 형식 출력 |
| 디버깅/추적이 필요할 때 | `recall` + `trace=True` | 검색 과정 확인 |

**JediSOS 권장 패턴:** LangGraph 에이전트 내부에서는 `recall`로 기억을 가져와서 LLM 프롬프트에 넣고, 메모리 관련 직접 질문에만 `reflect`를 사용한다. 이유: reflect는 내부적으로 LLM을 한번 더 호출하므로 비용이 2배.

---

## 11. REST API (직접 호출)

Python SDK를 쓰지 않고 HTTP로 직접 호출할 수도 있다 (MCP 서버 등에서 활용).

### 11.1 retain

```bash
POST http://localhost:8888/v1/default/banks/{bank_id}/memories
Content-Type: application/json

{
  "items": [
    {
      "content": "오늘 LangGraph 워크플로우를 완성했다",
      "timestamp": "2026-02-17T16:00:00",
      "context": "업무 일지",
      "tags": ["work", "langgraph"]
    }
  ]
}
```

### 11.2 recall

```bash
POST http://localhost:8888/v1/default/banks/{bank_id}/memories/recall
Content-Type: application/json

{
  "query": "최근 프로젝트 진행 상황",
  "budget": "mid",
  "max_tokens": 4096,
  "types": ["experience", "observation"],
  "tags": ["work"],
  "tags_match": "any"
}
```

### 11.3 reflect

```bash
POST http://localhost:8888/v1/default/banks/{bank_id}/reflect
Content-Type: application/json

{
  "query": "내 기술 스택 선호도를 분석해줘",
  "budget": "mid",
  "context": "기술 블로그 작성 준비 중"
}
```

---

## 12. 주의사항 및 팁

### 12.1 성능

- `retain`은 내부적으로 LLM을 호출해서 엔티티 추출/사실 분류를 한다 → 지연 있음 (1-3초)
- `recall` budget="low"는 벡터 검색만 → 빠름 (<100ms)
- `recall` budget="high"는 그래프 탐색 포함 → 느림 (200-500ms)
- `reflect`는 recall + LLM 생성 → 가장 느림 (2-5초)

### 12.2 비용 관리

- retain 시 LLM이 사실 추출에 사용됨 → 입력 토큰 비용 발생
- reflect는 추가 LLM 호출 → recall 대비 2배 비용
- `max_tokens` 파라미터로 결과 크기 제한
- `budget` 레벨로 검색 깊이 제어

### 12.3 태그 전략 (JediSOS 권장)

```python
# 소스별 태그
"conversation"  # 대화에서 수집
"document"      # 문서에서 수집
"web"           # 웹 검색에서 수집
"manual"        # 사용자가 직접 입력

# 주제별 태그
"work"          # 업무
"daily"         # 일상
"tech"          # 기술
"people"        # 사람/관계

# 시간별 태그 (선택)
"2026-Q1"       # 분기
```

### 12.4 Bank 격리

- 사용자별 bank 1개가 기본
- 멀티 테넌트 시 bank_id로 완전 격리
- 같은 bank 내에서 tags로 용도 분리 권장 (bank 남용 지양)
