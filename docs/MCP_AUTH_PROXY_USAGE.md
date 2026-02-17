# MCP Auth Proxy 사용법 가이드

> JediSOS에서 OAuth 2.1 인증이 필요한 Tier 2 MCP 서버를 사용하는 방법을 정리한 문서
> sigbit/mcp-auth-proxy v1.2.1 기준

---

## 1. 핵심 개념

MCP Auth Proxy는 **기존 MCP 서버 코드 변경 없이 OAuth 2.1 인증을 추가**하는 게이트웨이다.

| 개념 | 설명 | 예시 |
|------|------|------|
| **Auth Proxy** | OAuth 2.1 인증 게이트웨이 | Gmail MCP 앞에 배치 |
| **Tier 2 MCP** | OAuth 필요한 MCP 서버 | google-calendar, gmail, github |
| **PKCE** | 인가 코드 탈취 방지 | code_verifier + code_challenge |
| **토큰 스왑** | 클라이언트가 OAuth 토큰 직접 볼 수 없음 | Auth Proxy 내부에서 암호화 저장 |
| **Fernet 암호화** | AES-128-CBC + HMAC-SHA256 | 토큰 안전 저장 |

### 1.1 JediSOS에서의 역할

```
사용자 → JediSOS UI → MCP Client → Auth Proxy (PKCE) → OAuth Provider
                                  ↓
                         Tier 2 MCP Server (Gmail, Calendar, GitHub)
```

**Tier 1 (인증 불필요):** filesystem, python, bash 등 → 직접 실행
**Tier 2 (OAuth 필수):** google-calendar, gmail, github 등 → Auth Proxy 거쳐서 실행

### 1.2 전체 흐름 (OAuth 2.1 + PKCE)

1. 클라이언트가 Auth Proxy에 MCP 요청
2. Auth Proxy가 OAuth 제공자에게 리다이렉트
3. 사용자가 제공자에서 인증 + 동의
4. 인가 코드 → Auth Proxy로 전달
5. Auth Proxy가 PKCE 검증 후 토큰 교환 (code + code_verifier 검증)
6. 토큰을 Fernet으로 암호화해서 내부 저장
7. Auth Proxy가 자신의 JWT 발급 (클라이언트에게)
8. 이후 MCP 요청 시 자동으로 토큰 주입 (클라이언트는 원본 OAuth 토큰 몰라도 됨)
9. 토큰 만료 시 자동 갱신 (refresh_token 사용)

---

## 2. 설치 및 실행

### 2.1 바이너리 직접 실행

```bash
# 다운로드 (GitHub Release)
wget https://github.com/sigbit/mcp-auth-proxy/releases/download/v1.2.1/mcp-auth-proxy-linux-x64
chmod +x mcp-auth-proxy-linux-x64

# 간단한 테스트 (로컬, 자체 서명 인증서)
./mcp-auth-proxy \
  --external-url https://localhost:8080 \
  --tls-accept-tos \
  --password changeme \
  -- npx -y @modelcontextprotocol/server-filesystem ./

# 프로덕션 (Let's Encrypt, Gmail + GitHub OAuth)
./mcp-auth-proxy \
  --external-url https://mcp.yourdomain.com \
  --tls \
  --google-client-id YOUR_CLIENT_ID \
  --google-client-secret YOUR_CLIENT_SECRET \
  --github-client-id YOUR_CLIENT_ID \
  --github-client-secret YOUR_CLIENT_SECRET \
  -- npx -y @modelcontextprotocol/server-gmail
```

### 2.2 Docker 이미지 사용

```bash
# 공식 이미지 실행
docker run -p 8080:8080 \
  -e EXTERNAL_URL=https://mcp.yourdomain.com \
  -e GOOGLE_CLIENT_ID=YOUR_ID \
  -e GOOGLE_CLIENT_SECRET=YOUR_SECRET \
  -e AUTH_ENCRYPTION_SECRET=$(openssl rand -base64 32) \
  sigbit/mcp-auth-proxy:latest \
  -- npx -y @modelcontextprotocol/server-gmail
```

### 2.3 Node.js 소스에서 빌드

```bash
git clone https://github.com/sigbit/mcp-auth-proxy.git
cd mcp-auth-proxy
npm install
npm run build

# 실행
node dist/index.js \
  --external-url https://mcp.yourdomain.com \
  --tls \
  --password changeme \
  -- npx -y @modelcontextprotocol/server-filesystem ./
```

---

## 3. Docker Compose 통합 (JediSOS 패턴)

### 3.1 Tier 2 OAuth MCP 서버 추가 예시

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: jedisos
      POSTGRES_USER: jedi
      POSTGRES_PASSWORD: changeme
    volumes:
      - postgres_data:/var/lib/postgresql/data

  hindsight:
    image: hindsight:latest
    environment:
      DATABASE_URL: postgresql://jedi:changeme@postgres:5432/hindsight
    depends_on:
      - postgres
    ports:
      - "8888:8888"

  jedisos-core:
    image: jedisos:latest
    environment:
      HINDSIGHT_URL: http://hindsight:8888
      MCP_SERVERS_CONFIG: /config/mcp_servers.json
      DATABASE_URL: postgresql://jedi:changeme@postgres:5432/jedisos
    depends_on:
      - postgres
      - hindsight
    ports:
      - "8000:8000"
    volumes:
      - ./mcp_servers.json:/config/mcp_servers.json

  # Tier 2: Gmail MCP with Auth Proxy
  gmail-mcp-proxy:
    image: sigbit/mcp-auth-proxy:latest
    environment:
      EXTERNAL_URL: https://mcp-gmail.yourdomain.com
      TLS: "true"
      TLS_CERT: /etc/letsencrypt/live/mcp-gmail.yourdomain.com/fullchain.pem
      TLS_KEY: /etc/letsencrypt/live/mcp-gmail.yourdomain.com/privkey.pem
      GOOGLE_CLIENT_ID: ${GOOGLE_GMAIL_CLIENT_ID}
      GOOGLE_CLIENT_SECRET: ${GOOGLE_GMAIL_CLIENT_SECRET}
      AUTH_ENCRYPTION_SECRET: ${AUTH_ENCRYPTION_SECRET}
      ALLOWED_USERS: jedi@yourdomain.com
      LOG_LEVEL: debug
    command: npx -y @modelcontextprotocol/server-gmail
    depends_on:
      - jedisos-core
    ports:
      - "8081:8080"
    volumes:
      - /etc/letsencrypt:/etc/letsencrypt:ro

  # Tier 2: Google Calendar MCP with Auth Proxy
  calendar-mcp-proxy:
    image: sigbit/mcp-auth-proxy:latest
    environment:
      EXTERNAL_URL: https://mcp-calendar.yourdomain.com
      TLS: "true"
      TLS_CERT: /etc/letsencrypt/live/mcp-calendar.yourdomain.com/fullchain.pem
      TLS_KEY: /etc/letsencrypt/live/mcp-calendar.yourdomain.com/privkey.pem
      GOOGLE_CLIENT_ID: ${GOOGLE_CALENDAR_CLIENT_ID}
      GOOGLE_CLIENT_SECRET: ${GOOGLE_CALENDAR_CLIENT_SECRET}
      AUTH_ENCRYPTION_SECRET: ${AUTH_ENCRYPTION_SECRET}
      ALLOWED_USERS: jedi@yourdomain.com
    command: npx -y @modelcontextprotocol/server-google-calendar
    depends_on:
      - jedisos-core
    ports:
      - "8082:8080"
    volumes:
      - /etc/letsencrypt:/etc/letsencrypt:ro

  # Tier 2: GitHub MCP with Auth Proxy
  github-mcp-proxy:
    image: sigbit/mcp-auth-proxy:latest
    environment:
      EXTERNAL_URL: https://mcp-github.yourdomain.com
      TLS: "true"
      TLS_CERT: /etc/letsencrypt/live/mcp-github.yourdomain.com/fullchain.pem
      TLS_KEY: /etc/letsencrypt/live/mcp-github.yourdomain.com/privkey.pem
      GITHUB_CLIENT_ID: ${GITHUB_CLIENT_ID}
      GITHUB_CLIENT_SECRET: ${GITHUB_CLIENT_SECRET}
      AUTH_ENCRYPTION_SECRET: ${AUTH_ENCRYPTION_SECRET}
      ALLOWED_USERS: jedi
    command: npx -y @modelcontextprotocol/server-github --owner jedi
    depends_on:
      - jedisos-core
    ports:
      - "8083:8080"
    volumes:
      - /etc/letsencrypt:/etc/letsencrypt:ro

  # Tier 2: Drive MCP with Auth Proxy
  drive-mcp-proxy:
    image: sigbit/mcp-auth-proxy:latest
    environment:
      EXTERNAL_URL: https://mcp-drive.yourdomain.com
      TLS: "true"
      TLS_CERT: /etc/letsencrypt/live/mcp-drive.yourdomain.com/fullchain.pem
      TLS_KEY: /etc/letsencrypt/live/mcp-drive.yourdomain.com/privkey.pem
      GOOGLE_CLIENT_ID: ${GOOGLE_DRIVE_CLIENT_ID}
      GOOGLE_CLIENT_SECRET: ${GOOGLE_DRIVE_CLIENT_SECRET}
      AUTH_ENCRYPTION_SECRET: ${AUTH_ENCRYPTION_SECRET}
      ALLOWED_USERS: jedi@yourdomain.com
    command: npx -y @modelcontextprotocol/server-google-drive
    depends_on:
      - jedisos-core
    ports:
      - "8084:8080"
    volumes:
      - /etc/letsencrypt:/etc/letsencrypt:ro

volumes:
  postgres_data:
```

### 3.2 환경변수 (.env 파일)

```bash
# 공통
EXTERNAL_URL=https://mcp.yourdomain.com
TLS=true
AUTH_ENCRYPTION_SECRET=$(openssl rand -base64 32)
ALLOWED_USERS=jedi@yourdomain.com,admin@yourdomain.com

# Google OAuth (Gmail, Calendar, Drive 공용)
GOOGLE_CLIENT_ID=YOUR_GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET=YOUR_GOOGLE_CLIENT_SECRET

# Google OAuth (Gmail 전용)
GOOGLE_GMAIL_CLIENT_ID=YOUR_GMAIL_CLIENT_ID
GOOGLE_GMAIL_CLIENT_SECRET=YOUR_GMAIL_CLIENT_SECRET

# Google OAuth (Calendar 전용)
GOOGLE_CALENDAR_CLIENT_ID=YOUR_CALENDAR_CLIENT_ID
GOOGLE_CALENDAR_CLIENT_SECRET=YOUR_CALENDAR_CLIENT_SECRET

# Google OAuth (Drive 전용)
GOOGLE_DRIVE_CLIENT_ID=YOUR_DRIVE_CLIENT_ID
GOOGLE_DRIVE_CLIENT_SECRET=YOUR_DRIVE_CLIENT_SECRET

# GitHub OAuth
GITHUB_CLIENT_ID=YOUR_GITHUB_CLIENT_ID
GITHUB_CLIENT_SECRET=YOUR_GITHUB_CLIENT_SECRET

# OIDC (선택)
OIDC_ISSUER=https://auth.yourdomain.com
OIDC_CLIENT_ID=YOUR_OIDC_CLIENT_ID
OIDC_CLIENT_SECRET=YOUR_OIDC_CLIENT_SECRET

# TLS 인증서 경로
TLS_CERT=/etc/letsencrypt/live/mcp.yourdomain.com/fullchain.pem
TLS_KEY=/etc/letsencrypt/live/mcp.yourdomain.com/privkey.pem

# 기타
LOG_LEVEL=info
PORT=8080
```

### 3.3 mcp_servers.json 설정 (JediSOS)

```json
{
  "servers": [
    {
      "name": "gmail",
      "type": "http",
      "url": "https://mcp-gmail.yourdomain.com/mcp",
      "transport": "http",
      "tier": 2,
      "requires_oauth": true,
      "oauth_provider": "google",
      "scopes": ["https://www.googleapis.com/auth/gmail.readonly"]
    },
    {
      "name": "google-calendar",
      "type": "http",
      "url": "https://mcp-calendar.yourdomain.com/mcp",
      "transport": "http",
      "tier": 2,
      "requires_oauth": true,
      "oauth_provider": "google",
      "scopes": ["https://www.googleapis.com/auth/calendar.readonly"]
    },
    {
      "name": "github",
      "type": "http",
      "url": "https://mcp-github.yourdomain.com/mcp",
      "transport": "http",
      "tier": 2,
      "requires_oauth": true,
      "oauth_provider": "github",
      "scopes": ["repo:status", "read:user"]
    },
    {
      "name": "google-drive",
      "type": "http",
      "url": "https://mcp-drive.yourdomain.com/mcp",
      "transport": "http",
      "tier": 2,
      "requires_oauth": true,
      "oauth_provider": "google",
      "scopes": ["https://www.googleapis.com/auth/drive.readonly"]
    }
  ]
}
```

---

## 4. OAuth 프로바이더 설정

### 4.1 Google OAuth (Gmail, Calendar, Drive)

**Step 1: Google Cloud Console에서 프로젝트 생성**

```
1. https://console.cloud.google.com 접속
2. 새 프로젝트 생성 (e.g., "JediSOS OAuth")
3. "OAuth 2.0 클라이언트" 검색 → "동의 화면 구성"
```

**Step 2: OAuth 동의 화면 설정**

```
앱 정보:
  - 앱 이름: "JediSOS MCP Gateway"
  - 사용자 지원 이메일: your@yourdomain.com
  - 개발자 연락처: your@yourdomain.com

범위 추가 (필요한 것만):
  - Gmail: https://www.googleapis.com/auth/gmail.readonly
  - Calendar: https://www.googleapis.com/auth/calendar.readonly
  - Drive: https://www.googleapis.com/auth/drive.readonly

테스트 사용자 추가:
  - your@yourdomain.com
```

**Step 3: OAuth 2.0 클라이언트 생성**

```
응용 프로그램 유형: 웹 애플리케이션
이름: Gmail MCP Proxy

승인된 리다이렉트 URI:
  https://mcp-gmail.yourdomain.com/auth/callback
  https://mcp-gmail.yourdomain.com/auth/google/callback

→ 클라이언트 ID, 클라이언트 보안 비밀 복사 (.env에 저장)
```

**각 서비스별 별도 클라이언트 생성:**

```
Gmail:
  redirect_uri: https://mcp-gmail.yourdomain.com/auth/callback
  scopes: https://www.googleapis.com/auth/gmail.readonly

Calendar:
  redirect_uri: https://mcp-calendar.yourdomain.com/auth/callback
  scopes: https://www.googleapis.com/auth/calendar.readonly

Drive:
  redirect_uri: https://mcp-drive.yourdomain.com/auth/callback
  scopes: https://www.googleapis.com/auth/drive.readonly
```

### 4.2 GitHub OAuth

**Step 1: GitHub Settings → Developer settings → OAuth Apps**

```
1. https://github.com/settings/developers 접속
2. "New OAuth App" 클릭
```

**Step 2: 앱 등록**

```
Application name: JediSOS GitHub MCP
Homepage URL: https://mcp-github.yourdomain.com
Authorization callback URL: https://mcp-github.yourdomain.com/auth/callback

→ Client ID, Client Secret 복사 (.env에 저장)
```

**Step 3: 권한 설정 (JediSOS 사용 시 필요)**

```
권장 scopes:
  - repo:status (공개/비공개 repo 상태 접근)
  - read:user (사용자 정보 조회)
  - read:repo_hook (repo 훅 조회, 선택)
```

### 4.3 OIDC 호환 프로바이더 (Okta, Auth0, Azure AD, Keycloak)

**일반 OIDC 설정 (환경변수)**

```bash
OIDC_ISSUER=https://auth.example.okta.com
OIDC_CLIENT_ID=YOUR_CLIENT_ID
OIDC_CLIENT_SECRET=YOUR_CLIENT_SECRET
OIDC_SCOPES=openid profile email

# 선택: 커스텀 인가 엔드포인트
OIDC_AUTH_ENDPOINT=https://auth.example.okta.com/oauth2/v1/authorize
OIDC_TOKEN_ENDPOINT=https://auth.example.okta.com/oauth2/v1/token
OIDC_USERINFO_ENDPOINT=https://auth.example.okta.com/oauth2/v1/userinfo
```

**Auth0 예시**

```bash
OIDC_ISSUER=https://jedisos.auth0.com
OIDC_CLIENT_ID=YOUR_AUTH0_CLIENT_ID
OIDC_CLIENT_SECRET=YOUR_AUTH0_CLIENT_SECRET
OIDC_SCOPES=openid profile email offline_access
```

**Azure AD 예시**

```bash
OIDC_ISSUER=https://login.microsoftonline.com/YOUR_TENANT_ID/v2.0
OIDC_CLIENT_ID=YOUR_AZURE_CLIENT_ID
OIDC_CLIENT_SECRET=YOUR_AZURE_CLIENT_SECRET
OIDC_SCOPES=openid profile email
```

---

## 5. 토큰 관리

### 5.1 토큰 저장 및 암호화

**Fernet 암호화 (AES-128-CBC + HMAC-SHA256)**

```python
# Auth Proxy 내부 동작
from cryptography.fernet import Fernet

encryption_secret = os.getenv("AUTH_ENCRYPTION_SECRET")
cipher = Fernet(encryption_secret.encode())

# 토큰 저장
encrypted_token = cipher.encrypt(oauth_token.encode())
db.tokens.insert(user_id, encrypted_token)

# 토큰 복호화 (MCP 요청 시)
decrypted = cipher.decrypt(encrypted_token)
# 클라이언트에는 Proxy의 JWT 제공, 원본 OAuth 토큰은 비노출
```

### 5.2 AUTH_ENCRYPTION_SECRET 생성

```bash
# 32바이트 Base64 인코딩된 키 생성
openssl rand -base64 32

# 출력 예시:
# c7f8k2x9mP1qL4nR7sT0vB3wF5gH8jK0lMoP9qRsT2u=

# .env에 저장
echo "AUTH_ENCRYPTION_SECRET=c7f8k2x9mP1qL4nR7sT0vB3wF5gH8jK0lMoP9qRsT2u=" >> .env
```

### 5.3 토큰 만료 및 자동 갱신

**토큰 갱신 메커니즘**

```
OAuth 토큰 만료까지 시간: 3600초 (1시간)
갱신 임계값: 5분 (300초)

MCP 요청 시:
  1. 저장된 토큰의 만료 시간 확인
  2. 남은 시간 < 5분 → 자동으로 refresh_token으로 갱신
  3. refresh_token도 만료됨 → 사용자 재인증 필요
```

**자동 갱신 설정 (환경변수)**

```bash
# 갱신 임계값 (초 단위, 기본값: 300)
TOKEN_REFRESH_THRESHOLD=300

# 갱신 최대 재시도 횟수 (기본값: 3)
TOKEN_REFRESH_MAX_RETRIES=3

# 갱신 재시도 간격 (초 단위, 기본값: 2)
TOKEN_REFRESH_RETRY_DELAY=2
```

### 5.4 토큰 저장소

**개발 환경**

```
저장소: 인메모리 (메모리에만 존재)
특징: 프로세스 재시작 시 토큰 소실 → 재인증 필요
권장: 로컬 개발용
```

**프로덕션 환경**

```bash
# PostgreSQL에 저장
AUTH_TOKEN_STORE=postgresql
DATABASE_URL=postgresql://user:pass@postgres:5432/auth_tokens

# Redis에 저장 (TTL 자동 관리)
AUTH_TOKEN_STORE=redis
REDIS_URL=redis://redis:6379/0
```

---

## 6. 전송 모드 지원

### 6.1 stdio (표준 입출력)

```bash
# 로컬 MCP 서버를 HTTP로 변환
./mcp-auth-proxy \
  --external-url https://localhost:8080 \
  --password changeme \
  -- npx -y @modelcontextprotocol/server-filesystem ./

# 내부 동작:
# stdio 프로토콜 (로컬 MCP) ← → HTTP /mcp 엔드포인트
```

**사용 시점:** 로컬 MCP 서버를 네트워크 상에서 접근 가능하게 할 때

### 6.2 SSE (Server-Sent Events)

```bash
# 실시간 스트리밍 지원
./mcp-auth-proxy \
  --external-url https://mcp.yourdomain.com \
  --tls \
  --transport sse \
  -- npx -y @modelcontextprotocol/server-gmail

# 클라이언트에서:
# POST /mcp → JSON 요청
# GET /mcp/events → EventSource로 응답 수신
```

**특징:**
- 웹브라우저에서 네이티브 지원
- HTTP long-polling 불필요
- 실시간 비동기 응답

### 6.3 HTTP (표준 요청/응답)

```bash
# 기본 모드 (요청/응답)
./mcp-auth-proxy \
  --external-url https://mcp.yourdomain.com \
  --tls \
  -- npx -y @modelcontextprotocol/server-gmail

# 클라이언트에서:
# POST /mcp
# {
#   "jsonrpc": "2.0",
#   "method": "resources/list",
#   "params": {},
#   "id": 1
# }
#
# ← 동기 응답:
# {
#   "jsonrpc": "2.0",
#   "result": { "resources": [...] },
#   "id": 1
# }
```

**특징:** 가장 단순, 대부분의 클라이언트 지원

---

## 7. PKCE 보안 상세

### 7.1 PKCE 흐름 (Proof Key for Code Exchange)

```
1. 클라이언트가 code_verifier 생성 (43-128자 랜덤 문자열)
   code_verifier = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3"

2. code_challenge 생성 (SHA256(code_verifier) Base64URL 인코딩)
   code_challenge = base64url(sha256(code_verifier))
   = "S9r-GOzpdmMF8uBsBqkQsJUjNlnSPVQVIAJlqihlFj0"

3. 인가 요청에 code_challenge 포함:
   GET /authorize?
     client_id=...
     &redirect_uri=https://mcp-gmail.yourdomain.com/auth/callback
     &code_challenge=S9r-GOzpdmMF8uBsBqkQsJUjNlnSPVQVIAJlqihlFj0
     &code_challenge_method=S256

4. OAuth 서버가 code 발급 (code_challenge와 매핑)

5. 토큰 요청 시 code_verifier 포함:
   POST /token
   {
     "grant_type": "authorization_code",
     "code": "auth_code_from_provider",
     "code_verifier": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3",
     "client_id": "..."
   }

6. OAuth 서버가 SHA256(code_verifier) == code_challenge 검증
   → 일치하면 토큰 발급
   → 불일치하면 거부
```

### 7.2 보안 이점

| 공격 | 기존 OAuth 2.0 | PKCE로 방어 |
|------|---|---|
| 인가 코드 탈취 | 공격자가 code를 훔치면 토큰 교환 가능 | code_verifier 없으면 불가능 |
| 악의적 앱 | 다른 앱의 code로 토큰 교환 시도 가능 | code_verifier 검증으로 차단 |
| Man-in-the-Middle | 리다이렉트 URI 변조 가능 | PKCE는 추가 보호 |

### 7.3 JediSOS에서의 PKCE 요구사항

```python
# MCP 클라이언트 구현 시 (JediSOS Core)
from mcp.client import ClientSession

# Auth Proxy와 통신할 때 반드시 PKCE 지원 확인
async def connect_to_oauth_mcp():
    async with ClientSession(...) as session:
        # Proxy에게 PKCE 지원 확인
        capabilities = await session.initialize()

        if "code_challenge_methods_supported" not in capabilities:
            raise ValueError("MCP Auth Proxy는 PKCE를 지원해야 함")

        if "S256" not in capabilities["code_challenge_methods_supported"]:
            raise ValueError("S256 (SHA256) 챌린지 메서드 필수")
```

---

## 8. JediSOS 통합 패턴

### 8.1 OAuth MCP 서버 설치 흐름

```bash
# 1. JediSOS CLI에서 Tier 2 MCP 설치
jedisos mcp install google-calendar

# 2. 설치 프롬프트:
# - Google OAuth 클라이언트 ID 입력 (없으면 생성 가이드 제공)
# - 클라이언트 보안 비밀 입력
# - 리다이렉트 URI 확인: https://mcp-calendar.yourdomain.com/auth/callback

# 3. JediSOS가 자동으로:
# - Auth Proxy Docker 이미지 구성
# - docker-compose.yml에 서비스 추가
# - mcp_servers.json에 등록
# - .env에 OAuth 자격증명 저장

# 4. 사용자 웹 UI에서:
# - 구글 계정 연동 버튼 클릭
# - OAuth 동의 화면 표시
# - 토큰 자동 저장 (Fernet 암호화)
```

### 8.2 mcp_servers 테이블 스키마

```sql
CREATE TABLE mcp_servers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    type VARCHAR(50) NOT NULL,
    url VARCHAR(1024) NOT NULL,
    transport VARCHAR(50) DEFAULT 'http',
    tier INTEGER DEFAULT 1,
    requires_oauth BOOLEAN DEFAULT FALSE,
    oauth_provider VARCHAR(50),
    status VARCHAR(50) DEFAULT 'inactive',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Tier 2 OAuth MCP 예시 행
INSERT INTO mcp_servers VALUES (
    NULL,
    'google-calendar',
    'http',
    'https://mcp-calendar.yourdomain.com/mcp',
    'http',
    2,
    true,
    'google',
    'active',
    NOW(),
    NOW()
);

-- oauth_tokens 테이블 (별도)
CREATE TABLE oauth_tokens (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    mcp_server_id INTEGER NOT NULL REFERENCES mcp_servers(id),
    encrypted_token TEXT NOT NULL,
    refresh_token TEXT,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, mcp_server_id)
);
```

### 8.3 전체 OAuth 스택 예시 (Docker Compose)

```yaml
# jedisos/docker-compose.prod.yml
version: '3.8'
services:
  # 데이터베이스
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: jedisos
      POSTGRES_USER: jedi
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - jedisos-net

  # Hindsight 메모리 엔진
  hindsight:
    image: hindsight:latest
    environment:
      DATABASE_URL: postgresql://jedi:${DB_PASSWORD}@postgres:5432/hindsight
      API_KEY: ${HINDSIGHT_API_KEY}
    depends_on:
      - postgres
    networks:
      - jedisos-net

  # JediSOS 코어
  jedisos-core:
    image: jedisos:latest
    environment:
      DATABASE_URL: postgresql://jedi:${DB_PASSWORD}@postgres:5432/jedisos
      HINDSIGHT_URL: http://hindsight:8888
      HINDSIGHT_API_KEY: ${HINDSIGHT_API_KEY}
      JWT_SECRET: ${JWT_SECRET}
      MCP_SERVERS_CONFIG: /config/mcp_servers.json
    depends_on:
      - postgres
      - hindsight
    ports:
      - "8000:8000"
    networks:
      - jedisos-net
    volumes:
      - ./mcp_servers.json:/config/mcp_servers.json

  # Auth Proxy + Gmail MCP
  gmail-proxy:
    image: sigbit/mcp-auth-proxy:latest
    environment:
      EXTERNAL_URL: https://mcp-gmail.yourdomain.com
      TLS: "true"
      TLS_CERT: /etc/letsencrypt/live/mcp-gmail.yourdomain.com/fullchain.pem
      TLS_KEY: /etc/letsencrypt/live/mcp-gmail.yourdomain.com/privkey.pem
      GOOGLE_CLIENT_ID: ${GOOGLE_GMAIL_CLIENT_ID}
      GOOGLE_CLIENT_SECRET: ${GOOGLE_GMAIL_CLIENT_SECRET}
      AUTH_ENCRYPTION_SECRET: ${AUTH_ENCRYPTION_SECRET}
      TOKEN_STORE: postgresql
      DATABASE_URL: postgresql://jedi:${DB_PASSWORD}@postgres:5432/auth_tokens
      ALLOWED_USERS: ${ALLOWED_USERS}
    command: npx -y @modelcontextprotocol/server-gmail
    depends_on:
      - postgres
      - jedisos-core
    ports:
      - "8081:8080"
    networks:
      - jedisos-net
    volumes:
      - /etc/letsencrypt:/etc/letsencrypt:ro

  # Auth Proxy + Google Calendar MCP
  calendar-proxy:
    image: sigbit/mcp-auth-proxy:latest
    environment:
      EXTERNAL_URL: https://mcp-calendar.yourdomain.com
      TLS: "true"
      TLS_CERT: /etc/letsencrypt/live/mcp-calendar.yourdomain.com/fullchain.pem
      TLS_KEY: /etc/letsencrypt/live/mcp-calendar.yourdomain.com/privkey.pem
      GOOGLE_CLIENT_ID: ${GOOGLE_CALENDAR_CLIENT_ID}
      GOOGLE_CLIENT_SECRET: ${GOOGLE_CALENDAR_CLIENT_SECRET}
      AUTH_ENCRYPTION_SECRET: ${AUTH_ENCRYPTION_SECRET}
      TOKEN_STORE: postgresql
      DATABASE_URL: postgresql://jedi:${DB_PASSWORD}@postgres:5432/auth_tokens
      ALLOWED_USERS: ${ALLOWED_USERS}
    command: npx -y @modelcontextprotocol/server-google-calendar
    depends_on:
      - postgres
      - jedisos-core
    ports:
      - "8082:8080"
    networks:
      - jedisos-net
    volumes:
      - /etc/letsencrypt:/etc/letsencrypt:ro

  # Auth Proxy + GitHub MCP
  github-proxy:
    image: sigbit/mcp-auth-proxy:latest
    environment:
      EXTERNAL_URL: https://mcp-github.yourdomain.com
      TLS: "true"
      TLS_CERT: /etc/letsencrypt/live/mcp-github.yourdomain.com/fullchain.pem
      TLS_KEY: /etc/letsencrypt/live/mcp-github.yourdomain.com/privkey.pem
      GITHUB_CLIENT_ID: ${GITHUB_CLIENT_ID}
      GITHUB_CLIENT_SECRET: ${GITHUB_CLIENT_SECRET}
      AUTH_ENCRYPTION_SECRET: ${AUTH_ENCRYPTION_SECRET}
      TOKEN_STORE: postgresql
      DATABASE_URL: postgresql://jedi:${DB_PASSWORD}@postgres:5432/auth_tokens
      ALLOWED_USERS: ${ALLOWED_USERS}
    command: npx -y @modelcontextprotocol/server-github
    depends_on:
      - postgres
      - jedisos-core
    ports:
      - "8083:8080"
    networks:
      - jedisos-net
    volumes:
      - /etc/letsencrypt:/etc/letsencrypt:ro

  # Auth Proxy + Google Drive MCP
  drive-proxy:
    image: sigbit/mcp-auth-proxy:latest
    environment:
      EXTERNAL_URL: https://mcp-drive.yourdomain.com
      TLS: "true"
      TLS_CERT: /etc/letsencrypt/live/mcp-drive.yourdomain.com/fullchain.pem
      TLS_KEY: /etc/letsencrypt/live/mcp-drive.yourdomain.com/privkey.pem
      GOOGLE_CLIENT_ID: ${GOOGLE_DRIVE_CLIENT_ID}
      GOOGLE_CLIENT_SECRET: ${GOOGLE_DRIVE_CLIENT_SECRET}
      AUTH_ENCRYPTION_SECRET: ${AUTH_ENCRYPTION_SECRET}
      TOKEN_STORE: postgresql
      DATABASE_URL: postgresql://jedi:${DB_PASSWORD}@postgres:5432/auth_tokens
      ALLOWED_USERS: ${ALLOWED_USERS}
    command: npx -y @modelcontextprotocol/server-google-drive
    depends_on:
      - postgres
      - jedisos-core
    ports:
      - "8084:8080"
    networks:
      - jedisos-net
    volumes:
      - /etc/letsencrypt:/etc/letsencrypt:ro

networks:
  jedisos-net:
    driver: bridge

volumes:
  postgres_data:
```

---

## 9. 대안 솔루션

### 9.1 FastMCP OAuth Proxy

**특징:** FastMCP 프레임워크 내장, Python 기반

```python
from fastmcp import FastMCP
from fastmcp.security import OAuthMiddleware

app = FastMCP()
app.add_middleware(
    OAuthMiddleware,
    providers={
        "google": {
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "scopes": ["gmail.readonly", "calendar.readonly"]
        },
        "github": {
            "client_id": os.getenv("GITHUB_CLIENT_ID"),
            "client_secret": os.getenv("GITHUB_CLIENT_SECRET")
        }
    }
)

@app.tool()
async def get_emails():
    """Gmail에서 이메일 조회 (OAuth 자동 적용)"""
    # OAuth 토큰이 자동으로 첨부됨
    ...

if __name__ == "__main__":
    app.run(port=8080)
```

**장점:** Python 커뮤니티, FastAPI 생태계
**단점:** JediSOS와 기술 스택 분산

### 9.2 mcp-oauth2-proxy (독립형)

**특징:** 경량, 단일 목적, Node.js

```bash
npm install -g mcp-oauth2-proxy

mcp-oauth2-proxy \
  --provider google \
  --client-id YOUR_ID \
  --client-secret YOUR_SECRET \
  --port 8080 \
  --command "npx @modelcontextprotocol/server-gmail"
```

**장점:** 설정 간단, 가벼움
**단점:** PKCE 지원 미확인, 문서 부족

### 9.3 Cloudflare Workers 패턴

**특징:** 엣지 컴퓨팅, 글로벌 분산

```javascript
// wrangler.toml
name = "jedisos-auth-proxy"
type = "javascript"
route = "https://mcp.yourdomain.com/*"

// src/index.js
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // /auth/callback 처리
    if (url.pathname === '/auth/callback') {
      const code = url.searchParams.get('code');
      const token = await exchangeCodeForToken(code, env);
      return new Response(JSON.stringify({ token }));
    }

    // /mcp 프록시
    if (url.pathname === '/mcp') {
      const token = await getStoredToken(env);
      const resp = await fetch('https://backend.yourdomain.com/mcp', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          ...request.headers
        },
        body: request.body
      });
      return resp;
    }
  }
};
```

**장점:** 무서버, 글로벌 지연 시간 최소화
**단점:** Cloudflare 종속, 복잡한 설정

**JediSOS 권장:** sigbit/mcp-auth-proxy (Node.js 기반, PKCE 지원, 문서 완성도 높음)

---

## 10. 보안 모범 사례

### 10.1 토큰 직접 노출 금지 (토큰 스왑 패턴)

**안전하지 않은 방식:**

```javascript
// ❌ 클라이언트에게 OAuth 토큰 직접 전달
app.get('/token', (req, res) => {
  const oauthToken = db.getToken(req.user.id);
  res.json({ token: oauthToken }); // 위험!
});
```

**안전한 방식 (MCP Auth Proxy):**

```javascript
// ✓ Proxy가 자신의 JWT 발급
app.get('/auth/callback', async (req, res) => {
  const code = req.query.code;

  // 1. OAuth 토큰 획득
  const oauthToken = await exchangeCodeForToken(code);

  // 2. Fernet으로 암호화해서 저장
  const encrypted = cipher.encrypt(oauthToken);
  db.tokens.save(req.user.id, encrypted);

  // 3. 클라이언트에게는 Proxy의 JWT만 반환
  const proxyJwt = jwt.sign(
    { sub: req.user.id, scope: 'mcp-access' },
    process.env.JWT_SECRET
  );
  res.json({ token: proxyJwt }); // OAuth 토큰이 아님
});

// 4. MCP 요청 시
app.post('/mcp', async (req, res) => {
  const proxyJwt = req.headers.authorization;
  const user = jwt.verify(proxyJwt, process.env.JWT_SECRET);

  // 5. 내부에서만 OAuth 토큰 복호화 사용
  const encrypted = db.tokens.get(user.sub);
  const oauthToken = cipher.decrypt(encrypted);

  // 6. MCP 서버로 요청 (클라이언트는 모름)
  const result = await mcpServer.call(method, {
    ...params,
    authorization: `Bearer ${oauthToken}`
  });

  res.json(result);
});
```

### 10.2 환경변수로 비밀 관리

```bash
# ✓ 좋은 예
export GOOGLE_CLIENT_SECRET="c7f8k2x9mP1qL4nR7sT0vB3wF5gH8jK0lMoP9qRsT2u="
export AUTH_ENCRYPTION_SECRET=$(openssl rand -base64 32)

# 프로세스 실행
./mcp-auth-proxy ...

# ❌ 나쁜 예 (절대 금지)
./mcp-auth-proxy --google-secret "c7f8k2x9mP1qL4nR7sT0vB3wF5gH8jK0lMoP9qRsT2u="
# → ps aux로 노출됨
```

**환경변수 관리 도구 (프로덕션)**

```bash
# 1. HashiCorp Vault
vault kv put secret/jedisos/google \
  client_id="YOUR_ID" \
  client_secret="YOUR_SECRET"

# Auth Proxy가 시작할 때 Vault에서 읽음
export VAULT_ADDR=https://vault.yourdomain.com
export VAULT_TOKEN=$(vault write -field=token auth/approle/login ...)

# 2. AWS Secrets Manager
aws secretsmanager get-secret-value \
  --secret-id jedisos/google-oauth > .env

# 3. Kubernetes Secrets
kubectl create secret generic google-oauth \
  --from-literal=client-id=YOUR_ID \
  --from-literal=client-secret=YOUR_SECRET
```

### 10.3 TLS 필수 (프로덕션)

```bash
# ❌ 개발용 자체 서명 인증서 (테스트만)
./mcp-auth-proxy \
  --external-url https://localhost:8080 \
  --tls-accept-tos \
  -- ...

# ✓ 프로덕션: Let's Encrypt
./mcp-auth-proxy \
  --external-url https://mcp.yourdomain.com \
  --tls \
  --tls-email admin@yourdomain.com \
  -- ...

# 또는 기존 인증서 사용
./mcp-auth-proxy \
  --external-url https://mcp.yourdomain.com \
  --tls-cert /etc/letsencrypt/live/mcp.yourdomain.com/fullchain.pem \
  --tls-key /etc/letsencrypt/live/mcp.yourdomain.com/privkey.pem \
  -- ...
```

### 10.4 ALLOWED_USERS로 접근 제한

```bash
# 쉼표로 구분된 사용자 목록만 접근 가능
ALLOWED_USERS="jedi@yourdomain.com,admin@yourdomain.com,alice@yourdomain.com"

# GitHub username 형식
ALLOWED_USERS="jedi,alice,bob"

# 와일드카드 (도메인 기반)
ALLOWED_USERS="*@yourdomain.com"

# OIDC 기반 (그룹)
ALLOWED_USERS="group:engineers,group:admins"
```

### 10.5 CSRF 보호

```bash
# Auth Proxy 자동 활성화
# CSRF 토큰이 /auth/authorize 링크에 포함됨

# 명시적 활성화 (환경변수)
CSRF_PROTECTION=true
CSRF_TOKEN_LENGTH=32

# 쿠키 보안 설정 (자동)
# - HttpOnly (JavaScript에서 접근 불가)
# - Secure (HTTPS만)
# - SameSite=Strict (CSRF 공격 방지)
```

---

## 11. 주의사항 및 팁

### 11.1 개발 vs 프로덕션

| 항목 | 개발 | 프로덕션 |
|------|------|---------|
| **TLS** | `--tls-accept-tos` (자체 서명) | Let's Encrypt 또는 유효한 인증서 |
| **인증** | `--password changeme` | OAuth 필수 |
| **토큰 저장** | 인메모리 | PostgreSQL / Redis |
| **외부 URL** | https://localhost:8080 | https://mcp.yourdomain.com |
| **ALLOWED_USERS** | 없음 (모두 허용) | 명시적 사용자 목록 |
| **로그 레벨** | debug | info / warn |

### 11.2 Google OAuth 설정 시 주의

**클라이언트 타입 선택**

```
⚠ Desktop App (❌ 잘못됨)
  - 데스크톱 앱용, redirect_uri 제한 있음

⚠ Web Application (⭕ 올바름)
  - 웹 서버용
  - redirect_uri를 자유롭게 설정 가능

⚠ OAuth 동의 화면
  - 테스트 사용자 추가하지 않으면
  - 다른 사용자가 접근 시 "앱이 확인되지 않음" 경고
  - 프로덕션: 앱 검증 신청 (Google에)
```

**scopes 최소화**

```bash
# ⭕ 필요한 것만
GOOGLE_SCOPES="https://www.googleapis.com/auth/gmail.readonly"

# ❌ 과도한 권한
GOOGLE_SCOPES="https://www.googleapis.com/auth/gmail.modify"
GOOGLE_SCOPES="https://www.googleapis.com/auth/drive"
```

### 11.3 GitHub OAuth 설정 시 주의

**인증 방식 선택**

```
⚠ Personal Access Token (❌ OAuth가 아님)
  - 개인 토큰, OAuth 흐름 없음
  - 장기 저장, 탈취 위험

⚠ OAuth 2.0 (⭕ 권장)
  - 사용자 동의 기반
  - 토큰 만료 및 갱신 가능
```

**조직(Organization) 접근**

```bash
# GitHub 개인 repo만 접근
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...

# 조직 repo도 접근 필요 시
# → 조직 OAuth App으로 별도 등록
# → 조직 소유자 승인 필요
```

### 11.4 토큰 갱신 실패 처리

**원인:**

```
1. refresh_token 만료 (만료 기간: 보통 6개월~1년)
2. 사용자가 OAuth 앱 권한 해제
3. OAuth 제공자 API 변경
4. 네트워크 문제
```

**해결책:**

```bash
# 자동 재시도 (기본값 3회, 2초 간격)
TOKEN_REFRESH_MAX_RETRIES=3
TOKEN_REFRESH_RETRY_DELAY=2

# 재시도 실패 시 사용자 재인증 필요
# JediSOS UI:
# "Google 계정 연동이 만료되었습니다. [다시 연동]을 클릭하세요"
# → 사용자가 클릭 → 새로운 OAuth 흐름
```

### 11.5 로깅 및 디버깅

```bash
# 상세 로깅 활성화
LOG_LEVEL=debug

# 로그 출력
docker logs -f jedisos-gmail-proxy

# PKCE 검증 로그 예시
2026-02-17T10:30:45.123Z [DEBUG] PKCE validation:
  code: "auth_code_abc123"
  code_verifier: "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3"
  code_challenge: "S9r-GOzpdmMF8uBsBqkQsJUjNlnSPVQVIAJlqihlFj0"
  method: "S256"
  result: "PASSED"

# 토큰 갱신 로그
2026-02-17T11:00:00.456Z [INFO] Token refresh:
  user: "jedi@yourdomain.com"
  provider: "google"
  expires_in: 3600
  status: "success"
```

### 11.6 여러 OAuth 프로바이더 동시 사용

```bash
# gmail + github + drive 동시 설정
GOOGLE_CLIENT_ID=gmail_google_id
GOOGLE_CLIENT_SECRET=gmail_google_secret
GITHUB_CLIENT_ID=github_id
GITHUB_CLIENT_SECRET=github_secret
OIDC_ISSUER=https://auth.yourdomain.com

# Auth Proxy가 자동으로 모든 제공자 지원
# 사용자가 로그인 시 선택: "Sign in with Google" / "Sign in with GitHub" / "Sign in with OIDC"
```

---

## 12. 환경변수 전체 참고

```bash
# 필수
EXTERNAL_URL=https://mcp.yourdomain.com
AUTH_ENCRYPTION_SECRET=$(openssl rand -base64 32)

# TLS
TLS=true
TLS_CERT=/etc/letsencrypt/live/mcp.yourdomain.com/fullchain.pem
TLS_KEY=/etc/letsencrypt/live/mcp.yourdomain.com/privkey.pem
TLS_ACCEPT_TOS=true  # 개발 전용, 자체 서명 인증서 자동 생성

# 개발용 인증 (OAuth 없을 때)
PASSWORD=changeme

# Google OAuth
GOOGLE_CLIENT_ID=YOUR_CLIENT_ID
GOOGLE_CLIENT_SECRET=YOUR_CLIENT_SECRET
GOOGLE_SCOPES=https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/calendar.readonly

# GitHub OAuth
GITHUB_CLIENT_ID=YOUR_CLIENT_ID
GITHUB_CLIENT_SECRET=YOUR_CLIENT_SECRET

# OIDC (Okta, Auth0, Azure AD, Keycloak 등)
OIDC_ISSUER=https://auth.yourdomain.com
OIDC_CLIENT_ID=YOUR_CLIENT_ID
OIDC_CLIENT_SECRET=YOUR_CLIENT_SECRET
OIDC_SCOPES=openid profile email offline_access
OIDC_AUTH_ENDPOINT=https://auth.yourdomain.com/authorize
OIDC_TOKEN_ENDPOINT=https://auth.yourdomain.com/token
OIDC_USERINFO_ENDPOINT=https://auth.yourdomain.com/userinfo

# 토큰 관리
TOKEN_STORE=postgresql  # or redis
DATABASE_URL=postgresql://user:pass@postgres:5432/auth_tokens
REDIS_URL=redis://redis:6379/0
TOKEN_REFRESH_THRESHOLD=300  # 초, 기본값
TOKEN_REFRESH_MAX_RETRIES=3
TOKEN_REFRESH_RETRY_DELAY=2

# 접근 제어
ALLOWED_USERS=jedi@yourdomain.com,admin@yourdomain.com
ALLOWED_DOMAINS=yourdomain.com,partner.com

# 포트 및 네트워크
PORT=8080
BIND_ADDRESS=0.0.0.0
CORS_ORIGINS=https://jedisos.yourdomain.com,https://localhost:3000

# 로깅
LOG_LEVEL=info  # debug, info, warn, error
LOG_FORMAT=json  # json or text

# PKCE
PKCE_ENABLED=true
PKCE_CHALLENGE_METHOD=S256  # S256 or plain

# CSRF
CSRF_PROTECTION=true
CSRF_TOKEN_LENGTH=32

# 세션
SESSION_TIMEOUT=3600  # 초
SESSION_COOKIE_NAME=mcp_auth_session
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_HTTPONLY=true
SESSION_COOKIE_SAMESITE=Strict

# 캐싱
CACHE_STORE=redis  # or memory
CACHE_TTL=300  # 초

# 메트릭 (선택)
METRICS_ENABLED=true
METRICS_PORT=9090
METRICS_PATH=/metrics  # Prometheus 포맷
```

---

## 체크리스트: JediSOS에 Tier 2 OAuth MCP 추가하기

### 사전 준비

- [ ] Google/GitHub OAuth 앱 등록 완료
- [ ] 클라이언트 ID, 시크릿 준비
- [ ] 도메인 준비 (TLS 인증서)
- [ ] Docker 및 Docker Compose 설치

### 설정

- [ ] `.env` 파일에 OAuth 자격증명 입력
- [ ] `AUTH_ENCRYPTION_SECRET` 생성 (`openssl rand -base64 32`)
- [ ] `docker-compose.yml`에 Auth Proxy 서비스 추가
- [ ] `mcp_servers.json`에 MCP 서버 등록

### 실행 및 검증

- [ ] `docker-compose up -d`로 모든 서비스 시작
- [ ] `docker logs jedisos-core`에서 에러 확인
- [ ] JediSOS 웹 UI에서 "OAuth 연동" 버튼 클릭
- [ ] OAuth 동의 화면 표시되는지 확인
- [ ] 토큰 저장 및 토큰 암호화 로그 확인
- [ ] MCP 서버 호출 테스트 (예: 메일 조회)

### 보안 검증

- [ ] HTTPS 사용 (자체 서명 아님)
- [ ] ALLOWED_USERS 설정 (명시적 사용자 목록)
- [ ] 환경변수로 비밀 관리 (하드코딩 금지)
- [ ] 로그에 토큰 노출 여부 확인 (노출되면 안 됨)

---

## FAQ

**Q: Auth Proxy와 MCP 서버를 다른 도메인에서 실행할 수 있나?**

A: 가능. Auth Proxy는 게이트웨이 역할만 하므로 별도 도메인 가능.
```
mcp-gmail.yourdomain.com → Auth Proxy
  ↓
mcp-backend.yourdomain.com → MCP 서버
```

**Q: 클라이언트에서 직접 OAuth 토큰에 접근할 수 있나?**

A: 아니오. 토큰 스왑 패턴으로 클라이언트는 Auth Proxy의 JWT만 받음. 원본 OAuth 토큰은 Proxy 내부에서만 사용.

**Q: 토큰 갱신 실패 시 어떻게 되나?**

A: MCP 요청이 실패하고, JediSOS UI에서 사용자에게 재인증 요청. 사용자가 "다시 연동" 클릭 → 새로운 OAuth 흐름.

**Q: PKCE 없이 동작 가능한가?**

A: 가능하지만 보안 위험. 프로덕션에서는 항상 PKCE (S256) 사용 권장.

**Q: refresh_token 만료 기간은?**

A: OAuth 제공자마다 다름. Google: ~6개월, GitHub: 8시간. 만료되면 사용자 재인증 필요.

**Q: 여러 사용자의 토큰을 동시에 관리할 수 있나?**

A: 가능. 각 사용자별로 암호화된 토큰을 저장 (PostgreSQL). 사용자가 로그인할 때 자신의 토큰만 사용.

**Q: 개발 중에 TLS 없이 테스트할 수 있나?**

A: 가능. `--tls-accept-tos` 플래그로 자체 서명 인증서 자동 생성. 로컬 테스트 전용.

**Q: 로그에서 민감 정보 (토큰 등)이 노출되나?**

A: 아니오. Auth Proxy는 자동으로 로그에서 토큰, 시크릿 마스킹. 로그 레벨 debug에서도 마스킹됨.
