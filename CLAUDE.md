# JediSOS - Claude Code 개발 가이드

> 이 파일은 Claude Code가 JediSOS 프로젝트를 개발할 때 반드시 참조해야 하는 마스터 가이드입니다.
> 모든 코드 생성, 수정, 테스트, 릴리즈 작업은 이 문서의 규칙을 따릅니다.

## 프로젝트 개요

**JediSOS**는 Hindsight 메모리 엔진 + LangGraph 에이전트 프레임워크 + LiteLLM 멀티-LLM 라우터를 결합한 **오픈소스 개인 AI 비서 시스템**입니다.
누구나 `docker compose up` 한 명령으로 설치하고, 웹 UI에서 설정하고, MCP 마켓플레이스에서 기능을 확장할 수 있습니다.

- **메모리:** Hindsight (서버 v0.4.11+, 클라이언트 `hindsight-client>=0.4.11`) - 4-네트워크 모델: World/Bank/Opinion/Observation
- **에이전트:** LangGraph 1.0.8+ (StateGraph 기반 ReAct 루프)
- **LLM:** LiteLLM 1.81+ (100+ 프로바이더 통합)
- **MCP:** FastMCP 2.14+ (Model Context Protocol 도구 서버/클라이언트)
- **확장:** MCP 마켓플레이스 (mcp.so 17,600+ / smithery.ai / Docker MCP Catalog) + MCP Auth Proxy (OAuth 2.1)
- **웹 UI:** FastAPI + React 기반 대시보드 (채팅, 설정, MCP 관리, 모니터링)
- **배포:** Docker 이미지 (`ghcr.io`) + PyPI 패키지 + 설치 스크립트
- **대상:** 개발자 (CLI/Docker) → 일반 사용자 (웹 UI + 원클릭 설치)
- **실행:** 로컬 머신 또는 VPS — 동일한 `docker-compose.yml`
- **Python:** 3.12+
- **라이선스:** MIT

### 오픈소스 배포 전략

JediSOS는 3가지 배포 채널을 통해 배포됩니다:

1. **Docker 이미지** (`ghcr.io/jedikim/jedisos`) — `docker compose up -d`로 전체 스택 실행
2. **PyPI 패키지** (`pip install jedisos`) — CLI 도구 + 라이브러리
3. **설치 스크립트** (`curl -sSL https://get.jedisos.com | bash`) — 일반 사용자용 자동 설치

GitHub Actions가 `v*` 태그 push 시 3개 채널에 자동 배포합니다.
상세: `docs/RELEASE.md`

### 확장 아키텍처 (2-Tier)

JediSOS는 **2-Tier 확장 아키텍처**를 사용합니다:
- **Tier 1 (기본): JediSOS Skill** — Python `@tool` 함수 + `tool.yaml`. Docker 불필요. `importlib` 핫로드.
- **Tier 2 (복잡한 경우만): MCP Server** — OAuth 필요 외부 서비스만 (Google Calendar, Gmail 등). Docker 컨테이너.

OAuth가 필요한 서비스는 `sigbit/mcp-auth-proxy`가 토큰 관리를 자동 처리합니다.
상세: `docs/MCP_EXTENSIONS.md`, `docs/SELF_EVOLVING.md`

## 핵심 규칙

### 1. 코드 해시 추적 시스템 (필수)

모든 함수, 클래스, 모듈에는 추적 해시를 반드시 포함합니다.

```python
# [JS-A001] jedisos.core.envelope - Envelope 메시지 계약
# version: 1.0.0 | created: 2026-02-16 | modified: 2026-02-16
class Envelope(BaseModel):
    """에이전트 간 메시지 표준 계약.

    Tracking: JS-A001
    """
    ...
```

**해시 형식:** `[JS-{영역코드}{3자리숫자}]`

| 영역코드 | 영역 | 범위 |
|-----------|------|------|
| A | core (핵심) | A001-A099 |
| B | memory (메모리) | B001-B099 |
| C | llm (LLM 통합) | C001-C099 |
| D | mcp (MCP 도구) | D001-D099 |
| E | agents (에이전트) | E001-E099 |
| F | channels (채널) | F001-F099 |
| G | security (보안) | G001-G099 |
| H | cli (CLI) | H001-H099 |
| W | web (웹 UI) | W001-W099 |
| K | forge (자가코딩) | K001-K099 |
| M | marketplace (마켓플레이스) | M001-M099 |
| T | tests (테스트) | T001-T099 |
| X | scripts/infra | X001-X099 |

### 2. 코드 작성 규칙

```python
# 모든 파일의 시작에 모듈 해시 포함
"""
[JS-A001] jedisos.core.envelope
Envelope 메시지 계약 - 에이전트 간 통신의 기본 단위

version: 1.0.0
created: 2026-02-16
modified: 2026-02-16
dependencies: pydantic>=2.12, uuid6>=2025.0
"""

# 모든 public 함수에 해시 포함
def create_envelope(content: str) -> Envelope:
    """Envelope 생성.  # [JS-A001.1]

    Args:
        content: 메시지 내용

    Returns:
        Envelope: 생성된 Envelope 객체

    Raises:
        ValueError: content가 빈 문자열인 경우
    """
    ...
```

### 3. 타입 힌팅 (필수)

```python
# 모든 함수에 타입 힌팅 필수
from typing import Any

async def recall_memory(
    query: str,
    bank_id: str = "default",
    limit: int = 10,
) -> list[dict[str, Any]]:
    ...
```

### 4. 에러 처리 패턴

```python
# 커스텀 예외 사용 (stdlib Exception 직접 raise 금지)
from jedisos.core.exceptions import (
    JedisosError,        # 기본 예외
    MemorySystemError,    # 메모리 관련
    LLMError,             # LLM 호출 관련
    ChannelError,         # 채널 관련
    SecurityError,        # 보안 관련
)

# 에러 처리 시 구조화된 로깅 필수
import structlog
logger = structlog.get_logger()

try:
    result = await client.recall(query=query)
except httpx.HTTPStatusError as e:
    logger.error("hindsight_recall_failed", status=e.response.status_code, query=query)
    raise MemorySystemError(f"Recall 실패: {e.response.status_code}") from e
```

### 5. 로깅 표준

```python
import structlog

# structlog만 사용 (stdlib logging 사용 금지)
logger = structlog.get_logger()

# 구조화된 이벤트명 사용 (snake_case)
logger.info("envelope_created", envelope_id=str(env.id), channel=env.channel)
logger.warning("llm_fallback_triggered", primary="claude-sonnet-5-20260203", fallback="gpt-5.2")
logger.error("memory_retain_failed", error=str(e), bank_id=bank_id)
```

## 프로젝트 구조

```
jedisos/
├── CLAUDE.md                    # 이 파일 (Claude Code 마스터 가이드)
├── pyproject.toml               # 프로젝트 설정 + 의존성
├── Makefile                     # 개발 명령어 모음
├── docker-compose.yml           # 프로덕션 서비스
├── docker-compose.dev.yml       # 개발 환경 (Hindsight + PostgreSQL)
├── .env.example                 # 환경변수 템플릿
├── .github/
│   └── workflows/
│       ├── ci.yml               # CI 파이프라인
│       └── release.yml          # 릴리즈 자동화
├── docs/
│   ├── ARCHITECTURE.md          # 시스템 아키텍처 + Mermaid 다이어그램
│   ├── DEVELOPMENT_GUIDE.md     # 개발 단계별 가이드
│   ├── TESTING_STRATEGY.md      # 테스트 전략
│   ├── RELEASE.md               # 릴리즈 방법론
│   ├── TRACKING.md              # 해시 추적 + 문서화 시스템
│   ├── LIBRARY_REFERENCE.md     # 핵심 라이브러리 레퍼런스
│   ├── HINDSIGHT_USAGE.md      # Hindsight 사용법 가이드 (retain/recall/reflect)
│   ├── LANGGRAPH_USAGE.md      # LangGraph 사용법 가이드 (StateGraph/체크포인팅/스트리밍)
│   ├── LITELLM_USAGE.md        # LiteLLM 사용법 가이드 (멀티LLM 라우터/폴백/비용추적)
│   ├── FASTMCP_USAGE.md        # FastMCP 사용법 가이드 (MCP 서버/클라이언트/도구)
│   ├── MCP_AUTH_PROXY_USAGE.md # MCP Auth Proxy 사용법 (OAuth 2.1/PKCE/토큰관리)
│   └── PHASE_VERIFICATION.md  # Phase별 검증 가이드 (자동검증/사람검증/체크리스트)
├── src/
│   └── jedisos/
│       ├── __init__.py
│       ├── core/                # [JS-A] 핵심 모듈
│       │   ├── __init__.py
│       │   ├── envelope.py      # [JS-A001] Envelope 메시지 계약
│       │   ├── config.py        # [JS-A002] 설정 관리
│       │   ├── exceptions.py    # [JS-A003] 커스텀 예외
│       │   └── types.py         # [JS-A004] 공통 타입 정의
│       ├── memory/              # [JS-B] 메모리 시스템
│       │   ├── __init__.py
│       │   ├── hindsight.py     # [JS-B001] Hindsight 클라이언트 래퍼
│       │   ├── identity.py      # [JS-B002] 에이전트 정체성
│       │   └── mcp_wrapper.py   # [JS-B003] Hindsight MCP 래퍼
│       ├── llm/                 # [JS-C] LLM 통합
│       │   ├── __init__.py
│       │   ├── router.py        # [JS-C001] LiteLLM 라우터
│       │   └── prompts.py       # [JS-C002] 프롬프트 템플릿
│       ├── mcp/                 # [JS-D] MCP 도구
│       │   ├── __init__.py
│       │   ├── server.py        # [JS-D001] FastMCP 서버
│       │   └── client.py        # [JS-D002] MCP 클라이언트 매니저
│       ├── agents/              # [JS-E] 에이전트
│       │   ├── __init__.py
│       │   ├── react.py         # [JS-E001] ReAct 에이전트 (LangGraph)
│       │   ├── supervisor.py    # [JS-E002] 슈퍼바이저 에이전트
│       │   └── worker.py        # [JS-E003] 워커 에이전트
│       ├── channels/            # [JS-F] 채널 어댑터
│       │   ├── __init__.py
│       │   ├── telegram.py      # [JS-F001] 텔레그램
│       │   ├── discord.py       # [JS-F002] 디스코드
│       │   └── slack.py         # [JS-F003] 슬랙
│       ├── security/            # [JS-G] 보안
│       │   ├── __init__.py
│       │   ├── pdp.py           # [JS-G001] Policy Decision Point
│       │   └── audit.py         # [JS-G002] 감사 로그
│       ├── cli/                 # [JS-H] CLI
│       │   ├── __init__.py
│       │   └── main.py          # [JS-H001] Typer CLI 엔트리포인트
│       ├── web/                 # [JS-W] 웹 UI
│       │   ├── __init__.py
│       │   ├── app.py           # [JS-W001] FastAPI 앱 + 라우터
│       │   ├── api/             # REST API 엔드포인트
│       │   │   ├── chat.py      # [JS-W002] 채팅 API (WebSocket)
│       │   │   ├── settings.py  # [JS-W003] 설정 관리 API
│       │   │   ├── mcp.py       # [JS-W004] MCP 서버 관리 API
│       │   │   └── monitoring.py # [JS-W005] 상태/로그 API
│       │   ├── static/          # React 빌드 결과물
│       │   └── setup_wizard.py  # [JS-W006] 첫 실행 Setup Wizard
│       ├── forge/               # [JS-K] 자가 코딩 엔진
│       │   ├── __init__.py
│       │   ├── generator.py     # [JS-K001] Skill 코드 생성기 (LLM + Jinja2)
│       │   ├── tester.py        # [JS-K002] 자동 테스트 실행기
│       │   ├── decorator.py     # [JS-K003] @tool 데코레이터 정의
│       │   ├── security.py      # [JS-K004] 코드 보안 정적분석
│       │   ├── loader.py        # [JS-K005] importlib 핫로더
│       │   └── templates/       # Skill 생성 템플릿 (Jinja2)
│       └── marketplace/         # [JS-M] 마켓플레이스 클라이언트
│           ├── __init__.py
│           ├── client.py        # [JS-M001] Registry API 클라이언트
│           ├── publisher.py     # [JS-M002] 패키지 게시기
│           ├── validator.py     # [JS-M003] 패키지 검증기
│           └── models.py        # [JS-M004] 패키지 메타데이터 모델
├── tools/                       # Tier 1 Skill 도구 디렉토리
│   ├── weather/                 # 예시: 날씨 Skill
│   │   ├── tool.yaml            # 메타데이터
│   │   └── tool.py              # @tool 데코레이터 함수
│   └── generated/               # 에이전트 자동 생성 도구
├── web-ui/                      # React 프론트엔드 소스
│   ├── package.json
│   ├── src/
│   │   ├── App.jsx              # 메인 앱
│   │   ├── pages/
│   │   │   ├── Chat.jsx         # 채팅 인터페이스
│   │   │   ├── Settings.jsx     # 설정 페이지
│   │   │   ├── McpStore.jsx     # MCP 마켓플레이스 브라우저
│   │   │   ├── Monitoring.jsx   # 상태 모니터링
│   │   │   └── SetupWizard.jsx  # 초기 설정 마법사
│   │   └── components/
│   └── public/
├── tests/
│   ├── conftest.py              # 공통 픽스처
│   ├── unit/                    # 단위 테스트 (mock, ~5초)
│   ├── integration/             # 통합 테스트 (real Hindsight, ~30초)
│   └── e2e/                     # E2E 테스트 (전체 플로우, ~2분)
├── scripts/
│   ├── ai_debug.sh              # AI 디버깅 스크립트
│   ├── health_check.py          # 헬스체크
│   └── generate_tracking.py     # 추적 해시 문서 생성
└── docker/
    └── Dockerfile               # 프로덕션 이미지
```

## 개발 환경 설정

### 1단계: 저장소 클론 및 환경 준비

```bash
git clone https://github.com/jedikim/jedisos.git
cd jedisos
cp .env.example .env
# .env 파일에 API 키 설정
```

### 2단계: 인프라 실행

```bash
# Hindsight + PostgreSQL 실행
docker compose -f docker-compose.dev.yml up -d

# 상태 확인 (Hindsight API가 8888 포트에서 응답해야 함)
curl -s http://localhost:8888/health | python -m json.tool
```

### 3단계: Python 환경

```bash
# uv 사용 (pip보다 빠름)
pip install uv
uv venv .venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev,channels]"
```

### 4단계: 개발 도구 확인

```bash
make check  # ruff + bandit + pytest 한 번에 실행
```

## Makefile 명령어

```makefile
.PHONY: dev check test lint format security

dev:             ## 개발 환경 전체 시작
	docker compose -f docker-compose.dev.yml up -d
	@echo "Hindsight: http://localhost:8888"
	@echo "Hindsight UI: http://localhost:9999"

down:            ## 개발 환경 중지
	docker compose -f docker-compose.dev.yml down

check: lint security test  ## 전체 검증

lint:            ## 코드 린트
	ruff check src/ tests/
	ruff format --check src/ tests/

format:          ## 코드 포맷팅
	ruff format src/ tests/

security:        ## 보안 검사
	bandit -r src/ -c pyproject.toml
	pip-audit

test:            ## 단위 테스트만
	pytest tests/unit/ -v --timeout=30

test-all:        ## 전체 테스트
	pytest tests/ -v --timeout=300

test-cov:        ## 커버리지 포함
	pytest tests/ --cov=jedisos --cov-report=html --cov-report=term

tracking:        ## 추적 해시 문서 생성
	python scripts/generate_tracking.py > docs/TRACKING_REGISTRY.md
```

## 핵심 라이브러리 버전 (2026-02-16 PyPI 검증)

| 패키지 | 버전 | 용도 |
|--------|------|------|
| litellm | >=1.81.12 | LLM 라우터 (100+ 프로바이더) |
| langgraph | >=1.0.8 | 에이전트 그래프 프레임워크 |
| langgraph-checkpoint-postgres | >=3.0.4 | LangGraph PostgreSQL 체크포인터 |
| hindsight-client | >=0.4.11 | Hindsight 메모리 클라이언트 |
| fastmcp | >=2.14.5,<3.0 | MCP 서버/클라이언트 (v3.0 RC1 출시, GA 후 마이그레이션 계획) |
| mcp | >=1.26.0,<2.0 | Model Context Protocol SDK (v2 Q1 2026 브레이킹) |
| pydantic | >=2.12.5 | 데이터 검증 |
| pydantic-settings | >=2.13.0 | 환경변수 기반 설정 |
| httpx | >=0.28.1 | 비동기 HTTP 클라이언트 |
| structlog | >=25.5.0 | 구조화된 로깅 |
| typer | >=0.23.1 | CLI 프레임워크 |
| rich | >=14.3.2 | 터미널 UI |
| uuid6 | >=2025.0.1 | UUIDv7 생성 |
| cryptography | >=46.0.5 | 암호화 |
| nest-asyncio | >=1.6.0 | Hindsight 클라이언트 필수 |
| croniter | >=6.0.0 | Cron 스케줄 파싱 |
| keyring | >=25.7.0 | 시크릿 저장 |
| python-telegram-bot | >=22.6 | 텔레그램 봇 |
| discord.py | >=2.6.4 | 디스코드 봇 |
| slack-bolt | >=1.27.0 | 슬랙 봇 |

### 개발 의존성

| 패키지 | 버전 | 용도 |
|--------|------|------|
| pytest | >=9.0.2 | 테스트 프레임워크 |
| pytest-asyncio | >=1.3.0 | 비동기 테스트 |
| pytest-cov | >=7.0.0 | 커버리지 |
| pytest-timeout | >=2.4.0 | 테스트 타임아웃 |
| hypothesis | >=6.151.8 | 속성 기반 테스트 |
| ruff | >=0.15.1 | 린트 + 포맷터 |
| bandit | >=1.9.3 | 보안 정적분석 |
| pip-audit | >=2.10.0 | 의존성 취약점 검사 |
| pre-commit | >=4.5.1 | Git 훅 관리 |

## 개발 순서 (Phase별)

> 각 Phase는 기간이 아닌 **순서**입니다. 이전 Phase가 완료되어야 다음으로 넘어갑니다.

### Phase 1: Foundation (기반)
**목표:** 프로젝트 스캐폴딩 + 핵심 데이터 구조

1. `pyproject.toml` 작성 (의존성, 메타데이터, 툴 설정)
2. `src/jedisos/__init__.py` + 버전 정보
3. `src/jedisos/core/exceptions.py` [JS-A003] - 예외 계층
4. `src/jedisos/core/types.py` [JS-A004] - 공통 타입
5. `src/jedisos/core/config.py` [JS-A002] - pydantic-settings 기반 설정
6. `src/jedisos/core/envelope.py` [JS-A001] - Envelope 메시지 계약
7. `tests/unit/test_envelope.py` [JS-T001] - Envelope 단위 테스트
8. `Makefile` + `docker-compose.dev.yml` + `.env.example`
9. `.github/workflows/ci.yml` - 기본 CI

**검증:** `make check` 통과

### Phase 2: Memory (메모리)
**목표:** Hindsight 연동 + 정체성 시스템

1. `docker-compose.dev.yml`에 Hindsight 컨테이너 추가
2. `src/jedisos/memory/hindsight.py` [JS-B001] - Hindsight 클라이언트 래퍼
   - `retain()`, `recall()`, `reflect()` 메서드
   - 연결 풀링, 재시도, 타임아웃 처리
3. `src/jedisos/memory/identity.py` [JS-B002] - IDENTITY.md 로더
4. `tests/unit/test_memory_mock.py` [JS-T002] - mock 기반 단위 테스트
5. `tests/integration/test_hindsight_live.py` [JS-T003] - 실제 Hindsight 연동 테스트
6. `src/jedisos/memory/mcp_wrapper.py` [JS-B003] - Hindsight MCP 래퍼

**검증:** `pytest tests/integration/test_hindsight_live.py` 통과

### Phase 3: LLM (LLM 통합)
**목표:** LiteLLM 라우터 + 프롬프트 관리

1. `src/jedisos/llm/router.py` [JS-C001] - LiteLLM Router 래퍼
   - **설정 기반** 모델 폴백 체인 (`llm_config.yaml` 또는 환경변수)
   - 모델 추가/삭제/순서 변경이 코드 수정 없이 가능해야 함
   - 비용 추적
   - 속도 제한 처리
2. `llm_config.yaml` - 모델 폴백 설정 파일
3. `src/jedisos/llm/prompts.py` [JS-C002] - 프롬프트 템플릿
4. `tests/unit/test_llm_router.py` [JS-T004]

**검증:** 설정 변경만으로 폴백 체인이 바뀌는지 테스트 통과

### Phase 4: Agent (에이전트 루프)
**목표:** LangGraph 기반 ReAct 에이전트

1. `src/jedisos/agents/react.py` [JS-E001] - LangGraph StateGraph 기반 ReAct
   - `reason → act → observe → memory_update` 루프
   - Hindsight retain/recall 통합
   - LiteLLM 라우터 연동
2. `src/jedisos/agents/supervisor.py` [JS-E002] - 멀티에이전트 슈퍼바이저
3. `src/jedisos/agents/worker.py` [JS-E003] - 워커 에이전트
4. `tests/unit/test_react_agent.py` [JS-T005]
5. `tests/integration/test_agent_memory.py` [JS-T006]

**검증:** 에이전트가 메모리를 저장하고 이전 대화를 기억하는지 E2E 테스트

### Phase 5: MCP (도구 연동)
**목표:** FastMCP 서버 + 클라이언트

1. `src/jedisos/mcp/server.py` [JS-D001] - FastMCP 도구 서버
2. `src/jedisos/mcp/client.py` [JS-D002] - MCP 클라이언트 매니저
3. `tests/unit/test_mcp_tools.py` [JS-T007]

**검증:** MCP 도구 호출 → 에이전트 응답 E2E 플로우

### Phase 6: Security (보안)
**목표:** PDP + 감사 로그

1. `src/jedisos/security/pdp.py` [JS-G001] - Policy Decision Point
2. `src/jedisos/security/audit.py` [JS-G002] - 감사 로그
3. `tests/unit/test_pdp.py` [JS-T008]

**검증:** 금지된 도구 호출이 차단되는지 테스트

### Phase 7: Channels (채널)
**목표:** 메신저 봇 어댑터

1. `src/jedisos/channels/telegram.py` [JS-F001]
2. `src/jedisos/channels/discord.py` [JS-F002]
3. `src/jedisos/channels/slack.py` [JS-F003]
4. `tests/unit/test_channels.py` [JS-T009]

**검증:** 각 채널에서 메시지 수신 → 에이전트 응답 → 메시지 발송

### Phase 8: CLI (CLI + 릴리즈)
**목표:** CLI 인터페이스 + 빌드/릴리즈

1. `src/jedisos/cli/main.py` [JS-H001] - Typer CLI
2. `docker/Dockerfile` - 프로덕션 이미지
3. `.github/workflows/release.yml` - 릴리즈 자동화 (ghcr.io + PyPI + GitHub Release)
4. `scripts/install.sh` - 원클릭 설치 스크립트 (`curl | bash`)
5. `tests/e2e/test_full_flow.py` [JS-T010]

**검증:** `jedisos chat "안녕"` CLI 명령이 작동하는지 E2E 테스트

### Phase 9: Web UI (웹 대시보드)
**목표:** 웹 기반 채팅 + 설정 + MCP 관리 + 모니터링

1. `src/jedisos/web/app.py` [JS-W001] - FastAPI 앱 (포트 8080)
2. `src/jedisos/web/api/chat.py` [JS-W002] - WebSocket 채팅 API
3. `src/jedisos/web/api/settings.py` [JS-W003] - 설정 관리 API (.env, llm_config.yaml, mcp_servers.json 편집)
4. `src/jedisos/web/api/mcp.py` [JS-W004] - MCP 서버 관리 API (검색, 설치, 삭제)
5. `src/jedisos/web/api/monitoring.py` [JS-W005] - 상태/로그/비용 API
6. `src/jedisos/web/setup_wizard.py` [JS-W006] - 첫 실행 Setup Wizard (API 키 입력, 모델 선택, MCP 추천)
7. `web-ui/` - React 프론트엔드 (Tailwind CSS)
8. `tests/e2e/test_web_ui.py` [JS-T011] - Playwright 기반 웹 UI E2E 테스트

**검증:** 브라우저에서 `http://localhost:8080` 접속 → Setup Wizard → 채팅 → MCP 설치 E2E 플로우

### Phase 10: Forge (자가 코딩 — 2-Tier 경량 아키텍처)
**목표:** 에이전트가 직접 Skill(@tool 함수)을 생성하고, 정적분석으로 검증 후 핫로드

1. `src/jedisos/forge/generator.py` [JS-K001] - LLM 기반 Skill 생성 (tool.yaml + tool.py)
2. `src/jedisos/forge/tester.py` [JS-K002] - 자동 테스트 (AST 구문/Bandit/금지패턴/타입힌트)
3. `src/jedisos/forge/decorator.py` [JS-K003] - `@tool` 데코레이터 정의
4. `src/jedisos/forge/security.py` [JS-K004] - 코드 보안 정적분석 (Bandit + 금지 패턴 + import 화이트리스트)
5. `src/jedisos/forge/loader.py` [JS-K005] - `importlib` 핫로더
6. `src/jedisos/forge/templates/` - Jinja2 기반 Skill 생성 템플릿
7. `tools/` 디렉토리 구조 + `tools/generated/` (에이전트 자동 생성)
8. `tests/unit/test_forge.py` [JS-T012]
9. `tests/unit/test_tool_loader.py` [JS-T013]

**검증:** 에이전트에게 "날씨 도구 만들어줘" → Skill 생성 → 정적분석 → 핫로드 → 도구 사용 E2E

### Phase 11: Marketplace (마켓플레이스)
**목표:** 커뮤니티 패키지 레지스트리 + 게시/검색/설치

1. `src/jedisos/marketplace/models.py` [JS-M004] - 패키지 메타데이터 모델 (6종: Skill, MCP 서버, 프롬프트 팩, 워크플로우, 정체성 팩, 번들)
2. `src/jedisos/marketplace/client.py` [JS-M001] - Registry API 클라이언트
3. `src/jedisos/marketplace/publisher.py` [JS-M002] - 패키지 게시 + 자동 검증
4. `src/jedisos/marketplace/validator.py` [JS-M003] - 패키지 검증기 (Bandit + 정적분석 + 라이선스)
5. CLI 확장: `jedisos market search/install/publish/review`
6. 웹 UI 확장: `McpStore.jsx` 마켓플레이스 브라우저 강화
7. `tests/unit/test_marketplace.py` [JS-T014]

**검증:** 패키지 게시 → 검색 → 설치 → 사용 E2E 플로우

## 테스트 규칙

```bash
# 단위 테스트: mock만 사용, 외부 서비스 없이 5초 이내
pytest tests/unit/ -v --timeout=30

# 통합 테스트: 실제 Hindsight 필요, 30초 이내
pytest tests/integration/ -v --timeout=120 -m integration

# E2E 테스트: 전체 스택, 2분 이내
pytest tests/e2e/ -v --timeout=300 -m e2e
```

### 테스트 파일 명명

```
tests/unit/test_{모듈명}.py          # 단위
tests/integration/test_{기능}_live.py # 통합
tests/e2e/test_{시나리오}_flow.py     # E2E
```

### 테스트 작성 시 필수

1. 모든 public 함수에 최소 1개 테스트
2. 에러 경로(happy path + sad path) 모두 테스트
3. 비동기 함수는 `@pytest.mark.asyncio` 사용
4. 통합/E2E 테스트는 마커 필수: `@pytest.mark.integration`, `@pytest.mark.e2e`
5. 테스트에도 해시 코멘트 포함

## AI 디버깅 워크플로우

테스트 실패 시 Claude Code에게 다음과 같이 지시:

```bash
# 1. 실패한 테스트 확인
pytest tests/ -v --tb=long 2>&1 | tee /tmp/test_output.txt

# 2. 실패 원인 분석 요청
# "test_output.txt를 읽고 실패 원인을 분석해줘.
#  각 실패에 대해:
#  1) 어떤 assertion이 실패했는지
#  2) 원인이 코드 버그인지 테스트 버그인지
#  3) 수정 방안을 해시 코드와 함께 제시해줘"

# 3. 수정 후 재실행
pytest tests/ -v --tb=short
```

## 커밋 메시지 규칙

```
<type>(<scope>): <description>

[JS-XXXX] <상세 설명>

type: feat | fix | refactor | test | docs | chore | ci
scope: core | memory | llm | mcp | agents | channels | security | cli
```

예시:
```
feat(memory): Hindsight retain/recall 래퍼 구현

[JS-B001] HindsightMemory 클래스 구현
- retain(): 대화 내용을 Hindsight에 저장
- recall(): 쿼리 기반 메모리 검색
- reflect(): 주기적 메모리 통합 트리거
```

## 개발 시작점

> **처음 개발을 시작할 때:** `docs/BUILD_PLAYBOOK.md`를 먼저 읽으세요.
> Phase/Step 단위로 "무엇을 만들고 → 어떻게 검증하고 → 다음은 무엇"이 정리되어 있습니다.
> 상세 코드 패턴은 `docs/DEVELOPMENT_GUIDE.md`, 아키텍처는 `docs/ARCHITECTURE.md`를 참조합니다.

## 참고 문서

| 문서 | 경로 | 내용 |
|------|------|------|
| **빌드 플레이북** | `docs/BUILD_PLAYBOOK.md` | **AI 실행 가이드 — 여기서부터 시작** |
| 아키텍처 | `docs/ARCHITECTURE.md` | 시스템 구조 + 배포 아키텍처 + Mermaid 다이어그램 |
| 개발 가이드 | `docs/DEVELOPMENT_GUIDE.md` | Phase 1~11 상세 개발 가이드 |
| 테스트 전략 | `docs/TESTING_STRATEGY.md` | 3단계 테스트 + AI 디버깅 |
| 릴리즈 | `docs/RELEASE.md` | 오픈소스 배포 전략 + 3채널 릴리즈 |
| 추적 시스템 | `docs/TRACKING.md` | 해시 추적 + 문서 연동 |
| 라이브러리 | `docs/LIBRARY_REFERENCE.md` | 핵심 라이브러리 API 레퍼런스 |
| **MCP 확장** | `docs/MCP_EXTENSIONS.md` | **MCP 마켓플레이스 + OAuth + 플러그인 시스템** |
| **자가 진화** | `docs/SELF_EVOLVING.md` | **자가 코딩 (2-Tier) + 마켓플레이스** |
| **⚠️ 위험/결정** | `docs/RISKS_AND_DECISIONS.md` | **위험 요소 + Phase별 사람 개입 체크리스트** |
| 데이터베이스 | `docs/DATABASE_SCHEMA.md` | DB 스키마 (3 스키마: hindsight, langgraph, jedisos) |
| **Hindsight** | `docs/HINDSIGHT_USAGE.md` | **Hindsight 사용법 (retain/recall/reflect + JediSOS 통합 패턴)** |
| **LangGraph** | `docs/LANGGRAPH_USAGE.md` | **LangGraph 사용법 (StateGraph/체크포인팅/스트리밍/Human-in-the-Loop)** |
| **LiteLLM** | `docs/LITELLM_USAGE.md` | **LiteLLM 사용법 (멀티LLM 라우터/폴백/비용추적/도구호출)** |
| **FastMCP** | `docs/FASTMCP_USAGE.md` | **FastMCP 사용법 (MCP 서버/클라이언트/도구/전송모드)** |
| **MCP Auth** | `docs/MCP_AUTH_PROXY_USAGE.md` | **MCP Auth Proxy (OAuth 2.1/PKCE/토큰관리/Docker 통합)** |
| **🔍 Phase 검증** | `docs/PHASE_VERIFICATION.md` | **Phase 1~11 검증 가이드 (자동검증 + 사람검증 + 완료 체크리스트)** |
| v7 기획서 | `../JediSOS_최종_기획서_v7.md` | 전체 프로젝트 기획서 |
