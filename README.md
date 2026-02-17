# JediSOS

Hindsight Memory + LangGraph + LiteLLM 기반 **오픈소스 개인 AI 비서 시스템**

텔레그램, 디스코드, 슬랙, 웹 UI에서 대화하고, 대화 내용을 기억하며, MCP 도구와 자체 생성 Skill로 기능을 확장할 수 있습니다.

---

## 목차

1. [시스템 요구사항](#시스템-요구사항)
2. [빠른 설치 (Docker 원클릭)](#빠른-설치-docker-원클릭)
3. [개발자 설치 (소스 코드)](#개발자-설치-소스-코드)
4. [환경 설정 (.env)](#환경-설정-env)
5. [LLM 모델 설정](#llm-모델-설정)
6. [텔레그램 봇 연결](#텔레그램-봇-연결)
7. [웹 UI 사용법](#웹-ui-사용법)
8. [CLI 명령어](#cli-명령어)
9. [패키지 매니저 (jedisos market)](#패키지-매니저-jedisos-market)
10. [자가 코딩 (Forge)](#자가-코딩-forge)
11. [MCP 도구 확장](#mcp-도구-확장)
12. [디스코드 / 슬랙 봇](#디스코드--슬랙-봇)
13. [서비스 관리](#서비스-관리)
14. [트러블슈팅](#트러블슈팅)

---

## 시스템 요구사항

| 항목 | 최소 | 권장 |
|------|------|------|
| OS | Linux, macOS, Windows (WSL2) | Ubuntu 22.04+ / macOS 14+ |
| Docker | Docker 24+ & Compose V2 | Docker Desktop 최신 |
| Python | 3.12+ (소스 설치 시) | 3.12 |
| RAM | 4GB | 8GB+ |
| 디스크 | 5GB | 10GB+ |
| LLM API 키 | OpenAI 또는 Google 중 1개 | 둘 다 (폴백용) |

---

## 빠른 설치 (Docker 원클릭)

Docker만 설치되어 있으면 한 줄로 설치합니다.

```bash
curl -sSL https://raw.githubusercontent.com/jedikim/jedisos/main/scripts/install.sh | bash
```

이 스크립트가 하는 일:
1. Docker, Docker Compose V2 확인
2. `~/.jedisos/` 디렉토리 생성
3. `docker-compose.yml` 다운로드
4. `.env` 파일 생성 (빈 상태)
5. Docker 이미지 pull + 컨테이너 시작
6. 브라우저에서 `http://localhost:8080/setup` 열기

설치 완료 후 웹 브라우저에서 Setup Wizard가 열립니다. API 키를 입력하면 바로 사용 가능합니다.

### 수동 Docker 설치

```bash
# 1. 디렉토리 생성
mkdir -p ~/.jedisos && cd ~/.jedisos

# 2. docker-compose.yml 다운로드
curl -sSL https://raw.githubusercontent.com/jedikim/jedisos/main/docker-compose.yml -o docker-compose.yml

# 3. .env 설정
cat > .env << 'EOF'
OPENAI_API_KEY=sk-your-key-here
POSTGRES_PASSWORD=your-secure-password
EOF

# 4. 시작
docker compose up -d

# 5. 상태 확인 (30초 정도 대기)
docker compose ps
curl http://localhost:8080/health
```

### 서비스 포트

| 서비스 | 포트 | 설명 |
|--------|------|------|
| JediSOS 웹 UI | `8080` | 메인 대시보드 + 채팅 + API |
| Hindsight API | `8888` | 메모리 서버 |
| Hindsight UI | `9999` | 메모리 관리 대시보드 |
| PostgreSQL | `5432` | 데이터베이스 (내부) |

---

## 개발자 설치 (소스 코드)

```bash
# 1. 저장소 클론
git clone https://github.com/jedikim/jedisos.git
cd jedisos

# 2. 환경 변수 설정
cp .env.example .env
# .env 파일을 편집하여 API 키 입력

# 3. 인프라 실행 (Hindsight + PostgreSQL)
docker compose -f docker-compose.dev.yml up -d

# 4. 인프라 상태 확인 (healthy가 되기까지 30초 대기)
docker compose -f docker-compose.dev.yml ps

# 5. Python 환경 설정
pip install uv
uv venv .venv --python 3.12
source .venv/bin/activate

# 6. 의존성 설치
uv pip install -e ".[dev,channels]"
#   dev: pytest, ruff, bandit 등 개발 도구
#   channels: 텔레그램, 디스코드, 슬랙 봇 의존성

# 7. 검증
make check    # ruff lint + bandit security + pytest
```

---

## 환경 설정 (.env)

`.env.example`을 복사하여 `.env`를 만듭니다. 아래는 전체 설정 항목입니다.

```bash
# === LLM API 키 (사용하는 프로바이더만 설정) ===
OPENAI_API_KEY=sk-your-openai-key
GEMINI_API_KEY=your-google-api-key

# === Hindsight 메모리 ===
HINDSIGHT_API_URL=http://localhost:8888       # Docker 내부: http://hindsight:8888
HINDSIGHT_BANK_ID=jedisos-default             # 기본 메모리 뱅크
HINDSIGHT_API_LLM_PROVIDER=openai             # Hindsight 내부 LLM
HINDSIGHT_API_LLM_API_KEY=sk-your-openai-key  # Hindsight용 API 키

# === LLM 설정 ===
LLM_MODELS=["gpt-5.2","gemini/gemini-3-flash"]  # 폴백 체인 (첫 번째가 기본)
LLM_CONFIG_FILE=llm_config.yaml                   # 별도 설정 파일 사용 시
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=8192

# === 채널 봇 토큰 ===
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIjKlMnOpQrStUvWxYz
DISCORD_BOT_TOKEN=your-discord-bot-token
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
SLACK_APP_TOKEN=xapp-your-slack-app-token

# === 보안 ===
SECURITY_MAX_REQUESTS_PER_MINUTE=30

# === 일반 ===
DEBUG=false
LOG_LEVEL=INFO
```

**최소 설정**: `OPENAI_API_KEY` 하나만 있으면 기본 기능이 작동합니다.

---

## LLM 모델 설정

JediSOS는 LiteLLM을 통해 100개 이상의 LLM 프로바이더를 지원합니다. 모델 설정은 코드 수정 없이 변경 가능합니다.

### 방법 1: llm_config.yaml (권장)

```yaml
# config/llm_config.yaml
models:
  - model: gpt-5.2
    description: "OpenAI GPT-5.2 (기본)"
  - model: gemini/gemini-3-flash
    description: "Google Gemini 3 Flash (폴백)"
  - model: claude-sonnet-4-5-20250929
    description: "Anthropic Claude Sonnet 4.5 (2차 폴백)"

temperature: 0.7
max_tokens: 8192
timeout: 60
```

첫 번째 모델이 실패하면 자동으로 다음 모델로 폴백됩니다.

### 방법 2: 환경 변수

```bash
LLM_MODELS=["gpt-5.2","gemini/gemini-3-flash"]
```

`llm_config.yaml`이 있으면 환경 변수보다 우선합니다.

### 지원 프로바이더 예시

| 프로바이더 | 모델 이름 예시 | 필요 환경 변수 |
|-----------|---------------|--------------|
| OpenAI | `gpt-5.2`, `gpt-4o` | `OPENAI_API_KEY` |
| Google | `gemini/gemini-3-flash` | `GEMINI_API_KEY` |
| Anthropic | `claude-sonnet-4-5-20250929` | `ANTHROPIC_API_KEY` |
| Groq | `groq/llama-3.1-70b` | `GROQ_API_KEY` |
| Ollama (로컬) | `ollama/llama3` | 없음 (로컬 실행) |

---

## 텔레그램 봇 연결

### 1단계: 텔레그램에서 봇 생성

1. 텔레그램 앱에서 **@BotFather** 검색하여 대화 시작
2. `/newbot` 명령 전송
3. 봇 이름 입력 (예: `JediSOS AI`)
4. 봇 사용자명 입력 (예: `jedisos_ai_bot` — 반드시 `bot`으로 끝나야 함)
5. BotFather가 **API 토큰**을 발급합니다:
   ```
   123456789:ABCdefGhIjKlMnOpQrStUvWxYz
   ```
6. 이 토큰을 복사합니다

### 2단계: 토큰을 .env에 설정

```bash
# .env 파일에 추가
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIjKlMnOpQrStUvWxYz
```

### 3단계: 텔레그램 봇 실행

#### Docker 사용 시 (프로덕션)

`docker-compose.yml`에 텔레그램 봇 서비스를 추가합니다:

```yaml
# docker-compose.yml의 services 하위에 추가
  telegram-bot:
    image: ghcr.io/jedikim/jedisos:${JEDISOS_VERSION:-latest}
    restart: unless-stopped
    depends_on:
      - hindsight
    environment:
      HINDSIGHT_API_URL: http://hindsight:8888
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}
    env_file:
      - .env
    command: ["python", "-m", "jedisos.channels.telegram"]
```

```bash
docker compose up -d telegram-bot
```

#### 소스 코드 사용 시 (개발)

```python
# run_telegram.py
import asyncio
import os

from jedisos.core.config import HindsightConfig, LLMConfig
from jedisos.llm.router import LLMRouter
from jedisos.memory.hindsight import HindsightMemory
from jedisos.agents.react import ReActAgent
from jedisos.security.pdp import PolicyDecisionPoint
from jedisos.security.audit import AuditLogger
from jedisos.channels.telegram import TelegramChannel


async def main():
    # 메모리
    memory = HindsightMemory(HindsightConfig())

    # LLM
    llm = LLMRouter(LLMConfig())

    # 에이전트
    agent = ReActAgent(memory=memory, llm=llm)

    # 보안 (선택)
    pdp = PolicyDecisionPoint()
    audit = AuditLogger()

    # 텔레그램 채널
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    channel = TelegramChannel(
        token=token,
        agent=agent,
        pdp=pdp,
        audit=audit,
    )

    # 봇 실행 (Ctrl+C로 중지)
    app = channel.build_app()
    print("텔레그램 봇이 시작됩니다...")
    await app.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
```

```bash
source .venv/bin/activate
python run_telegram.py
```

### 4단계: 텔레그램에서 대화

1. 텔레그램 앱에서 봇 사용자명(예: `@jedisos_ai_bot`)을 검색
2. **시작** 버튼을 누르거나 `/start` 전송
3. 봇이 인사합니다: `"안녕하세요! JediSOS 개인 AI 비서입니다."`
4. 아무 메시지나 보내면 AI가 답변합니다

### 텔레그램 봇 명령어

| 명령 | 설명 |
|------|------|
| `/start` | 시작 인사 |
| `/help` | 사용법 안내 |
| 일반 텍스트 | AI 에이전트에게 질문/요청 |

### 작동 원리

```
사용자 메시지 → 텔레그램 API → TelegramChannel
  → Envelope 생성 (user_id, channel=TELEGRAM)
  → PDP 보안 검사 (rate limit, 권한)
  → ReActAgent.run() (LLM + 메모리 + MCP 도구)
  → 응답 → 텔레그램 API → 사용자
```

각 사용자의 대화 기록은 `telegram-{user_id}` 메모리 뱅크에 저장되어, 이전 대화를 기억합니다.

---

## 웹 UI 사용법

### 접속

```
http://localhost:8080
```

### Setup Wizard (최초 실행)

처음 접속하면 Setup Wizard가 나타납니다:

1. **API 키 입력** — OpenAI, Google 등 사용할 프로바이더의 API 키
2. **모델 선택** — 기본 모델과 폴백 모델 설정
3. **MCP 서버 추천** — Hindsight(기본 내장) + 선택 가능한 확장 도구
4. **완료** — 설정이 저장되고 메인 채팅 화면으로 이동

### 주요 페이지

| 페이지 | 경로 | 설명 |
|--------|------|------|
| 채팅 | `/` | WebSocket 기반 실시간 AI 대화 |
| 설정 | `/settings` | API 키, LLM 모델, 보안 정책 관리 |
| MCP 스토어 | `/mcp` | MCP 서버 검색/설치/관리 |
| 모니터링 | `/monitoring` | 시스템 상태, 감사 로그, 비용 추적 |
| API 문서 | `/docs` | FastAPI 자동 생성 Swagger 문서 |

### 채팅 API (프로그래밍)

#### WebSocket

```javascript
const ws = new WebSocket("ws://localhost:8080/api/chat/ws");
ws.send(JSON.stringify({ message: "오늘 날씨 어때?", bank_id: "web-user" }));
ws.onmessage = (event) => console.log(JSON.parse(event.data));
```

#### HTTP POST

```bash
curl -X POST http://localhost:8080/api/chat/send \
  -H "Content-Type: application/json" \
  -d '{"message": "안녕하세요", "bank_id": "api-user"}'
```

---

## CLI 명령어

```bash
# AI에게 메시지 보내기
jedisos chat "오늘 할 일 알려줘"
jedisos chat "날씨 알려줘" --model gpt-5.2    # 특정 모델 지정
jedisos chat "전에 뭘 했었지?" --bank my-bank  # 특정 메모리 뱅크

# 시스템 관리
jedisos health                    # 서비스 상태 확인
jedisos init                      # 프로젝트 초기화 (.env + config 생성)
jedisos serve                     # 웹 서버 실행 (포트 8080)
jedisos serve --port 3000         # 다른 포트로 실행
jedisos update                    # Docker 이미지 업데이트
jedisos --version                 # 버전 확인
```

---

## 패키지 매니저 (jedisos market)

JediSOS는 로컬 파일시스템 기반 패키지 매니저를 내장하고 있습니다. 6종의 패키지를 관리합니다.

### 패키지 유형

| 유형 | 디렉토리 | 설명 |
|------|----------|------|
| `skill` | `tools/skills/` | Python `@tool` 함수 (tool.yaml + tool.py) |
| `mcp_server` | `tools/mcp-servers/` | MCP 서버 설정 (Docker) |
| `prompt_pack` | `tools/prompts/` | 프롬프트 템플릿 모음 |
| `workflow` | `tools/workflows/` | LangGraph 워크플로우 정의 |
| `identity_pack` | `tools/identities/` | 에이전트 정체성 (IDENTITY.md) |
| `bundle` | `tools/bundles/` | 여러 패키지를 묶은 번들 |

### 패키지 구조

```
my-weather-tool/
├── jedisos-package.yaml    # 필수: 패키지 메타데이터
├── tool.py                 # Skill인 경우: @tool 함수
├── README.md               # 권장: 사용법 문서
└── requirements.txt        # 선택: 추가 의존성
```

`jedisos-package.yaml` 예시:

```yaml
name: weather
version: 1.0.0
description: "날씨 정보를 조회하는 Skill"
type: skill
license: MIT
author: jedi
tags:
  - weather
  - api
```

### 명령어

```bash
# 설치된 패키지 목록
jedisos market list
jedisos market list --type skill       # Skill만

# 검색 (이름, 설명, 태그)
jedisos market search "weather"

# 상세 정보
jedisos market info weather

# 검증 (설치 전 체크)
jedisos market validate ./my-weather-tool/

# 설치 (로컬 디렉토리에서 복사)
jedisos market install ./my-weather-tool/
jedisos market install ./my-weather-tool/ --force  # 덮어쓰기

# 삭제
jedisos market remove weather
jedisos market remove weather --yes    # 확인 없이 삭제
```

### 검증 항목

`jedisos market validate`가 확인하는 내용:

| 검사 | 대상 | 설명 |
|------|------|------|
| metadata | 모든 유형 | jedisos-package.yaml 필수 필드 (name, version, description) |
| license | 모든 유형 | MIT, Apache-2.0, BSD-3-Clause 중 하나 |
| security | Skill만 | Forge 보안 검사 (금지 패턴, import 화이트리스트) |
| docs | 모든 유형 | README.md 존재 여부 (경고만, 필수 아님) |

---

## 자가 코딩 (Forge)

JediSOS는 AI가 직접 도구를 생성할 수 있는 자가 코딩 엔진을 내장하고 있습니다.

### 작동 방식

사용자가 "날씨 도구 만들어줘"라고 요청하면:

1. **LLM이 코드 설계** — 함수명, 파라미터, 구현 로직을 JSON으로 생성
2. **Jinja2 템플릿 렌더링** — `tool.py` + `tool.yaml` 파일 생성
3. **보안 검사** — 금지 패턴(eval, subprocess 등), import 화이트리스트, 타입 힌트 확인
4. **핫로드** — 서버 재시작 없이 즉시 사용 가능
5. **자동 재시도** — 보안 검사 실패 시 최대 3회 재생성

생성된 도구는 `tools/generated/` 디렉토리에 저장됩니다.

### 보안 제한

자동 생성 코드에서 금지되는 패턴:
- `os.system`, `subprocess`, `eval`, `exec`
- `__import__`, `socket`, `ctypes`
- `shutil.rmtree`, `/etc/` 접근

허용되는 import:
- `httpx`, `json`, `re`, `datetime`, `pathlib`, `typing`, `pydantic`
- `math`, `collections`, `itertools`, `functools`, `hashlib`, `base64`

---

## MCP 도구 확장

JediSOS는 2-Tier 확장 아키텍처를 사용합니다.

### Tier 1: JediSOS Skill (기본)

- Python `@tool` 함수 + `tool.yaml`
- Docker 불필요, `importlib` 핫로드
- `tools/skills/` 디렉토리에 저장

```python
# tools/skills/calculator/tool.py
from jedisos.forge.decorator import tool

@tool(name="calculator", description="간단한 계산기", tags=["math"])
async def calculate(expression: str) -> str:
    """수학 표현식을 계산합니다."""
    result = eval(expression)  # 실제 코드에서는 안전한 파서 사용
    return f"결과: {result}"
```

### Tier 2: MCP Server (복잡한 경우)

- OAuth가 필요한 외부 서비스 (Google Calendar, Gmail 등)
- Docker 컨테이너로 실행
- `mcp-auth-proxy`가 OAuth 2.1 토큰 자동 관리

### 내장 MCP 도구

| 도구 | 설명 |
|------|------|
| `memory_retain` | Hindsight 메모리에 정보 저장 |
| `memory_recall` | 메모리에서 정보 검색 |
| `memory_reflect` | 메모리 통합/정리 |
| `system_health` | 시스템 상태 확인 |

---

## 디스코드 / 슬랙 봇

### 디스코드

```bash
# .env에 추가
DISCORD_BOT_TOKEN=your-discord-bot-token
```

디스코드 봇 생성:
1. [Discord Developer Portal](https://discord.com/developers/applications) 접속
2. New Application → Bot → Token 복사
3. OAuth2 → URL Generator → `bot` + `Send Messages` 권한 선택
4. 생성된 URL로 서버에 봇 초대

### 슬랙

```bash
# .env에 추가
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
```

슬랙 앱 생성:
1. [Slack API](https://api.slack.com/apps) → Create New App
2. Socket Mode 활성화 → App-Level Token 생성
3. OAuth & Permissions → `chat:write` 스코프 추가
4. Event Subscriptions → `message.channels` 이벤트 구독
5. 워크스페이스에 설치

---

## 서비스 관리

### Docker (프로덕션)

```bash
cd ~/.jedisos  # 또는 docker-compose.yml 위치

# 시작
docker compose up -d

# 상태 확인
docker compose ps

# 로그 확인
docker compose logs -f jedisos      # JediSOS 앱 로그
docker compose logs -f hindsight    # Hindsight 메모리 로그

# 중지
docker compose down

# 업데이트
docker compose pull && docker compose up -d

# 데이터 완전 삭제 (주의!)
docker compose down -v
```

### 개발 환경

```bash
cd ~/code/jedisos

# 인프라만 시작 (Hindsight + PostgreSQL)
make dev

# 인프라 중지
make down

# 린트 + 보안 + 테스트
make check

# 웹 서버 실행
jedisos serve
```

---

## 트러블슈팅

### Hindsight 연결 실패

```
jedisos health
# Hindsight: OFFLINE
```

원인: Docker 컨테이너가 실행 중이지 않거나 아직 시작 중

```bash
# 컨테이너 상태 확인
docker compose ps

# Hindsight 로그 확인
docker compose logs hindsight

# 재시작
docker compose restart hindsight

# 직접 확인
curl http://localhost:8888/health
```

### LLM API 키 오류

```
LLMError: Authentication failed
```

`.env`의 API 키가 올바른지 확인:

```bash
# OpenAI 키 테스트
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

### 텔레그램 봇 응답 없음

1. `TELEGRAM_BOT_TOKEN`이 올바른지 확인
2. BotFather에서 봇이 비활성화되지 않았는지 확인
3. 봇 프로세스가 실행 중인지 확인
4. Hindsight가 정상인지 `jedisos health`로 확인

### 포트 충돌

다른 서비스가 8080, 8888, 9999 포트를 사용 중인 경우:

```bash
# .env에서 포트 변경
JEDISOS_PORT=3000
HINDSIGHT_PORT=18888
HINDSIGHT_UI_PORT=19999
```

---

## 라이선스

MIT
