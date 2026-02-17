"""
[JS-K002] jedisos.forge.tester
생성된 Skill 코드 자동 검증 - AST/보안/패턴/타입/데코레이터 일괄 테스트

version: 1.0.0
created: 2026-02-18
modified: 2026-02-18
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import structlog
import yaml

from jedisos.forge.loader import ToolLoader
from jedisos.forge.security import CodeSecurityChecker, SecurityResult

logger = structlog.get_logger()


@dataclass
class TestResult:  # [JS-K002.1]
    """자동 테스트 결과."""

    passed: bool
    tool_name: str
    checks: dict[str, bool] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    security_result: SecurityResult | None = None


class SkillTester:  # [JS-K002.2]
    """생성된 Skill의 자동 검증을 수행합니다."""

    def __init__(self) -> None:
        self.security_checker = CodeSecurityChecker()
        self.tool_loader = ToolLoader()

    async def test_skill(self, tool_dir: Path) -> TestResult:  # [JS-K002.3]
        """도구 디렉토리의 Skill을 종합 테스트합니다.

        Args:
            tool_dir: 도구 디렉토리 경로 (tool.yaml + tool.py 포함)

        Returns:
            TestResult: 테스트 결과

        검증 순서:
            1. tool.yaml 존재 + 유효성
            2. tool.py 존재 + AST 파싱
            3. 보안 정적분석 (CodeSecurityChecker)
            4. 핫로드 가능 여부
            5. @tool 데코레이터 + 메타데이터 확인
        """
        tool_name = tool_dir.name
        checks: dict[str, bool] = {}
        errors: list[str] = []

        # 1. tool.yaml 검사
        yaml_ok, yaml_err = self._check_yaml(tool_dir)
        checks["yaml_valid"] = yaml_ok
        if yaml_err:
            errors.append(yaml_err)

        # 2. tool.py 존재 + AST 파싱
        syntax_ok, syntax_err = self._check_syntax(tool_dir)
        checks["syntax_valid"] = syntax_ok
        if syntax_err:
            errors.append(syntax_err)

        if not syntax_ok:
            return TestResult(
                passed=False,
                tool_name=tool_name,
                checks=checks,
                errors=errors,
            )

        # 3. 보안 정적분석
        code = (tool_dir / "tool.py").read_text()
        security_result = await self.security_checker.check(code, tool_name)
        checks["security_passed"] = security_result.passed
        if not security_result.passed:
            errors.extend(
                f"[{i.severity}] {i.category}: {i.message}" for i in security_result.issues
            )

        # 4. 핫로드 테스트
        load_ok, load_err, tools = self._check_load(tool_dir)
        checks["load_success"] = load_ok
        if load_err:
            errors.append(load_err)

        # 5. @tool 메타데이터 확인
        if load_ok and tools:
            meta_ok, meta_err = self._check_tool_meta(tools)
            checks["tool_meta_valid"] = meta_ok
            if meta_err:
                errors.append(meta_err)
        else:
            checks["tool_meta_valid"] = False

        passed = all(checks.values())

        logger.info(
            "skill_test_complete",
            tool_name=tool_name,
            passed=passed,
            checks=checks,
        )

        return TestResult(
            passed=passed,
            tool_name=tool_name,
            checks=checks,
            errors=errors,
            security_result=security_result,
        )

    async def test_code(self, code: str, tool_name: str) -> TestResult:  # [JS-K002.4]
        """코드 문자열을 직접 테스트합니다 (파일 저장 없이).

        Args:
            code: Python 코드 문자열
            tool_name: 도구 이름

        Returns:
            TestResult: 테스트 결과
        """
        checks: dict[str, bool] = {}
        errors: list[str] = []

        # AST 파싱
        try:
            ast.parse(code)
            checks["syntax_valid"] = True
        except SyntaxError as e:
            checks["syntax_valid"] = False
            errors.append(f"구문 오류: {e.msg}")
            return TestResult(
                passed=False,
                tool_name=tool_name,
                checks=checks,
                errors=errors,
            )

        # 보안 검사
        security_result = await self.security_checker.check(code, tool_name)
        checks["security_passed"] = security_result.passed
        if not security_result.passed:
            errors.extend(
                f"[{i.severity}] {i.category}: {i.message}" for i in security_result.issues
            )

        passed = all(checks.values())

        return TestResult(
            passed=passed,
            tool_name=tool_name,
            checks=checks,
            errors=errors,
            security_result=security_result,
        )

    def _check_yaml(self, tool_dir: Path) -> tuple[bool, str]:  # [JS-K002.5]
        """tool.yaml의 유효성을 검사합니다."""
        yaml_path = tool_dir / "tool.yaml"
        if not yaml_path.exists():
            return False, f"tool.yaml이 없습니다: {yaml_path}"

        try:
            data = yaml.safe_load(yaml_path.read_text())
        except yaml.YAMLError as e:
            return False, f"tool.yaml 파싱 오류: {e}"

        if not isinstance(data, dict):
            return False, "tool.yaml이 유효한 YAML 딕셔너리가 아닙니다"

        required_fields = ["name", "version", "description"]
        missing = [f for f in required_fields if f not in data]
        if missing:
            return False, f"tool.yaml 필수 필드 누락: {missing}"

        return True, ""

    def _check_syntax(self, tool_dir: Path) -> tuple[bool, str]:  # [JS-K002.6]
        """tool.py의 구문을 검사합니다."""
        tool_py = tool_dir / "tool.py"
        if not tool_py.exists():
            return False, f"tool.py가 없습니다: {tool_py}"

        try:
            ast.parse(tool_py.read_text())
        except SyntaxError as e:
            return False, f"구문 오류 (line {e.lineno}): {e.msg}"

        return True, ""

    def _check_load(self, tool_dir: Path) -> tuple[bool, str, list[Any]]:  # [JS-K002.7]
        """도구 핫로드를 테스트합니다."""
        try:
            tools = self.tool_loader.load_tool(tool_dir)
            if not tools:
                return False, "로드된 @tool 함수가 없습니다", []
            return True, "", tools
        except (ImportError, FileNotFoundError) as e:
            return False, f"핫로드 실패: {e}", []

    def _check_tool_meta(self, tools: list[Any]) -> tuple[bool, str]:  # [JS-K002.8]
        """@tool 메타데이터를 검사합니다."""
        for t in tools:
            if not hasattr(t, "_tool_name") or not t._tool_name:
                return False, f"도구에 _tool_name이 없습니다: {t}"
            if not hasattr(t, "_tool_description"):
                return False, f"도구에 _tool_description이 없습니다: {t}"
        return True, ""
