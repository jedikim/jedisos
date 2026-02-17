"""
[JS-K001] jedisos.forge.generator
LLM 기반 Skill 코드 생성기 - tool.yaml + tool.py를 Jinja2 템플릿으로 생성

version: 1.0.0
created: 2026-02-18
modified: 2026-02-18
dependencies: jinja2>=3.1, litellm>=1.81
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jinja2
import structlog
import yaml

from jedisos.forge.loader import ToolLoader
from jedisos.forge.security import CodeSecurityChecker, SecurityResult

logger = structlog.get_logger()

# tool.yaml Jinja2 템플릿  [JS-K001.1]
TOOL_YAML_TEMPLATE = """\
name: {{ tool_name }}
version: "1.0.0"
description: "{{ description }}"
author: jedisos-agent
auto_generated: true
created: {{ timestamp }}
license: MIT
tags: {{ tags }}
{% if env_required %}
env_required:
{% for env in env_required %}
  - {{ env }}
{% endfor %}
{% endif %}
tools:
{% for tool in tools %}
  - name: {{ tool.name }}
    description: "{{ tool.description }}"
    parameters:
{% for param_name, param_info in tool.parameters.items() %}
      {{ param_name }}: { type: {{ param_info.type }}{% if param_info.get('required', False) %}, required: true{% endif %}{% if param_info.get('default') is not none %}, default: {{ param_info.default }}{% endif %} }
{% endfor %}
{% endfor %}
"""

# LLM에게 보낼 코드 생성 프롬프트  [JS-K001.2]
CODE_GEN_PROMPT = """\
You are a JediSOS Skill code generator. Generate a Python tool file.

Requirements:
1. Use the @tool decorator from jedisos.forge.decorator
2. All functions MUST be async (async def)
3. All functions MUST have type hints (parameters and return type)
4. Only use allowed imports: httpx, aiohttp, json, re, datetime, pathlib, typing, \
pydantic, jedisos.forge.decorator, os, math, collections, itertools, functools, \
hashlib, base64, urllib.parse, html, textwrap, dataclasses
5. NEVER use: subprocess, eval, exec, __import__, os.system, socket, ctypes, shutil.rmtree
6. Return ONLY a JSON object with this exact structure:

{{
    "tool_name": "name_of_tool",
    "description": "Brief description",
    "template": "basic_tool",
    "tags": ["tag1", "tag2"],
    "env_required": [],
    "functions": [
        {{
            "name": "function_name",
            "description": "What it does",
            "parameters": "param1: str, param2: int = 10",
            "return_type": "dict",
            "docstring": "Detailed description",
            "implementation": "return {{\\"result\\": param1}}"
        }}
    ]
}}

User request: {request}
"""


class SkillGenerator:  # [JS-K001.3]
    """LLM + Jinja2를 사용한 Skill 코드 생성기."""

    def __init__(
        self,
        output_dir: Path | None = None,
        max_retries: int = 3,
    ) -> None:
        self.output_dir = output_dir or Path("tools/generated")
        self.max_retries = max_retries
        self.security_checker = CodeSecurityChecker()
        self.tool_loader = ToolLoader()

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
        for attempt in range(1, self.max_retries + 1):
            logger.info("skill_generation_start", request=request, attempt=attempt)

            # 1. LLM으로 코드 스펙 생성 (또는 직접 주입)
            if llm_response is None:
                spec = await self._call_llm(request)
            else:
                spec = llm_response

            if spec is None:
                logger.error("skill_generation_llm_failed", attempt=attempt)
                continue

            # 2. 템플릿으로 코드 렌더링
            tool_name = spec.get("tool_name", "unnamed")
            code = self._render_code(spec)
            yaml_content = self._render_yaml(spec)

            # 3. 보안 검사
            security_result = await self.security_checker.check(code, tool_name)
            if not security_result.passed:
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
            except (ImportError, FileNotFoundError) as e:
                logger.error(
                    "skill_generation_load_failed",
                    tool_name=tool_name,
                    attempt=attempt,
                    error=str(e),
                )
                continue

            logger.info(
                "skill_generation_success",
                tool_name=tool_name,
                tool_count=len(tools),
            )

            return GenerationResult(
                success=True,
                tool_name=tool_name,
                tool_dir=tool_dir,
                tools=tools,
                code=code,
                yaml_content=yaml_content,
                security_result=security_result,
            )

        return GenerationResult(
            success=False,
            tool_name="",
            tool_dir=Path(),
            tools=[],
            code="",
            yaml_content="",
            security_result=SecurityResult(passed=False, tool_name="", issues=[]),
        )

    async def _call_llm(self, request: str) -> dict[str, Any] | None:  # [JS-K001.5]
        """LLM에게 코드 생성을 요청합니다."""
        import litellm

        prompt = CODE_GEN_PROMPT.format(request=request)

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
        """Jinja2 템플릿으로 tool.py 코드를 렌더링합니다."""
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
    ) -> None:
        self.success = success
        self.tool_name = tool_name
        self.tool_dir = tool_dir
        self.tools = tools
        self.code = code
        self.yaml_content = yaml_content
        self.security_result = security_result
