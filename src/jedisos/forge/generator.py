"""
[JS-K001] jedisos.forge.generator
LLM 기반 Skill 코드 생성기 - 멀티 웹 검색 + 페이지 크롤링 + Hindsight 스킬 메모리 + 에러 피드백 루프

version: 1.4.0
created: 2026-02-18
modified: 2026-02-18
dependencies: jinja2>=3.1, litellm>=1.81, ddgs>=8.0, httpx>=0.28
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import jinja2
import structlog
import yaml

from jedisos.forge.context import SKILL_MEMORY_BANK
from jedisos.forge.loader import ToolLoader
from jedisos.forge.security import CodeSecurityChecker, SecurityResult
from jedisos.forge.tester import SkillTester

if TYPE_CHECKING:
    from jedisos.memory.hindsight import HindsightMemory

logger = structlog.get_logger()


# LLM에게 보낼 코드 생성 프롬프트  [JS-K001.2]
CODE_GEN_PROMPT = """\
You are a JediSOS Skill code generator. Generate a complete Python tool file.

CRITICAL RULES:
1. Return a JSON object with a "code" field containing the COMPLETE Python file as a string.
2. The file MUST import and use: from jedisos.forge.decorator import tool
3. Decorate each tool function with: @tool(name="...", description="...")
4. All functions MUST be async (async def) with type hints.
5. Allowed imports: httpx, json, re, datetime, pathlib, typing, os, math, \
collections, itertools, functools, hashlib, base64, urllib.parse, html, textwrap, \
jedisos.forge.context (for AI/LLM and memory features)
6. FORBIDDEN: subprocess, eval, exec, __import__, os.system, socket, ctypes, shutil.rmtree
7. Use free, no-API-key-required JSON/REST APIs whenever possible.
8. NEVER scrape HTML web pages. HTML scraping is fragile, gets blocked (HTTP 403/500), \
and breaks when page layout changes. Always find and use structured JSON API endpoints instead.
9. If the user's request implies non-English input (Korean, Japanese, etc.), \
make sure the tool handles that language properly. Choose APIs that support \
the relevant language for geocoding, search, etc.
10. If the tool accepts free-form natural language input (e.g., "삼성전자 주가 알려줘"), \
use llm_complete() from jedisos.forge.context to parse/interpret the query into \
structured parameters. Do NOT use regex or rule-based pattern matching for NLP.

Return ONLY this JSON structure:

{{
    "tool_name": "snake_case_name",
    "description": "Brief description of the tool",
    "tags": ["tag1", "tag2"],
    "env_required": [],
    "code": "from jedisos.forge.decorator import tool\\nimport httpx\\n\\n@tool(name=\\"my_tool\\", description=\\"Does something\\")\\nasync def my_tool(param: str) -> dict:\\n    return {{\\"result\\": param}}"
}}

CONTEXT FUNCTIONS (from jedisos.forge.context):
If the tool needs AI/NLP processing or memory storage/recall, import and use these:
- llm_complete(prompt, system="", temperature=0.7, max_tokens=1024) -> str
  Use for: summarization, translation, classification, analysis, text generation,
  AND for parsing/interpreting natural language user queries into structured parameters
- llm_chat(messages, temperature=0.7, max_tokens=1024) -> str
  Use for: multi-turn conversations, complex reasoning with message history
- memory_retain(content, context="", bank_id=None) -> dict
  Use for: saving results, user preferences, learned information to memory
- memory_recall(query, bank_id=None) -> dict
  Use for: retrieving previously saved information, finding related context

Example (NLP query parsing + API call):
from jedisos.forge.context import llm_complete
parsed = await llm_complete(
    f"Extract the stock name from this query: {query}",
    system="Extract the company/stock name. Return ONLY the name, nothing else.",
    temperature=0.0,
)
data = await fetch_from_api(parsed.strip())

Example (summarization + memory):
from jedisos.forge.context import llm_complete, memory_retain
result = await llm_complete("Summarize this: " + text, system="You are a summarizer")
await memory_retain(content=result, context="summary of user request")

WHEN TO USE:
- llm_complete for NLP: When the tool receives free-form natural language input that
  needs to be parsed/classified/interpreted before calling an API. ALWAYS prefer
  llm_complete over regex-based or rule-based NLP parsing.
- External APIs (httpx): For fetching live data. ALWAYS prefer JSON/REST APIs over
  HTML page scraping. HTML scraping is fragile and breaks frequently (HTTP 500, layout changes).
- NEVER scrape HTML pages when a JSON API endpoint is available.
- NEVER use regex patterns to parse natural language queries — use llm_complete instead.

IMPORTANT:
- "code" must be a COMPLETE, valid Python file. Do NOT use template placeholders.
- Only ONE @tool decorator per function. No duplicate definitions.
- Keep functions focused and simple.
- Prefer the reference code/API docs below over your own knowledge. They are more up-to-date.
{reference_section}
{error_section}
{skill_memory_section}
User request: {request}
"""

# LLM에게 검색 쿼리 생성을 요청하는 프롬프트  [JS-K001.13]
QUERY_GEN_PROMPT = """\
Extract 2-3 focused web search queries to find reference code and API docs \
for building the following tool. Each query should target a different aspect.

User request: {request}

Rules:
- Query 1: Find a working code example (Python preferred)
- Query 2: Find the specific API documentation or library for the core feature
- Query 3 (optional): If there's a language/locale challenge (e.g., Korean input), \
search specifically for that
- Each query should be concise (5-10 words)
- Include "python" in at least one query
- Include "free" or "no API key" if relevant

Return a JSON array of query strings:
["query 1", "query 2", "query 3"]
"""


class SkillGenerator:  # [JS-K001.3]
    """LLM + Jinja2를 사용한 Skill 코드 생성기.

    멀티 웹 검색으로 참조 코드를 확보하고, 주요 URL의 페이지 본문을 크롤링하여
    실제 코드 예제를 추출합니다. Hindsight 메모리에서 기존/삭제된 스킬을 검색하여
    LLM 코드 생성 품질을 높입니다. 실패 시 에러 피드백을 포함한 재시도를 합니다.
    """

    def __init__(
        self,
        output_dir: Path | None = None,
        max_retries: int = 3,
        memory: HindsightMemory | None = None,
    ) -> None:
        self.output_dir = output_dir or Path("tools/generated")
        self.max_retries = max_retries
        self.security_checker = CodeSecurityChecker()
        self.tool_loader = ToolLoader()
        self.tester = SkillTester()
        self.memory = memory

        # Jinja2 환경 설정
        template_dir = Path(__file__).parent / "templates"
        self.jinja_env = jinja2.Environment(  # nosec B701 - Python code templates, not HTML
            loader=jinja2.FileSystemLoader(str(template_dir)),
            autoescape=False,
        )

    async def generate(  # [JS-K001.4]
        self,
        request: str,
        llm_response: dict[str, Any] | None = None,
    ) -> GenerationResult:
        """사용자 요청에서 Skill을 생성합니다.

        Args:
            request: 사용자 요청 문자열 (예: "날씨 도구 만들어줘")
            llm_response: LLM 응답 (테스트용 직접 주입)

        Returns:
            GenerationResult: 생성 결과
        """
        # 사전 조사: 웹 검색 + Hindsight 스킬 메모리
        reference_code = await self._search_web(request)
        skill_memory_context = await self._search_similar_skills(request)

        last_error: str = ""

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info("skill_generation_start", request=request, attempt=attempt)

                # 1. LLM으로 코드 스펙 생성 (또는 직접 주입)
                if llm_response is None:
                    spec = await self._call_llm(
                        request,
                        reference_code=reference_code,
                        error_context=last_error,
                        skill_memory=skill_memory_context,
                    )
                else:
                    spec = llm_response

                if spec is None:
                    last_error = "LLM이 유효한 JSON 응답을 반환하지 못했습니다."
                    logger.error("skill_generation_llm_failed", attempt=attempt)
                    continue

                # 2. tool_name 검증 (경로 traversal 방지)
                tool_name = spec.get("tool_name", "unnamed")
                if not re.match(r"^[a-zA-Z0-9_]+$", tool_name):
                    last_error = (
                        f"잘못된 tool_name '{tool_name}' — 영문, 숫자, 밑줄만 허용됩니다."
                    )
                    logger.error(
                        "skill_generation_invalid_name",
                        tool_name=tool_name,
                        attempt=attempt,
                    )
                    continue

                code = self._render_code(spec)
                yaml_content = self._render_yaml(spec)

                # 3. 보안 검사
                security_result = await self.security_checker.check(code, tool_name)
                if not security_result.passed:
                    issues_str = "; ".join(i.message for i in security_result.issues)
                    last_error = f"보안 검사 실패: {issues_str}"
                    logger.warning(
                        "skill_generation_security_failed",
                        tool_name=tool_name,
                        attempt=attempt,
                        issues=[i.message for i in security_result.issues],
                    )
                    continue

                # 4. 파일 저장
                tool_dir = self.output_dir / tool_name
                tool_dir.mkdir(parents=True, exist_ok=True)
                (tool_dir / "tool.py").write_text(code)
                (tool_dir / "tool.yaml").write_text(yaml_content)

                # 5. 핫로드 테스트
                try:
                    tools = self.tool_loader.load_tool(tool_dir)
                except Exception as e:
                    last_error = f"핫로드 실패 ({type(e).__name__}): {e}"
                    logger.error(
                        "skill_generation_load_failed",
                        tool_name=tool_name,
                        attempt=attempt,
                        error=str(e),
                    )
                    continue

                # 5.5. 런타임 테스트 (실제 함수 호출)
                runtime_results = []
                if tools:
                    try:
                        test_cases = await self.tester.generate_test_cases(
                            tool_name=tool_name,
                            tool_description=spec.get("description", ""),
                            parameters=getattr(tools[0], "_tool_parameters", {}),
                        )
                        runtime_results = await self.tester.run_runtime_tests(
                            tools[0], test_cases
                        )
                        failed = [r for r in runtime_results if not r.passed]
                        if failed:
                            error_details = "; ".join(
                                f"Test '{r.test_case.description}': {r.error}"
                                for r in failed
                            )
                            last_error = (
                                f"런타임 테스트 실패 ({len(failed)}/{len(runtime_results)}): "
                                f"{error_details}"
                            )
                            logger.warning(
                                "skill_generation_runtime_test_failed",
                                tool_name=tool_name,
                                attempt=attempt,
                                failed_count=len(failed),
                                total_count=len(runtime_results),
                            )
                            continue  # retry with error feedback
                    except Exception as e:
                        logger.warning(
                            "skill_runtime_test_error",
                            tool_name=tool_name,
                            error=str(e),
                        )
                        # Don't fail on test infrastructure error, proceed

                logger.info(
                    "skill_generation_success",
                    tool_name=tool_name,
                    tool_count=len(tools),
                )

                # 6. 성공: Hindsight에 스킬 정보 기록
                await self._retain_skill_memory(
                    tool_name=tool_name,
                    description=spec.get("description", ""),
                    tags=spec.get("tags", []),
                    code=code,
                )

                return GenerationResult(
                    success=True,
                    tool_name=tool_name,
                    tool_dir=tool_dir,
                    tools=tools,
                    code=code,
                    yaml_content=yaml_content,
                    security_result=security_result,
                    runtime_results=runtime_results,
                )

            except Exception as e:
                last_error = f"예기치 않은 오류 ({type(e).__name__}): {e}"
                logger.error(
                    "skill_generation_unexpected_error",
                    attempt=attempt,
                    error_type=type(e).__name__,
                    error=str(e),
                )
                continue

        return GenerationResult(
            success=False,
            tool_name="",
            tool_dir=Path(),
            tools=[],
            code="",
            yaml_content="",
            security_result=SecurityResult(passed=False, tool_name="", issues=[]),
        )

    async def _generate_search_queries(self, request: str) -> list[str]:  # [JS-K001.14]
        """LLM으로 요청에 맞는 타겟 검색 쿼리 2-3개를 생성합니다.

        Args:
            request: 사용자 요청

        Returns:
            검색 쿼리 리스트 (2-3개)
        """
        import litellm

        try:
            response = await litellm.acompletion(
                model="gpt-5.2",
                messages=[
                    {"role": "user", "content": QUERY_GEN_PROMPT.format(request=request)},
                ],
                temperature=0.2,
                max_tokens=200,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            data = json.loads(content)
            # JSON 배열이 바로 올 수도 있고, {"queries": [...]} 형태일 수도 있음
            if isinstance(data, list):
                queries = data
            elif isinstance(data, dict):
                queries = data.get("queries", data.get("search_queries", []))
            else:
                queries = []

            queries = [q for q in queries if isinstance(q, str) and len(q) > 3]
            logger.info("search_queries_generated", count=len(queries), queries=queries)
            return queries[:3]

        except Exception as e:
            logger.warning("search_query_gen_failed", error=str(e))
            # 폴백: 단순 쿼리 생성
            return [f"python {request} API example code"]

    async def _fetch_page_content(self, url: str) -> str:  # [JS-K001.15]
        """URL에서 페이지 본문 텍스트를 가져옵니다.

        GitHub README, 블로그, 문서 등에서 코드 블록을 포함한 텍스트를 추출합니다.

        Args:
            url: 크롤링할 URL

        Returns:
            정리된 텍스트 (최대 3000자)
        """
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(
                    url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (compatible; JediSOS/1.0; "
                            "+https://github.com/jedikim/jedisos)"
                        ),
                    },
                )
                resp.raise_for_status()
                html = resp.text

            # GitHub raw/API URL이면 텍스트 그대로 반환
            if "raw.githubusercontent.com" in url or resp.headers.get(
                "content-type", ""
            ).startswith("text/plain"):
                return html[:3000]

            # HTML에서 텍스트 추출 (간단한 태그 제거)
            text = _strip_html(html)

            # 코드 블록 우선 추출
            code_blocks = _extract_code_blocks(html)
            if code_blocks:
                code_text = "\n\n".join(code_blocks[:3])  # 상위 3개 코드 블록
                text = f"[CODE EXAMPLES]\n{code_text}\n\n[PAGE TEXT]\n{text}"

            return text[:3000]

        except Exception as e:
            logger.debug("page_fetch_failed", url=url, error=str(e))
            return ""

    async def _search_web(self, request: str) -> str:  # [JS-K001.9]
        """멀티 쿼리 웹 검색 + 상위 페이지 크롤링으로 참조 코드를 수집합니다.

        1단계: LLM으로 타겟 검색 쿼리 2-3개 생성
        2단계: DDGS로 각 쿼리 검색 (결과 병합 + 중복 제거)
        3단계: 상위 2개 URL의 실제 페이지 본문 크롤링

        Args:
            request: 사용자 요청 (예: "날씨 도구 만들어줘")

        Returns:
            검색 결과 + 페이지 본문 결합 텍스트
        """
        try:
            from ddgs import DDGS
        except ImportError:
            logger.warning("ddgs_not_installed")
            return ""

        # 1단계: 타겟 검색 쿼리 생성
        queries = await self._generate_search_queries(request)

        # 2단계: 멀티 쿼리 검색 + 중복 제거
        all_results: list[dict[str, str]] = []
        seen_urls: set[str] = set()

        try:
            with DDGS() as ddgs:
                for query in queries:
                    try:
                        results = list(ddgs.text(query, max_results=5))
                        for r in results:
                            href = r.get("href", "")
                            if href and href not in seen_urls:
                                seen_urls.add(href)
                                all_results.append(r)
                    except Exception as e:
                        logger.debug("search_query_failed", query=query, error=str(e))
        except Exception as e:
            logger.warning("web_search_failed", error=str(e))
            return ""

        if not all_results:
            logger.info("web_search_no_results", queries=queries)
            return ""

        # 검색 snippet 조합
        snippets: list[str] = []
        for r in all_results[:8]:
            title = r.get("title", "")
            body = r.get("body", "")
            href = r.get("href", "")
            snippets.append(f"- {title}\n  URL: {href}\n  {body}")

        reference = "\n".join(snippets)

        # 3단계: 상위 2개 URL에서 실제 페이지 본문 크롤링
        page_contents: list[str] = []
        crawl_targets = [
            r.get("href", "")
            for r in all_results[:4]
            if r.get("href", "")
            and any(
                domain in r.get("href", "")
                for domain in ("github.com", "readthedocs", "pypi.org", "dev.to", "medium.com")
            )
        ]

        # 우선 대상이 없으면 상위 2개 아무거나
        if not crawl_targets:
            crawl_targets = [r.get("href", "") for r in all_results[:2] if r.get("href", "")]

        for url in crawl_targets[:2]:
            content = await self._fetch_page_content(url)
            if content:
                page_contents.append(f"[Content from {url}]\n{content}")

        if page_contents:
            reference += "\n\n--- PAGE CONTENTS ---\n" + "\n\n".join(page_contents)

        logger.info(
            "web_search_complete",
            queries=queries,
            result_count=len(all_results),
            pages_crawled=len(page_contents),
            ref_length=len(reference),
        )
        return reference

    async def _search_similar_skills(self, request: str) -> str:  # [JS-K001.10]
        """Hindsight에서 기존/삭제된 유사 스킬을 검색합니다.

        Args:
            request: 사용자 요청

        Returns:
            유사 스킬 메모리 컨텍스트 (존재/삭제 이력 포함)
        """
        if self.memory is None:
            return ""

        try:
            result = await self.memory.recall(
                query=f"skill: {request}",
                bank_id=SKILL_MEMORY_BANK,
            )
            # Hindsight recall 응답에서 컨텍스트 추출 (dict/RecallResponse 모두 지원)
            context = ""
            if isinstance(result, dict):
                context = result.get("context", "")
                if not context:
                    memories = result.get("memories", [])
                    if memories:
                        parts = [
                            m.get("content", "") for m in memories if m.get("content")
                        ]
                        context = "\n".join(parts)
            elif result is not None:
                # RecallResponse 등 비-dict 객체 → 문자열 변환
                context = str(result)

            if context:
                logger.info("skill_memory_found", request=request, context_len=len(context))
            return context

        except Exception as e:
            logger.warning("skill_memory_search_failed", error=str(e))
            return ""

    async def _retain_skill_memory(  # [JS-K001.11]
        self,
        tool_name: str,
        description: str,
        tags: list[str],
        code: str,
    ) -> None:
        """생성된 스킬 정보를 Hindsight에 저장합니다.

        Args:
            tool_name: 스킬 이름
            description: 스킬 설명
            tags: 태그 목록
            code: 생성된 코드
        """
        if self.memory is None:
            return

        content = (
            f"[스킬 생성됨] {tool_name}\n"
            f"설명: {description}\n"
            f"태그: {', '.join(tags)}\n"
            f"생성일: {datetime.now(tz=UTC).strftime('%Y-%m-%d %H:%M')}\n"
            f"상태: 활성\n"
            f"코드:\n{code[:1000]}"  # 코드는 처음 1000자만
        )

        try:
            await self.memory.retain(
                content=content,
                context=f"JediSOS 자동 생성 스킬: {tool_name}",
                bank_id=SKILL_MEMORY_BANK,
            )
            logger.info("skill_memory_retained", tool_name=tool_name)
        except Exception as e:
            logger.warning("skill_memory_retain_failed", tool_name=tool_name, error=str(e))

    async def retain_skill_deletion(  # [JS-K001.12]
        self,
        tool_name: str,
        description: str = "",
    ) -> None:
        """삭제된 스킬 정보를 Hindsight에 기록합니다.

        이 정보는 향후 유사 스킬 생성 요청 시 '이미 삭제된 스킬'로 참조됩니다.

        Args:
            tool_name: 삭제된 스킬 이름
            description: 스킬 설명
        """
        if self.memory is None:
            return

        content = (
            f"[스킬 삭제됨] {tool_name}\n"
            f"설명: {description}\n"
            f"삭제일: {datetime.now(tz=UTC).strftime('%Y-%m-%d %H:%M')}\n"
            f"상태: 삭제됨\n"
            f"참고: 사용자가 이 스킬을 삭제했습니다. "
            f"동일한 스킬을 재생성하지 마세요."
        )

        try:
            await self.memory.retain(
                content=content,
                context=f"JediSOS 삭제된 스킬: {tool_name}",
                bank_id=SKILL_MEMORY_BANK,
            )
            logger.info("skill_deletion_retained", tool_name=tool_name)
        except Exception as e:
            logger.warning("skill_deletion_retain_failed", tool_name=tool_name, error=str(e))

    async def _call_llm(  # [JS-K001.5]
        self,
        request: str,
        reference_code: str = "",
        error_context: str = "",
        skill_memory: str = "",
    ) -> dict[str, Any] | None:
        """LLM에게 코드 생성을 요청합니다.

        Args:
            request: 사용자 요청
            reference_code: 웹 검색으로 찾은 참조 코드/문서
            error_context: 이전 시도의 에러 메시지 (재시도 시)
            skill_memory: Hindsight에서 검색된 유사 스킬 정보
        """
        import litellm

        # 참조 코드 섹션 구성
        reference_section = ""
        if reference_code:
            reference_section = (
                "\n--- REFERENCE CODE & API DOCS (from web search) ---\n"
                "Use these as reference for correct API URLs, parameters, and patterns.\n"
                "Trust this reference over your training data — it is more current.\n"
                f"{reference_code}\n"
                "--- END REFERENCE ---\n"
            )

        # 에러 피드백 섹션 구성
        error_section = ""
        if error_context:
            error_section = (
                "\n--- PREVIOUS ATTEMPT FAILED ---\n"
                f"Error: {error_context}\n"
                "Fix this error in your new attempt. Try a DIFFERENT approach if needed.\n"
                "--- END ERROR ---\n"
            )

        # 스킬 메모리 섹션 구성
        skill_memory_section = ""
        if skill_memory:
            skill_memory_section = (
                "\n--- EXISTING/DELETED SKILL HISTORY ---\n"
                f"{skill_memory}\n"
                "If a similar skill already exists, avoid duplication.\n"
                "If a similar skill was DELETED, do NOT recreate it.\n"
                "--- END HISTORY ---\n"
            )

        prompt = CODE_GEN_PROMPT.format(
            request=request,
            reference_section=reference_section,
            error_section=error_section,
            skill_memory_section=skill_memory_section,
        )

        try:
            response = await litellm.acompletion(
                model="gpt-5.2",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            logger.error("skill_gen_llm_error", error=str(e))
            return None

    def _render_code(self, spec: dict[str, Any]) -> str:  # [JS-K001.6]
        """tool.py 코드를 렌더링합니다.

        LLM이 "code" 필드로 완전한 코드를 직접 생성한 경우 그대로 사용하고,
        레거시 "functions" 형식이면 Jinja2 템플릿을 사용합니다.
        """
        # 새 방식: LLM이 완전한 코드를 직접 생성
        if spec.get("code"):
            return spec["code"]

        # 레거시 방식: Jinja2 템플릿 사용
        template_name = spec.get("template", "basic_tool")
        template_file = f"{template_name}.py.j2"

        try:
            template = self.jinja_env.get_template(template_file)
        except jinja2.TemplateNotFound:
            template = self.jinja_env.get_template("basic_tool.py.j2")

        return template.render(
            tool_name=spec.get("tool_name", "unnamed"),
            timestamp=datetime.now(tz=UTC).strftime("%Y-%m-%d"),
            functions=spec.get("functions", []),
        )

    def _render_yaml(self, spec: dict[str, Any]) -> str:  # [JS-K001.7]
        """tool.yaml을 렌더링합니다."""
        data = {
            "name": spec.get("tool_name", "unnamed"),
            "version": "1.0.0",
            "description": spec.get("description", ""),
            "author": "jedisos-agent",
            "auto_generated": True,
            "created": datetime.now(tz=UTC).strftime("%Y-%m-%d"),
            "license": "MIT",
            "tags": spec.get("tags", []),
        }

        env_required = spec.get("env_required", [])
        if env_required:
            data["env_required"] = env_required

        tools_spec = []
        for func in spec.get("functions", []):
            tools_spec.append(
                {
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                }
            )
        if tools_spec:
            data["tools"] = tools_spec

        return yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _strip_html(html: str) -> str:  # [JS-K001.16]
    """HTML에서 태그를 제거하고 텍스트만 추출합니다."""
    # script, style 블록 제거
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # 태그 제거
    text = re.sub(r"<[^>]+>", " ", text)
    # HTML 엔티티
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&#\d+;", "", text)
    # 연속 공백 정리
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_code_blocks(html: str) -> list[str]:  # [JS-K001.17]
    """HTML에서 코드 블록(<pre><code>...</code></pre>)을 추출합니다."""
    blocks: list[str] = []

    # <pre><code>...</code></pre> 패턴
    for match in re.finditer(
        r"<pre[^>]*>\s*<code[^>]*>(.*?)</code>\s*</pre>",
        html,
        re.DOTALL | re.IGNORECASE,
    ):
        code = match.group(1)
        code = re.sub(r"<[^>]+>", "", code)  # 내부 태그 제거
        code = re.sub(r"&amp;", "&", code)
        code = re.sub(r"&lt;", "<", code)
        code = re.sub(r"&gt;", ">", code)
        code = re.sub(r"&quot;", '"', code)
        code = re.sub(r"&#39;", "'", code)
        code = code.strip()
        if len(code) > 20:  # 너무 짧은 건 제외
            blocks.append(code)

    # <code>...</code> 단독 (인라인이 아닌 멀티라인만)
    if not blocks:
        for match in re.finditer(r"<code[^>]*>(.*?)</code>", html, re.DOTALL | re.IGNORECASE):
            code = match.group(1)
            if "\n" in code and len(code) > 50:
                code = re.sub(r"<[^>]+>", "", code)
                blocks.append(code.strip())

    return blocks


class GenerationResult:  # [JS-K001.8]
    """Skill 생성 결과."""

    def __init__(
        self,
        success: bool,
        tool_name: str,
        tool_dir: Path,
        tools: list[Any],
        code: str,
        yaml_content: str,
        security_result: SecurityResult,
        runtime_results: list[Any] | None = None,
    ) -> None:
        self.success = success
        self.tool_name = tool_name
        self.tool_dir = tool_dir
        self.tools = tools
        self.code = code
        self.yaml_content = yaml_content
        self.security_result = security_result
        self.runtime_results = runtime_results or []
