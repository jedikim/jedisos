# JediSOS 데이터베이스 구조

> 2026-02-17 기준. JediSOS는 단일 PostgreSQL 18 + pgvector 인스턴스에 **3개 스키마**를 사용합니다.
> 외부 라이브러리(Hindsight, LangGraph)가 관리하는 테이블과 JediSOS 자체 테이블을 구분합니다.
>
> **확정 결정:** Hindsight가 PostgreSQL + pgvector에 강결합되어 있으므로 (asyncpg raw SQL, pgvector `<=>` 연산자,
> Alembic 마이그레이션 등 교체 불가), 전체 프로젝트를 **PostgreSQL 단일 구성**으로 통일합니다.
> SQLite, zvec 등 대안은 검토 완료 후 제외되었습니다.

---

## 1. 전체 구조 개요

```mermaid
graph TB
    subgraph "PostgreSQL 18 + pgvector"
        subgraph "hindsight 스키마<br/>(Hindsight 관리 — 직접 수정 금지)"
            H_BANKS[banks]
            H_MEM[memory_units]
            H_DOC[documents]
            H_ENT[entities]
            H_ELINK[entity_links]
            H_MIG[alembic_version]
        end

        subgraph "langgraph 스키마<br/>(LangGraph 관리 — 직접 수정 금지)"
            LG_CP[checkpoints]
            LG_BLOB[checkpoint_blobs]
            LG_WRITE[checkpoint_writes]
            LG_MIG[checkpoint_migrations]
        end

        subgraph "jedisos 스키마<br/>(JediSOS 자체 관리)"
            JS_TOOL[installed_tools]
            JS_MCP[mcp_servers]
            JS_AUDIT[audit_logs]
            JS_COST[cost_tracking]
            JS_PREF[user_preferences]
            JS_SCHED[schedules]
            JS_PKG[marketplace_packages]
            JS_MIG[schema_migrations]
        end
    end

    style H_BANKS fill:#e8f5e9
    style H_MEM fill:#e8f5e9
    style LG_CP fill:#e1f5fe
    style LG_BLOB fill:#e1f5fe
    style JS_TOOL fill:#f3e5f5
    style JS_AUDIT fill:#f3e5f5
```

### 데이터베이스 연결 문자열

```
# 개발
postgresql://hindsight:hindsight_dev@localhost:5432/hindsight

# 프로덕션
postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
```

### 스키마 분리

```sql
-- Hindsight가 자동 생성 (HINDSIGHT_API_DATABASE_SCHEMA 환경변수)
CREATE SCHEMA IF NOT EXISTS hindsight;

-- LangGraph checkpoint setup()이 자동 생성
CREATE SCHEMA IF NOT EXISTS langgraph;

-- JediSOS 마이그레이션이 생성
CREATE SCHEMA IF NOT EXISTS jedisos;
```

### Hindsight + LangGraph 공존 전략

세 시스템(Hindsight, LangGraph, JediSOS)이 같은 PostgreSQL 인스턴스를 공유하므로 아래 규칙을 따릅니다.

**1) 스키마 격리 (필수)**

| 시스템 | 스키마 | 환경변수 |
|--------|--------|----------|
| Hindsight | `hindsight` | `HINDSIGHT_API_DATABASE_SCHEMA=hindsight` |
| LangGraph | `langgraph` | PostgresSaver `schema="langgraph"` 파라미터 |
| JediSOS | `jedisos` | `JEDISOS_DB_SCHEMA=jedisos` |

**2) 커넥션 풀 분리 (필수)**

```python
# Hindsight: 자체 asyncpg 풀 (memory_engine.py 내부)
# → Hindsight 서버 프로세스가 관리. JediSOS가 개입하지 않음.

# LangGraph: AsyncPostgresSaver 전용 풀
langgraph_pool = await asyncpg.create_pool(db_url, min_size=2, max_size=10)
checkpointer = AsyncPostgresSaver(langgraph_pool, schema="langgraph")

# JediSOS: SQLAlchemy async 엔진 (자체 테이블용)
jedisos_engine = create_async_engine(db_url, pool_size=5, max_overflow=10)
```

각 시스템이 독립 커넥션 풀을 사용하므로 한쪽의 부하가 다른 쪽을 블로킹하지 않습니다.

**3) 마이그레이션 순서**

```
1. PostgreSQL 시작 → pgvector 확장 활성화
2. Hindsight 서버 시작 → Alembic으로 hindsight 스키마 마이그레이션 (자동)
3. JediSOS 시작 →
   a. LangGraph checkpointer.setup() → langgraph 스키마 테이블 생성
   b. Alembic으로 jedisos 스키마 마이그레이션
```

**4) 충돌 방지 체크리스트**

| 항목 | 조치 |
|------|------|
| 테이블 이름 충돌 | 스키마 분리로 해결 (`hindsight.banks` vs `jedisos.installed_tools`) |
| 인덱스 이름 충돌 | 각 스키마 내에서만 유니크 → 충돌 없음 |
| 시퀀스 충돌 | 각 스키마별 독립 시퀀스 |
| pgvector 확장 | DB 레벨 1회 설치 (`CREATE EXTENSION vector`), 모든 스키마에서 공유 가능 |
| 커넥션 수 한계 | `max_connections=200` (기본 100은 부족할 수 있음) — docker-compose에서 설정 |
| 백업 | `pg_dump` 1회로 전체 3개 스키마 동시 백업 가능 |

---

## 2. Hindsight 스키마 (외부 관리)

> ⚠️ Hindsight 서버가 Alembic 마이그레이션으로 자동 관리합니다.
> JediSOS는 이 테이블을 **직접 읽거나 쓰지 않습니다** — 반드시 Hindsight REST API를 통해 접근합니다.

### 2-1. 테이블 목록 (소스코드 기반, 7개 테이블)

| 테이블 | 역할 | 주요 컬럼 | JediSOS 접근 |
|--------|------|----------|-------------|
| `banks` | 메모리 뱅크 | `bank_id`, `disposition` (JSONB: skepticism/literalism/empathy 1-5), `background` | REST API |
| `memory_units` | 개별 기억 (**벡터 + 그래프 노드**) | `id`, `text`, `embedding` (Vector), `fact_type` (world/bank/opinion/observation), `confidence_score` | REST API |
| `documents` | 원본 문서/대화 | `id`, `bank_id`, `original_text`, `content_hash` | REST API |
| `entities` | 추출된 엔티티 | `id`, `canonical_name`, `bank_id`, `mention_count` | REST API |
| `unit_entities` | 기억↔엔티티 매핑 | `unit_id` (FK), `entity_id` (FK) | REST API |
| `entity_cooccurrences` | 엔티티 동시 출현 관계 | `entity_id_1`, `entity_id_2`, `cooccurrence_count` | REST API |
| `memory_links` | **기억 간 그래프 엣지** | `from_unit_id`, `to_unit_id`, `link_type` (temporal/semantic/entity/causes/caused_by/enables/prevents), `weight`, `entity_id` | REST API |
| `alembic_version` | 마이그레이션 추적 | `version_num` | 접근 불필요 |

### 2-2. Hindsight의 내장 그래프 구조

Hindsight는 **별도 그래프 DB 없이 PostgreSQL 테이블로 그래프를 구현**합니다:

```
Bank (뱅크)
  ├── memory_units (노드 — 벡터 임베딩 + fact_type)
  │     ├── embedding (pgvector, 384차원 기본)
  │     ├── unit_entities → entities (엔티티 연결)
  │     └── memory_links → memory_units (그래프 엣지)
  │           ├── temporal (시간 관계)
  │           ├── semantic (의미 관계)
  │           ├── entity (엔티티 공유)
  │           ├── causes / caused_by (인과 관계)
  │           └── enables / prevents (영향 관계)
  ├── entities (엔티티 노드)
  │     └── entity_cooccurrences (엔티티 간 동시 출현)
  └── documents (원본 문서)
```

**그래프 검색 알고리즘 (Hindsight 내장):**

| 알고리즘 | 파일 | 방식 |
|----------|------|------|
| **BFS + Spreading Activation** | `graph_retrieval.py` | 벡터 시드 → memory_links 순회 → 활성값 전파 (decay=0.8, 인과 관계 2x 부스트) |
| **Link Expansion** | `link_expansion_retrieval.py` | 벡터 시드 → 1-hop 엔티티/인과 확장 → <100ms |
| **Fusion** | `fusion.py` | 벡터(semantic) + BM25(keyword) + 그래프(link) 점수 융합 |
| **MPFP Retrieval** | `mpfp_retrieval.py` | Multi-Path Fact Propagation (다경로 전파) |

> **결론: 별도 그래프 DB(Neo4j 등)가 불필요합니다.**
> Hindsight가 이미 `memory_links` 테이블로 7종의 typed edge를 가진 그래프를 구현하고,
> BFS spreading activation + link expansion으로 그래프 순회를 수행합니다.
> Neo4j를 추가하면 데이터 동기화 복잡도만 증가하고, Hindsight의 REST API를 우회해야 합니다.

- **Bank**: JediSOS는 사용자별로 1개의 bank를 생성 (`bank_id = "jedisos-{user_id}"`)
- **4-네트워크 모델**: World(객관적 사실), Bank(경험), Opinion(주관적 판단), Observation(엔티티 요약)는 `memory_units.fact_type`으로 구분
- **임베딩 차원**: `HINDSIGHT_API_EMBEDDING_MODEL` 설정에 따라 자동 결정 (기본 384, OpenAI 1536)
- **그래프 깊이**: BFS는 activation이 `min_activation`(기본 0.1) 이하가 될 때까지 순회, Link Expansion은 1-hop

### 2-3. JediSOS에서의 사용

```python
# [JS-B001] Hindsight 클라이언트 래퍼 — REST API만 사용
class HindsightClient:
    async def retain(self, content: str, bank_id: str) -> dict:
        """POST /v1/default/banks/{bank_id}/memories"""

    async def recall(self, query: str, bank_id: str) -> list[dict]:
        """POST /v1/default/banks/{bank_id}/reflect"""

    async def get_entities(self, bank_id: str) -> list[dict]:
        """GET /v1/default/banks/{bank_id}/entities"""
```

---

## 3. LangGraph 스키마 (외부 관리)

> ⚠️ `langgraph-checkpoint-postgres`의 `setup()` 메서드가 자동 생성합니다.
> JediSOS는 이 테이블을 **직접 읽거나 쓰지 않습니다** — LangGraph API를 통해 접근합니다.

### 3-1. 테이블 목록

| 테이블 | 역할 | 주요 컬럼 |
|--------|------|----------|
| `checkpoints` | 에이전트 상태 스냅샷 | `thread_id`, `checkpoint_id`, `parent_checkpoint_id`, `checkpoint` (JSONB), `metadata` (JSONB) |
| `checkpoint_blobs` | 대용량 상태 데이터 (메시지 목록 등) | `thread_id`, `checkpoint_ns`, `channel`, `type`, `blob` (BYTEA) |
| `checkpoint_writes` | 도구 실행 중간 결과 (임시) | `thread_id`, `checkpoint_id`, `task_id`, `idx`, `channel`, `type`, `blob` |
| `checkpoint_migrations` | 스키마 버전 추적 | `v` (INTEGER) |

### 3-2. 핵심 개념

```
Thread (대화 스레드)
  ├── Checkpoint (상태 스냅샷)
  │     ├── AgentState.messages (대화 메시지 목록)
  │     ├── AgentState.memory_context (Hindsight에서 가져온 기억)
  │     ├── AgentState.bank_id (사용자 메모리 뱅크)
  │     └── AgentState.tool_call_count (도구 호출 횟수)
  └── Checkpoint Writes (중간 결과)
```

- **thread_id**: 대화별 고유 ID. JediSOS는 `thread_id = "jedisos-{session_id}"` 형식 사용
- **checkpoint_ns**: 네임스페이스 (기본값 "")
- 프로덕션에서는 `AsyncPostgresSaver` 사용 필수 (`autocommit=True`, `row_factory=dict_row`)

### 3-3. JediSOS에서의 사용

```python
# [JS-E001] ReAct 에이전트 — LangGraph API로만 접근
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async with AsyncPostgresSaver.from_conn_string(db_url) as checkpointer:
    await checkpointer.setup()  # 테이블 자동 생성
    graph = builder.compile(checkpointer=checkpointer)

    # 대화 실행 — LangGraph가 내부적으로 checkpoint 관리
    result = await graph.ainvoke(
        initial_state,
        config={"configurable": {"thread_id": f"jedisos-{session_id}"}}
    )
```

---

## 4. JediSOS 스키마 (자체 관리)

> JediSOS가 직접 관리하는 테이블입니다. Alembic 마이그레이션으로 스키마를 관리합니다.

### 4-1. installed_tools — 설치된 도구 레지스트리

Tier 1 Skill과 Tier 2 MCP 서버를 통합 관리합니다.

```sql
CREATE TABLE jedisos.installed_tools (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL UNIQUE,  -- "@jedisos/weather"
    tier            SMALLINT NOT NULL DEFAULT 1,    -- 1: Skill, 2: MCP Server
    version         VARCHAR(50) NOT NULL,           -- "1.0.0"
    description     TEXT,
    author          VARCHAR(255),

    -- Tier 1: Skill 정보
    tool_path       VARCHAR(512),                   -- "tools/weather/tool.py"
    tool_yaml_path  VARCHAR(512),                   -- "tools/weather/tool.yaml"

    -- Tier 2: MCP Server 정보
    docker_image    VARCHAR(512),                   -- "ghcr.io/..."
    mcp_endpoint    VARCHAR(512),                   -- "http://localhost:3001"

    -- 메타데이터
    source          VARCHAR(50) NOT NULL DEFAULT 'manual',  -- manual | forge | marketplace
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    tags            JSONB DEFAULT '[]',
    env_required    JSONB DEFAULT '[]',             -- 필요한 환경변수 목록

    installed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tools_tier ON jedisos.installed_tools(tier);
CREATE INDEX idx_tools_source ON jedisos.installed_tools(source);
CREATE INDEX idx_tools_enabled ON jedisos.installed_tools(enabled);
```

### 4-2. mcp_servers — MCP 서버 설정

Tier 2 MCP 서버의 Docker 컨테이너 설정을 관리합니다.

```sql
CREATE TABLE jedisos.mcp_servers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tool_id         UUID NOT NULL REFERENCES jedisos.installed_tools(id) ON DELETE CASCADE,
    server_name     VARCHAR(255) NOT NULL UNIQUE,   -- "google-calendar"

    -- Docker 설정
    docker_image    VARCHAR(512) NOT NULL,
    container_name  VARCHAR(255),
    port            INTEGER,

    -- OAuth 설정
    oauth_provider  VARCHAR(100),                   -- "google" | "github" | "notion"
    oauth_scopes    JSONB DEFAULT '[]',
    auth_proxy_url  VARCHAR(512),                   -- "http://mcp-auth-proxy:3000"

    -- 상태
    status          VARCHAR(50) NOT NULL DEFAULT 'stopped',  -- stopped | starting | running | error
    last_health_check TIMESTAMPTZ,
    error_message   TEXT,

    -- 환경변수 (암호화된 값)
    env_encrypted   BYTEA,                          -- Fernet 암호화

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 4-3. audit_logs — 감사 로그

보안 이벤트, 도구 실행, 정책 결정을 기록합니다.

```sql
CREATE TABLE jedisos.audit_logs (
    id              BIGSERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 이벤트 정보
    event_type      VARCHAR(100) NOT NULL,          -- "tool_executed" | "policy_denied" | "skill_created" | "login" | ...
    severity        VARCHAR(20) NOT NULL DEFAULT 'info',  -- debug | info | warning | error | critical

    -- 컨텍스트
    user_id         VARCHAR(255),
    channel         VARCHAR(50),                    -- "web" | "telegram" | "discord" | "slack" | "cli"
    session_id      VARCHAR(255),

    -- 상세 내용
    tool_name       VARCHAR(255),
    action          VARCHAR(255),
    result          VARCHAR(50),                    -- "success" | "denied" | "error"
    details         JSONB DEFAULT '{}',

    -- 보안
    ip_address      INET,
    envelope_id     UUID                            -- 관련 Envelope ID
);

CREATE INDEX idx_audit_timestamp ON jedisos.audit_logs(timestamp DESC);
CREATE INDEX idx_audit_event_type ON jedisos.audit_logs(event_type);
CREATE INDEX idx_audit_user ON jedisos.audit_logs(user_id);
CREATE INDEX idx_audit_severity ON jedisos.audit_logs(severity) WHERE severity IN ('warning', 'error', 'critical');

-- 30일 이상 된 debug/info 로그 자동 삭제 (선택사항)
-- CREATE POLICY audit_retention ...
```

### 4-4. cost_tracking — LLM 비용 추적

LiteLLM의 `success_callback`으로 수집한 비용 데이터를 저장합니다.

```sql
CREATE TABLE jedisos.cost_tracking (
    id              BIGSERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- LLM 호출 정보
    model           VARCHAR(255) NOT NULL,          -- "claude-sonnet-5-20260203"
    provider        VARCHAR(100) NOT NULL,          -- "anthropic" | "openai" | "google"

    -- 토큰 사용량
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    total_tokens    INTEGER NOT NULL DEFAULT 0,

    -- 비용 (USD)
    cost_usd        DECIMAL(10,6) NOT NULL DEFAULT 0,

    -- 컨텍스트
    source          VARCHAR(50) NOT NULL,           -- "agent" | "hindsight" | "forge"
    session_id      VARCHAR(255),
    user_id         VARCHAR(255),

    -- 응답 메타
    latency_ms      INTEGER,
    status          VARCHAR(20) NOT NULL DEFAULT 'success'  -- "success" | "error" | "timeout"
);

CREATE INDEX idx_cost_timestamp ON jedisos.cost_tracking(timestamp DESC);
CREATE INDEX idx_cost_model ON jedisos.cost_tracking(model);
CREATE INDEX idx_cost_source ON jedisos.cost_tracking(source);
CREATE INDEX idx_cost_user ON jedisos.cost_tracking(user_id);

-- 일별 비용 집계 뷰
CREATE VIEW jedisos.daily_cost_summary AS
SELECT
    DATE(timestamp) AS date,
    user_id,
    source,
    model,
    COUNT(*) AS call_count,
    SUM(input_tokens) AS total_input_tokens,
    SUM(output_tokens) AS total_output_tokens,
    SUM(cost_usd) AS total_cost_usd,
    AVG(latency_ms) AS avg_latency_ms
FROM jedisos.cost_tracking
GROUP BY DATE(timestamp), user_id, source, model;
```

### 4-5. user_preferences — 사용자 설정

Web UI와 CLI에서 설정한 사용자 환경 설정을 저장합니다.

```sql
CREATE TABLE jedisos.user_preferences (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         VARCHAR(255) NOT NULL UNIQUE,

    -- LLM 설정
    primary_model   VARCHAR(255) DEFAULT 'claude-sonnet-5-20260203',
    fallback_models JSONB DEFAULT '[]',
    temperature     DECIMAL(3,2) DEFAULT 0.7,
    max_tokens      INTEGER DEFAULT 8192,

    -- 비용 제한
    daily_budget_usd    DECIMAL(10,2),              -- NULL = 무제한
    monthly_budget_usd  DECIMAL(10,2),              -- NULL = 무제한

    -- 보안 설정
    auto_approve_skills BOOLEAN DEFAULT FALSE,      -- Forge 생성 Skill 자동 승인
    allowed_tools       JSONB DEFAULT '[]',         -- 빈 = 모두 허용
    blocked_tools       JSONB DEFAULT '["shell_exec", "file_delete"]',

    -- 알림 설정
    notification_channels JSONB DEFAULT '{}',       -- {"telegram": true, "email": false}

    -- 정체성
    identity_file   VARCHAR(512),                   -- IDENTITY.md 경로
    bank_id         VARCHAR(255),                   -- Hindsight 메모리 뱅크 ID

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 4-6. schedules — 예약 작업

cron 기반 자동 실행 작업을 관리합니다.

```sql
CREATE TABLE jedisos.schedules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         VARCHAR(255) NOT NULL,

    name            VARCHAR(255) NOT NULL,          -- "아침 브리핑"
    cron_expr       VARCHAR(100) NOT NULL,          -- "0 8 * * *"

    -- 실행 내용
    action_type     VARCHAR(50) NOT NULL,           -- "chat" | "tool" | "workflow"
    action_payload  JSONB NOT NULL,                 -- {"message": "오늘 일정 알려줘"}

    -- 상태
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    last_run        TIMESTAMPTZ,
    next_run        TIMESTAMPTZ,
    last_result     VARCHAR(50),                    -- "success" | "error"
    last_error      TEXT,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_schedules_next_run ON jedisos.schedules(next_run) WHERE enabled = TRUE;
CREATE INDEX idx_schedules_user ON jedisos.schedules(user_id);
```

### 4-7. marketplace_packages — 마켓플레이스 캐시

마켓플레이스에서 검색/설치한 패키지 메타데이터를 로컬 캐시합니다.
(마켓플레이스 레지스트리 서버의 원본 DB와는 별도)

```sql
CREATE TABLE jedisos.marketplace_packages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    package_name    VARCHAR(255) NOT NULL UNIQUE,   -- "@jedisos/weather"
    package_type    VARCHAR(50) NOT NULL,           -- "skill" | "mcp_server" | "prompt" | "workflow" | "identity" | "bundle"

    -- 메타데이터 (레지스트리에서 가져옴)
    latest_version  VARCHAR(50),
    description     TEXT,
    author          VARCHAR(255),
    license         VARCHAR(100),
    tags            JSONB DEFAULT '[]',
    download_count  INTEGER DEFAULT 0,
    rating          DECIMAL(3,2),

    -- 로컬 상태
    installed_version VARCHAR(50),                  -- NULL = 미설치
    installed_tool_id UUID REFERENCES jedisos.installed_tools(id),

    -- 캐시
    last_synced     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    registry_data   JSONB                           -- 원본 레지스트리 응답 캐시
);

CREATE INDEX idx_packages_type ON jedisos.marketplace_packages(package_type);
CREATE INDEX idx_packages_installed ON jedisos.marketplace_packages(installed_version) WHERE installed_version IS NOT NULL;
```

---

## 5. 테이블 관계 다이어그램 (JediSOS 스키마)

```mermaid
erDiagram
    installed_tools ||--o| mcp_servers : "Tier 2만"
    installed_tools ||--o| marketplace_packages : "설치된 경우"
    user_preferences ||--o{ schedules : "사용자별"
    installed_tools ||--o{ audit_logs : "도구 실행 시"
    cost_tracking }o--|| user_preferences : "사용자별 비용"

    installed_tools {
        uuid id PK
        varchar name UK
        smallint tier
        varchar version
        varchar tool_path
        varchar docker_image
        varchar source
        boolean enabled
        jsonb tags
    }

    mcp_servers {
        uuid id PK
        uuid tool_id FK
        varchar server_name UK
        varchar docker_image
        varchar oauth_provider
        varchar status
    }

    audit_logs {
        bigserial id PK
        timestamptz timestamp
        varchar event_type
        varchar severity
        varchar user_id
        varchar tool_name
        jsonb details
    }

    cost_tracking {
        bigserial id PK
        timestamptz timestamp
        varchar model
        integer input_tokens
        integer output_tokens
        decimal cost_usd
        varchar source
    }

    user_preferences {
        uuid id PK
        varchar user_id UK
        varchar primary_model
        decimal daily_budget_usd
        boolean auto_approve_skills
    }

    schedules {
        uuid id PK
        varchar user_id
        varchar name
        varchar cron_expr
        varchar action_type
        jsonb action_payload
        boolean enabled
    }

    marketplace_packages {
        uuid id PK
        varchar package_name UK
        varchar package_type
        varchar installed_version
        uuid installed_tool_id FK
    }
```

---

## 6. 마이그레이션 전략

### Alembic 설정

```
src/jedisos/
  alembic/
    env.py
    versions/
      001_initial_schema.py          # installed_tools, audit_logs
      002_add_cost_tracking.py       # cost_tracking + daily_cost_summary 뷰
      003_add_user_preferences.py    # user_preferences
      004_add_schedules.py           # schedules
      005_add_marketplace.py         # marketplace_packages
      006_add_mcp_servers.py         # mcp_servers
    alembic.ini
```

### 마이그레이션 실행

```bash
# 자동 실행 (JediSOS 시작 시)
jedisos db upgrade

# 수동 실행
alembic -c src/jedisos/alembic/alembic.ini upgrade head

# 새 마이그레이션 생성
alembic -c src/jedisos/alembic/alembic.ini revision --autogenerate -m "add_new_table"
```

### Phase별 테이블 생성 순서

| Phase | 생성되는 테이블 | 마이그레이션 |
|-------|---------------|-------------|
| Phase 1 | (없음 — 스키마 인프라만) | `alembic init` |
| Phase 4 | `audit_logs` | 001 |
| Phase 5 | `installed_tools`, `mcp_servers` | 001, 006 |
| Phase 6 | `audit_logs` 확장 (보안 이벤트) | 001 |
| Phase 7 | (없음 — 채널은 stateless) | — |
| Phase 8 | `user_preferences`, `schedules` | 003, 004 |
| Phase 9 | `cost_tracking` | 002 |
| Phase 10 | `installed_tools`에 forge 도구 추가 | (테이블 변경 없음) |
| Phase 11 | `marketplace_packages` | 005 |

---

## 7. 데이터 볼륨 추정

| 테이블 | 예상 레코드/월 (활발 사용자 1명) | 디스크 사용 |
|--------|------------------------------|-----------|
| Hindsight memory_units | ~600 (하루 20회 대화) | ~50MB |
| LangGraph checkpoints | ~600 (대화당 1개) | ~30MB |
| audit_logs | ~3,000 | ~10MB |
| cost_tracking | ~6,000 | ~5MB |
| installed_tools | ~50 (누적) | <1MB |
| schedules | ~10 (누적) | <1MB |
| marketplace_packages | ~100 (캐시) | <1MB |

**총 예상**: 활발 사용자 1명 기준, 월 ~100MB 증가. 1년 후 ~1.2GB.

### 데이터 보존 정책 (권장)

```sql
-- audit_logs: 90일 이상 된 debug/info 삭제
DELETE FROM jedisos.audit_logs
WHERE timestamp < NOW() - INTERVAL '90 days'
  AND severity IN ('debug', 'info');

-- cost_tracking: 365일 이상 된 상세 삭제 (daily_cost_summary 뷰는 유지)
DELETE FROM jedisos.cost_tracking
WHERE timestamp < NOW() - INTERVAL '365 days';

-- LangGraph checkpoints: thread 종료 후 30일 이상 된 것 정리
-- (LangGraph API를 통해 처리)
```

---

## 8. 환경변수

```bash
# PostgreSQL 연결 (전체 공유)
POSTGRES_USER=jedisos
POSTGRES_PASSWORD=changeme
POSTGRES_DB=hindsight
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Hindsight 전용
HINDSIGHT_API_DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}
HINDSIGHT_API_DATABASE_SCHEMA=hindsight

# LangGraph 체크포인트 전용
LANGGRAPH_DB_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}

# JediSOS 자체
JEDISOS_DB_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}
JEDISOS_DB_SCHEMA=jedisos

# MCP Auth Proxy 전용 (별도 DB 또는 같은 DB 다른 스키마)
MCP_AUTH_DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}
```

---

## 9. 백업 전략

```bash
# 전체 데이터베이스 백업 (모든 스키마 포함)
pg_dump -U ${POSTGRES_USER} -h ${POSTGRES_HOST} ${POSTGRES_DB} > backup_$(date +%Y%m%d).sql

# JediSOS 스키마만 백업
pg_dump -U ${POSTGRES_USER} -h ${POSTGRES_HOST} -n jedisos ${POSTGRES_DB} > jedisos_backup_$(date +%Y%m%d).sql

# Hindsight 메모리만 백업
pg_dump -U ${POSTGRES_USER} -h ${POSTGRES_HOST} -n hindsight ${POSTGRES_DB} > hindsight_backup_$(date +%Y%m%d).sql
```

---

## 10. 개발 참고

### 테이블 접근 규칙

| 스키마 | JediSOS 코드에서 접근 | 접근 방식 |
|--------|---------------------|----------|
| `hindsight` | ❌ 직접 SQL 금지 | Hindsight REST API (`httpx`) |
| `langgraph` | ❌ 직접 SQL 금지 | LangGraph Python API (`AsyncPostgresSaver`) |
| `jedisos` | ✅ 직접 SQL 가능 | SQLAlchemy 또는 asyncpg |

### ORM 선택

JediSOS 자체 테이블은 **SQLAlchemy 2.0 + asyncpg** 조합을 사용합니다:

```python
# [JS-A005] 데이터베이스 연결 관리 (향후 추가)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase

engine = create_async_engine(
    "postgresql+asyncpg://user:pass@localhost/hindsight",
    echo=False,
    pool_size=5,
    max_overflow=10,
)

class Base(DeclarativeBase):
    pass
```

### 새 의존성 (pyproject.toml에 추가 필요)

```
sqlalchemy[asyncio]>=2.0.38
asyncpg>=0.30.0
alembic>=1.15.2
```
