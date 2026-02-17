# JediSOS 릴리즈 방법론

> 오픈소스 배포 전략, 버전 관리, 빌드, 릴리즈 프로세스를 정의합니다.
> JediSOS는 누구나 설치해서 쓸 수 있는 오픈소스 개인 AI 비서입니다.

## 1. 배포 전략 개요

### 배포 철학

**"docker compose up 한 방이면 끝"** — 개발자든 일반 사용자든 최종 설치 경험은 동일합니다.

```mermaid
flowchart TB
    subgraph "배포 채널 (3개)"
        GHCR["1. Docker 이미지<br/>ghcr.io/jedikim/jedisos<br/><b>메인 배포 채널</b>"]
        PYPI["2. PyPI 패키지<br/>pip install jedisos<br/>CLI + 라이브러리"]
        SCRIPT["3. 설치 스크립트<br/>curl -sSL get.jedisos.com | bash<br/>일반 사용자용"]
    end

    subgraph "사용자 유형"
        DEV["개발자<br/>git clone + docker compose up"]
        POWER["파워유저<br/>pip install + docker compose up"]
        GENERAL["일반 사용자<br/>curl 설치 스크립트"]
    end

    DEV --> GHCR
    POWER --> PYPI
    GENERAL --> SCRIPT
    SCRIPT --> GHCR

    style GHCR fill:#e1f5fe
    style PYPI fill:#e8f5e9
    style SCRIPT fill:#fff3e0
```

### 타겟 사용자별 설치 경험

| 사용자 | 설치 방법 | 설정 방법 | 난이도 |
|--------|-----------|-----------|--------|
| 개발자 | `git clone` → `.env` 편집 → `docker compose up -d` | `.env` + `llm_config.yaml` 직접 편집 | 쉬움 |
| 파워유저 | `pip install jedisos` → `jedisos init` | CLI 대화형 설정 | 보통 |
| 일반 사용자 | `curl -sSL https://get.jedisos.com \| bash` | 웹 UI Setup Wizard (브라우저) | 매우 쉬움 |

### 실행 환경

동일한 `docker-compose.yml`이 로컬과 VPS에서 모두 작동합니다.

| 환경 | 장점 | 단점 | 추천 |
|------|------|------|------|
| 로컬 (PC/Mac) | 비용 $0, 로컬 파일 접근 용이 | PC 꺼지면 중단 | 개발/테스트, 가벼운 사용 |
| VPS (Hetzner/Oracle) | 24시간 운영, 외부 접근 가능 | 월 $5~$10 | 상시 운영, 채널봇 연동 |

## 2. 버전 관리 전략

### Semantic Versioning (SemVer)

```
MAJOR.MINOR.PATCH
  │      │     └─ 버그 수정 (하위 호환)
  │      └─── 기능 추가 (하위 호환)
  └──────── 브레이킹 체인지
```

| 버전 | Phase | 의미 | 비고 |
|------|-------|------|------|
| 0.1.0 | Phase 1 | 기반 (Envelope + Config) | 내부 개발 |
| 0.2.0 | Phase 2 | 메모리 (Hindsight 연동) | 내부 개발 |
| 0.3.0 | Phase 3 | LLM (LiteLLM 라우터) | 내부 개발 |
| 0.4.0 | Phase 4 | 에이전트 (LangGraph ReAct) | 내부 개발 |
| 0.5.0 | Phase 5 | MCP (FastMCP 도구) | 내부 개발 |
| 0.6.0 | Phase 6 | 보안 (PDP + 감사) | 내부 개발 |
| 0.7.0 | Phase 7 | 채널 (텔레그램/디스코드/슬랙) | 내부 개발 |
| 0.8.0 | Phase 8 | CLI + 릴리즈 파이프라인 | **첫 공개 alpha** |
| 0.9.0 | Phase 9 | 웹 UI (대시보드 + Setup Wizard) | **공개 beta** |
| 0.10.0 | Phase 10 | Forge (자가 코딩 — 2-Tier 경량) | **자가 진화** |
| 0.11.0 | Phase 11 | Marketplace (패키지 레지스트리) | **마켓플레이스** |
| 1.0.0 | — | 첫 정식 릴리즈 | 안정화 + 문서화 완료 |

### 공개 시점

- **v0.8.0 (alpha)**: 개발자 대상. CLI로 작동, Docker Compose로 배포. README + CONTRIBUTING.md 필요.
- **v0.9.0 (beta)**: 일반 사용자 대상. 웹 UI + Setup Wizard + 설치 스크립트 포함.
- **v1.0.0 (stable)**: 프로덕션 사용 가능. 완전한 문서, 튜토리얼, 보안 감사 완료.

### 버전 관리 위치

**단일 소스 (Single Source of Truth):** `src/jedisos/__init__.py`

```python
__version__ = "0.1.0"
```

`pyproject.toml`에서 동적으로 읽기:

```toml
[project]
dynamic = ["version"]

[tool.hatch.version]
path = "src/jedisos/__init__.py"
```

## 3. 브랜치 전략

```mermaid
gitgraph
    commit id: "init"
    branch develop
    checkout develop
    commit id: "Phase 1"
    commit id: "Phase 2"
    checkout main
    merge develop id: "v0.2.0" tag: "v0.2.0"
    checkout develop
    commit id: "Phase 3~7"
    checkout main
    merge develop id: "v0.7.0" tag: "v0.7.0"
    checkout develop
    commit id: "Phase 8: CLI"
    checkout main
    merge develop id: "v0.8.0-alpha" tag: "v0.8.0-alpha"
    checkout develop
    commit id: "Phase 9: Web UI"
    checkout main
    merge develop id: "v0.9.0-beta" tag: "v0.9.0-beta"
    checkout develop
    commit id: "stabilize"
    checkout main
    merge develop id: "v1.0.0" tag: "v1.0.0"
```

| 브랜치 | 용도 | 머지 대상 |
|--------|------|-----------|
| `main` | 릴리즈 브랜치 | 태그 생성 시에만 머지 |
| `develop` | 개발 브랜치 | feature → develop |
| `feature/*` | 기능 브랜치 | develop |
| `fix/*` | 버그 수정 | develop 또는 main (핫픽스) |

### 머지 규칙

1. `feature/*` → `develop`: Squash merge (커밋 정리)
2. `develop` → `main`: Merge commit (이력 보존)
3. 모든 머지에 CI 통과 필수

## 4. 설치 방법 상세

### 4-1. 개발자 설치 (git clone)

```bash
# 1. 저장소 클론
git clone https://github.com/jedikim/jedisos.git
cd jedisos

# 2. 환경변수 설정
cp .env.example .env
# .env 편집: ANTHROPIC_API_KEY, OPENAI_API_KEY 등

# 3. 전체 스택 실행 (Hindsight + PostgreSQL + JediSOS + Web UI)
docker compose up -d

# 4. 확인
open http://localhost:8080   # 웹 UI
jedisos health               # CLI 헬스체크
```

### 4-2. PyPI 설치 (pip)

```bash
# 1. CLI 도구 설치
pip install jedisos
# 또는
pipx install jedisos

# 2. 초기 설정 (대화형)
jedisos init
# → API 키 입력
# → LLM 모델 선택
# → docker-compose.yml 자동 생성
# → docker compose up -d 자동 실행

# 3. 사용
jedisos chat "안녕, 오늘 할 일 알려줘"
open http://localhost:8080   # 웹 UI
```

### 4-3. 일반 사용자 설치 (원클릭 스크립트)

```bash
curl -sSL https://get.jedisos.com | bash
```

**설치 스크립트가 하는 일:**

```mermaid
flowchart TD
    START["curl ... | bash"] --> CHECK_DOCKER{"Docker 설치됨?"}
    CHECK_DOCKER -->|No| INSTALL_DOCKER["Docker Desktop 설치 안내<br/>(OS별 링크 제공)"]
    INSTALL_DOCKER --> ABORT["설치 중단<br/>(Docker 설치 후 재실행 안내)"]
    CHECK_DOCKER -->|Yes| PULL["docker pull ghcr.io/jedikim/jedisos:latest"]
    PULL --> COMPOSE["docker-compose.yml 생성<br/>(~/.jedisos/)"]
    COMPOSE --> UP["docker compose up -d"]
    UP --> WIZARD["브라우저 열기<br/>http://localhost:8080/setup"]

    style START fill:#e8eaf6
    style WIZARD fill:#e8f5e9
    style ABORT fill:#ffebee
```

### 4-4. 설치 스크립트 코드

```bash
#!/bin/bash
# scripts/install.sh
# JediSOS 원클릭 설치 스크립트
set -euo pipefail

JEDISOS_VERSION="${JEDISOS_VERSION:-latest}"
JEDISOS_HOME="${JEDISOS_HOME:-$HOME/.jedisos}"
COMPOSE_URL="https://raw.githubusercontent.com/jedikim/jedisos/main/docker-compose.yml"

echo "🤖 JediSOS 설치를 시작합니다..."

# 1. Docker 확인
if ! command -v docker &> /dev/null; then
    echo "❌ Docker가 설치되어 있지 않습니다."
    echo ""
    echo "Docker Desktop을 먼저 설치해주세요:"
    echo "  macOS: https://docs.docker.com/desktop/install/mac-install/"
    echo "  Windows: https://docs.docker.com/desktop/install/windows-install/"
    echo "  Linux: https://docs.docker.com/engine/install/"
    echo ""
    echo "설치 후 이 스크립트를 다시 실행하세요."
    exit 1
fi

# 2. docker compose 확인
if ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose V2가 필요합니다."
    exit 1
fi

# 3. 디렉토리 생성
mkdir -p "$JEDISOS_HOME"
cd "$JEDISOS_HOME"

# 4. docker-compose.yml 다운로드
echo "📦 설정 파일을 다운로드합니다..."
curl -sSL "$COMPOSE_URL" -o docker-compose.yml

# 5. .env 생성 (비어있는 상태 — Setup Wizard에서 설정)
if [ ! -f .env ]; then
    cat > .env << 'EOF'
# JediSOS 환경변수 — 웹 UI Setup Wizard에서 자동 설정됩니다
JEDISOS_FIRST_RUN=true
EOF
fi

# 6. Docker 이미지 pull + 실행
echo "🐳 Docker 이미지를 다운로드합니다... (최초 1회, 약 2~5분)"
docker compose pull
docker compose up -d

# 7. 헬스체크 대기
echo "⏳ JediSOS를 시작하는 중..."
for i in $(seq 1 30); do
    if curl -s http://localhost:8080/health > /dev/null 2>&1; then
        break
    fi
    sleep 2
done

# 8. 완료
echo ""
echo "✅ JediSOS가 설치되었습니다!"
echo ""
echo "  웹 UI:     http://localhost:8080"
echo "  설정 위치:  $JEDISOS_HOME/"
echo ""
echo "  중지: cd $JEDISOS_HOME && docker compose down"
echo "  시작: cd $JEDISOS_HOME && docker compose up -d"
echo "  업데이트: cd $JEDISOS_HOME && docker compose pull && docker compose up -d"
echo ""

# 9. 브라우저 열기 (가능한 경우)
if command -v open &> /dev/null; then
    open "http://localhost:8080/setup"
elif command -v xdg-open &> /dev/null; then
    xdg-open "http://localhost:8080/setup"
fi
```

### 4-5. 원클릭 배포 버튼 (VPS)

README.md에 포함할 원클릭 배포 버튼:

```markdown
## Deploy

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/jedisos)
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/jedikim/jedisos)
```

Railway/Render용 설정 파일:

```yaml
# railway.toml
[build]
builder = "dockerfile"
dockerfilePath = "docker/Dockerfile"

[deploy]
startCommand = "jedisos serve --host 0.0.0.0 --port $PORT"
healthcheckPath = "/health"
```

## 5. 업데이트 전략

### CLI 업데이트

```bash
# 방법 1: CLI 명령
jedisos update
# → docker compose pull && docker compose up -d 실행

# 방법 2: 수동
cd ~/.jedisos  # 또는 프로젝트 디렉토리
docker compose pull
docker compose up -d
```

### 웹 UI 업데이트 알림

웹 UI에서 새 버전이 있으면 상단에 알림 배너를 표시합니다.
GitHub API (`/repos/jedi/jedisos/releases/latest`)를 주기적으로 체크합니다.

```mermaid
flowchart LR
    CHECK["GitHub API<br/>releases/latest 체크"] --> COMPARE{"현재 버전<br/>< 최신 버전?"}
    COMPARE -->|No| DONE["최신 상태"]
    COMPARE -->|Yes| BANNER["웹 UI 상단<br/>업데이트 알림 배너"]
    BANNER --> CLICK["'업데이트' 클릭"]
    CLICK --> PULL["docker compose pull<br/>docker compose up -d"]
    PULL --> DONE

    style BANNER fill:#fff3e0
    style DONE fill:#e8f5e9
```

## 6. 릴리즈 프로세스

### 6-1. 릴리즈 체크리스트

```markdown
## 릴리즈 체크리스트 v{VERSION}

### 코드 품질
- [ ] 모든 테스트 통과 (`make test-all`)
- [ ] 린트 통과 (`make lint`)
- [ ] 보안 검사 통과 (`make security`)
- [ ] 커버리지 70% 이상 (`make test-cov`)

### 문서
- [ ] CHANGELOG.md 업데이트
- [ ] 추적 해시 문서 생성 (`make tracking`)
- [ ] README.md 설치 가이드 정확성 확인

### 배포
- [ ] 버전 번호 업데이트 (`scripts/bump_version.sh {VERSION}`)
- [ ] develop → main 머지
- [ ] 태그 생성 (`git tag v{VERSION}`)
- [ ] 태그 푸시 (`git push origin v{VERSION}`)

### 검증 (자동)
- [ ] GitHub Actions release.yml 실행 확인
- [ ] Docker 이미지 ghcr.io에 push 확인
- [ ] PyPI 배포 확인
- [ ] GitHub Release 노트 확인

### 수동 검증
- [ ] `docker compose up -d`로 새 이미지 정상 실행
- [ ] 웹 UI http://localhost:8080 접속 확인
- [ ] Setup Wizard 플로우 정상 작동 (v0.9.0+)
- [ ] `pip install jedisos=={VERSION}` 정상 설치
```

### 6-2. 버전 업데이트 스크립트

```bash
#!/bin/bash
# scripts/bump_version.sh
# 사용법: ./scripts/bump_version.sh 0.2.0

set -euo pipefail

NEW_VERSION=$1

if [ -z "$NEW_VERSION" ]; then
    echo "Usage: $0 <version>"
    exit 1
fi

# 1. __init__.py 업데이트
sed -i "s/__version__ = \".*\"/__version__ = \"$NEW_VERSION\"/" src/jedisos/__init__.py

# 2. 확인
echo "Version updated to: $NEW_VERSION"
grep "__version__" src/jedisos/__init__.py

# 3. 커밋
git add src/jedisos/__init__.py
git commit -m "chore: bump version to $NEW_VERSION"

echo "Done. Now run: git tag v$NEW_VERSION && git push origin v$NEW_VERSION"
```

### 6-3. CHANGELOG.md 형식

```markdown
# Changelog

## [0.11.0] - 2026-XX-XX

### Added
- [JS-M001] 마켓플레이스 Registry API 클라이언트
- [JS-M002] 패키지 게시기 (자동 검증 포함)
- [JS-M003] 패키지 검증기 (Bandit + 정적분석 + 라이선스)
- [JS-M004] 패키지 메타데이터 모델 (6종: Skill, MCP, 프롬프트, 워크플로우, 정체성, 번들)
- `jedisos market` CLI 명령어 (search/install/publish/review)
- 웹 UI 마켓플레이스 브라우저 강화
- 검증 배지 시스템 (agent-made, verified, official)

## [0.10.0] - 2026-XX-XX

### Added
- 2-Tier 확장 아키텍처 (Tier 1: Skill 경량 / Tier 2: MCP OAuth용)
- [JS-K001] LLM 기반 Skill 코드 생성기 (tool.yaml + tool.py)
- [JS-K002] 자동 테스트 실행기 (AST 구문/Bandit/금지패턴/타입힌트)
- [JS-K003] @tool 데코레이터 정의
- [JS-K004] 코드 보안 정적분석 (Bandit + 금지 패턴 + import 화이트리스트)
- [JS-K005] importlib 핫로더
- Jinja2 기반 Skill 생성 템플릿
- tools/ 디렉토리 구조 + tools/generated/ (에이전트 자동 생성)
- 에이전트 자가 코딩 루프 (감지 → 생성 → 정적분석 → 핫로드 → 등록)

## [0.9.0-beta] - 2026-XX-XX

### Added
- [JS-W001] FastAPI 웹 대시보드
- [JS-W002] WebSocket 채팅 인터페이스
- [JS-W003] 설정 관리 웹 UI
- [JS-W004] MCP 마켓플레이스 브라우저
- [JS-W005] 상태 모니터링 대시보드
- [JS-W006] Setup Wizard (첫 실행 설정)
- 설치 스크립트 (curl | bash)
- Railway/Render 원클릭 배포 지원

## [0.8.0-alpha] - 2026-XX-XX

### Added
- [JS-H001] Typer CLI 인터페이스
- Docker 이미지 ghcr.io/jedikim/jedisos
- PyPI 패키지 배포
- `jedisos init` 대화형 설정
- 프로덕션 Dockerfile
- GitHub Actions CI/CD 파이프라인

## [0.1.0] - 2026-XX-XX

### Added
- [JS-A001] Envelope 메시지 계약
- [JS-A002] pydantic-settings 설정 관리
- [JS-A003] 커스텀 예외 계층
- [JS-A004] 공통 타입 정의
- [JS-T001] Envelope 단위 테스트
- Docker Compose 개발 환경
- Makefile 개발 명령어
```

## 7. CI/CD 파이프라인

### 7-1. CI (`ci.yml`)

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install ruff
      - run: ruff check src/ tests/
      - run: ruff format --check src/ tests/

  security:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install bandit pip-audit
      - run: bandit -r src/ -c pyproject.toml
      - run: pip install -e ".[dev]" && pip-audit

  test-unit:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: pytest tests/unit/ -v --timeout=30 --cov=jedisos --cov-report=xml
      - uses: codecov/codecov-action@v4
        with:
          file: coverage.xml

  test-integration:
    runs-on: ubuntu-latest
    needs: test-unit
    services:
      postgres:
        image: pgvector/pgvector:pg18
        env:
          POSTGRES_USER: hindsight
          POSTGRES_PASSWORD: test_password
          POSTGRES_DB: hindsight
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Start Hindsight
        run: |
          docker run -d --name hindsight \
            --network host \
            -e HINDSIGHT_API_LLM_API_KEY=${{ secrets.OPENAI_API_KEY }} \
            -e HINDSIGHT_API_DATABASE_URL=postgresql://hindsight:test_password@localhost:5432/hindsight \
            ghcr.io/vectorize-io/hindsight:latest
          sleep 30  # Hindsight 시작 대기
      - run: pip install -e ".[dev]"
      - run: pytest tests/integration/ -v --timeout=120 -m integration
        env:
          HINDSIGHT_API_URL: http://localhost:8888

  # Web UI 빌드 (Phase 9+)
  build-web:
    runs-on: ubuntu-latest
    needs: lint
    defaults:
      run:
        working-directory: web-ui
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: "npm"
          cache-dependency-path: web-ui/package-lock.json
      - run: npm ci
      - run: npm run lint
      - run: npm run build
      - uses: actions/upload-artifact@v4
        with:
          name: web-ui-dist
          path: web-ui/dist/
```

### 7-2. Release (`release.yml`)

```yaml
name: Release

on:
  push:
    tags:
      - "v*"

permissions:
  contents: write
  packages: write

jobs:
  # 1. 테스트 통과 확인
  verify:
    uses: ./.github/workflows/ci.yml

  # 2. 빌드 + 배포
  release:
    runs-on: ubuntu-latest
    needs: verify
    steps:
      - uses: actions/checkout@v4

      # Python 빌드
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Build Python package
        run: |
          pip install build twine
          python -m build

      # Web UI 빌드
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - name: Build Web UI
        run: |
          cd web-ui
          npm ci
          npm run build
          # 빌드 결과를 Python 패키지의 static 디렉토리로 복사
          cp -r dist/ ../src/jedisos/web/static/

      # PyPI 배포
      - name: Publish to PyPI
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_TOKEN }}
        run: twine upload dist/*

      # Docker 멀티 아키텍처 빌드 + push
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push Docker image
        uses: docker/build-push-action@v6
        with:
          context: .
          file: docker/Dockerfile
          push: true
          platforms: linux/amd64,linux/arm64
          tags: |
            ghcr.io/${{ github.repository }}:${{ github.ref_name }}
            ghcr.io/${{ github.repository }}:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max

      # GitHub Release
      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
          files: dist/*
```

> **주요 변경점 vs 이전 버전:**
> - `docker/build-push-action@v6`로 멀티 아키텍처 (amd64 + arm64) 지원
> - Web UI 빌드 단계 추가
> - CI 통과를 release의 선행 조건으로 설정
> - GitHub Actions 캐시 (`type=gha`)로 빌드 속도 개선

## 8. Docker 빌드

### 8-1. 프로덕션 Dockerfile

```dockerfile
# docker/Dockerfile
# --- Stage 1: Web UI 빌드 ---
FROM node:22-slim AS web-builder
WORKDIR /web
COPY web-ui/package*.json ./
RUN npm ci --production=false
COPY web-ui/ ./
RUN npm run build

# --- Stage 2: Python 빌드 ---
FROM python:3.12-slim AS py-builder
WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
# Web UI 빌드 결과 포함
COPY --from=web-builder /web/dist/ src/jedisos/web/static/
RUN pip install --no-cache-dir build && \
    python -m build --wheel && \
    pip install --no-cache-dir dist/*.whl

# --- Stage 3: 프로덕션 ---
FROM python:3.12-slim
WORKDIR /app

COPY --from=py-builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=py-builder /usr/local/bin/jedisos /usr/local/bin/jedisos

# 비-root 사용자
RUN groupadd -r jedisos && useradd -r -g jedisos jedisos
USER jedisos

# 웹 UI 포트
EXPOSE 8080

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

ENTRYPOINT ["jedisos"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8080"]
```

### 8-2. 프로덕션 docker-compose.yml

```yaml
# docker-compose.yml
# 사용법: docker compose up -d
version: "3.9"

services:
  # PostgreSQL + pgvector
  postgres:
    image: pgvector/pgvector:pg18
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-jedisos}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-changeme}
      POSTGRES_DB: ${POSTGRES_DB:-hindsight}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-jedisos}"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Hindsight 메모리 서버
  hindsight:
    image: ghcr.io/vectorize-io/hindsight:latest
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      HINDSIGHT_API_DATABASE_URL: postgresql://${POSTGRES_USER:-jedisos}:${POSTGRES_PASSWORD:-changeme}@postgres:5432/${POSTGRES_DB:-hindsight}
      HINDSIGHT_API_LLM_API_KEY: ${OPENAI_API_KEY:-}
    ports:
      - "${HINDSIGHT_PORT:-8888}:8888"
      - "${HINDSIGHT_UI_PORT:-9999}:9999"

  # JediSOS 메인 앱 (API + Web UI)
  jedisos:
    image: ghcr.io/jedikim/jedisos:${JEDISOS_VERSION:-latest}
    restart: unless-stopped
    depends_on:
      hindsight:
        condition: service_started
    environment:
      HINDSIGHT_API_URL: http://hindsight:8888
      JEDISOS_LLM_CONFIG: /config/llm_config.yaml
      JEDISOS_MCP_CONFIG: /config/mcp_servers.json
    env_file:
      - .env
    ports:
      - "${JEDISOS_PORT:-8080}:8080"
    volumes:
      - ./config:/config:ro
      - jedisos_data:/data

volumes:
  postgres_data:
  jedisos_data:
```

## 9. 오픈소스 운영

### 9-1. 필수 파일 (v0.8.0 공개 전)

| 파일 | 내용 |
|------|------|
| `README.md` | 프로젝트 소개, 스크린샷, 설치 가이드, 배지 |
| `LICENSE` | MIT 라이선스 |
| `CONTRIBUTING.md` | 기여 가이드 (브랜치 규칙, 커밋 컨벤션, PR 템플릿) |
| `CODE_OF_CONDUCT.md` | 행동 강령 (Contributor Covenant) |
| `.github/ISSUE_TEMPLATE/` | 이슈 템플릿 (버그 리포트, 기능 요청) |
| `.github/PULL_REQUEST_TEMPLATE.md` | PR 템플릿 |
| `SECURITY.md` | 보안 취약점 신고 절차 |

### 9-2. README 배지

```markdown
[![CI](https://github.com/jedikim/jedisos/actions/workflows/ci.yml/badge.svg)](https://github.com/jedikim/jedisos/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/jedisos)](https://pypi.org/project/jedisos/)
[![Docker](https://img.shields.io/badge/ghcr.io-jedisos-blue)](https://ghcr.io/jedikim/jedisos)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![codecov](https://codecov.io/gh/jedikim/jedisos/branch/main/graph/badge.svg)](https://codecov.io/gh/jedikim/jedisos)
```

### 9-3. 시크릿 관리

GitHub Secrets에 설정해야 할 값:

| 시크릿 | 용도 | 필수 |
|--------|------|------|
| `PYPI_TOKEN` | PyPI 배포 토큰 | Yes |
| `OPENAI_API_KEY` | CI 통합 테스트용 | Yes |
| `CODECOV_TOKEN` | Codecov 업로드 | No |

> `GITHUB_TOKEN`은 GitHub Actions에서 자동 제공 (ghcr.io push에 사용)

## 10. 릴리즈 흐름 요약

```mermaid
flowchart LR
    DEV["개발 완료"] --> CHECK["체크리스트 확인"]
    CHECK --> BUMP["버전 업데이트<br/>scripts/bump_version.sh"]
    BUMP --> MERGE["develop → main<br/>머지"]
    MERGE --> TAG["git tag v{VERSION}"]
    TAG --> PUSH["git push origin v{VERSION}"]
    PUSH --> CI["GitHub Actions<br/>release.yml"]

    CI --> PYPI["PyPI 배포<br/>pip install jedisos"]
    CI --> DOCKER["Docker 이미지<br/>ghcr.io (amd64+arm64)"]
    CI --> GH["GitHub Release<br/>+ 릴리즈 노트"]
    CI --> SCRIPT["설치 스크립트<br/>자동으로 latest 사용"]

    style DEV fill:#e8eaf6
    style CI fill:#fff3e0
    style PYPI fill:#e8f5e9
    style DOCKER fill:#e1f5fe
    style GH fill:#f3e5f5
    style SCRIPT fill:#fff3e0
```
