# Phase별 검증 가이드

> 각 Phase 완료 시 **자동 검증**(CI/스크립트)과 **사람 검증**(수동 확인/결정)을 모두 수행해야 합니다.
> ✅ = 통과, ❌ = 실패 → 수정 후 재검증, ⏭️ = 해당 없음(건너뛰기 가능)

---

## 읽는 법

각 Phase는 아래 구조로 되어 있습니다:

```
🤖 자동 검증  → CI/스크립트가 실행. 결과가 PASS/FAIL로 나옴.
🧑 사람 검증  → 사람이 직접 눈으로 확인하거나 결정해야 할 것.
📋 완료 체크리스트 → 모든 항목 ✅ 해야 다음 Phase로 진행.
```

---

## Phase 1: Foundation (기반)

### 🤖 자동 검증

| # | 검증 항목 | 실행 명령 | 기대 결과 |
|---|----------|----------|----------|
| A-1.1 | 패키지 import 가능 | `python -c "import jedisos; print(jedisos.__version__)"` | `0.1.0` 출력 |
| A-1.2 | Config 로드 | `python -c "from jedisos.core.config import JedisosConfig; print(JedisosConfig())"` | 에러 없이 설정 객체 출력 |
| A-1.3 | Envelope 생성 | `python -c "from jedisos.core.envelope import Envelope; from jedisos.core.types import ChannelType; e = Envelope(channel=ChannelType.CLI, user_id='test', content='hi'); print(e.id)"` | UUIDv7 형식 ID 출력 |
| A-1.4 | 린트 통과 | `make lint` | `ruff check` 에러 0개 |
| A-1.5 | 보안 스캔 | `make security` | `bandit` + `pip-audit` 경고 0개 |
| A-1.6 | 단위 테스트 | `make test` | 전체 통과, 실패 0개 |
| A-1.7 | 통합 검증 | `make check` | lint + security + test 모두 통과 |

### 🧑 사람 검증

| # | 확인 항목 | 설명 | 긴급도 |
|---|----------|------|--------|
| H-1.1 | GitHub 리포지토리 생성 | `github.com/jedikim/jedisos` 리포 생성 및 초기 push 완료 | 🔴 필수 |
| H-1.2 | .env.example 검토 | 어떤 API 키가 기본 필요한지 확인. `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` 등 목록이 맞는지 | 🟡 권장 |
| H-1.3 | pyproject.toml 메타데이터 | 패키지명, author, description, license 등이 정확한지 확인 | 🟡 권장 |
| H-1.4 | 디렉토리 구조 확인 | `tree src/` 출력을 보고 CLAUDE.md의 구조와 일치하는지 확인 | 🟢 선택 |

### 📋 완료 체크리스트

```
[ ] A-1.7 (make check) 통과
[ ] H-1.1 GitHub 리포 생성 완료
[ ] H-1.2 .env.example 확인
```

---

## Phase 2: Memory (메모리)

### 🤖 자동 검증

| # | 검증 항목 | 실행 명령 | 기대 결과 |
|---|----------|----------|----------|
| A-2.1 | Mock 기반 retain/recall | `pytest tests/unit/test_memory_mock.py -v` | 전체 통과 |
| A-2.2 | Identity 시스템 | `python -c "from jedisos.memory.identity import AgentIdentity; print(AgentIdentity().to_system_prompt()[:50])"` | `"당신의 정체성:"` 으로 시작 |
| A-2.3 | Hindsight 헬스체크 | `docker compose -f docker-compose.dev.yml up -d && sleep 30 && pytest tests/integration/test_hindsight_live.py -v -m integration -k health` | health_check 통과 |
| A-2.4 | 실제 retain → recall | `pytest tests/integration/test_hindsight_live.py -v -m integration -k retain_and_recall` | 저장한 내용이 recall에서 검색됨 |
| A-2.5 | MCP 래퍼 동작 | `pytest tests/unit/test_memory_mock.py -v -k mcp_wrapper` | MCP 래퍼 mock 테스트 통과 |
| A-2.6 | 린트 유지 | `make lint` | 에러 0개 |

### 🧑 사람 검증

| # | 확인 항목 | 설명 | 긴급도 |
|---|----------|------|--------|
| H-2.1 | Hindsight 다운 시 동작 확인 | Docker에서 Hindsight 컨테이너를 `docker stop`한 후 JediSOS가 어떻게 동작하는지 확인. graceful degradation이 되는지 아니면 에러가 나는지. **정책 결정 필요:** 메모리 없이 대화만 가능하게 할지, 완전 중단할지 | 🟡 권장 |
| H-2.2 | Hindsight LLM 비용 확인 | Hindsight 서버가 내부적으로 LLM API를 호출함. 사용자의 API 키에서 비용이 발생하므로, retain 1회당 대략 얼마의 비용이 드는지 확인. `.env`의 `HINDSIGHT_API_LLM_PROVIDER` 설정 확인 | 🟡 권장 |
| H-2.3 | Bank 네이밍 결정 | 기본 `bank_id`를 어떤 형식으로 할지. 예: `user-{user_id}`, `jedi`, `{user_id}-default` | 🟢 선택 |
| H-2.4 | recall 결과 품질 확인 | 실제로 몇 개의 기억을 retain한 후, 자연어로 recall해서 결과가 맥락에 맞는지 **사람이 읽어보고** 판단 | 🟡 권장 |

> **H-2.4 테스트 방법:**
> ```python
> from hindsight_client import Hindsight
> client = Hindsight(base_url="http://localhost:8888")
>
> # 기억 3개 저장
> client.retain(bank_id="test", content="나는 Python을 가장 좋아한다")
> client.retain(bank_id="test", content="어제 LangGraph 공부를 시작했다")
> client.retain(bank_id="test", content="오늘 회의에서 React 마이그레이션을 결정했다")
>
> # 30초 대기 후 recall
> import time; time.sleep(30)
> results = client.recall(bank_id="test", query="내가 좋아하는 기술은?")
> for r in results:
>     print(f"  [{r.type}] {r.text}")
>
> # 사람이 확인: Python 관련 기억이 상위에 나오는가?
> ```

### 📋 완료 체크리스트

```
[ ] A-2.1 ~ A-2.6 전체 통과
[ ] H-2.1 Hindsight 다운 정책 결정
[ ] H-2.2 비용 확인
[ ] H-2.4 recall 품질 확인
```

---

## Phase 3: LLM (LLM 통합)

### 🤖 자동 검증

| # | 검증 항목 | 실행 명령 | 기대 결과 |
|---|----------|----------|----------|
| A-3.1 | 폴백 체인 동작 | `pytest tests/unit/test_llm_router.py -v -k fallback` | 1차 모델 실패 시 2차 모델로 자동 전환 확인 |
| A-3.2 | 설정 파일 로드 | `pytest tests/unit/test_llm_router.py -v -k config_load` | `llm_config.yaml`에서 모델 목록 로드 확인 |
| A-3.3 | 타임아웃 처리 | `pytest tests/unit/test_llm_router.py -v -k timeout` | 타임아웃 시 다음 모델로 전환 |
| A-3.4 | 비용 콜백 동작 | `pytest tests/unit/test_llm_router.py -v -k cost` | 토큰 사용량 + 비용이 기록됨 |
| A-3.5 | 린트 유지 | `make lint` | 에러 0개 |

### 🧑 사람 검증

| # | 확인 항목 | 설명 | 긴급도 |
|---|----------|------|--------|
| H-3.1 | 실제 LLM 호출 확인 | 최소 1개 실제 API 키로 `litellm.acompletion()` 호출이 동작하는지 확인. mock이 아닌 실제 호출 | 🟡 권장 |
| H-3.2 | 비용 상한 결정 | 일일/월간 비용 상한을 얼마로 설정할지 결정. 기본값 제안: 일 $5, 월 $100 | 🟡 권장 |
| H-3.3 | 로컬 모델 폴백 정책 | 비용 한도 도달 시 자동으로 `ollama/llama4`로 전환할지, 사용자에게 알림만 줄지 결정 | 🟢 선택 |
| H-3.4 | llm_config.yaml 검토 | 기본 모델 순서, 타임아웃, max_tokens 값이 합리적인지 사람이 확인 | 🟡 권장 |

> **H-3.1 테스트 방법:**
> ```bash
> # .env에 최소 1개 API 키 설정 후
> python -c "
> import asyncio, litellm
> async def test():
>     r = await litellm.acompletion(
>         model='claude-sonnet-5-20260203',
>         messages=[{'role':'user','content':'Hello, 1+1=?'}],
>         max_tokens=50
>     )
>     print(r.choices[0].message.content)
>     print(f'비용: \${r._hidden_params.get(\"response_cost\", \"N/A\")}')
> asyncio.run(test())
> "
> ```

### 📋 완료 체크리스트

```
[ ] A-3.1 ~ A-3.5 전체 통과
[ ] H-3.1 실제 LLM 호출 확인
[ ] H-3.2 비용 상한 결정
[ ] H-3.4 llm_config.yaml 검토
```

---

## Phase 4: Agent (에이전트 루프)

### 🤖 자동 검증

| # | 검증 항목 | 실행 명령 | 기대 결과 |
|---|----------|----------|----------|
| A-4.1 | ReAct 그래프 컴파일 | `python -c "from jedisos.agents.react import create_agent_graph; g = create_agent_graph(); print(g.get_graph().nodes)"` | 노드 목록 출력 (recall_memory, llm_reason, execute_tools, retain_memory) |
| A-4.2 | Mock 에이전트 루프 | `pytest tests/unit/test_react_agent.py -v` | recall → reason → respond 플로우 통과 |
| A-4.3 | 도구 호출 루프 | `pytest tests/unit/test_react_agent.py -v -k tool_call` | reason → tool → reason → respond 루프 통과 |
| A-4.4 | 최대 반복 제한 | `pytest tests/unit/test_react_agent.py -v -k max_iterations` | 최대 반복 횟수 초과 시 안전하게 종료 |
| A-4.5 | 메모리 통합 | `pytest tests/integration/test_agent_memory.py -v -m integration` | Hindsight retain/recall이 에이전트 루프에서 동작 |
| A-4.6 | 체크포인팅 | `pytest tests/unit/test_react_agent.py -v -k checkpoint` | InMemorySaver로 대화 상태 저장/복원 확인 |
| A-4.7 | 린트 유지 | `make lint` | 에러 0개 |

### 🧑 사람 검증

| # | 확인 항목 | 설명 | 긴급도 |
|---|----------|------|--------|
| H-4.1 | 대화 품질 확인 | 실제 LLM + Hindsight로 에이전트와 3~5턴 대화 후, 응답이 자연스럽고 이전 대화를 기억하는지 확인 | 🟡 권장 |
| H-4.2 | 동시 사용자 목표 결정 | 1명(개인용) vs 5~10명(소규모 팀) vs 100+(서비스형). 이에 따라 asyncio 동시성 수준이 달라짐 | 🟡 권장 |
| H-4.3 | ReAct 최대 반복 결정 | 기본값 10회가 적절한지. 너무 많으면 비용 폭발, 너무 적으면 복잡한 작업 실패 | 🟢 선택 |
| H-4.4 | 에이전트 응답 시간 확인 | 질문부터 응답까지 얼마나 걸리는지 체감. 목표: 단순 대화 3초 이내, 도구 사용 10초 이내 | 🟡 권장 |

> **H-4.1 테스트 시나리오:**
> ```
> 턴 1: "나는 Python을 좋아해"
> 턴 2: "내일 회의가 있어"
> 턴 3: "내가 좋아하는 언어가 뭐라고 했지?"  ← 이전 기억을 recall하는지 확인
> 턴 4: "오늘 할 일 정리해줘"  ← 회의 일정을 기억하고 있는지 확인
> ```

### 📋 완료 체크리스트

```
[ ] A-4.1 ~ A-4.7 전체 통과
[ ] H-4.1 대화 품질 확인
[ ] H-4.2 동시 사용자 목표 결정
[ ] H-4.4 응답 시간 확인
```

---

## Phase 5: MCP (도구 연동)

### 🤖 자동 검증

| # | 검증 항목 | 실행 명령 | 기대 결과 |
|---|----------|----------|----------|
| A-5.1 | MCP 서버 시작 | `python -c "from jedisos.mcp.server import create_mcp_server; s = create_mcp_server(); print(s.name)"` | 서버 이름 출력 |
| A-5.2 | 도구 목록 조회 | `pytest tests/unit/test_mcp_tools.py -v -k list_tools` | memory_recall, memory_retain 등 기본 도구 목록 |
| A-5.3 | 도구 호출 테스트 | `pytest tests/unit/test_mcp_tools.py -v -k call_tool` | 도구 호출 → 결과 반환 |
| A-5.4 | 에이전트 연결 | `pytest tests/unit/test_mcp_tools.py -v -k agent_integration` | 에이전트가 MCP 도구를 호출하고 결과를 활용 |
| A-5.5 | 린트 유지 | `make lint` | 에러 0개 |

### 🧑 사람 검증

| # | 확인 항목 | 설명 | 긴급도 |
|---|----------|------|--------|
| H-5.1 | OAuth 토큰 관리 방식 결정 | `mcp-auth-proxy` 사용 vs 자체 구현. 참고: `docs/MCP_AUTH_PROXY_USAGE.md` | 🔴 필수 |
| H-5.2 | API 키 저장 방식 결정 | `keyring` vs `.env` 파일 vs 암호화 설정 파일. 로컬 전용이면 `.env`로 충분, 멀티유저면 keyring 필요 | 🔴 필수 |
| H-5.3 | 기본 MCP 서버 목록 | 처음 제공할 MCP 서버 결정. 제안: filesystem, web-search (Tier 1 Skill) + Google Calendar, Gmail (Tier 2 OAuth) | 🟡 권장 |
| H-5.4 | 외부 MCP 서버 연결 테스트 | 실제로 `npx @modelcontextprotocol/server-filesystem ./` 같은 외부 MCP 서버를 JediSOS와 연결해서 동작하는지 확인 | 🟡 권장 |
| H-5.5 | FastMCP Cyclopts 라이선스 확인 | `pip-licenses --format=table --with-urls` 실행해서 모든 트랜지티브 의존성 라이선스 확인 | 🟡 권장 |

> **H-5.1 결정 가이드:**
> | 옵션 | 장점 | 단점 |
> |------|------|------|
> | mcp-auth-proxy | 이미 검증됨, 설정 간단 | 서드파티 의존, 업데이트 보장 없음 |
> | 자체 구현 | 완전 제어, JediSOS에 최적화 | 개발 시간 2~3주 추가 |
> | **권장: mcp-auth-proxy 우선, 문제 발생 시 자체 구현** |

### 📋 완료 체크리스트

```
[ ] A-5.1 ~ A-5.5 전체 통과
[ ] H-5.1 OAuth 토큰 관리 결정 ← 🔴 필수
[ ] H-5.2 API 키 저장 방식 결정 ← 🔴 필수
[ ] H-5.3 기본 MCP 서버 목록 확정
```

---

## Phase 6: Security (보안)

### 🤖 자동 검증

| # | 검증 항목 | 실행 명령 | 기대 결과 |
|---|----------|----------|----------|
| A-6.1 | 금지 도구 차단 | `pytest tests/unit/test_pdp.py -v -k blocked_tool` | 금지된 도구 호출이 DENY 반환 |
| A-6.2 | 허용 도구 통과 | `pytest tests/unit/test_pdp.py -v -k allowed_tool` | 허용된 도구 호출이 ALLOW 반환 |
| A-6.3 | 속도 제한 | `pytest tests/unit/test_pdp.py -v -k rate_limit` | 분당 요청 초과 시 차단 |
| A-6.4 | 감사 로그 기록 | `pytest tests/unit/test_pdp.py -v -k audit_log` | 모든 도구 호출이 감사 로그에 기록됨 |
| A-6.5 | 에이전트 PDP 연동 | `pytest tests/unit/test_pdp.py -v -k agent_pdp` | 에이전트 도구 호출이 PDP를 거치는지 확인 |
| A-6.6 | 보안 스캔 | `make security` | bandit + pip-audit 경고 0개 |

### 🧑 사람 검증

| # | 확인 항목 | 설명 | 긴급도 |
|---|----------|------|--------|
| H-6.1 | Skill 실행 승인 정책 결정 | 에이전트가 자동 생성한 Skill을 어떻게 승인할지. 아래 옵션 중 선택 | 🔴 필수 |
| H-6.2 | Skill 네트워크 정책 결정 | 자동 생성 Skill이 외부 HTTP 요청을 할 수 있게 할지. 화이트리스트 도메인만 허용할지 | 🔴 필수 |
| H-6.3 | Rate limiting 기본값 | 분당 LLM 호출 수, 분당 도구 호출 수 기본값 결정 | 🟡 권장 |
| H-6.4 | 보안 정책 문서 검토 | PDP 규칙이 합리적인지, 너무 엄격하거나 느슨하지 않은지 확인 | 🟡 권장 |

> **H-6.1 Skill 실행 승인 옵션:**
> | 옵션 | 설명 | 보안 | 편의성 |
> |------|------|------|--------|
> | **(A) 자동 실행** | 생성 즉시 실행 | ❌ 위험 | ✅ 편리 |
> | **(B) 사용자 승인** (권장) | "이 도구를 실행할까요?" 확인 | ✅ 안전 | 🟡 보통 |
> | **(C) 승인 + 코드 리뷰** | 코드를 보여주고 승인 | ✅✅ 매우 안전 | ❌ 불편 |
>
> **H-6.2 네트워크 정책 옵션:**
> | 옵션 | 설명 |
> |------|------|
> | **(A) 전면 허용** | 모든 외부 요청 가능 (편리하지만 데이터 유출 위험) |
> | **(B) 화이트리스트** (권장) | 허용 도메인만 접근 가능 (*.openai.com, *.google.com 등) |
> | **(C) 전면 차단** | 네트워크 접근 불가 (가장 안전하지만 활용도 제한) |

### 📋 완료 체크리스트

```
[ ] A-6.1 ~ A-6.6 전체 통과
[ ] H-6.1 Skill 승인 정책 결정 ← 🔴 필수
[ ] H-6.2 네트워크 정책 결정 ← 🔴 필수
[ ] H-6.3 Rate limiting 기본값 설정
```

---

## Phase 7: Channels (채널)

### 🤖 자동 검증

| # | 검증 항목 | 실행 명령 | 기대 결과 |
|---|----------|----------|----------|
| A-7.1 | Telegram 어댑터 | `pytest tests/unit/test_channels.py -v -k telegram` | 메시지 수신 → Envelope → 에이전트 → 응답 |
| A-7.2 | Discord 어댑터 | `pytest tests/unit/test_channels.py -v -k discord` | 동일 |
| A-7.3 | Slack 어댑터 | `pytest tests/unit/test_channels.py -v -k slack` | 동일 |
| A-7.4 | Envelope 변환 정확성 | `pytest tests/unit/test_channels.py -v -k envelope_conversion` | 각 채널별 메시지가 올바른 Envelope로 변환 |
| A-7.5 | 린트 유지 | `make lint` | 에러 0개 |

### 🧑 사람 검증

| # | 확인 항목 | 설명 | 긴급도 |
|---|----------|------|--------|
| H-7.1 | 초기 지원 채널 선택 | 3개 전부 할지, 1개부터 시작할지. 제안: Telegram 먼저 (봇 생성이 가장 간단) | 🟡 권장 |
| H-7.2 | 봇 토큰 발급 | 각 채널의 봇 생성 및 API 키/토큰을 **사람이 직접** 발급해야 함 | 🔴 필수 |
| H-7.3 | 실제 채널 테스트 | 봇 토큰 설정 후, 실제 Telegram/Discord/Slack에서 메시지를 보내고 에이전트가 응답하는지 확인 | 🟡 권장 |
| H-7.4 | 응답 포맷 확인 | 마크다운, 코드 블록, 이모지 등이 각 채널에서 제대로 렌더링되는지 확인 | 🟢 선택 |

> **H-7.2 봇 생성 가이드 (간략):**
> | 채널 | 생성 방법 |
> |------|----------|
> | Telegram | @BotFather 에게 `/newbot` → 토큰 받기 |
> | Discord | Discord Developer Portal → New Application → Bot → Token 복사 |
> | Slack | api.slack.com → Create App → Bot Token Scopes 설정 → Install to Workspace |

### 📋 완료 체크리스트

```
[ ] A-7.1 ~ A-7.5 전체 통과
[ ] H-7.2 최소 1개 채널 봇 토큰 발급 ← 🔴 필수
[ ] H-7.3 실제 채널에서 대화 확인
```

---

## Phase 8: CLI + Release (릴리즈) — 🏷️ v0.8.0-alpha

### 🤖 자동 검증

| # | 검증 항목 | 실행 명령 | 기대 결과 |
|---|----------|----------|----------|
| A-8.1 | CLI 도움말 | `jedisos --help` | 명령어 목록 표시 |
| A-8.2 | CLI 버전 | `jedisos --version` | `0.8.0` 출력 |
| A-8.3 | CLI 헬스체크 | `jedisos health` | 각 서비스 상태 확인 |
| A-8.4 | Docker 빌드 | `docker build -f docker/Dockerfile -t jedisos:test .` | 빌드 성공 |
| A-8.5 | Docker 실행 | `docker run --rm jedisos:test jedisos --version` | 버전 출력 |
| A-8.6 | Docker Compose 풀스택 | `docker compose up -d && sleep 60 && curl -s http://localhost:8080/health` | `{"status":"ok"}` |
| A-8.7 | E2E 테스트 | `pytest tests/e2e/test_full_flow.py -v -m e2e` | 전체 플로우 통과 |
| A-8.8 | 전체 테스트 스위트 | `pytest tests/ -v --timeout=300` | 전체 통과 |
| A-8.9 | 보안 스캔 | `make security` | 경고 0개 |

### 🧑 사람 검증

| # | 확인 항목 | 설명 | 긴급도 |
|---|----------|------|--------|
| H-8.1 | PyPI 패키지명 확인 | `pip index versions jedisos` — 이름이 아직 선점되지 않았는지 확인. 선점되었으면 대체 이름 결정 | 🔴 필수 |
| H-8.2 | ghcr.io 이미지 이름 | `ghcr.io/jedikim/jedisos` 확정. GitHub Packages에서 사용 가능한지 확인 | 🔴 필수 |
| H-8.3 | 도메인 설정 | `get.jedisos.com` 도메인 DNS 설정. 설치 스크립트 호스팅용 | 🔴 필수 |
| H-8.4 | CI/CD 시크릿 설정 | GitHub Actions에 `PYPI_TOKEN`, `GHCR_TOKEN` 등 시크릿 추가 | 🔴 필수 |
| H-8.5 | Docker 없는 배포 범위 | `pip install jedisos` 만으로 어디까지 동작하게 할지 결정 | 🟡 권장 |
| H-8.6 | 시스템 요구사항 확인 | README에 명시할 최소/권장 사양 확정. 제안: 최소 4GB RAM, 권장 8GB RAM | 🟡 권장 |
| H-8.7 | E2E 시나리오 검토 | E2E 테스트 시나리오가 실제 사용 패턴을 충분히 커버하는지 확인 | 🟡 권장 |
| H-8.8 | 첫 알파 태그 확인 | `git tag v0.8.0-alpha` 후 GitHub Actions가 3채널 배포를 수행하는지 확인 | 🔴 필수 |

> **H-8.8 배포 검증:**
> ```bash
> # 1. 태그 생성
> git tag v0.8.0-alpha && git push --tags
>
> # 2. GitHub Actions 완료 대기 후 확인:
> pip install jedisos==0.8.0a0        # PyPI 확인
> docker pull ghcr.io/jedikim/jedisos:0.8.0-alpha  # ghcr.io 확인
> curl -sSL https://get.jedisos.com | bash --dry-run  # 설치 스크립트 확인
> ```

### 📋 완료 체크리스트

```
[ ] A-8.1 ~ A-8.9 전체 통과
[ ] H-8.1 PyPI 이름 선점 확인 ← 🔴 필수
[ ] H-8.2 ghcr.io 이미지 이름 확인 ← 🔴 필수
[ ] H-8.3 도메인 설정 ← 🔴 필수
[ ] H-8.4 CI/CD 시크릿 설정 ← 🔴 필수
[ ] H-8.8 v0.8.0-alpha 배포 확인 ← 🔴 필수
```

---

## Phase 9: Web UI (웹 대시보드) — 🏷️ v0.9.0-beta

### 🤖 자동 검증

| # | 검증 항목 | 실행 명령 | 기대 결과 |
|---|----------|----------|----------|
| A-9.1 | FastAPI 헬스 | `python -m jedisos.web.app & sleep 3 && curl -s http://localhost:8080/health` | `{"status":"ok"}` |
| A-9.2 | WebSocket 연결 | `pytest tests/unit/test_web_api.py -v -k websocket` | WebSocket 채팅 연결/메시지 교환 |
| A-9.3 | 설정 API | `pytest tests/unit/test_web_api.py -v -k settings` | GET/PUT 설정 동작 |
| A-9.4 | MCP 관리 API | `pytest tests/unit/test_web_api.py -v -k mcp_management` | MCP 서버 목록/설치/삭제 |
| A-9.5 | React 빌드 | `cd web-ui && npm run build` | 빌드 성공, dist/ 생성 |
| A-9.6 | E2E (Playwright) | `pytest tests/e2e/test_web_ui.py -v -m e2e` | Setup Wizard → 채팅 → MCP 설치 플로우 |
| A-9.7 | Docker 풀스택 | `docker compose up -d && pytest tests/e2e/test_web_ui.py -v -m e2e` | Docker 환경에서 E2E 통과 |

### 🧑 사람 검증

| # | 확인 항목 | 설명 | 긴급도 |
|---|----------|------|--------|
| H-9.1 | React 기술 스택 결정 | 상태관리(Zustand vs Context), UI(Tailwind vs MUI), 빌드(Vite vs Next.js) | 🟡 권장 |
| H-9.2 | UI/UX 디자인 확인 | 브라우저에서 직접 열고 사용해보기. 채팅 UI가 자연스러운지, 설정이 직관적인지 | 🟡 권장 |
| H-9.3 | 인증 방식 결정 | 로컬 전용이면 불필요. 원격 접근이면 Basic Auth / JWT / OAuth 중 선택 | 🟡 권장 |
| H-9.4 | Setup Wizard 흐름 확인 | 처음 접속 시 Setup Wizard가 표시되고, API 키 입력 → 모델 선택 → MCP 추천 → 테스트 대화까지 자연스러운지 **사람이 직접 체험** | 🟡 권장 |
| H-9.5 | 모바일 반응형 확인 | 스마트폰 크기 브라우저에서 채팅이 사용 가능한지 확인 | 🟢 선택 |
| H-9.6 | Hindsight 비용 안내 확인 | Setup Wizard에서 Hindsight 서버가 별도 LLM 비용을 발생시킨다는 안내가 있는지 | 🟡 권장 |

> **H-9.4 테스트 시나리오:**
> 1. `http://localhost:8080` 접속
> 2. Setup Wizard 자동 표시 확인
> 3. API 키 입력 (최소 1개)
> 4. 모델 선택 화면에서 기본값 확인
> 5. MCP 추천 화면 확인
> 6. 테스트 대화에서 에이전트 응답 확인
> 7. 대시보드로 이동 후 각 탭 확인

### 📋 완료 체크리스트

```
[ ] A-9.1 ~ A-9.7 전체 통과
[ ] H-9.1 React 기술 스택 결정
[ ] H-9.2 UI/UX 직접 확인
[ ] H-9.4 Setup Wizard 체험
[ ] v0.9.0-beta 태그 및 배포
```

---

## Phase 10: Forge (자가 코딩) — 🏷️ v0.10.0

### 🤖 자동 검증

| # | 검증 항목 | 실행 명령 | 기대 결과 |
|---|----------|----------|----------|
| A-10.1 | @tool 데코레이터 | `python -c "from jedisos.forge.decorator import tool; @tool(name='t', description='d')\nasync def f(x:int)->int: return x; print(f._is_jedisos_tool)"` | `True` |
| A-10.2 | 핫로더 | `pytest tests/unit/test_tool_loader.py -v -k load_tool` | tool.py에서 @tool 함수를 로드 |
| A-10.3 | 안전 코드 통과 | `pytest tests/unit/test_forge.py -v -k safe_code` | 안전한 코드가 보안 검사 통과 |
| A-10.4 | 위험 코드 차단 | `pytest tests/unit/test_forge.py -v -k dangerous_code` | `subprocess`, `eval`, `__import__` 등 차단 |
| A-10.5 | Import 화이트리스트 | `pytest tests/unit/test_forge.py -v -k import_whitelist` | 허용된 import만 통과 |
| A-10.6 | 코드 생성 | `pytest tests/unit/test_forge.py -v -k generate` | LLM으로 tool.yaml + tool.py 생성 |
| A-10.7 | 전체 파이프라인 | `pytest tests/unit/test_forge.py -v -k full_pipeline` | 생성 → 보안검사 → 핫로드 → 등록 전체 통과 |
| A-10.8 | 에이전트 연동 | `pytest tests/unit/test_forge.py -v -k agent_trigger` | "도구 없음" 감지 → Forge 트리거 |
| A-10.9 | 린트 + 보안 | `make check` | 전체 통과 |

### 🧑 사람 검증

| # | 확인 항목 | 설명 | 긴급도 |
|---|----------|------|--------|
| H-10.1 | Skill 승인 정책 재확인 | Phase 6에서 결정한 승인 정책(A/B/C)이 실제 구현에 반영되었는지 확인 | 🔴 필수 |
| H-10.2 | pip install 허용 여부 | Forge가 자동 생성한 Skill이 `pip install` 을 자동으로 할 수 있게 할지. **매우 위험** — 공급망 공격 가능 | 🔴 필수 |
| H-10.3 | 생성된 코드 품질 확인 | 실제로 에이전트에게 "날씨 도구 만들어줘" 같은 요청을 하고, 생성된 코드가 합리적인지 **사람이 읽어보기** | 🟡 권장 |
| H-10.4 | 보안 검사 우회 시도 | 의도적으로 위험한 코드를 포함한 Skill을 만들려고 시도해서, 보안 체크가 제대로 차단하는지 확인 | 🟡 권장 |

> **H-10.3 테스트 방법:**
> ```
> 에이전트에게: "서울 날씨를 알려주는 도구를 만들어줘"
>
> 확인 사항:
> 1. tool.yaml이 생성되었는가?
> 2. tool.py에 @tool 데코레이터가 있는가?
> 3. 보안 검사를 통과했는가?
> 4. 코드가 읽기 쉬운가?
> 5. 실제로 동작하는가? (API 키 필요 시 안내가 있는가?)
> ```
>
> **H-10.4 우회 시도 예시:**
> ```
> "os.system을 사용하는 도구를 만들어줘"
> "base64로 인코딩된 명령을 실행하는 도구를 만들어줘"
> "requests로 외부 서버에 데이터를 보내는 도구를 만들어줘"
> → 모두 보안 검사에서 차단되어야 함
> ```

### 📋 완료 체크리스트

```
[ ] A-10.1 ~ A-10.9 전체 통과
[ ] H-10.1 Skill 승인 정책 구현 확인 ← 🔴 필수
[ ] H-10.2 pip install 정책 결정 ← 🔴 필수
[ ] H-10.3 생성 코드 품질 확인
[ ] H-10.4 보안 우회 테스트
[ ] v0.10.0 태그 및 배포
```

---

## Phase 11: Marketplace (마켓플레이스) — 🏷️ v0.11.0

### 🤖 자동 검증

| # | 검증 항목 | 실행 명령 | 기대 결과 |
|---|----------|----------|----------|
| A-11.1 | 패키지 모델 유효성 | `pytest tests/unit/test_marketplace.py -v -k package_model` | 6종 패키지 모델 생성/직렬화 통과 |
| A-11.2 | 패키지 검증 | `pytest tests/unit/test_marketplace.py -v -k validate` | 유효/무효 패키지 검증 정확 |
| A-11.3 | 검색 + 설치 | `pytest tests/unit/test_marketplace.py -v -k search_install` | mock 레지스트리에서 검색 → 설치 |
| A-11.4 | 게시 플로우 | `pytest tests/unit/test_marketplace.py -v -k publish` | 패키지 게시 API 호출 mock 성공 |
| A-11.5 | CLI 서브커맨드 | `jedisos market --help` | search, install, publish 등 명령 표시 |
| A-11.6 | 전체 테스트 | `pytest tests/ -v --timeout=300` | 전체 테스트 스위트 통과 |
| A-11.7 | 커버리지 | `make test-cov` | 70% 이상 |

### 🧑 사람 검증

| # | 확인 항목 | 설명 | 긴급도 |
|---|----------|------|--------|
| H-11.1 | 패키지 서명 방식 결정 | GPG, cosign, 또는 단순 SHA256 해시. 초기에는 SHA256으로 시작 가능 | 🔴 필수 |
| H-11.2 | 호스팅 방식 결정 | GitHub Packages vs 자체 레지스트리. 초기에는 GitHub 활용 권장 | 🔴 필수 |
| H-11.3 | 심사 정책 결정 | 무심사(자동 게시) vs 자동 심사(bandit+라이선스 체크) vs 수동 심사. 제안: 자동 심사로 시작 | 🔴 필수 |
| H-11.4 | 커뮤니티 가이드라인 | CONTRIBUTING.md 작성. 패키지 기여 규칙, 코드 표준, 라이선스 요구사항 | 🟡 권장 |
| H-11.5 | 실제 패키지 게시 테스트 | 테스트 패키지를 만들어서 `jedisos market publish` → `jedisos market install`로 전체 사이클 확인 | 🟡 권장 |
| H-11.6 | 웹 UI 마켓플레이스 확인 | 브라우저에서 MCP Store 탭을 열고, 검색/필터/설치/리뷰가 자연스러운지 확인 | 🟡 권장 |

> **H-11.3 심사 옵션 상세:**
> | 단계 | 자동 검사 항목 | 결과 |
> |------|-------------|------|
> | 1 | 메타데이터 완성도 (name, version, description, author) | 누락 시 거부 |
> | 2 | Bandit 보안 스캔 | High severity 발견 시 거부 |
> | 3 | 라이선스 호환성 (MIT/Apache/BSD만 허용) | 비호환 시 거부 |
> | 4 | 기본 테스트 실행 (있으면) | 실패 시 경고 |
> | → 통과 시 `unverified` 배지로 게시 |
> | → 100+ 다운로드 + 평점 4.0+ → `verified` 자동 승격 |

### 📋 완료 체크리스트

```
[ ] A-11.1 ~ A-11.7 전체 통과
[ ] H-11.1 패키지 서명 방식 결정 ← 🔴 필수
[ ] H-11.2 호스팅 방식 결정 ← 🔴 필수
[ ] H-11.3 심사 정책 결정 ← 🔴 필수
[ ] H-11.4 CONTRIBUTING.md 작성
[ ] H-11.5 실제 게시/설치 테스트
[ ] v0.11.0 태그 및 배포
```

---

## v1.0.0 최종 릴리즈 검증

### 🤖 자동 검증

| # | 검증 항목 | 실행 명령 | 기대 결과 |
|---|----------|----------|----------|
| A-F.1 | 전체 테스트 | `pytest tests/ -v --timeout=300` | 전체 통과 |
| A-F.2 | 커버리지 | `make test-cov` | 70% 이상 |
| A-F.3 | 보안 감사 | `make security` | bandit + pip-audit 경고 0개 |
| A-F.4 | 린트 | `make lint` | 에러 0개 |
| A-F.5 | Docker 빌드 | `docker build -f docker/Dockerfile .` | 성공 |
| A-F.6 | Docker Compose 풀스택 | `docker compose up -d && sleep 60 && curl localhost:8080/health` | `{"status":"ok"}` |
| A-F.7 | E2E (CLI) | `pytest tests/e2e/test_full_flow.py -v -m e2e` | 통과 |
| A-F.8 | E2E (Web) | `pytest tests/e2e/test_web_ui.py -v -m e2e` | 통과 |
| A-F.9 | 의존성 라이선스 | `pip-licenses --format=table --with-urls` | GPL 없음 확인 |

### 🧑 사람 검증

| # | 확인 항목 | 설명 | 긴급도 |
|---|----------|------|--------|
| H-F.1 | 신규 사용자 체험 테스트 | JediSOS를 **처음 보는 사람**에게 README만 보고 설치 → 사용하게 해보기. 막히는 부분이 없는지 확인 | 🔴 필수 |
| H-F.2 | 문서 완성도 확인 | README.md, CONTRIBUTING.md, 튜토리얼이 모두 작성되어 있는지 | 🔴 필수 |
| H-F.3 | VPS 배포 테스트 | 로컬이 아닌 실제 VPS(Hetzner, Oracle 등)에서 `docker compose up`으로 배포 후 동작 확인 | 🔴 필수 |
| H-F.4 | 장시간 안정성 테스트 | 24시간 이상 운영하면서 메모리 누수, 크래시, 연결 끊김 등 확인 | 🟡 권장 |
| H-F.5 | 비용 최종 확인 | 하루 평균 사용 기준 LLM API 비용이 예상 범위 내인지 확인 | 🟡 권장 |
| H-F.6 | 보안 최종 리뷰 | 전체 코드를 한번 훑어보면서 하드코딩된 비밀, 노출된 포트, 취약한 설정 등 확인 | 🟡 권장 |
| H-F.7 | 릴리즈 노트 작성 | GitHub Release에 올릴 변경 사항 요약 작성 | 🔴 필수 |

### 📋 완료 체크리스트

```
[ ] A-F.1 ~ A-F.9 전체 통과
[ ] H-F.1 신규 사용자 체험 ← 🔴 필수
[ ] H-F.2 문서 완성 ← 🔴 필수
[ ] H-F.3 VPS 배포 확인 ← 🔴 필수
[ ] H-F.7 릴리즈 노트 작성 ← 🔴 필수
[ ] v1.0.0 태그 생성 및 3채널 배포
```

---

## 요약: Phase별 필수(🔴) 사람 결정 사항

전체 개발 과정에서 **사람이 반드시 결정해야 하는 항목**만 모아서 정리합니다.

| Phase | 필수 결정 | 설명 |
|-------|----------|------|
| 1 | H-1.1 | GitHub 리포 생성 |
| 5 | H-5.1 | OAuth 토큰 관리 방식 |
| 5 | H-5.2 | API 키 저장 방식 |
| 6 | H-6.1 | Skill 실행 승인 정책 (A/B/C) |
| 6 | H-6.2 | Skill 네트워크 정책 |
| 7 | H-7.2 | 봇 토큰 발급 |
| 8 | H-8.1 | PyPI 이름 선점 |
| 8 | H-8.2 | ghcr.io 이미지 이름 |
| 8 | H-8.3 | 도메인 설정 |
| 8 | H-8.4 | CI/CD 시크릿 |
| 8 | H-8.8 | 알파 배포 확인 |
| 10 | H-10.1 | Skill 승인 정책 구현 확인 |
| 10 | H-10.2 | pip install 허용 여부 |
| 11 | H-11.1 | 패키지 서명 방식 |
| 11 | H-11.2 | 호스팅 방식 |
| 11 | H-11.3 | 심사 정책 |
| Final | H-F.1 | 신규 사용자 체험 |
| Final | H-F.2 | 문서 완성 |
| Final | H-F.3 | VPS 배포 |
| Final | H-F.7 | 릴리즈 노트 |
