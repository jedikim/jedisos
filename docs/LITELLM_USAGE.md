# LiteLLM 사용법 가이드

> JediSOS에서 LiteLLM을 통해 100+ LLM 프로바이더를 통합 관리하는 방법을 정리한 문서
> litellm v1.81.13 기준

---

## 1. 핵심 개념

LiteLLM은 **100+ LLM 프로바이더를 단일 인터페이스**로 제공한다.

| 개념 | 설명 | 예시 |
|------|------|------|
| **OpenAI 호환 API** | 모든 프로바이더가 동일한 completion() 함수 사용 | `litellm.completion(model="gpt-4", ...)` |
| **환경변수 자동 인증** | API 키를 .env에 저장하면 자동 로드 | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` |
| **프로바이더 접두사** | 프로바이더를 명시적으로 지정 (선택) | `gemini/gemini-pro`, `groq/mixtral-8x7b` |

### 1.1 주요 기능

| 기능 | 설명 |
|------|------|
| **completion()** | 동기 API 호출 |
| **acompletion()** | 비동기 API 호출 |
| **Router** | 멀티 모델 관리 + 폴백 + 로드 밸런싱 |
| **streaming** | 실시간 응답 스트리밍 |
| **tool_calling** | 함수 호출 (OpenAI 호환) |
| **cost_tracking** | 자동 비용 계산 및 추적 |
| **callbacks** | 요청/응답 인터셉팅 및 로깅 |

---

## 2. 기본 호출

### 2.1 동기 호출 (Sync)

```python
import litellm

# 기본 호출
response = litellm.completion(
    model="gpt-4",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain quantum computing in 2 sentences."}
    ],
    temperature=0.7,
    max_tokens=200,
    timeout=30
)

# 응답 접근
text = response.choices[0].message.content
print(f"모델: {response.model}")
print(f"생성 텍스트: {text}")
print(f"사용 토큰: {response.usage.total_tokens}")
```

### 2.2 비동기 호출 (Async)

```python
import asyncio
import litellm

async def chat_async():
    response = await litellm.acompletion(
        model="gpt-4",
        messages=[{"role": "user", "content": "Hello, how are you?"}],
        temperature=0.7,
        max_tokens=100,
        timeout=30
    )
    return response.choices[0].message.content

# 실행
result = asyncio.run(chat_async())
print(result)
```

### 2.3 핵심 파라미터

| 파라미터 | 타입 | 설명 | 기본값 |
|---------|------|------|--------|
| `model` | str | 모델 ID (프로바이더 접두사 포함 가능) | 필수 |
| `messages` | list | `role`, `content` 포함 메시지 리스트 | 필수 |
| `temperature` | float | 무작위성 (0.0-2.0) | 1.0 |
| `max_tokens` | int | 최대 응답 토큰 | None |
| `top_p` | float | 핵심 샘플링 (0.0-1.0) | 1.0 |
| `stop` | str/list | 생성 중단 조건 | None |
| `stream` | bool | 스트리밍 응답 | False |
| `timeout` | float | 요청 타임아웃 (초) | 600 |
| `tools` | list | 함수 호출 도구 목록 | None |
| `tool_choice` | str/dict | 도구 선택 옵션 | "auto" |

### 2.4 JediSOS 기본 사용 패턴

```python
# llm_config.yaml에서 설정 로드
import yaml
import litellm

with open("llm_config.yaml") as f:
    config = yaml.safe_load(f)

# JediSOS 기본 모델 체인
models = [
    "claude-sonnet-5-20260203",  # 1순위
    "gpt-5.2",                    # 2순위
    "gemini/gemini-3-flash",      # 3순위
    "ollama/llama4"               # 로컬 폴백
]

# 첫 번째 성공한 모델로 호출
for model in models:
    try:
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": "Hello"}],
            timeout=10
        )
        print(f"성공: {model}")
        break
    except litellm.APIError as e:
        print(f"실패: {model} - {e}")
        continue
```

---

## 3. 모델 이름 규칙

### 3.1 프로바이더별 접두사

| 프로바이더 | 접두사 | 예시 | 필수 |
|-----------|--------|------|------|
| OpenAI | 없음 | `gpt-4`, `gpt-3.5-turbo` | No |
| Anthropic | 없음 | `claude-3-opus-20240229` | No |
| Google Gemini | `gemini/` | `gemini/gemini-pro` | **Yes** |
| Groq | `groq/` | `groq/mixtral-8x7b-32768` | **Yes** |
| Ollama (로컬) | `ollama/` | `ollama/llama2` | **Yes** |
| Azure OpenAI | `azure/` | `azure/gpt-4-deployment` | **Yes** |
| AWS Bedrock | `bedrock/` | `bedrock/anthropic.claude-3-sonnet` | **Yes** |
| HuggingFace | `huggingface/` | `huggingface/meta-llama/Llama-2-7b` | **Yes** |
| Cohere | `cohere/` | `cohere/command-r-plus` | **Yes** |
| Together AI | `together_ai/` | `together_ai/meta-llama/Llama-2-70b` | **Yes** |
| Vertex AI | `vertex_ai/` | `vertex_ai/gemini-pro` | **Yes** |

### 3.2 JediSOS 기본 모델 체인

```
1순위: claude-sonnet-5-20260203 (Anthropic)
2순위: gpt-5.2 (OpenAI)
3순위: gemini/gemini-3-flash (Google)
4순위: ollama/llama4 (로컬 폴백)
```

### 3.3 환경변수 설정

```bash
# .env 파일
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
GROQ_API_KEY=...
GEMINI_API_KEY=...
```

```python
# Python에서 자동 로드 (설정 불필요)
response = litellm.completion(model="gpt-4", messages=[...])
response = litellm.completion(model="claude-3-opus-20240229", messages=[...])
response = litellm.completion(model="gemini/gemini-pro", messages=[...])
```

---

## 4. Tool/Function Calling

### 4.1 Tool 정의 (OpenAI 형식)

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "특정 위치의 날씨를 조회한다",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "도시, 국가 (예: 'Seoul, South Korea')"
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "온도 단위"
                    }
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "웹에서 정보를 검색한다",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "검색 쿼리"
                    }
                },
                "required": ["query"]
            }
        }
    }
]
```

### 4.2 Tool 호출 옵션

```python
# "auto" - 모델이 자동으로 판단
response = litellm.completion(
    model="gpt-4",
    messages=[{"role": "user", "content": "서울 날씨는?"}],
    tools=tools,
    tool_choice="auto"
)

# "required" - 반드시 도구 호출
response = litellm.completion(
    model="gpt-4",
    messages=[...],
    tools=tools,
    tool_choice="required"
)

# 특정 도구만 - 지정된 도구만 사용
response = litellm.completion(
    model="gpt-4",
    messages=[...],
    tools=tools,
    tool_choice={
        "type": "function",
        "function": {"name": "get_weather"}
    }
)

# "none" - 도구 호출 금지
response = litellm.completion(
    model="gpt-4",
    messages=[...],
    tools=tools,
    tool_choice="none"
)
```

### 4.3 Tool Call 응답 처리

```python
import json

response = litellm.completion(
    model="gpt-4",
    messages=[{"role": "user", "content": "서울과 부산 날씨는?"}],
    tools=tools,
    tool_choice="auto"
)

# Tool call 확인
message = response.choices[0].message

if message.tool_calls:
    for tool_call in message.tool_calls:
        print(f"도구: {tool_call.function.name}")
        print(f"ID: {tool_call.id}")

        # JSON 문자열을 파싱
        args = json.loads(tool_call.function.arguments)
        print(f"인자: {args}")

        # 도구 실행 (가상)
        if tool_call.function.name == "get_weather":
            result = get_weather(args["location"], args.get("unit", "celsius"))
        else:
            result = "Unknown tool"
else:
    print(f"응답: {message.content}")
```

### 4.4 ReAct 에이전트 루프 (JediSOS 패턴)

```python
import json

messages = [{"role": "user", "content": "서울과 부산 날씨를 비교해줘"}]
tools = [...]

while True:
    # LLM 호출
    response = litellm.completion(
        model="gpt-4",
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )

    # 어시스턴트 응답을 메시지에 추가
    assistant_message = {
        "role": "assistant",
        "content": response.choices[0].message.content,
    }
    if response.choices[0].message.tool_calls:
        assistant_message["tool_calls"] = response.choices[0].message.tool_calls

    messages.append(assistant_message)

    # Tool call이 없으면 종료
    if not response.choices[0].message.tool_calls:
        print(f"최종 답변: {response.choices[0].message.content}")
        break

    # Tool 실행 및 결과 추가
    for tool_call in response.choices[0].message.tool_calls:
        tool_name = tool_call.function.name
        tool_args = json.loads(tool_call.function.arguments)

        # 도구 실행
        if tool_name == "get_weather":
            result = {"weather": "sunny", "temp": 15}
        else:
            result = {"error": f"Unknown tool: {tool_name}"}

        # 결과를 tool role 메시지로 추가
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": json.dumps(result)
        })
```

---

## 5. 스트리밍

### 5.1 동기 스트리밍

```python
response = litellm.completion(
    model="gpt-4",
    messages=[{"role": "user", "content": "1부터 10까지 세어줘"}],
    stream=True
)

# CustomStreamWrapper 순회
for chunk in response:
    # delta에 증분 데이터 포함
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end='', flush=True)

    # 종료 확인
    if chunk.choices[0].finish_reason == "stop":
        print("\n[완료]")
        break
```

### 5.2 비동기 스트리밍 (권장)

```python
import asyncio

async def stream_chat():
    response = await litellm.acompletion(
        model="gpt-4",
        messages=[{"role": "user", "content": "1부터 10까지 세어줘"}],
        stream=True
    )

    # async for로 청크 순회
    async for chunk in response:
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end='', flush=True)

        if chunk.choices[0].finish_reason == "stop":
            break

asyncio.run(stream_chat())
```

### 5.3 스트리밍 + Tool Calling

```python
response = litellm.completion(
    model="gpt-4",
    messages=[{"role": "user", "content": "날씨 조회해줘"}],
    tools=tools,
    stream=True
)

for chunk in response:
    # 텍스트 청크
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end='', flush=True)

    # Tool call 청크
    if chunk.choices[0].delta.tool_calls:
        for tool_call in chunk.choices[0].delta.tool_calls:
            print(f"\n[도구] {tool_call.function.name}")
            print(f"[인자] {tool_call.function.arguments}")
```

### 5.4 스트리밍 옵션

```python
# include_usage=True로 토큰 수 확인 (마지막 청크에 포함)
response = await litellm.acompletion(
    model="gpt-4",
    messages=[...],
    stream=True,
    stream_options={
        "include_usage": True
    }
)

async for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end='')

    # 마지막 청크에서 usage 확인
    if hasattr(chunk, 'usage') and chunk.usage:
        print(f"\n사용 토큰: {chunk.usage.total_tokens}")
```

---

## 6. Router (멀티 모델 관리)

### 6.1 Router 초기화

```python
from litellm import Router

model_list = [
    {
        "model_name": "gpt4-prod",
        "litellm_params": {
            "model": "gpt-4",
            "api_key": "sk-...",
        },
        "tpm_limit": 10000,      # 분당 토큰 제한
        "rpm_limit": 500,        # 분당 요청 제한
        "timeout": 30,
    },
    {
        "model_name": "gpt35-backup",
        "litellm_params": {
            "model": "gpt-3.5-turbo",
            "api_key": "sk-...",
        },
        "tpm_limit": 90000,
        "timeout": 30,
    },
    {
        "model_name": "claude-prod",
        "litellm_params": {
            "model": "claude-3-opus-20240229",
            "api_key": "sk-ant-...",
        },
        "timeout": 30,
    },
]

router = Router(
    model_list=model_list,
    routing_strategy="least-busy"  # 로드 밸런싱 전략
)
```

### 6.2 Router 호출

```python
# model_name으로 호출 (model_list의 "model_name" 사용)
response = router.completion(
    model="gpt4-prod",
    messages=[{"role": "user", "content": "Hello"}],
    temperature=0.7,
    max_tokens=500
)

# 비동기
response = await router.acompletion(
    model="gpt4-prod",
    messages=[...],
)

# 어느 배포가 사용될지 확인
deployment = router.get_available_deployment(
    model="gpt4-prod",
    messages=messages
)
print(f"사용 모델: {deployment['litellm_params']['model']}")
```

### 6.3 라우팅 전략 (6가지)

| 전략 | 설명 | 용도 |
|------|------|------|
| `simple-shuffle` | 무작위 선택 | 기본값, 단순 로드 분산 |
| `least-busy` | 활성 요청 가장 적은 배포 | 일반적으로 최적 |
| `cost-based` | 가장 저렴한 배포 우선 | 비용 최소화 |
| `latency-based` | 가장 빠른 배포 | 응답 속도 최적화 |
| `usage-based` | TPM/RPM 사용량 기반 | 할당량 관리 |
| `usage-based-v2` | 개선된 사용량 기반 | 고급 할당량 관리 |

```python
# latency-based 전략
router = Router(
    model_list=model_list,
    routing_strategy="latency-based-routing",
    routing_strategy_args={"window_size": 100}  # 최근 100개 요청 기반
)
```

### 6.4 폴백 (Fallback)

```python
fallbacks = [
    {
        "model_name": "gpt4-prod",
        "fallbacks": ["gpt35-backup", "claude-prod"]
    }
]

context_window_fallbacks = [
    {
        "model_name": "gpt4-prod",
        "fallbacks": ["gpt35-backup"]  # 컨텍스트 초과 시 더 작은 모델로
    }
]

router = Router(
    model_list=model_list,
    fallbacks=fallbacks,
    context_window_fallbacks=context_window_fallbacks,
    allowed_fails=3,          # 3번 실패 후 쿨다운
    cooldown_time=60,         # 60초 대기
)
```

### 6.5 JediSOS Router 통합 패턴

```python
from litellm import Router

# JediSOS 기본 설정
router = Router(
    model_list=[
        {
            "model_name": "primary",
            "litellm_params": {"model": "claude-sonnet-5-20260203"},
            "timeout": 30
        },
        {
            "model_name": "fallback1",
            "litellm_params": {"model": "gpt-5.2"},
            "timeout": 30
        },
        {
            "model_name": "fallback2",
            "litellm_params": {"model": "gemini/gemini-3-flash"},
            "timeout": 30
        },
        {
            "model_name": "local",
            "litellm_params": {"model": "ollama/llama4"},
            "timeout": 10
        }
    ],
    fallbacks=[
        {
            "model_name": "primary",
            "fallbacks": ["fallback1", "fallback2", "local"]
        }
    ],
    routing_strategy="least-busy",
    allowed_fails=2,
    cooldown_time=30
)

# 사용
response = await router.acompletion(
    model="primary",
    messages=[{"role": "user", "content": query}],
    temperature=0.7
)
```

---

## 7. 비용 추적

### 7.1 자동 비용 계산

```python
response = litellm.completion(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}],
)

# 응답에서 비용 추출
if hasattr(response, '_hidden_params'):
    cost = response._hidden_params.get('response_cost', 0)
    print(f"비용: ${cost:.6f}")

# 토큰 정보
print(f"입력 토큰: {response.usage.prompt_tokens}")
print(f"출력 토큰: {response.usage.completion_tokens}")
print(f"전체 토큰: {response.usage.total_tokens}")
```

### 7.2 completion_cost() 함수

```python
import litellm

# 응답 객체에서 비용 계산
cost = litellm.completion_cost(
    completion_response=response,
    model="gpt-4"
)
print(f"비용: ${cost:.6f}")

# 토큰 수로 수동 계산
cost = litellm.completion_cost(
    model="gpt-4",
    completion_tokens=100,
    prompt_tokens=50
)
print(f"예상 비용: ${cost:.6f}")
```

### 7.3 Success Callback으로 자동 추적

```python
def log_cost_callback(kwargs, completion_response, start_time, end_time):
    """비용을 자동으로 로깅하는 콜백"""
    model = kwargs.get("model")

    # 비용 추출
    if hasattr(completion_response, '_hidden_params'):
        cost = completion_response._hidden_params.get('response_cost', 0)
    else:
        cost = 0

    # 토큰 정보
    usage = completion_response.get('usage', {})

    # 데이터베이스에 저장 (JediSOS cost_tracking 테이블)
    db.insert_into_cost_tracking(
        model=model,
        cost=cost,
        prompt_tokens=usage.get('prompt_tokens', 0),
        completion_tokens=usage.get('completion_tokens', 0),
        timestamp=datetime.now()
    )

    print(f"[비용] {model}: ${cost:.6f} ({usage.get('total_tokens', 0)} 토큰)")

# 콜백 등록
litellm.success_callback = [log_cost_callback]

# 이후 모든 completion()이 자동으로 콜백 호출
response = litellm.completion(...)
```

### 7.4 모델별 가격 정보

```python
from litellm import model_cost

# 모델 가격 조회
pricing = model_cost.get("gpt-4")
print(f"입력 가격: ${pricing['input_cost_per_token']}/token")
print(f"출력 가격: ${pricing['output_cost_per_token']}/token")

# 모든 모델 목록
for model_name, info in model_cost.items():
    print(f"{model_name}: in=${info['input_cost_per_token']}, out=${info['output_cost_per_token']}")
```

---

## 8. 콜백 및 로깅

### 8.1 전역 콜백 리스트

```python
import litellm

# 4가지 콜백 포인트
litellm.input_callback = []      # API 호출 전 (요청 검증)
litellm.success_callback = []    # 성공 후
litellm.failure_callback = []    # 실패 후
litellm.service_callback = []    # 서비스 레벨 이벤트
```

### 8.2 커스텀 콜백

```python
def my_success_callback(kwargs, completion_response, start_time, end_time):
    """
    성공 후 호출되는 콜백

    Args:
        kwargs: 원본 요청 파라미터
        completion_response: ModelResponse 객체
        start_time: 요청 시작 시각 (unix timestamp)
        end_time: 요청 종료 시각 (unix timestamp)
    """
    duration = end_time - start_time
    model = kwargs.get("model")

    print(f"✓ {model}")
    print(f"  요청 시간: {duration:.2f}초")
    print(f"  토큰: {completion_response.usage.total_tokens}")

def my_failure_callback(kwargs, completion_response, start_time, end_time):
    """실패 후 호출되는 콜백"""
    model = kwargs.get("model")
    error = completion_response.get("error", "Unknown error")

    print(f"✗ {model}: {error}")

# 등록
litellm.success_callback = [my_success_callback]
litellm.failure_callback = [my_failure_callback]

# 사용
response = litellm.completion(...)  # 콜백이 자동 호출됨
```

### 8.3 Input Callback (요청 전 검증)

```python
def validate_request(kwargs, user_auth_token=None):
    """API 호출 전 요청 검증"""
    model = kwargs.get("model")
    tokens = len(kwargs.get("messages", [])) * 100  # 대략적 추정

    # 속도 제한 확인
    if tokens > 100000:
        raise ValueError(f"요청이 너무 큽니다: {tokens} 토큰")

    # 필요시 kwargs 수정
    kwargs["timeout"] = 30

    return kwargs

litellm.input_callback = [validate_request]
```

### 8.4 구조화된 로깅 (Structlog)

```python
import litellm
import structlog

logger = structlog.get_logger()

def structured_logging_callback(kwargs, completion_response, start_time, end_time):
    """구조화된 로그 기록"""
    logger.info(
        "litellm_completion",
        model=kwargs.get("model"),
        duration_seconds=end_time - start_time,
        prompt_tokens=completion_response.usage.prompt_tokens,
        completion_tokens=completion_response.usage.completion_tokens,
        cost=completion_response._hidden_params.get('response_cost', 0)
    )

litellm.success_callback = [structured_logging_callback]
```

### 8.5 여러 콜백 등록

```python
litellm.success_callback = [
    log_cost_callback,
    structured_logging_callback,
    my_success_callback,
    "langfuse"  # 내장 Langfuse 콜백
]
```

---

## 9. 에러 처리

### 9.1 주요 예외

```python
import litellm

try:
    response = litellm.completion(...)

except litellm.RateLimitError as e:
    # 속도 제한 초과
    print(f"Rate limit: {e}")
    print(f"재시도 대기: {e.response.headers.get('retry-after')}초")
    # → 잠깐 기다렸다가 재시도 권장

except litellm.ContextWindowExceededError as e:
    # 컨텍스트 윈도우 초과
    print(f"컨텍스트 초과: {e}")
    # → 더 작은 모델로 폴백

except litellm.AuthenticationError as e:
    # 인증 실패 (API 키 오류)
    print(f"인증 실패: {e}")
    print(f"프로바이더: {e.llm_provider}")

except litellm.APIConnectionError as e:
    # 네트워크 연결 오류
    print(f"연결 실패: {e}")

except litellm.Timeout as e:
    # 요청 타임아웃
    print(f"타임아웃: {e}")

except litellm.BadRequestError as e:
    # 잘못된 파라미터
    print(f"잘못된 요청: {e}")

except litellm.BudgetExceededError as e:
    # 비용 예산 초과 (Router)
    print(f"예산 초과: {e}")

except litellm.APIError as e:
    # 일반 API 에러
    print(f"API 에러: {e}")
```

### 9.2 전체 예외 목록

```python
litellm.APIError                      # 기본 API 에러
litellm.RateLimitError                # Rate limit
litellm.ContextWindowExceededError    # 컨텍스트 윈도우 초과
litellm.AuthenticationError           # 인증 실패
litellm.NotFoundError                 # 모델 없음
litellm.BadRequestError               # 잘못된 요청
litellm.ContentPolicyViolationError   # 정책 위반
litellm.ServiceUnavailableError       # 서비스 오류
litellm.APIConnectionError            # 연결 오류
litellm.Timeout                       # 타임아웃
litellm.BudgetExceededError           # 예산 초과
litellm.UnsupportedParamsError        # 미지원 파라미터
```

### 9.3 자동 재시도

```python
# completion() 함수 레벨 재시도
response = litellm.completion(
    model="gpt-4",
    messages=[...],
    max_retries=3,      # 최대 3번 재시도
    timeout=30
)

# Router 레벨 재시도
from litellm.types.router import RetryPolicy

retry_policy = RetryPolicy(
    RateLimitError=5,           # Rate limit은 5번 재시도
    APIConnectionError=2,       # 연결 에러는 2번 재시도
    ContextWindowExceededError=0  # 컨텍스트 초과는 재시도 안함
)

router = Router(
    model_list=model_list,
    retry_policy=retry_policy,
    retry_after=5  # 재시도 전 5초 대기
)
```

### 9.4 JediSOS 패턴: 에러 처리 + 폴백

```python
async def complete_with_fallback(
    query: str,
    max_retries: int = 2
) -> str:
    """폴백 및 재시도를 포함한 completion"""

    models = [
        "claude-sonnet-5-20260203",
        "gpt-5.2",
        "gemini/gemini-3-flash",
        "ollama/llama4"
    ]

    for attempt in range(max_retries):
        for model in models:
            try:
                response = await litellm.acompletion(
                    model=model,
                    messages=[{"role": "user", "content": query}],
                    timeout=30
                )
                return response.choices[0].message.content

            except litellm.ContextWindowExceededError:
                # 컨텍스트 초과 → 다음 모델로
                continue

            except litellm.RateLimitError:
                # 속도 제한 → 3초 대기 후 재시도
                await asyncio.sleep(3)
                break  # 같은 모델로 다시 시도

            except litellm.APIConnectionError:
                # 연결 오류 → 다음 모델로
                continue

            except Exception as e:
                print(f"[에러] {model}: {e}")
                continue

    raise RuntimeError("모든 모델에서 실패")
```

---

## 10. 응답 구조

### 10.1 ModelResponse

```python
response = litellm.completion(...)

# 최상위 필드
response.id              # "chatcmpl-abc123..."
response.model           # "gpt-4"
response.created         # Unix timestamp
response.object          # "chat.completion"
response.choices         # [Choice] - 일반적으로 1개
response.usage           # Usage 객체

# 첫 번째 choice 접근
choice = response.choices[0]
choice.message           # Message 객체
choice.finish_reason     # "stop", "tool_calls", "length"
choice.index             # 0
choice.logprobs          # Log probabilities (요청한 경우)
```

### 10.2 Message

```python
message = response.choices[0].message

message.role             # "assistant"
message.content          # 생성된 텍스트 (str)
message.tool_calls       # Tool call 목록 (있는 경우)
message.function_call    # 레거시 함수 호출 (deprecated)
message.reasoning_content  # O1 모델의 추론 내용
```

### 10.3 Tool Call

```python
import json

for tool_call in message.tool_calls:
    tool_call.id              # "call_abc123..."
    tool_call.type            # "function"
    tool_call.function.name   # "get_weather"
    tool_call.function.arguments  # JSON 문자열

    # JSON 파싱
    args = json.loads(tool_call.function.arguments)
    print(f"{tool_call.function.name}({args})")
```

### 10.4 Usage

```python
usage = response.usage

usage.prompt_tokens      # 입력 토큰 수
usage.completion_tokens  # 출력 토큰 수
usage.total_tokens       # 합계
```

### 10.5 Hidden Parameters (메타데이터)

```python
# 비용 및 성능 메타데이터
hidden = response._hidden_params

hidden.get('response_cost')    # 비용 (USD)
hidden.get('prompt_tokens')    # 입력 토큰
hidden.get('completion_tokens')  # 출력 토큰
hidden.get('model')            # 실제 사용 모델
hidden.get('latency')          # 응답 시간 (ms)
hidden.get('cache_hit')        # 캐시 hit 여부
```

---

## 11. JediSOS 통합 패턴

### 11.1 llm_config.yaml 로드

```yaml
# llm_config.yaml
models:
  primary: claude-sonnet-5-20260203
  fallback1: gpt-5.2
  fallback2: gemini/gemini-3-flash
  local: ollama/llama4

settings:
  temperature: 0.7
  max_tokens: 2000
  timeout: 30
```

```python
import yaml
import litellm

with open("llm_config.yaml") as f:
    config = yaml.safe_load(f)

models = list(config["models"].values())
settings = config["settings"]
```

### 11.2 complete_with_fallback() 전체 구현

```python
import litellm
from datetime import datetime

async def complete_with_fallback(
    query: str,
    models: list[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    timeout: int = 30,
    track_cost: bool = True
) -> dict:
    """
    폴백 체인을 포함한 LLM 호출

    Returns:
        {
            "response": "...",
            "model": "gpt-4",
            "cost": 0.0025,
            "tokens": 150,
            "duration": 1.5
        }
    """

    if models is None:
        models = [
            "claude-sonnet-5-20260203",
            "gpt-5.2",
            "gemini/gemini-3-flash",
            "ollama/llama4"
        ]

    for model in models:
        try:
            start_time = datetime.now()

            response = await litellm.acompletion(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": query}
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout
            )

            duration = (datetime.now() - start_time).total_seconds()

            # 비용 추출
            cost = 0.0
            if hasattr(response, '_hidden_params'):
                cost = response._hidden_params.get('response_cost', 0)

            result = {
                "response": response.choices[0].message.content,
                "model": model,
                "cost": cost,
                "tokens": response.usage.total_tokens,
                "duration": duration
            }

            # 비용 추적 DB 저장
            if track_cost:
                db.insert_cost_tracking(
                    model=model,
                    cost=cost,
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                    duration_seconds=duration
                )

            print(f"[성공] {model} ({duration:.2f}초, ${cost:.6f})")
            return result

        except litellm.ContextWindowExceededError:
            print(f"[컨텍스트 초과] {model} → 다음 모델로")
            continue

        except litellm.RateLimitError as e:
            print(f"[Rate limit] {model} → {e.response.headers.get('retry-after', 10)}초 대기")
            import asyncio
            await asyncio.sleep(5)
            continue

        except litellm.APIConnectionError:
            print(f"[연결 실패] {model} → 다음 모델로")
            continue

        except Exception as e:
            print(f"[에러] {model}: {type(e).__name__} {e}")
            continue

    raise RuntimeError(f"모든 모델에서 실패: {models}")
```

### 11.3 LangGraph llm_reason 노드에서의 사용

```python
from langgraph.graph import StateGraph

async def llm_reason_node(state: AgentState) -> dict:
    """LangGraph에서 LLM 추론 노드"""

    query = state["messages"][-1]["content"]
    user_id = state.get("user_id", "default")

    # Hindsight에서 기억 조회
    memory_context = ""
    if hindsight_enabled:
        memories = await hindsight.arecall(
            bank_id=user_id,
            query=query,
            budget="mid"
        )
        memory_context = "\n".join([m.text for m in memories])

    # LLM 호출 (폴백 포함)
    result = await complete_with_fallback(
        query=query + f"\n\n[관련 기억]\n{memory_context}",
        track_cost=True
    )

    # 대화 저장
    state["messages"].append({
        "role": "assistant",
        "content": result["response"],
        "metadata": {
            "model": result["model"],
            "cost": result["cost"],
            "duration": result["duration"]
        }
    })

    return {"messages": state["messages"]}
```

### 11.4 비용 콜백 + DB 통합

```python
def jedisos_cost_callback(kwargs, completion_response, start_time, end_time):
    """JediSOS cost_tracking 테이블에 저장"""

    import sqlite3
    from datetime import datetime

    # DB 연결
    conn = sqlite3.connect("jedisos.db")
    cursor = conn.cursor()

    # 비용 추출
    cost = 0.0
    if hasattr(completion_response, '_hidden_params'):
        cost = completion_response._hidden_params.get('response_cost', 0)

    # cost_tracking 테이블에 저장
    cursor.execute("""
        INSERT INTO cost_tracking
        (model, cost, prompt_tokens, completion_tokens, duration_seconds, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        kwargs.get("model"),
        cost,
        completion_response.usage.prompt_tokens,
        completion_response.usage.completion_tokens,
        end_time - start_time,
        datetime.now()
    ))

    conn.commit()
    conn.close()

# 등록
litellm.success_callback = [jedisos_cost_callback]
```

---

## 12. 주의사항 및 팁

### 12.1 프로바이더별 주의점

| 프로바이더 | 주의사항 |
|-----------|---------|
| **Gemini** | 반드시 `gemini/` 접두사 필수 |
| **Ollama** | 반드시 `ollama/` 접두사 필수 |
| **Azure** | `api_version`과 `base_url` 필수 |
| **Groq** | `groq/` 접두사 필수 |
| **모든 모델** | Tool calling 미지원 모델 확인 필수 |

### 12.2 max_tokens vs max_completion_tokens

```python
# 대부분의 OpenAI 호환 API는 max_tokens 사용
response = litellm.completion(
    model="gpt-4",
    messages=[...],
    max_tokens=500  # 출력 최대 500 토큰
)

# 일부 모델은 max_completion_tokens 사용
response = litellm.completion(
    model="claude-3-opus-20240229",
    messages=[...],
    max_completion_tokens=500  # Anthropic API
)
```

### 12.3 스트리밍 시 토큰 수 확인

```python
# stream_options={"include_usage": True}로 마지막 청크에 usage 포함
response = await litellm.acompletion(
    model="gpt-4",
    messages=[...],
    stream=True,
    stream_options={"include_usage": True}
)

total_tokens = 0
async for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end='')

    # 마지막 청크에서 usage 확인
    if hasattr(chunk, 'usage') and chunk.usage:
        total_tokens = chunk.usage.total_tokens

print(f"\n총 토큰: {total_tokens}")
```

### 12.4 로컬 모델 (Ollama) 사용

```python
# Ollama 서버 실행 필수
# $ ollama serve

# Python에서 호출
response = litellm.completion(
    model="ollama/llama2",         # 또는 ollama/mistral, ollama/neural-chat 등
    messages=[{"role": "user", "content": "Hello"}],
    base_url="http://localhost:11434/v1",
    api_key="sk-local"  # Ollama는 더미 키만 필요
)

# 또는 환경변수로
import os
os.environ["OLLAMA_API_BASE"] = "http://localhost:11434/v1"

response = litellm.completion(
    model="ollama/llama2",
    messages=[...]
)
```

### 12.5 비용 추적 최적화

```python
# 콜백이 동기이므로 비동기 저장 권장
import asyncio

async def async_cost_save(kwargs, completion_response, start_time, end_time):
    """비동기 비용 저장"""
    cost = completion_response._hidden_params.get('response_cost', 0)

    # 백그라운드에서 비동기 저장
    asyncio.create_task(
        db.async_insert_cost_tracking(
            model=kwargs.get("model"),
            cost=cost,
            timestamp=datetime.now()
        )
    )

litellm.success_callback = [async_cost_save]
```

### 12.6 디버깅 및 로깅

```python
import litellm
import os

# 상세 로깅 활성화
litellm.set_verbose = True
os.environ["LITELLM_LOG"] = "TRUE"

# 이제 모든 API 호출이 상세히 로깅됨
response = litellm.completion(...)
```

### 12.7 도구 호출 모델 확인

```python
# Tool calling을 지원하는 모델:
# ✓ GPT-4, GPT-3.5-Turbo
# ✓ Claude 3 (Opus, Sonnet, Haiku)
# ✓ Gemini Pro
# ✓ Groq models
# ✗ Ollama (모델에 따라 다름)
# ✗ 대부분의 오픈소스 모델

# 도구가 필요하면 GPT-4 또는 Claude로 폴백
if model in ["ollama/llama2", "ollama/mistral"]:
    # 로컬 모델은 tool calling 미지원 → GPT-4로 대체
    model = "gpt-4"
```

---

## 빠른 참고 (Quick Reference)

### 기본 패턴
```python
import litellm

# 동기
response = litellm.completion(model="gpt-4", messages=[...])

# 비동기
response = await litellm.acompletion(model="gpt-4", messages=[...])

# 스트리밍
async for chunk in await litellm.acompletion(model="gpt-4", messages=[...], stream=True):
    print(chunk.choices[0].delta.content, end='')
```

### 폴백 체인
```python
models = ["claude-sonnet-5-20260203", "gpt-5.2", "gemini/gemini-3-flash"]

for model in models:
    try:
        response = await litellm.acompletion(model=model, messages=[...])
        break
    except litellm.APIError:
        continue
```

### 비용 추적
```python
def track_cost(kwargs, response, start, end):
    cost = response._hidden_params.get('response_cost', 0)
    print(f"${cost:.6f}")

litellm.success_callback = [track_cost]
```

### 도구 호출
```python
tools = [{
    "type": "function",
    "function": {
        "name": "search",
        "description": "Search",
        "parameters": {...}
    }
}]

response = litellm.completion(model="gpt-4", messages=[...], tools=tools)

if response.choices[0].message.tool_calls:
    for call in response.choices[0].message.tool_calls:
        name = call.function.name
        args = json.loads(call.function.arguments)
```

---

## 문제 해결

| 문제 | 원인 | 해결책 |
|------|------|--------|
| "Model not found" | 잘못된 모델 이름 | 프로바이더 접두사 확인 (예: `gemini/gemini-pro`) |
| API 키 오류 | 환경변수 누락 | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` 등 설정 |
| 타임아웃 | 응답 시간 초과 | `timeout` 파라미터 증가 또는 더 빠른 모델 사용 |
| 속도 제한 | Rate limit 초과 | Router 사용 또는 요청 간격 조정 |
| 컨텍스트 초과 | 입력이 너무 큼 | 더 작은 모델로 폴백 또는 입력 줄이기 |
| Tool calling 실패 | 모델이 미지원 | GPT-4 또는 Claude로 변경 |

---

**문서 버전**: litellm v1.81.13
**작성일**: 2026년 2월
**JediSOS 통합**: LangGraph + Hindsight + Router 조합
