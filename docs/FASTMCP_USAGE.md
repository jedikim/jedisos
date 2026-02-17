# FastMCP v2.14+ 사용법 가이드

> JediSOS에서 FastMCP를 사용하여 MCP 서버를 구축하는 방법을 정리한 문서
> FastMCP 2.14.5 기준 (v3.0 RC1 출시되었으므로 <3.0 버전 핀 필수)

---

## 1. 핵심 개념

FastMCP는 LLM과 외부 도구를 연결하는 표준 프로토콜인 **MCP(Model Context Protocol)**를 Python에서 쉽게 구축할 수 있게 해주는 프레임워크다.

### 1.1 MCP vs FastMCP

| 구분 | 설명 |
|------|------|
| **MCP** | Model Context Protocol의 약자. LLM ↔ 외부 도구 간 통신 표준 |
| **FastMCP** | MCP 서버를 Python으로 쉽게 만드는 프레임워크 (Flask 같은 수준의 간편성) |

### 1.2 JediSOS에서의 사용 범위

FastMCP는 **Tier 2 확장(외부 API 연동)**에만 사용된다.

| Tier | 용도 | 도구 | 예시 |
|------|------|------|------|
| **Tier 1** | 로컬 기본 도구 | @tool (LangChain) | 메모리 검색, 계산 |
| **Tier 2** | 외부 API 연동 | FastMCP 서버 | OAuth 필요한 Google Calendar, GitHub API |
| **Tier 3** | 고급 확장 | FastMCP + 미들웨어 | 복잡한 권한 관리, 상태 유지 |

### 1.3 FastMCP 서버의 3가지 주요 요소

```
FastMCP 서버
├── @server.tool()      — LLM이 호출 가능한 함수
├── @server.resource()  — 외부에 노출할 리소스 (파일, API, 설정)
└── @server.prompt()    — LLM을 유도하는 프롬프트 템플릿
```

---

## 2. 서버 생성

### 2.1 FastMCP() 생성자 핵심 파라미터

```python
from fastmcp import FastMCP
from contextlib import asynccontextmanager

server = FastMCP(
    name="MyMCPServer",                    # 서버 이름
    version="1.0.0",                       # 서버 버전
    instructions="이 서버는 GitHub API를 제공합니다",  # 클라이언트용 설명
    lifespan=lifespan_func,                # 생명주기 관리 (DB 연결 등)
    website_url="https://example.com",     # (선택) 웹사이트 URL
    mask_error_details=False,              # (선택) 에러 상세정보 숨김 여부
    strict_input_validation=True,          # (선택) 파라미터 엄격 검증
)
```

**자주 사용하는 파라미터:**
- `name` (필수): 서버 식별자. CLI에서 표시됨
- `instructions`: 클라이언트가 읽을 수 있는 사용 방법
- `version`: Semantic Versioning 권장
- `lifespan`: 서버 시작/종료 시 리소스 관리 (다음 섹션 참고)

### 2.2 Lifespan 패턴 (생명주기 관리)

데이터베이스 연결, API 클라이언트 초기화 등 리소스를 관리할 때 사용한다.

```python
from contextlib import asynccontextmanager
import aiohttp

@asynccontextmanager
async def lifespan(server: FastMCP):
    # ========== 시작 (Startup) ==========
    print("서버 시작 중...")

    # DB 연결
    db = await connect_database()

    # API 클라이언트 초기화
    http_session = aiohttp.ClientSession()

    # 리소스를 딕셔너리로 반환 (서버 전역에서 접근 가능)
    result = {
        "db": db,
        "http": http_session,
    }

    yield result

    # ========== 종료 (Shutdown) ==========
    print("서버 종료 중...")
    await db.close()
    await http_session.close()

# 서버 생성 시 lifespan 등록
server = FastMCP(
    name="DatabaseServer",
    lifespan=lifespan
)

# 도구에서 접근하기
@server.tool
async def query_data(query: str, ctx: Context) -> str:
    # lifespan에서 반환한 결과는 ctx.fastmcp._lifespan_result에 저장됨
    db = ctx.fastmcp._lifespan_result.get("db")
    result = await db.execute(query)
    return str(result)
```

**Lifespan 패턴의 이점:**
- 서버 시작 시 한 번만 리소스 생성 (효율성)
- 모든 도구에서 공유 가능 (DB 연결풀 등)
- 정상 종료 시 자동으로 리소스 정리 (메모리 누수 방지)

---

## 3. @mcp.tool() — 도구 정의

도구는 LLM이 호출할 수 있는 함수다. 동기/비동기 모두 지원한다.

### 3.1 5가지 데코레이터 패턴

```python
# 패턴 1: 괄호 없음 (가장 간단, 함수명 + docstring 자동 사용)
@server.tool
def add(a: int, b: int) -> int:
    """두 숫자를 더한다."""
    return a + b

# 패턴 2: 빈 괄호
@server.tool()
def subtract(a: int, b: int) -> int:
    """두 숫자를 뺀다."""
    return a - b

# 패턴 3: 이름 지정 (함수명과 다르게 도구 이름을 설정)
@server.tool("multiply_numbers")
def mul(a: int, b: int) -> int:
    """두 숫자를 곱한다."""
    return a * b

# 패턴 4: 키워드 인자 (상세 설정)
@server.tool(
    name="divide",
    description="두 숫자를 나눈다 (0으로 나눌 수 없음)",
    tags={"math", "calculation"}
)
def div(a: float, b: float) -> float:
    if b == 0:
        raise ValueError("0으로 나눌 수 없습니다")
    return a / b

# 패턴 5: 명시적 함수 호출 (동적 등록)
def my_func() -> str:
    return "dynamic tool"

server.tool(my_func, name="dynamic_tool")
```

### 3.2 동기 vs 비동기 도구

```python
# 동기 도구 (I/O 없거나 빠른 작업)
@server.tool
def fast_operation(x: int) -> int:
    return x * 2  # 간단한 계산

# 비동기 도구 (HTTP 요청, 데이터베이스 쿼리 등)
@server.tool
async def fetch_github_repo(owner: str, repo: str) -> dict:
    """GitHub에서 레포지토리 정보를 가져온다."""
    async with httpx.AsyncClient() as client:
        url = f"https://api.github.com/repos/{owner}/{repo}"
        response = await client.get(url)
        return response.json()

# ⚠️ v2.14에서 sync 도구는 자동으로 threadpool 디스패치된다
# 따라서 sync 함수도 안전하게 사용 가능 (DB 동기 라이브러리도 OK)
```

### 3.3 Context 접근 (로깅, 진행률 보고)

```python
from fastmcp import Context

@server.tool
async def process_with_logging(data: str, ctx: Context) -> dict:
    """Context를 통해 로깅과 진행률을 보고한다."""

    # 로깅 (4가지 레벨)
    await ctx.debug("디버그 메시지")
    await ctx.info(f"데이터 처리 시작: {data}")
    await ctx.warning("주의: 처리 시간이 오래 걸릴 수 있습니다")
    await ctx.error("오류 발생!")

    # 진행률 보고 (LLM 클라이언트에 표시됨)
    await ctx.report_progress(30, 100, "1단계 완료")
    await ctx.report_progress(60, 100, "2단계 완료")
    await ctx.report_progress(100, 100, "완료!")

    # 요청 정보 접근
    request_id = ctx.request_id  # 고유 요청 ID
    client_id = ctx.client_id    # 클라이언트 식별자

    return {
        "result": f"처리 완료: {data}",
        "request_id": request_id,
        "client_id": client_id
    }
```

### 3.4 반환 타입 (4가지)

```python
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

# 타입 1: 간단한 문자열/숫자/dict (자동으로 변환됨)
@server.tool
def simple_return() -> str:
    return "결과 텍스트"

# 타입 2: 구조화된 JSON (output_schema와 함께)
@server.tool(
    output_schema={
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "count": {"type": "integer"}
        }
    }
)
def structured_return() -> dict:
    return {"status": "success", "count": 42}

# 타입 3: ToolResult (가장 세밀한 제어)
@server.tool
def advanced_return() -> ToolResult:
    content = [TextContent(type="text", text="출력 텍스트")]
    structured = {"result": "데이터"}
    meta = {"processing_time": 1.23}

    return ToolResult(
        content=content,
        structured_content=structured,
        meta=meta
    )

# 타입 4: MCP 콘텐츠 타입
from mcp.types import ImageContent

@server.tool
def image_return() -> ImageContent:
    import base64
    with open("image.png", "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return ImageContent(type="image", mimeType="image/png", data=data)
```

### 3.5 파라미터 검증 (Pydantic Field + Annotated)

```python
from typing import Annotated
from pydantic import Field

@server.tool
def validated_params(
    name: Annotated[str, Field(
        description="사용자의 이름",
        min_length=1,
        max_length=100
    )],
    age: Annotated[int, Field(
        description="나이",
        ge=0,
        le=150
    )] = 0,
    email: Annotated[str, Field(
        description="이메일 주소",
        pattern=r"^[^@]+@[^@]+\.[^@]+$"
    )] = "unknown@example.com"
) -> dict:
    """파라미터가 자동으로 검증된다."""
    return {
        "name": name,
        "age": age,
        "email": email
    }

# LLM이 호출할 때:
# - name 미입력 → 오류 (필수)
# - age = -5 → 오류 (ge=0 위반)
# - email 형식 잘못 → 오류 (pattern 위반)
```

### 3.6 Tag를 통한 도구 분류

```python
# 태그를 지정하면 클라이언트가 선택적으로 도구를 필터링 가능
@server.tool(tags={"github", "vcs"})
async def create_github_issue(repo: str, title: str) -> str:
    """GitHub 이슈를 생성한다."""
    pass

@server.tool(tags={"github", "read"})
async def list_github_issues(repo: str) -> list[dict]:
    """GitHub 이슈 목록을 조회한다."""
    pass

@server.tool(tags={"calendar"})
async def create_event(title: str, date: str) -> str:
    """캘린더 이벤트를 생성한다."""
    pass

# 서버 생성 시 필터링
server = FastMCP(
    name="APIServer",
    include_tags={"github", "read"}  # 이 태그들만 포함
    # 또는
    # exclude_tags={"calendar"}  # 이 태그 제외
)
```

---

## 4. @mcp.resource() — 리소스 노출

리소스는 도구와 달리 **상태를 가진 데이터**를 노출한다. 파일, 설정, API 응답 등.

### 4.1 URI 패턴

```
리소스 URI 형식:
scheme://[template_params]

예시:
- file://config.json          → 정적 리소스
- file://{filename}           → 템플릿 리소스
- config://app/database       → 계층적 리소스
- resource://user/{user_id}   → REST-like 리소스
```

### 4.2 정적 vs 템플릿 리소스

```python
# 정적 리소스 (고정된 URI)
@server.resource("file://config.json")
def get_config() -> str:
    """앱 설정을 반환한다."""
    import json
    with open("config.json", "r") as f:
        return f.read()

# 템플릿 리소스 (매개변수 포함)
@server.resource("file://{filename}")
def read_file(filename: str) -> str:
    """지정된 파일을 읽는다."""
    with open(filename, "r") as f:
        return f.read()

# 중첩 템플릿
@server.resource("resource://projects/{project_id}/config/{config_name}")
async def get_project_config(project_id: str, config_name: str) -> dict:
    """프로젝트의 특정 설정을 조회한다."""
    import json
    path = f"projects/{project_id}/{config_name}.json"
    with open(path, "r") as f:
        return json.load(f)
```

### 4.3 MIME 타입 지정

```python
@server.resource(
    "resource://data.csv",
    mime_type="text/csv"
)
def get_csv_data() -> str:
    """CSV 데이터를 반환한다."""
    return "name,age\nJohn,30\nJane,25"

@server.resource(
    "resource://image.png",
    mime_type="image/png"
)
def get_image() -> bytes:
    """PNG 이미지를 반환한다."""
    with open("image.png", "rb") as f:
        return f.read()

@server.resource(
    "resource://data.json",
    mime_type="application/json"
)
def get_json() -> dict:
    """JSON 데이터 (자동으로 직렬화됨)."""
    return {"key": "value", "number": 42}
```

### 4.4 Context와 함께 사용

```python
@server.resource("resource://status")
async def get_status(ctx: Context) -> dict:
    """리소스도 Context에 접근할 수 있다."""
    await ctx.info("상태 조회 중...")

    db = ctx.fastmcp._lifespan_result.get("db")
    status = await db.get_status()

    await ctx.report_progress(100, 100, "완료")

    return {
        "health": "ok",
        "db_status": status
    }
```

---

## 5. @mcp.prompt() — 프롬프트 정의

프롬프트는 LLM을 유도하기 위해 미리 작성된 메시지 템플릿이다.

### 5.1 기본 프롬프트

```python
from mcp.types import SamplingMessage

@server.prompt
def analyze_code() -> list[SamplingMessage]:
    """코드 분석 프롬프트."""
    return [
        {
            "role": "user",
            "content": """다음 Python 코드를 분석하고:
1. 버그가 있는지 확인
2. 성능 개선 제안
3. 보안 문제 확인

코드:
```python
def process_data(data):
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
    return result
```"""
        }
    ]
```

### 5.2 매개변수화된 프롬프트

```python
@server.prompt
def code_review(language: str, level: str = "basic") -> list[SamplingMessage]:
    """지정된 언어와 수준으로 코드 리뷰 프롬프트를 생성한다."""

    instructions = {
        "basic": "기본 문법, 가독성 검사",
        "advanced": "디자인 패턴, 성능, 보안 분석"
    }

    return [
        {
            "role": "user",
            "content": f"{language} 코드를 {level} 수준으로 리뷰해주세요.\n검사 항목: {instructions[level]}"
        }
    ]
```

### 5.3 멀티턴 프롬프트

```python
@server.prompt
def brainstorm_session(topic: str) -> list[SamplingMessage]:
    """주제에 대해 브레인스토밍하는 멀티턴 프롬프트."""
    return [
        {
            "role": "user",
            "content": f"'{topic}'에 대해 브레인스토밍해보자"
        },
        {
            "role": "assistant",
            "content": "좋아합니다! 어떤 측면에서 생각해볼까요?"
        },
        {
            "role": "user",
            "content": "기술적 가능성, 시장 기회, 사용자 가치 측면에서 각각 아이디어를 내주세요"
        }
    ]
```

### 5.4 Context와 함께 사용

```python
@server.prompt
async def personalized_prompt(name: str, ctx: Context) -> list[SamplingMessage]:
    """사용자 정보를 기반으로 개인화된 프롬프트."""
    await ctx.info(f"{name}을(를) 위한 프롬프트 생성 중...")

    db = ctx.fastmcp._lifespan_result.get("db")
    user_profile = await db.get_user_profile(name)

    return [
        {
            "role": "user",
            "content": f"""사용자: {user_profile['name']}
기술 수준: {user_profile['level']}
관심사: {', '.join(user_profile['interests'])}

이 사용자를 위한 맞춤형 학습 경로를 제안해주세요."""
        }
    ]
```

---

## 6. Context 객체

Context는 도구/리소스/프롬프트 실행 중에 요청 정보와 서버 기능에 접근하는 객체다.

### 6.1 주요 속성

```python
@server.tool
async def inspect_context(ctx: Context) -> dict:
    """Context의 모든 주요 속성을 확인한다."""
    return {
        "request_id": ctx.request_id,      # 고유 요청 ID (추적용)
        "session_id": ctx.session_id,      # 세션 ID
        "client_id": ctx.client_id,        # 클라이언트 식별자
        "fastmcp": str(ctx.fastmcp),       # FastMCP 서버 인스턴스
    }
```

### 6.2 로깅 메서드

```python
@server.tool
async def logging_example(ctx: Context) -> str:
    """다양한 로깅 레벨을 사용한다."""

    await ctx.debug("디버그 수준 (개발자용)")
    await ctx.info("정보 수준 (일반)")
    await ctx.warning("경고 수준 (주의)")
    await ctx.error("오류 수준 (문제 발생)")

    # 고급: 원본 log() 메서드 (레벨 지정)
    await ctx.log(
        message="커스텀 로그",
        level="notice",
        logger_name="my_tool",
        extra={"user_id": "jedi", "action": "process"}
    )

    return "로깅 완료"
```

### 6.3 진행률 보고

```python
@server.tool
async def progress_example(ctx: Context) -> str:
    """처리 진행도를 보고한다."""

    items = ["item1", "item2", "item3", "item4", "item5"]

    for i, item in enumerate(items, 1):
        # 처리 로직
        await process_item(item)

        # 진행률 보고 (현재 진행도, 전체, 메시지)
        await ctx.report_progress(i, len(items), f"{item} 처리 중...")

    return "모든 항목 처리 완료"
```

### 6.4 리소스 접근

```python
@server.tool
async def access_resources(ctx: Context) -> dict:
    """서버의 리소스에 접근한다."""

    # 모든 리소스 목록 조회
    resources = await ctx.list_resources()
    resource_names = [r.name for r in resources]

    # 특정 리소스 읽기
    content = await ctx.read_resource("file://config.json")

    # 프롬프트 조회
    prompts = await ctx.list_prompts()

    # 특정 프롬프트 실행
    prompt_result = await ctx.get_prompt(
        name="analyze_code",
        arguments={"language": "python"}
    )

    return {
        "resources": resource_names,
        "prompts": [p.name for p in prompts]
    }
```

### 6.5 상태 관리

```python
@server.tool
async def state_management(input_data: str, ctx: Context) -> str:
    """요청 범위 내에서 상태를 유지한다."""

    # 상태 저장
    counter = ctx.get_state("counter", 0)
    ctx.set_state("counter", counter + 1)

    # 맥락 정보 저장
    ctx.set_state("current_input", input_data)

    return f"현재 호출 #{ctx.get_state('counter')}"
```

---

## 7. 클라이언트 (Client)

MCP 서버를 클라이언트에서 사용하려면 Client 객체로 연결한다.

### 7.1 Client 초기화

```python
from fastmcp import Client

# 로컬 서버 (in-process)
async with Client(server) as client:
    # 클라이언트 초기화 자동 (auto_initialize=True)
    tools = await client.list_tools()

# HTTP 서버에 연결
async with Client("http://localhost:8000/mcp") as client:
    result = await client.call_tool("add", {"a": 5, "b": 3})

# STDIO 프로토콜 (외부 프로세스)
async with Client("stdio://python server.py") as client:
    pass
```

### 7.2 도구 호출

```python
async def use_client():
    async with Client(server) as client:
        # 도구 목록 조회
        tools = await client.list_tools()
        for tool in tools:
            print(f"- {tool.name}: {tool.description}")

        # 도구 호출 (기본)
        result = await client.call_tool(
            "add",
            {"a": 5, "b": 3}
        )
        print(result.data)  # {"result": 8}

        # 도구 호출 (고급)
        result = await client.call_tool(
            "process_data",
            {"input": "test"},
            timeout=30,
            raise_on_error=True,
            meta={"user_id": "jedi"}
        )
```

### 7.3 리소스 및 프롬프트 접근

```python
async def access_resources():
    async with Client(server) as client:
        # 리소스 목록
        resources = await client.list_resources()

        # 리소스 읽기
        content = await client.read_resource("file://config.json")

        # 프롬프트 목록
        prompts = await client.list_prompts()

        # 프롬프트 실행
        result = await client.get_prompt(
            "analyze_code",
            arguments={"language": "python"}
        )
```

---

## 8. 전송 모드 (Transport)

MCP 서버는 다양한 전송 모드를 지원한다.

### 8.1 STDIO (기본, 로컬 개발)

```python
# 서버
if __name__ == "__main__":
    server.run(transport="stdio")
    # 또는
    # await server.run_async(transport="stdio")

# 클라이언트
client = Client("stdio://python server.py")
```

**특징:**
- 표준 입출력 기반
- 프로세스 간 통신
- 로컬 개발에 최적

### 8.2 HTTP/Streamable HTTP (원격)

```python
# 서버 실행
import asyncio

async def run_http():
    await server.run_http_async(
        transport="streamable-http",  # 기본값
        host="0.0.0.0",
        port=8000,
        path="/mcp",
        log_level="info"
    )

asyncio.run(run_http())

# 클라이언트
client = Client("http://localhost:8000/mcp")
```

**특징:**
- REST-like HTTP 기반
- 방화벽 친화적
- 원격 배포에 최적

### 8.3 SSE (Server-Sent Events)

```python
# 서버
await server.run_http_async(
    transport="sse",
    host="localhost",
    port=8000,
    path="/sse"
)

# 클라이언트
client = Client("http://localhost:8000/sse")
```

**특징:**
- 양방향 스트리밍
- 브라우저 호환
- 실시간 업데이트

### 8.4 In-Process (테스트)

```python
# 테스트 코드
async def test_server():
    # 외부 프로세스 없이 직접 테스트
    async with Client(server) as client:
        result = await client.call_tool("add", {"a": 2, "b": 3})
        assert result.data == 5
```

---

## 9. 에러 처리

### 9.1 예외 계층

```
FastMCPError (기본)
├── ToolError           — 도구 실행 오류
├── PromptError         — 프롬프트 생성 오류
├── ResourceError       — 리소스 접근 오류
├── ValidationError     — 파라미터 검증 오류
└── InvalidSignature    — 함수 서명 오류
```

### 9.2 도구에서 에러 발생시키기

```python
from fastmcp.exceptions import ToolError

@server.tool
async def risky_operation(data: str, ctx: Context) -> str:
    """오류 처리 예제."""

    if not data:
        # 클라이언트에 에러 전송
        raise ToolError("데이터가 비어있습니다")

    try:
        result = await process_data(data)
        return result
    except ValueError as e:
        # 특정 예외를 ToolError로 변환
        await ctx.error(f"처리 실패: {e}")
        raise ToolError(f"데이터 처리 실패: {e}") from e
    except Exception as e:
        # 예상치 못한 오류
        await ctx.error(f"예상치 못한 오류: {e}")
        raise ToolError("시스템 오류가 발생했습니다") from e
```

### 9.3 에러 상세정보 마스킹

```python
# 프로덕션: 에러 상세정보 숨기기
server = FastMCP(
    name="SafeServer",
    mask_error_details=True  # 클라이언트가 "An error occurred" 만 받음
)

# 개발: 전체 스택 트레이스 표시
server = FastMCP(
    name="DevServer",
    mask_error_details=False
)
```

### 9.4 입력 검증

```python
# 엄격한 입력 검증 (잘못된 인자는 도구 실행 전 거절)
server = FastMCP(
    name="ValidatedServer",
    strict_input_validation=True
)

@server.tool
def strict_tool(
    count: Annotated[int, Field(ge=1, le=100)]
) -> str:
    """count는 반드시 1~100 사이여야 함."""
    return f"count={count}"
```

---

## 10. 서버 실행

### 10.1 기본 실행

```python
from fastmcp import FastMCP

server = FastMCP(name="MyServer", version="1.0.0")

@server.tool
def hello(name: str) -> str:
    """인사말을 한다."""
    return f"안녕하세요, {name}님!"

# STDIO 모드 (기본)
if __name__ == "__main__":
    server.run()  # 또는 server.run(transport="stdio")
```

**실행:**
```bash
python server.py
# 그러면 표준 입출력으로 MCP 통신 시작
```

### 10.2 HTTP 모드로 실행

```python
import asyncio

if __name__ == "__main__":
    asyncio.run(
        server.run_http_async(
            transport="streamable-http",
            host="0.0.0.0",
            port=8000,
            path="/mcp"
        )
    )
```

**실행:**
```bash
python server.py
# 그러면 http://0.0.0.0:8000/mcp 에서 수신
```

### 10.3 Docker 컨테이너에서 실행

```dockerfile
# Dockerfile
FROM python:3.10

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY server.py .

# HTTP 모드 (포트 노출용)
EXPOSE 8000

CMD ["python", "server.py"]
```

```bash
# 빌드 및 실행
docker build -t my-mcp-server .
docker run -p 8000:8000 my-mcp-server
```

### 10.4 Docker Compose에서 JediSOS와 함께 실행

```yaml
version: '3.8'

services:
  # Hindsight 메모리 서버
  hindsight:
    image: hindsight:latest
    ports:
      - "8888:8888"
    environment:
      - LOG_LEVEL=info

  # Tier 2 MCP 서버 (예: Google Calendar OAuth)
  google_calendar_mcp:
    build:
      context: ./mcp-servers
      dockerfile: Dockerfile.google_calendar
    ports:
      - "8001:8000"
    environment:
      - GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
      - GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}
      - AUTH_PROXY_URL=http://auth-proxy:8002

  # OAuth 권한 관리 프록시
  auth-proxy:
    image: oauth-proxy:latest
    ports:
      - "8002:8000"
    environment:
      - ALLOWED_SCOPES=calendar,drive

  # JediSOS 에이전트 (LangGraph)
  jedi-agent:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8003:8000"
    environment:
      - HINDSIGHT_URL=http://hindsight:8888
      - MCP_GOOGLE_CALENDAR_URL=http://google_calendar_mcp:8000/mcp
      - AUTH_PROXY_URL=http://auth-proxy:8000
    depends_on:
      - hindsight
      - google_calendar_mcp
      - auth-proxy
```

---

## 11. LangGraph 통합

### 11.1 MCP 도구 → LangChain @tool 변환

```python
from langchain.tools import tool
from fastmcp import Client

# 전역 MCP 클라이언트 (서버 시작 시 초기화)
mcp_client: Client | None = None

async def init_mcp_client(server_url: str = "http://localhost:8000/mcp"):
    global mcp_client
    mcp_client = Client(server_url)
    await mcp_client.initialize()

async def close_mcp_client():
    if mcp_client:
        await mcp_client.aclose()

# MCP 도구를 LangChain @tool로 래핑
@tool
async def call_github_api(action: str, args: dict) -> str:
    """GitHub API를 호출한다 (MCP 서버를 통해)."""
    result = await mcp_client.call_tool(
        f"github_{action}",
        args
    )

    if result.is_error:
        return f"오류: {result.content[0].text}"

    if result.structured_content:
        return str(result.structured_content)

    return result.content[0].text if result.content else "결과 없음"

# LangGraph 노드에 등록
tools = [call_github_api, ...]
```

### 11.2 LangGraph 에이전트에 MCP 통합

```python
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_id: str

async def setup_agent():
    """MCP 도구를 포함한 LangGraph 에이전트 생성."""

    # MCP 클라이언트 초기화
    await init_mcp_client("http://google-calendar-mcp:8000/mcp")

    # MCP 도구들을 LangChain @tool로 변환
    mcp_tools = [
        call_github_api,
        call_google_calendar_api,
    ]

    # LLM 모델
    llm = ChatOpenAI(model="gpt-4")

    # ReAct 에이전트 생성
    agent = create_react_agent(llm, mcp_tools)

    return agent

async def run_agent_with_mcp(user_input: str):
    """MCP 도구를 사용하는 에이전트 실행."""
    agent = await setup_agent()

    result = agent.invoke({
        "input": user_input,
        "messages": [{"role": "user", "content": user_input}]
    })

    await close_mcp_client()

    return result["output"]
```

---

## 12. JediSOS 통합 패턴

### 12.1 Tier 2 MCP 서버 (Google Calendar 예제)

```python
# mcp_servers/google_calendar/server.py
from fastmcp import FastMCP, Context
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from contextlib import asynccontextmanager
import os

# OAuth 설정
SCOPES = ['https://www.googleapis.com/auth/calendar']
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

@asynccontextmanager
async def lifespan(server: FastMCP):
    """서버 시작/종료 시 Google API 클라이언트 초기화."""
    print("Google Calendar 초기화 중...")

    # OAuth 토큰 로드
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            "credentials.json", SCOPES
        )
        creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    # Google Calendar 서비스 생성
    service = build("calendar", "v3", credentials=creds)

    yield {"calendar_service": service}

    print("Google Calendar 종료 중...")

# MCP 서버 생성
server = FastMCP(
    name="GoogleCalendarMCP",
    version="1.0.0",
    instructions="Google Calendar를 관리하는 MCP 서버",
    lifespan=lifespan
)

@server.tool
async def list_events(
    calendar_id: str = "primary",
    max_results: int = 10,
    ctx: Context = None
) -> list[dict]:
    """캘린더의 이벤트 목록을 조회한다."""
    service = ctx.fastmcp._lifespan_result["calendar_service"]

    await ctx.info(f"이벤트 조회 중... (최대 {max_results}개)")

    events_result = service.events().list(
        calendarId=calendar_id,
        maxResults=max_results,
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])

    await ctx.report_progress(100, 100, f"{len(events)}개 이벤트 조회됨")

    return events

@server.tool
async def create_event(
    calendar_id: str,
    title: str,
    start_time: str,
    end_time: str,
    ctx: Context = None
) -> dict:
    """새로운 캘린더 이벤트를 생성한다."""
    service = ctx.fastmcp._lifespan_result["calendar_service"]

    event = {
        'summary': title,
        'start': {'dateTime': start_time},
        'end': {'dateTime': end_time},
    }

    await ctx.info(f"이벤트 생성 중: {title}")

    event = service.events().insert(
        calendarId=calendar_id,
        body=event
    ).execute()

    await ctx.report_progress(100, 100, "이벤트 생성 완료")

    return event

@server.resource("resource://calendars")
async def list_calendars(ctx: Context) -> list[dict]:
    """사용 가능한 모든 캘린더를 조회한다."""
    service = ctx.fastmcp._lifespan_result["calendar_service"]

    calendars_result = service.calendarList().list().execute()
    return calendars_result.get('items', [])

if __name__ == "__main__":
    import asyncio
    asyncio.run(
        server.run_http_async(
            transport="streamable-http",
            host="0.0.0.0",
            port=8000
        )
    )
```

### 12.2 JediSOS MCP 클라이언트 통합

```python
# jedisos/integrations/mcp_client_manager.py
from fastmcp import Client
from typing import Dict
import os

class MCPClientManager:
    """JediSOS에서 여러 Tier 2 MCP 서버를 관리한다."""

    def __init__(self):
        self.clients: Dict[str, Client] = {}
        self.server_urls = {
            "google_calendar": os.getenv(
                "MCP_GOOGLE_CALENDAR_URL",
                "http://localhost:8001/mcp"
            ),
            "github": os.getenv(
                "MCP_GITHUB_URL",
                "http://localhost:8002/mcp"
            ),
            "slack": os.getenv(
                "MCP_SLACK_URL",
                "http://localhost:8003/mcp"
            ),
        }

    async def initialize(self):
        """모든 MCP 클라이언트 초기화."""
        for name, url in self.server_urls.items():
            try:
                self.clients[name] = Client(url)
                await self.clients[name].initialize()
                print(f"✓ MCP '{name}' 초기화 성공")
            except Exception as e:
                print(f"✗ MCP '{name}' 초기화 실패: {e}")

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        args: dict
    ) -> dict:
        """MCP 서버의 도구를 호출한다."""
        if server_name not in self.clients:
            raise ValueError(f"Unknown MCP server: {server_name}")

        client = self.clients[server_name]
        result = await client.call_tool(tool_name, args)

        return {
            "success": not result.is_error,
            "data": result.structured_content or result.data,
            "error": result.content[0].text if result.is_error else None
        }

    async def close(self):
        """모든 클라이언트 연결 종료."""
        for client in self.clients.values():
            await client.aclose()

# LangGraph 노드에서 사용
mcp_manager = MCPClientManager()

async def external_api_node(state: AgentState) -> AgentState:
    """외부 API (Tier 2) 호출 노드."""

    # 사용자 명령 분석
    user_message = state["messages"][-1].content

    if "캘린더" in user_message or "일정" in user_message:
        # Google Calendar MCP 호출
        result = await mcp_manager.call_tool(
            "google_calendar",
            "list_events",
            {"calendar_id": "primary", "max_results": 5}
        )

        context = f"조회된 캘린더 이벤트:\n{result['data']}"

    elif "GitHub" in user_message or "레포" in user_message:
        # GitHub MCP 호출
        result = await mcp_manager.call_tool(
            "github",
            "list_repositories",
            {"username": state.get("github_user", "octocat")}
        )

        context = f"GitHub 레포지토리:\n{result['data']}"

    else:
        context = ""

    return {
        **state,
        "external_context": context
    }
```

### 12.3 Hindsight 메모리와 MCP 연동

```python
# jedisos/agents/memory_and_api_agent.py
from langgraph.graph import StateGraph, START, END
from hindsight_client import Hindsight
from jedisos.integrations.mcp_client_manager import MCPClientManager
from jedisos.types import AgentState

# 전역 클라이언트
hindsight_client = Hindsight(
    base_url=os.getenv("HINDSIGHT_URL", "http://localhost:8888")
)
mcp_manager = MCPClientManager()

async def memory_and_context_node(state: AgentState) -> AgentState:
    """기억 검색 + 외부 API 호출 노드."""

    query = state["messages"][-1].content
    user_id = state["user_id"]

    # Step 1: 과거 기억 검색
    memories = await hindsight_client.arecall(
        bank_id=user_id,
        query=query,
        budget="mid"
    )

    memory_context = "\n".join([f"- {m.text}" for m in memories])

    # Step 2: 관련 외부 API 호출
    api_context = ""
    if "캘린더" in query:
        result = await mcp_manager.call_tool(
            "google_calendar",
            "list_events",
            {"calendar_id": "primary"}
        )
        api_context = f"현재 일정:\n{result['data']}"

    # Step 3: 기억에 현재 쿼리 저장
    await hindsight_client.aretain(
        bank_id=user_id,
        content=f"사용자 질문: {query}",
        context="대화",
        tags=["conversation"]
    )

    return {
        **state,
        "memory_context": memory_context,
        "api_context": api_context
    }
```

---

## 13. 주의사항 및 팁

### 13.1 버전 관리

```python
# ⚠️ 중요: FastMCP v3.0 RC1이 출시되었으므로 v2.x로 핀 필수
# requirements.txt
fastmcp>=2.14.0,<3.0.0  # v3.0 출시 예정, 아직 RC1 단계

# mcp SDK도 v2.x로 유지
mcp>=1.0.0,<2.0.0  # v2.0은 Q1 2026 예정
```

### 13.2 동기 도구의 ThreadPool 디스패치

```python
# v2.14에서 sync 도구는 자동으로 threadpool에서 실행됨
# 따라서 동기식 DB 라이브러리도 안전하게 사용 가능

import sqlite3

@server.tool
def query_database(query: str) -> list[dict]:
    """동기식 SQLite 호출 (자동으로 threadpool 디스패치됨)."""
    conn = sqlite3.connect("data.db")
    cursor = conn.cursor()
    cursor.execute(query)
    return cursor.fetchall()
    # → FastMCP가 자동으로 asyncio의 to_thread() 사용해 실행
```

### 13.3 Lifespan에서의 DB 연결 관리 (권장 패턴)

```python
@asynccontextmanager
async def lifespan(server: FastMCP):
    """DB 연결풀 패턴."""

    # 연결풀 생성
    pool = await create_db_pool(
        dsn=os.getenv("DATABASE_URL"),
        min_size=5,
        max_size=20
    )

    yield {"db_pool": pool}

    # 연결풀 종료 (모든 연결 정리)
    await pool.close()

@server.tool
async def query(sql: str, ctx: Context) -> list[dict]:
    """연결풀에서 커넥션을 가져와 사용."""
    pool = ctx.fastmcp._lifespan_result["db_pool"]

    async with pool.acquire() as conn:
        result = await conn.fetch(sql)
        return result
```

### 13.4 에러 처리 Best Practices

```python
from fastmcp.exceptions import ToolError

@server.tool
async def safe_operation(data: str, ctx: Context) -> dict:
    """안전한 에러 처리."""

    # 1. 입력 검증
    if not data:
        raise ToolError("입력 데이터가 필요합니다")

    # 2. 작업 실행 (예외 처리)
    try:
        result = await risky_operation(data)
        await ctx.info("작업 성공")
        return result

    except ValueError as e:
        # 3. 예상된 오류는 로깅 후 ToolError로 전환
        await ctx.warning(f"데이터 검증 실패: {e}")
        raise ToolError(f"잘못된 입력: {e}") from e

    except Exception as e:
        # 4. 예상치 못한 오류는 스택 트레이스 로깅
        await ctx.error(f"예상치 못한 오류: {type(e).__name__}: {e}")
        raise ToolError("시스템 오류 발생") from e
```

### 13.5 성능 최적화

```python
# 1. 비동기 도구 사용 (I/O 대기 시간 숨김)
@server.tool
async def fetch_many_urls(urls: list[str]) -> dict:
    """여러 URL을 동시에 가져온다."""
    import asyncio
    import httpx

    async with httpx.AsyncClient() as client:
        # 동시 요청 (순차가 아님!)
        tasks = [client.get(url) for url in urls]
        responses = await asyncio.gather(*tasks)

        return {
            "results": [r.json() for r in responses]
        }

# 2. Context를 통한 진행률 보고
@server.tool
async def batch_process(items: list[str], ctx: Context) -> str:
    """배치 처리 진행도 표시."""
    total = len(items)

    for i, item in enumerate(items, 1):
        result = await process_item(item)

        # 진행률 보고 (LLM에 표시)
        await ctx.report_progress(i, total, f"{item} 처리 중")

    return f"{total}개 항목 처리 완료"

# 3. 캐싱 활용
from functools import lru_cache
import asyncio

@server.tool
async def fetch_config() -> dict:
    """설정 파일을 가져온다 (캐시 활용)."""

    # 비동기 캐시가 필요하면 수동으로 구현
    if not hasattr(fetch_config, "_cache"):
        fetch_config._cache = await load_config()

    return fetch_config._cache
```

### 13.6 로깅과 디버깅

```python
from fastmcp import settings

# 로깅 설정
settings.log_level = "debug"  # "debug" | "info" | "warning" | "error"
settings.enable_rich_tracebacks = True  # 예쁜 스택 트레이스

@server.tool
async def debug_tool(data: str, ctx: Context) -> str:
    """디버깅용 도구."""

    # 로깅 활용
    await ctx.debug(f"입력: {data}")
    await ctx.info(f"처리 중...")

    # 추적 정보 포함 (프로덕션에서는 비활성화)
    if settings.log_level == "debug":
        import traceback
        await ctx.debug(f"스택: {traceback.format_stack()}")

    return "완료"
```

---

## 14. 완전한 예제: Hindsight 메모리 MCP 서버

```python
# mcp_servers/hindsight_memory/server.py
"""
JediSOS의 Tier 2 MCP 서버: Hindsight 메모리 엔진
외부에서 메모리 저장/검색/반영을 요청할 수 있는 인터페이스 제공
"""

from fastmcp import FastMCP, Context
from hindsight_client import Hindsight
from contextlib import asynccontextmanager
from typing import Annotated
from pydantic import Field
import os

@asynccontextmanager
async def lifespan(server: FastMCP):
    """Hindsight 클라이언트 초기화."""
    print("Hindsight 메모리 서버 시작...")

    hindsight = Hindsight(
        base_url=os.getenv("HINDSIGHT_URL", "http://localhost:8888"),
        api_key=os.getenv("HINDSIGHT_API_KEY")
    )

    yield {"hindsight": hindsight}

    await hindsight.aclose()
    print("Hindsight 메모리 서버 종료...")

server = FastMCP(
    name="HindsightMemoryMCP",
    version="1.0.0",
    instructions="""
    이 서버는 Hindsight 메모리 엔진을 MCP 인터페이스로 제공합니다.
    - remember: 새로운 기억 저장
    - search: 기억 검색 (의미 기반)
    - reflect: 기억 기반 답변 생성
    """,
    lifespan=lifespan
)

@server.tool
async def remember(
    bank_id: str,
    content: str,
    context: Annotated[str, Field(description="기억의 맥락")] = "conversation",
    tags: Annotated[list[str], Field(description="분류용 태그")] = None,
    ctx: Context = None
) -> dict:
    """새로운 기억을 저장한다."""
    hindsight = ctx.fastmcp._lifespan_result["hindsight"]

    await ctx.info(f"기억 저장 중... ({len(content)} 글자)")

    result = await hindsight.aretain(
        bank_id=bank_id,
        content=content,
        context=context,
        tags=tags or []
    )

    await ctx.report_progress(100, 100, "저장 완료")

    return {
        "success": result.success,
        "items_count": result.items_count,
        "bank_id": result.bank_id
    }

@server.tool
async def search(
    bank_id: str,
    query: str,
    budget: Annotated[
        str,
        Field(description="검색 깊이: low/mid/high")
    ] = "mid",
    types: Annotated[
        list[str],
        Field(description="필터링할 기억 유형")
    ] = None,
    ctx: Context = None
) -> dict:
    """기억에서 관련 정보를 검색한다."""
    hindsight = ctx.fastmcp._lifespan_result["hindsight"]

    await ctx.info(f"기억 검색 중: {query}")
    await ctx.report_progress(50, 100, "검색 진행 중...")

    results = await hindsight.arecall(
        bank_id=bank_id,
        query=query,
        budget=budget,
        types=types
    )

    await ctx.report_progress(100, 100, f"{len(results)}개 결과 발견")

    return {
        "query": query,
        "count": len(results),
        "results": [
            {
                "text": r.text,
                "type": r.type,
                "context": r.context,
                "score": getattr(r, "score", None)
            }
            for r in results
        ]
    }

@server.tool
async def reflect(
    bank_id: str,
    question: str,
    budget: str = "mid",
    ctx: Context = None
) -> dict:
    """기억을 기반으로 질문에 답변한다."""
    hindsight = ctx.fastmcp._lifespan_result["hindsight"]

    await ctx.info(f"기억 기반 답변 생성 중: {question}")

    answer = await hindsight.areflect(
        bank_id=bank_id,
        query=question,
        budget=budget
    )

    await ctx.report_progress(100, 100, "답변 완료")

    return {
        "question": question,
        "answer": answer.text,
        "based_on": answer.based_on
    }

@server.resource("resource://banks/{bank_id}/status")
async def get_bank_status(bank_id: str, ctx: Context) -> dict:
    """뱅크의 상태를 조회한다."""
    # 예: 저장된 기억 개수, 최근 업데이트 등
    return {
        "bank_id": bank_id,
        "status": "active",
        "total_memories": 1234,
        "last_update": "2026-02-17T10:30:00Z"
    }

if __name__ == "__main__":
    import asyncio

    asyncio.run(
        server.run_http_async(
            transport="streamable-http",
            host="0.0.0.0",
            port=8000
        )
    )
```

### Docker 실행 (docker-compose.yml)

```yaml
services:
  hindsight-memory-mcp:
    build:
      context: ./mcp-servers/hindsight_memory
    ports:
      - "8100:8000"
    environment:
      - HINDSIGHT_URL=http://hindsight:8888
      - HINDSIGHT_API_KEY=${HINDSIGHT_API_KEY}
      - LOG_LEVEL=info
    depends_on:
      - hindsight
```

---

## 참고 자료

- **FastMCP 공식 문서**: https://gofastmcp.com
- **GitHub 저장소**: https://github.com/jlowin/fastmcp
- **MCP 사양**: https://spec.modelcontextprotocol.io
- **JediSOS 아키텍처**: `/docs/ARCHITECTURE.md`
- **Hindsight 사용법**: `/docs/HINDSIGHT_USAGE.md`

---

## 버전 정보

- **FastMCP**: 2.14.5 (v3.0 RC1 출시, <3.0 핀 필수)
- **MCP SDK**: 1.26.0 (v2.0은 Q1 2026 예정, <2.0 핀 필수)
- **Python**: 3.10+
- **최종 업데이트**: 2026-02-17
