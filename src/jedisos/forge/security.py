"""
[JS-K004] jedisos.forge.security
코드 보안 정적분석 - Bandit + 금지 패턴 + import 화이트리스트

version: 1.0.0
created: 2026-02-18
modified: 2026-02-18
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()

# 금지 패턴 — 생성 코드에서 사용 불가  [JS-K004.1]
FORBIDDEN_PATTERNS: list[str] = [
    r"os\.system",
    r"subprocess\.",
    r"eval\(",
    r"exec\(",
    r"__import__\(",
    r"open\(.*/etc/",
    r"shutil\.rmtree",
    r"requests\.get\(.*localhost",
    r"socket\.",
    r"ctypes\.",
]

# 허용 import 화이트리스트 (에이전트 생성 코드용)  [JS-K004.2]
ALLOWED_IMPORTS: list[str] = [
    "httpx",
    "aiohttp",
    "json",
    "re",
    "datetime",
    "pathlib",
    "typing",
    "pydantic",
    "jedisos.forge.decorator",
    "os",
    "math",
    "collections",
    "itertools",
    "functools",
    "hashlib",
    "base64",
    "urllib.parse",
    "html",
    "textwrap",
    "dataclasses",
]


@dataclass
class SecurityIssue:  # [JS-K004.3]
    """보안 검사에서 발견된 문제."""

    severity: str  # "high", "medium", "low"
    category: str  # "forbidden_pattern", "import", "syntax", "type_hint", "decorator"
    message: str
    line: int | None = None


@dataclass
class SecurityResult:  # [JS-K004.4]
    """보안 검사 결과."""

    passed: bool
    tool_name: str
    issues: list[SecurityIssue] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        """결과 요약을 반환합니다."""
        return {
            "passed": self.passed,
            "tool_name": self.tool_name,
            "issue_count": len(self.issues),
            "issues": [
                {"severity": i.severity, "category": i.category, "message": i.message}
                for i in self.issues
            ],
        }


class CodeSecurityChecker:  # [JS-K004.5]
    """생성된 도구 코드의 보안을 정적분석으로 검증."""

    def __init__(
        self,
        forbidden_patterns: list[str] | None = None,
        allowed_imports: list[str] | None = None,
    ) -> None:
        self.forbidden_patterns = forbidden_patterns or FORBIDDEN_PATTERNS
        self.allowed_imports = allowed_imports or ALLOWED_IMPORTS

    async def check(self, code: str, tool_name: str) -> SecurityResult:  # [JS-K004.6]
        """생성된 코드의 안전성을 검증합니다.

        Args:
            code: 검증할 Python 코드 문자열
            tool_name: 도구 이름

        Returns:
            SecurityResult: 검증 결과
        """
        issues: list[SecurityIssue] = []

        # 1. 구문 검사 (ast.parse)
        issues.extend(self._check_syntax(code))

        # 구문 오류가 있으면 나머지 검사 생략
        if any(i.category == "syntax" for i in issues):
            return SecurityResult(passed=False, tool_name=tool_name, issues=issues)

        # 2. 금지 패턴 검사
        issues.extend(self._check_forbidden_patterns(code))

        # 3. import 화이트리스트 검사
        issues.extend(self._check_imports(code))

        # 4. 타입 힌트 확인
        issues.extend(self._check_type_hints(code))

        # 5. @tool 데코레이터 확인
        issues.extend(self._check_tool_decorator(code))

        # 6. 비동기 함수 확인
        issues.extend(self._check_async(code))

        passed = not any(i.severity == "high" for i in issues)

        logger.info(
            "code_security_check",
            tool_name=tool_name,
            passed=passed,
            issue_count=len(issues),
        )

        return SecurityResult(passed=passed, tool_name=tool_name, issues=issues)

    def _check_syntax(self, code: str) -> list[SecurityIssue]:  # [JS-K004.7]
        """AST 파싱으로 구문을 검사합니다."""
        try:
            ast.parse(code)
        except SyntaxError as e:
            return [
                SecurityIssue(
                    severity="high",
                    category="syntax",
                    message=f"구문 오류: {e.msg}",
                    line=e.lineno,
                )
            ]
        return []

    def _check_forbidden_patterns(self, code: str) -> list[SecurityIssue]:  # [JS-K004.8]
        """금지 패턴을 검사합니다."""
        issues: list[SecurityIssue] = []
        for pattern in self.forbidden_patterns:
            for i, line in enumerate(code.splitlines(), 1):
                # 주석은 건너뜀
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if re.search(pattern, line):
                    issues.append(
                        SecurityIssue(
                            severity="high",
                            category="forbidden_pattern",
                            message=f"금지 패턴 발견: {pattern}",
                            line=i,
                        )
                    )
        return issues

    def _check_imports(self, code: str) -> list[SecurityIssue]:  # [JS-K004.9]
        """import 화이트리스트를 검사합니다."""
        issues: list[SecurityIssue] = []
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return issues

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if not self._is_allowed_import(alias.name):
                        issues.append(
                            SecurityIssue(
                                severity="high",
                                category="import",
                                message=f"허용되지 않는 import: {alias.name}",
                                line=node.lineno,
                            )
                        )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if not self._is_allowed_import(module):
                    issues.append(
                        SecurityIssue(
                            severity="high",
                            category="import",
                            message=f"허용되지 않는 import: {module}",
                            line=node.lineno,
                        )
                    )

        return issues

    def _is_allowed_import(self, module_name: str) -> bool:
        """import가 허용 목록에 있는지 확인합니다."""
        for allowed in self.allowed_imports:
            if module_name == allowed or module_name.startswith(f"{allowed}."):
                return True
        return False

    def _check_type_hints(self, code: str) -> list[SecurityIssue]:  # [JS-K004.10]
        """함수에 타입 힌트가 있는지 확인합니다."""
        issues: list[SecurityIssue] = []
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return issues

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is None:
                issues.append(
                    SecurityIssue(
                        severity="medium",
                        category="type_hint",
                        message=f"함수 '{node.name}'에 반환 타입 힌트가 없습니다",
                        line=node.lineno,
                    )
                )

        return issues

    def _check_tool_decorator(self, code: str) -> list[SecurityIssue]:  # [JS-K004.11]
        """@tool 데코레이터 사용을 확인합니다."""
        issues: list[SecurityIssue] = []
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return issues

        has_tool_decorator = False
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call):
                        func = decorator.func
                        if isinstance(func, ast.Name) and func.id == "tool":
                            has_tool_decorator = True
                    elif isinstance(decorator, ast.Name) and decorator.id == "tool":
                        has_tool_decorator = True

        if not has_tool_decorator:
            issues.append(
                SecurityIssue(
                    severity="medium",
                    category="decorator",
                    message="@tool 데코레이터를 사용하는 함수가 없습니다",
                )
            )

        return issues

    def _check_async(self, code: str) -> list[SecurityIssue]:  # [JS-K004.12]
        """비동기 함수 여부를 확인합니다."""
        issues: list[SecurityIssue] = []
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return issues

        has_async = any(isinstance(node, ast.AsyncFunctionDef) for node in ast.walk(tree))

        if not has_async:
            issues.append(
                SecurityIssue(
                    severity="low",
                    category="async",
                    message="비동기 함수(async def)를 권장합니다",
                )
            )

        return issues
