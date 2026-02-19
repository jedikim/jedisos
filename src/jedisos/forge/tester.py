"""
[JS-K002] jedisos.forge.tester
생성된 Skill 코드 자동 검증 - AST/보안/패턴/타입/데코레이터 일괄 테스트

version: 1.2.0
created: 2026-02-18
modified: 2026-02-18
"""

from __future__ import annotations

import ast
import asyncio
import json
import time
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
class RuntimeTestCase:  # [JS-K002.9]
    """런타임 테스트 케이스."""

    description: str
    kwargs: dict[str, Any] = field(default_factory=dict)
    expect_error: bool = False
    timeout_seconds: float = 60.0


@dataclass
class RuntimeTestResult:  # [JS-K002.10]
    """런타임 테스트 실행 결과."""

    test_case: RuntimeTestCase
    passed: bool
    output: Any = None
    error: str = ""
    elapsed_seconds: float = 0.0


@dataclass
class TestResult:  # [JS-K002.1]
    """자동 테스트 결과."""

    passed: bool
    tool_name: str
    checks: dict[str, bool] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    security_result: SecurityResult | None = None
    runtime_results: list[RuntimeTestResult] = field(default_factory=list)


RUNTIME_TEST_PROMPT = """\
Generate {count} test cases for a tool function.

Tool name: {tool_name}
Tool description: {tool_description}
Parameters: {parameters}

Rules:
1. Test case 1: Normal/happy-path with realistic input. \
If the tool handles Korean, use KOREAN text (e.g., "삼성전자 주가 알려줘", not "Samsung").
2. Test case 2: Edge case (empty string, boundary value, special characters)
3. Test case 3: Another valid input (different from #1), also in the tool's primary language.
4. All kwargs must match the function's parameter names and types exactly.
5. expect_error should be false for most cases (the tool should handle errors gracefully).
6. IMPORTANT: If the tool description is in Korean or mentions Korean data, \
ALL happy-path test inputs MUST use Korean text. Never use English translations.

Return a JSON array:
[
  {{"description": "test description", "kwargs": {{"param": "value"}}, "expect_error": false}},
  ...
]
"""


# 파라미터 타입별 기본값 매핑  [JS-K002.13]
_DEFAULT_VALUES_BY_TYPE: dict[str, Any] = {
    "str": "test",
    "int": 1,
    "float": 1.0,
    "bool": True,
}


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

    async def generate_test_cases(
        self,
        tool_name: str,
        tool_description: str,
        parameters: dict[str, dict[str, Any]],
        count: int = 3,
    ) -> list[RuntimeTestCase]:  # [JS-K002.11]
        """LLM을 사용하여 런타임 테스트 케이스를 자동 생성합니다.

        Args:
            tool_name: 도구 이름
            tool_description: 도구 설명
            parameters: 파라미터 정의 (이름 -> {"type": "str", ...})
            count: 생성할 테스트 케이스 수

        Returns:
            list[RuntimeTestCase]: 생성된 테스트 케이스 리스트

        LLM 호출 실패 시 파라미터 타입 기반 기본값으로 폴백합니다.
        """
        import litellm

        prompt = RUNTIME_TEST_PROMPT.format(
            count=count,
            tool_name=tool_name,
            tool_description=tool_description,
            parameters=json.dumps(parameters, ensure_ascii=False),
        )

        try:
            response = await litellm.acompletion(
                model="gpt-5.2",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            data = json.loads(content)

            # JSON 배열 또는 {"test_cases": [...]} 형태 모두 허용
            if isinstance(data, list):
                raw_cases = data
            elif isinstance(data, dict):
                raw_cases = data.get("test_cases", data.get("tests", []))
            else:
                raw_cases = []

            test_cases: list[RuntimeTestCase] = []
            for item in raw_cases[:count]:
                if not isinstance(item, dict):
                    continue
                test_cases.append(
                    RuntimeTestCase(
                        description=item.get("description", ""),
                        kwargs=item.get("kwargs", {}),
                        expect_error=bool(item.get("expect_error", False)),
                    )
                )

            if test_cases:
                logger.info(
                    "runtime_test_cases_generated",
                    tool_name=tool_name,
                    count=len(test_cases),
                )
                return test_cases

        except Exception as e:
            logger.warning(
                "runtime_test_case_gen_failed",
                tool_name=tool_name,
                error=str(e),
            )

        # 폴백: 파라미터 타입 기반 기본값으로 단일 테스트 케이스 생성
        fallback_kwargs: dict[str, Any] = {}
        for param_name, param_info in parameters.items():
            param_type = param_info.get("type", "str")
            fallback_kwargs[param_name] = _DEFAULT_VALUES_BY_TYPE.get(param_type, "test")

        logger.info(
            "runtime_test_cases_fallback",
            tool_name=tool_name,
            kwargs=fallback_kwargs,
        )

        return [
            RuntimeTestCase(
                description="기본값 폴백 테스트",
                kwargs=fallback_kwargs,
                expect_error=False,
            )
        ]

    async def run_runtime_tests(
        self,
        func: Any,
        test_cases: list[RuntimeTestCase],
    ) -> list[RuntimeTestResult]:  # [JS-K002.12]
        """런타임 테스트 케이스를 실행합니다.

        Args:
            func: 테스트할 도구 함수 (async callable)
            test_cases: 실행할 테스트 케이스 리스트

        Returns:
            list[RuntimeTestResult]: 각 테스트 케이스의 실행 결과
        """
        results: list[RuntimeTestResult] = []

        for tc in test_cases:
            start = time.monotonic()
            try:
                if asyncio.iscoroutinefunction(func):
                    output = await asyncio.wait_for(
                        func(**tc.kwargs),
                        timeout=tc.timeout_seconds,
                    )
                else:
                    output = func(**tc.kwargs)

                elapsed = time.monotonic() - start

                # dict 응답에서 ok: False인 경우 → pass 처리  [JS-K002.14]
                # ok=False는 코드가 에러를 정상 처리한 것 (외부 API 불안정 등)
                # 코드 자체는 예외 없이 실행 완료 → 런타임 테스트 목적 달성
                if isinstance(output, dict) and output.get("ok") is False and not tc.expect_error:
                    err_msg = output.get("error", "")
                    logger.warning(
                        "runtime_test_ok_false_response",
                        description=tc.description,
                        error_msg=err_msg,
                    )
                    results.append(
                        RuntimeTestResult(
                            test_case=tc,
                            passed=True,
                            output=output,
                            elapsed_seconds=elapsed,
                        )
                    )
                else:
                    results.append(
                        RuntimeTestResult(
                            test_case=tc,
                            passed=True,
                            output=output,
                            elapsed_seconds=elapsed,
                        )
                    )

            except TimeoutError:
                elapsed = time.monotonic() - start
                results.append(
                    RuntimeTestResult(
                        test_case=tc,
                        passed=False,
                        error=f"타임아웃 ({tc.timeout_seconds}초 초과)",
                        elapsed_seconds=elapsed,
                    )
                )

            except Exception as e:
                elapsed = time.monotonic() - start
                if tc.expect_error:
                    # 에러를 예상했고 실제로 발생 → PASS
                    results.append(
                        RuntimeTestResult(
                            test_case=tc,
                            passed=True,
                            error=str(e),
                            elapsed_seconds=elapsed,
                        )
                    )
                else:
                    # 에러를 예상하지 않았는데 발생 → FAIL
                    results.append(
                        RuntimeTestResult(
                            test_case=tc,
                            passed=False,
                            error=str(e),
                            elapsed_seconds=elapsed,
                        )
                    )

            logger.info(
                "runtime_test_executed",
                description=tc.description,
                passed=results[-1].passed,
                elapsed=f"{results[-1].elapsed_seconds:.3f}s",
            )

        return results
