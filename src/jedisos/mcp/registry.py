"""
[JS-D003] jedisos.mcp.registry
MCP 서버 검색 — 큐레이티드 리스트 + npm/PyPI API + mcp.so 폴백

version: 1.0.0
created: 2026-02-20
modified: 2026-02-20
dependencies: httpx>=0.28.1
"""

from __future__ import annotations

import re
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

# npm 검색 API
_NPM_SEARCH_URL = "https://registry.npmjs.org/-/v1/search"

# mcp.so 검색
_MCP_SO_URL = "https://mcp.so/servers"


# ──────────────────────────────────────────────
# 큐레이티드 인기 MCP 서버 목록
# ──────────────────────────────────────────────
CURATED_SERVERS: list[dict[str, Any]] = [  # [JS-D003.1]
    # ── 웹/데이터 ──
    {
        "name": "fetch",
        "description": "웹 페이지를 가져와 마크다운으로 변환합니다.",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-fetch"],
        "tags": ["web", "fetch", "http", "scraping"],
        "source": "curated",
    },
    {
        "name": "brave-search",
        "description": "Brave Search API로 웹 검색을 수행합니다.",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "env": {"BRAVE_API_KEY": ""},
        "tags": ["search", "web", "brave"],
        "source": "curated",
    },
    {
        "name": "puppeteer",
        "description": "Puppeteer로 웹 브라우저를 제어합니다. 스크린샷, 클릭, 폼 입력 등.",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-puppeteer"],
        "tags": ["browser", "web", "puppeteer", "scraping", "automation"],
        "source": "curated",
    },
    # ── 파일/시스템 ──
    {
        "name": "filesystem",
        "description": "로컬 파일시스템을 읽고 쓸 수 있습니다.",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        "tags": ["file", "filesystem", "directory", "read", "write"],
        "source": "curated",
    },
    {
        "name": "memory",
        "description": "지식 그래프 기반 영구 메모리를 제공합니다.",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-memory"],
        "tags": ["memory", "knowledge", "graph", "storage"],
        "source": "curated",
    },
    {
        "name": "sqlite",
        "description": "SQLite 데이터베이스를 조회하고 관리합니다.",
        "command": "uvx",
        "args": ["mcp-server-sqlite", "--db-path", "/tmp/test.db"],
        "tags": ["database", "sqlite", "sql", "query"],
        "source": "curated",
    },
    # ── 개발 도구 ──
    {
        "name": "github",
        "description": "GitHub 리포지토리, 이슈, PR을 관리합니다.",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": ""},
        "tags": ["github", "git", "repository", "issue", "pr"],
        "source": "curated",
    },
    {
        "name": "gitlab",
        "description": "GitLab 프로젝트, 이슈, 머지 리퀘스트를 관리합니다.",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-gitlab"],
        "env": {"GITLAB_PERSONAL_ACCESS_TOKEN": "", "GITLAB_API_URL": "https://gitlab.com/api/v4"},
        "tags": ["gitlab", "git", "repository", "issue", "mr"],
        "source": "curated",
    },
    {
        "name": "sequential-thinking",
        "description": "복잡한 문제를 단계적으로 분해하여 사고합니다.",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
        "tags": ["thinking", "reasoning", "problem-solving"],
        "source": "curated",
    },
    # ── 클라우드/SaaS ──
    {
        "name": "slack",
        "description": "Slack 메시지 전송, 채널 관리를 수행합니다.",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-slack"],
        "env": {"SLACK_BOT_TOKEN": "", "SLACK_TEAM_ID": ""},
        "tags": ["slack", "chat", "message", "team"],
        "source": "curated",
    },
    {
        "name": "google-drive",
        "description": "Google Drive 파일을 검색하고 읽습니다.",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-gdrive"],
        "tags": ["google", "drive", "file", "document"],
        "source": "curated",
    },
    {
        "name": "google-maps",
        "description": "Google Maps API로 장소 검색, 경로, 지오코딩을 수행합니다.",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-google-maps"],
        "env": {"GOOGLE_MAPS_API_KEY": ""},
        "tags": ["google", "maps", "location", "place", "geocoding", "directions"],
        "source": "curated",
    },
    {
        "name": "sentry",
        "description": "Sentry 이슈와 에러를 조회합니다.",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-sentry"],
        "env": {"SENTRY_AUTH_TOKEN": "", "SENTRY_ORG": ""},
        "tags": ["sentry", "error", "monitoring", "debug"],
        "source": "curated",
    },
    # ── 데이터/분석 ──
    {
        "name": "postgres",
        "description": "PostgreSQL 데이터베이스를 조회합니다.",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-postgres"],
        "env": {"POSTGRES_CONNECTION_STRING": ""},
        "tags": ["database", "postgres", "postgresql", "sql", "query"],
        "source": "curated",
    },
    {
        "name": "everart",
        "description": "AI 이미지를 생성합니다.",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-everart"],
        "env": {"EVERART_API_KEY": ""},
        "tags": ["image", "art", "generation", "ai"],
        "source": "curated",
    },
    # ── Python (uvx) ──
    {
        "name": "time",
        "description": "현재 시간, 타임존 변환을 수행합니다.",
        "command": "uvx",
        "args": ["mcp-server-time"],
        "tags": ["time", "timezone", "clock", "date"],
        "source": "curated",
    },
    {
        "name": "weather",
        "description": "미국 NWS API를 사용하여 날씨 정보를 조회합니다.",
        "command": "uvx",
        "args": ["mcp-server-fetch"],
        "tags": ["weather", "forecast", "temperature", "날씨"],
        "source": "curated",
    },
]


async def search_curated(query: str) -> list[dict[str, Any]]:  # [JS-D003.2]
    """큐레이티드 리스트에서 검색합니다."""
    q = query.lower()
    results = []
    for srv in CURATED_SERVERS:
        if (
            q in srv["name"].lower()
            or q in srv["description"].lower()
            or any(q in tag for tag in srv.get("tags", []))
        ):
            results.append(srv)
    return results


async def search_npm(query: str, size: int = 10) -> list[dict[str, Any]]:  # [JS-D003.3]
    """npm 레지스트리에서 MCP 서버를 검색합니다."""
    results: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                _NPM_SEARCH_URL,
                params={"text": f"modelcontextprotocol server {query}", "size": size},
            )
            resp.raise_for_status()
            data = resp.json()

        for obj in data.get("objects", []):
            pkg = obj.get("package", {})
            name = pkg.get("name", "")
            # MCP 서버 관련 패키지만 필터링
            if not name:
                continue
            results.append(
                {
                    "name": name.split("/")[-1],  # @scope/name → name
                    "package": name,
                    "description": pkg.get("description", ""),
                    "version": pkg.get("version", ""),
                    "command": "npx",
                    "args": ["-y", name],
                    "tags": pkg.get("keywords", []),
                    "source": "npm",
                    "url": pkg.get("links", {}).get("npm", ""),
                }
            )
    except Exception as e:
        logger.warning("npm_search_failed", query=query, error=str(e))

    return results


async def search_pypi(query: str, size: int = 10) -> list[dict[str, Any]]:  # [JS-D003.4]
    """PyPI에서 MCP 서버 패키지를 검색합니다."""
    results: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(
                "https://pypi.org/search/",
                params={"q": f"mcp server {query}"},
            )
            resp.raise_for_status()
            html = resp.text

        # 간단한 HTML 파싱 (정규식)
        # PyPI 검색 결과: <a class="package-snippet" href="/project/{name}/">
        #   <h3 class="package-snippet__title">...</h3>
        #   <p class="package-snippet__description">...</p>
        pattern = re.compile(
            r'<a class="package-snippet"[^>]*href="/project/([^/]+)/"[^>]*>.*?'
            r'<span class="package-snippet__name">([^<]+)</span>\s*'
            r'<span class="package-snippet__version">([^<]+)</span>.*?'
            r'<p class="package-snippet__description">([^<]*)</p>',
            re.DOTALL,
        )
        for match in pattern.finditer(html):
            slug, name, version, description = match.groups()
            name = name.strip()
            if not name:
                continue
            results.append(
                {
                    "name": name,
                    "package": name,
                    "description": description.strip(),
                    "version": version.strip(),
                    "command": "uvx",
                    "args": [name],
                    "tags": [],
                    "source": "pypi",
                    "url": f"https://pypi.org/project/{slug}/",
                }
            )
            if len(results) >= size:
                break
    except Exception as e:
        logger.warning("pypi_search_failed", query=query, error=str(e))

    return results


async def search_mcp_so(query: str, size: int = 10) -> list[dict[str, Any]]:  # [JS-D003.5]
    """mcp.so에서 MCP 서버를 검색합니다 (HTML 크롤링, 폴백용)."""
    results: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(_MCP_SO_URL, params={"q": query})
            resp.raise_for_status()
            html = resp.text

        # mcp.so 카드에서 서버 이름과 설명 추출
        # 패턴: /server/{name}/{author} 링크 + 설명 텍스트
        link_pattern = re.compile(
            r'href="/server/([^/]+)/([^"]+)"[^>]*>\s*(?:<[^>]*>)*\s*([^<]+)',
            re.DOTALL,
        )
        seen: set[str] = set()
        for match in link_pattern.finditer(html):
            srv_name, author, title = match.groups()
            srv_name = srv_name.strip()
            title = title.strip()
            if not srv_name or srv_name in seen:
                continue
            seen.add(srv_name)
            results.append(
                {
                    "name": srv_name,
                    "description": title,
                    "author": author.strip(),
                    "tags": [],
                    "source": "mcp.so",
                    "url": f"https://mcp.so/server/{srv_name}/{author.strip()}",
                    "install_hint": f"mcp.so에서 설치 명령을 확인하세요: https://mcp.so/server/{srv_name}/{author.strip()}",
                }
            )
            if len(results) >= size:
                break
    except Exception as e:
        logger.warning("mcp_so_search_failed", query=query, error=str(e))

    return results


async def search_registry(query: str) -> dict[str, Any]:  # [JS-D003.6]
    """큐레이티드 + npm + PyPI에서 통합 검색합니다 (기본 소스)."""
    curated = await search_curated(query)
    npm = await search_npm(query)
    pypi = await search_pypi(query)

    # 큐레이티드 결과를 맨 앞에 (즉시 실행 가능)
    return {
        "curated": curated,
        "npm": npm,
        "pypi": pypi,
        "total": len(curated) + len(npm) + len(pypi),
        "hint": "큐레이티드 서버는 바로 실행 가능합니다. npm/pypi 서버는 command와 args를 확인 후 add_mcp_server로 등록하세요.",
    }


async def search_all(  # [JS-D003.7]
    query: str,
    source: str = "registry",
) -> dict[str, Any]:
    """MCP 서버를 검색합니다.

    Args:
        query: 검색어
        source: "registry" (큐레이티드+npm+pypi) 또는 "mcp_so" (mcp.so 폴백)
    """
    if source == "mcp_so":
        mcp_so_results = await search_mcp_so(query)
        return {
            "results": mcp_so_results,
            "total": len(mcp_so_results),
            "source": "mcp.so",
            "hint": "mcp.so 결과입니다. 각 서버 URL에서 설치 명령을 확인하세요.",
        }

    return await search_registry(query)
