"""
[JS-T012] tests.unit.test_forge
Forge 자가 코딩 엔진 단위 테스트 - decorator, security, generator, tester, runtime, context

version: 1.2.0
created: 2026-02-18
modified: 2026-02-18
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from jedisos.forge import context as skill_context
from jedisos.forge.decorator import tool
from jedisos.forge.generator import SKILL_MEMORY_BANK, SkillGenerator
from jedisos.forge.security import (
    ALLOWED_IMPORTS,
    FORBIDDEN_PATTERNS,
    CodeSecurityChecker,
)
from jedisos.forge.tester import RuntimeTestCase, SkillTester


class TestToolDecorator:  # [JS-T012.1]
    """@tool 데코레이터 테스트."""

    def test_basic_decoration(self):
        @tool(name="add", description="더하기")
        async def add(a: int, b: int) -> int:
            return a + b

        assert add._is_jedisos_tool is True
        assert add._tool_name == "add"
        assert add._tool_description == "더하기"

    def test_tags(self):
        @tool(name="calc", description="계산", tags=["math", "utility"])
        async def calc(x: int) -> int:
            return x

        assert calc._tool_tags == ["math", "utility"]

    def test_parameter_extraction(self):
        @tool(name="greet", description="인사")
        async def greet(name: str, count: int = 1) -> str:
            return name * count

        params = greet._tool_parameters
        assert "name" in params
        assert params["name"]["type"] == "string"
        assert params["name"]["required"] is True
        assert "count" in params
        assert params["count"]["type"] == "integer"
        assert params["count"]["required"] is False
        assert params["count"]["default"] == 1

    def test_description_from_docstring(self):
        @tool(name="func")
        async def func(x: int) -> int:
            """함수 설명입니다."""
            return x

        assert func._tool_description == "함수 설명입니다."

    async def test_async_execution(self):
        @tool(name="double", description="2배")
        async def double(x: int) -> int:
            return x * 2

        result = await double(5)
        assert result == 10

    def test_sync_function_wrapped(self):
        @tool(name="sync_add", description="동기 더하기")
        def sync_add(a: int, b: int) -> int:
            return a + b

        assert sync_add._is_jedisos_tool is True
        assert sync_add._tool_name == "sync_add"


class TestCodeSecurityChecker:  # [JS-T012.2]
    """보안 정적분석 테스트."""

    async def test_safe_code_passes(self):
        checker = CodeSecurityChecker()
        code = """
from jedisos.forge.decorator import tool

@tool(name="add", description="더하기")
async def add(a: int, b: int) -> int:
    return a + b
"""
        result = await checker.check(code, "test")
        assert result.passed is True
        assert len(result.issues) == 0

    async def test_forbidden_subprocess(self):
        checker = CodeSecurityChecker()
        code = "import subprocess\nsubprocess.run(['ls'])"
        result = await checker.check(code, "test")
        assert result.passed is False
        assert any(i.category == "forbidden_pattern" for i in result.issues)

    async def test_forbidden_eval(self):
        checker = CodeSecurityChecker()
        code = "result = eval('1+1')"
        result = await checker.check(code, "test")
        assert result.passed is False

    async def test_forbidden_exec(self):
        checker = CodeSecurityChecker()
        code = "exec('print(1)')"
        result = await checker.check(code, "test")
        assert result.passed is False

    async def test_forbidden_os_system(self):
        checker = CodeSecurityChecker()
        code = "import os\nos.system('ls')"
        result = await checker.check(code, "test")
        assert result.passed is False

    async def test_disallowed_import(self):
        checker = CodeSecurityChecker()
        code = "import socket\nsocket.connect()"
        result = await checker.check(code, "test")
        assert result.passed is False
        assert any(i.category == "import" for i in result.issues)

    async def test_allowed_imports(self):
        checker = CodeSecurityChecker()
        code = """
import json
import re
from datetime import datetime
from jedisos.forge.decorator import tool

@tool(name="t", description="t")
async def t() -> str:
    return json.dumps({"ok": True})
"""
        result = await checker.check(code, "test")
        assert result.passed is True

    async def test_syntax_error(self):
        checker = CodeSecurityChecker()
        code = "def invalid(:\n    pass"
        result = await checker.check(code, "test")
        assert result.passed is False
        assert any(i.category == "syntax" for i in result.issues)

    async def test_no_type_hint_warning(self):
        checker = CodeSecurityChecker()
        code = """
from jedisos.forge.decorator import tool

@tool(name="t", description="t")
async def no_hint(x):
    return x
"""
        result = await checker.check(code, "test")
        assert any(i.category == "type_hint" for i in result.issues)

    async def test_no_decorator_warning(self):
        checker = CodeSecurityChecker()
        code = "async def bare(x: int) -> int:\n    return x"
        result = await checker.check(code, "test")
        assert any(i.category == "decorator" for i in result.issues)

    async def test_no_async_info(self):
        checker = CodeSecurityChecker()
        code = """
from jedisos.forge.decorator import tool

@tool(name="t", description="t")
def sync_func(x: int) -> int:
    return x
"""
        result = await checker.check(code, "test")
        assert any(i.category == "async" for i in result.issues)

    def test_forbidden_patterns_list(self):
        assert len(FORBIDDEN_PATTERNS) >= 8

    def test_allowed_imports_list(self):
        assert "httpx" in ALLOWED_IMPORTS
        assert "jedisos.forge.decorator" in ALLOWED_IMPORTS

    async def test_summary(self):
        checker = CodeSecurityChecker()
        code = "import subprocess"
        result = await checker.check(code, "test")
        summary = result.summary()
        assert "passed" in summary
        assert "issue_count" in summary
        assert summary["issue_count"] > 0

    async def test_comment_lines_ignored(self):
        """주석 내 금지 패턴은 무시."""
        checker = CodeSecurityChecker()
        code = """
from jedisos.forge.decorator import tool

# subprocess.run은 금지됩니다
@tool(name="t", description="t")
async def t() -> str:
    return "ok"
"""
        result = await checker.check(code, "t")
        # 주석이므로 forbidden_pattern 이슈 없어야 함
        assert not any(
            i.category == "forbidden_pattern" and i.severity == "high" for i in result.issues
        )


class TestSkillGenerator:  # [JS-T012.3]
    """Skill 코드 생성기 테스트."""

    async def test_generate_with_memory(self, tmp_path):
        """Hindsight 메모리와 함께 생성 — 메모리에 retain 호출 확인."""
        mock_memory = AsyncMock()
        mock_memory.recall.return_value = {"context": ""}
        mock_memory.retain.return_value = {"status": "ok"}

        generator = SkillGenerator(output_dir=tmp_path, memory=mock_memory)
        spec = {
            "tool_name": "calc_mem",
            "description": "메모리 테스트 계산기",
            "template": "basic_tool",
            "tags": ["test"],
            "env_required": [],
            "functions": [
                {
                    "name": "add",
                    "description": "더하기",
                    "parameters": "a: int, b: int",
                    "return_type": "int",
                    "docstring": "두 수를 더합니다.",
                    "implementation": "return a + b",
                }
            ],
        }

        result = await generator.generate("계산기", llm_response=spec)
        assert result.success is True

        # Hindsight recall 호출 확인 (유사 스킬 검색)
        mock_memory.recall.assert_called_once_with(query="skill: 계산기", bank_id=SKILL_MEMORY_BANK)

        # Hindsight retain 호출 확인 (생성된 스킬 기록)
        mock_memory.retain.assert_called_once()
        retain_args = mock_memory.retain.call_args
        assert "calc_mem" in retain_args.kwargs["content"]
        assert retain_args.kwargs["bank_id"] == SKILL_MEMORY_BANK

    async def test_generate_without_memory(self, tmp_path):
        """메모리 없이도 정상 동작 확인."""
        generator = SkillGenerator(output_dir=tmp_path, memory=None)
        spec = {
            "tool_name": "no_mem",
            "description": "메모리 없는 도구",
            "template": "basic_tool",
            "tags": [],
            "env_required": [],
            "functions": [
                {
                    "name": "echo",
                    "description": "에코",
                    "parameters": "msg: str",
                    "return_type": "str",
                    "docstring": "그대로 반환",
                    "implementation": "return msg",
                }
            ],
        }
        result = await generator.generate("에코 도구", llm_response=spec)
        assert result.success is True

    async def test_search_web(self, tmp_path):
        """웹 검색 성공 시 참조 코드 반환."""
        generator = SkillGenerator(output_dir=tmp_path)

        mock_results = [
            {
                "title": "Weather API Example",
                "body": "Use Open-Meteo...",
                "href": "https://example.com",
            },
            {"title": "Python httpx", "body": "async HTTP client", "href": "https://example2.com"},
        ]

        with patch("ddgs.DDGS") as mock_ddgs_cls:
            mock_ddgs = MagicMock()
            mock_ddgs.__enter__ = MagicMock(return_value=mock_ddgs)
            mock_ddgs.__exit__ = MagicMock(return_value=False)
            mock_ddgs.text.return_value = mock_results
            mock_ddgs_cls.return_value = mock_ddgs

            result = await generator._search_web("날씨 도구")
            assert "Weather API Example" in result
            assert "Open-Meteo" in result

    async def test_search_web_no_results(self, tmp_path):
        """웹 검색 결과 없을 시 빈 문자열 반환."""
        generator = SkillGenerator(output_dir=tmp_path)

        with patch("ddgs.DDGS") as mock_ddgs_cls:
            mock_ddgs = MagicMock()
            mock_ddgs.__enter__ = MagicMock(return_value=mock_ddgs)
            mock_ddgs.__exit__ = MagicMock(return_value=False)
            mock_ddgs.text.return_value = []
            mock_ddgs_cls.return_value = mock_ddgs

            result = await generator._search_web("존재하지 않는 도구")
            assert result == ""

    async def test_search_web_exception(self, tmp_path):
        """웹 검색 실패 시 빈 문자열 반환."""
        generator = SkillGenerator(output_dir=tmp_path)

        with patch("ddgs.DDGS") as mock_ddgs_cls:
            mock_ddgs_cls.side_effect = Exception("network error")
            result = await generator._search_web("날씨")
            assert result == ""

    async def test_search_similar_skills(self, tmp_path):
        """Hindsight에서 유사 스킬 검색."""
        mock_memory = AsyncMock()
        mock_memory.recall.return_value = {"context": "[스킬 생성됨] weather\n설명: 날씨 조회"}

        generator = SkillGenerator(output_dir=tmp_path, memory=mock_memory)
        result = await generator._search_similar_skills("날씨 도구")
        assert "weather" in result
        assert "날씨 조회" in result

    async def test_search_similar_skills_no_memory(self, tmp_path):
        """메모리 없으면 빈 문자열."""
        generator = SkillGenerator(output_dir=tmp_path, memory=None)
        result = await generator._search_similar_skills("날씨")
        assert result == ""

    async def test_retain_skill_deletion(self, tmp_path):
        """삭제 이력이 Hindsight에 기록되는지 확인."""
        mock_memory = AsyncMock()
        mock_memory.retain.return_value = {"status": "ok"}

        generator = SkillGenerator(output_dir=tmp_path, memory=mock_memory)
        await generator.retain_skill_deletion(tool_name="old_weather", description="날씨 도구")

        mock_memory.retain.assert_called_once()
        retain_args = mock_memory.retain.call_args
        assert "삭제됨" in retain_args.kwargs["content"]
        assert "old_weather" in retain_args.kwargs["content"]
        assert "재생성하지 마세요" in retain_args.kwargs["content"]

    async def test_error_feedback_in_retry(self, tmp_path):
        """에러 피드백이 재시도 프롬프트에 포함되는지 확인."""
        mock_memory = AsyncMock()
        mock_memory.recall.return_value = {"context": ""}

        generator = SkillGenerator(output_dir=tmp_path, max_retries=2, memory=mock_memory)

        # 첫 번째: 잘못된 이름으로 실패, 두 번째: 성공
        bad_spec = {
            "tool_name": "bad-name!",
            "description": "실패",
            "tags": [],
            "env_required": [],
            "code": "pass",
        }
        good_spec = {
            "tool_name": "good_name",
            "description": "성공",
            "template": "basic_tool",
            "tags": [],
            "env_required": [],
            "functions": [
                {
                    "name": "ok",
                    "description": "ok",
                    "parameters": "",
                    "return_type": "str",
                    "docstring": "ok",
                    "implementation": "return 'ok'",
                }
            ],
        }

        with (
            patch.object(generator, "_call_llm", side_effect=[bad_spec, good_spec]) as mock_llm,
            patch.object(generator, "_search_web", return_value="ref code"),
        ):
            result = await generator.generate("도구 만들기")
            assert result.success is True
            # 두 번째 호출에 에러 컨텍스트가 포함되어야 함
            second_call = mock_llm.call_args_list[1]
            assert "bad-name" in second_call.kwargs.get("error_context", "")

    async def test_generate_with_spec(self, tmp_path):
        generator = SkillGenerator(output_dir=tmp_path)
        spec = {
            "tool_name": "test_calc",
            "description": "테스트 계산기",
            "template": "basic_tool",
            "tags": ["math"],
            "env_required": [],
            "functions": [
                {
                    "name": "add",
                    "description": "더하기",
                    "parameters": "a: int, b: int",
                    "return_type": "int",
                    "docstring": "두 수를 더합니다.",
                    "implementation": "return a + b",
                }
            ],
        }

        result = await generator.generate("계산기 도구", llm_response=spec)
        assert result.success is True
        assert result.tool_name == "test_calc"
        assert len(result.tools) == 1
        assert (tmp_path / "test_calc" / "tool.py").exists()
        assert (tmp_path / "test_calc" / "tool.yaml").exists()

    async def test_generate_security_fail(self, tmp_path):
        """보안 검사 실패 시 재시도 후 실패."""
        generator = SkillGenerator(output_dir=tmp_path, max_retries=1)
        spec = {
            "tool_name": "bad_tool",
            "description": "위험한 도구",
            "template": "basic_tool",
            "tags": [],
            "env_required": [],
            "functions": [
                {
                    "name": "danger",
                    "description": "위험",
                    "parameters": "",
                    "return_type": "str",
                    "docstring": "위험한 함수",
                    "implementation": "import subprocess; return subprocess.run(['ls'])",
                }
            ],
        }

        result = await generator.generate("위험한 도구", llm_response=spec)
        assert result.success is False

    async def test_render_yaml(self, tmp_path):
        generator = SkillGenerator(output_dir=tmp_path)
        spec = {
            "tool_name": "weather",
            "description": "날씨 조회",
            "tags": ["weather", "api"],
            "env_required": ["API_KEY"],
            "functions": [
                {"name": "get_weather", "description": "현재 날씨"},
            ],
        }
        yaml_content = generator._render_yaml(spec)
        assert "weather" in yaml_content
        assert "날씨 조회" in yaml_content

    async def test_render_code(self, tmp_path):
        generator = SkillGenerator(output_dir=tmp_path)
        spec = {
            "tool_name": "math_tool",
            "template": "basic_tool",
            "functions": [
                {
                    "name": "multiply",
                    "description": "곱하기",
                    "parameters": "a: int, b: int",
                    "return_type": "int",
                    "docstring": "두 수를 곱합니다.",
                    "implementation": "return a * b",
                }
            ],
        }
        code = generator._render_code(spec)
        assert "multiply" in code
        assert "@tool" in code
        assert "async def" in code


class TestSkillTester:  # [JS-T012.4]
    """자동 테스트 실행기 테스트."""

    async def test_valid_skill(self, tmp_path):
        """유효한 Skill은 테스트 통과."""
        tool_dir = tmp_path / "calc"
        tool_dir.mkdir()
        (tool_dir / "tool.yaml").write_text('name: calc\nversion: "1.0.0"\ndescription: "계산기"\n')
        (tool_dir / "tool.py").write_text(
            "from jedisos.forge.decorator import tool\n\n"
            '@tool(name="add", description="더하기")\n'
            "async def add(a: int, b: int) -> int:\n"
            "    return a + b\n"
        )

        tester = SkillTester()
        result = await tester.test_skill(tool_dir)
        assert result.passed is True
        assert result.checks["yaml_valid"] is True
        assert result.checks["syntax_valid"] is True
        assert result.checks["security_passed"] is True
        assert result.checks["load_success"] is True
        assert result.checks["tool_meta_valid"] is True

    async def test_missing_yaml(self, tmp_path):
        tool_dir = tmp_path / "no_yaml"
        tool_dir.mkdir()
        (tool_dir / "tool.py").write_text(
            "from jedisos.forge.decorator import tool\n\n"
            '@tool(name="t", description="t")\n'
            "async def t() -> str:\n"
            '    return "ok"\n'
        )

        tester = SkillTester()
        result = await tester.test_skill(tool_dir)
        assert result.checks["yaml_valid"] is False

    async def test_syntax_error(self, tmp_path):
        tool_dir = tmp_path / "bad_syntax"
        tool_dir.mkdir()
        (tool_dir / "tool.yaml").write_text('name: bad\nversion: "1.0.0"\ndescription: "bad"\n')
        (tool_dir / "tool.py").write_text("def invalid(:\n    pass")

        tester = SkillTester()
        result = await tester.test_skill(tool_dir)
        assert result.passed is False
        assert result.checks["syntax_valid"] is False

    async def test_security_fail(self, tmp_path):
        tool_dir = tmp_path / "insecure"
        tool_dir.mkdir()
        (tool_dir / "tool.yaml").write_text(
            'name: insecure\nversion: "1.0.0"\ndescription: "insecure"\n'
        )
        (tool_dir / "tool.py").write_text("import subprocess\nsubprocess.run(['ls'])")

        tester = SkillTester()
        result = await tester.test_skill(tool_dir)
        assert result.checks["security_passed"] is False

    async def test_code_only(self):
        """코드 문자열만으로 테스트."""
        tester = SkillTester()
        code = """
from jedisos.forge.decorator import tool

@tool(name="t", description="t")
async def t(x: int) -> int:
    return x * 2
"""
        result = await tester.test_code(code, "inline_test")
        assert result.passed is True
        assert result.checks["syntax_valid"] is True
        assert result.checks["security_passed"] is True

    async def test_code_syntax_error(self):
        tester = SkillTester()
        result = await tester.test_code("def bad(:\n  pass", "bad")
        assert result.passed is False


class TestRuntimeTesting:  # [JS-T012.5]
    """런타임 테스트 기능 테스트."""

    async def test_run_runtime_tests_success(self):
        """정상 함수 실행 시 모든 테스트 통과."""

        @tool(name="add", description="더하기")
        async def add(a: int, b: int) -> int:
            return a + b

        tester = SkillTester()
        test_cases = [
            RuntimeTestCase(description="정상 덧셈", kwargs={"a": 1, "b": 2}),
            RuntimeTestCase(description="0 더하기", kwargs={"a": 0, "b": 0}),
            RuntimeTestCase(description="음수", kwargs={"a": -1, "b": 5}),
        ]

        results = await tester.run_runtime_tests(add, test_cases)
        assert len(results) == 3
        assert all(r.passed for r in results)
        assert results[0].output == 3
        assert results[1].output == 0
        assert results[2].output == 4
        assert all(r.elapsed_seconds >= 0 for r in results)

    async def test_run_runtime_tests_exception(self):
        """함수가 예외를 발생시키면 실패."""

        @tool(name="fail", description="실패")
        async def fail(x: str) -> dict:
            raise ValueError(f"잘못된 값: {x}")

        tester = SkillTester()
        test_cases = [
            RuntimeTestCase(description="예외 발생", kwargs={"x": "bad"}),
        ]

        results = await tester.run_runtime_tests(fail, test_cases)
        assert len(results) == 1
        assert results[0].passed is False
        assert "잘못된 값" in results[0].error

    async def test_run_runtime_tests_expected_error(self):
        """expect_error=True인 경우 예외 발생이 정상."""

        @tool(name="validate", description="검증")
        async def validate(x: str) -> dict:
            if not x:
                raise ValueError("빈 값")
            return {"ok": True}

        tester = SkillTester()
        test_cases = [
            RuntimeTestCase(
                description="빈 문자열 에러 기대",
                kwargs={"x": ""},
                expect_error=True,
            ),
        ]

        results = await tester.run_runtime_tests(validate, test_cases)
        assert len(results) == 1
        assert results[0].passed is True

    async def test_run_runtime_tests_timeout(self):
        """타임아웃 초과 시 실패."""

        @tool(name="slow", description="느린 함수")
        async def slow(x: str) -> str:
            await asyncio.sleep(10)
            return x

        tester = SkillTester()
        test_cases = [
            RuntimeTestCase(
                description="타임아웃 테스트",
                kwargs={"x": "test"},
                timeout_seconds=0.1,  # 0.1초 타임아웃
            ),
        ]

        results = await tester.run_runtime_tests(slow, test_cases)
        assert len(results) == 1
        assert results[0].passed is False
        assert "타임아웃" in results[0].error or "timeout" in results[0].error.lower()

    async def test_run_runtime_tests_sync_function(self):
        """동기 함수도 정상 실행."""

        @tool(name="sync_double", description="동기 2배")
        def sync_double(x: int) -> int:
            return x * 2

        tester = SkillTester()
        test_cases = [
            RuntimeTestCase(description="동기 실행", kwargs={"x": 5}),
        ]

        results = await tester.run_runtime_tests(sync_double, test_cases)
        assert len(results) == 1
        assert results[0].passed is True
        assert results[0].output == 10

    async def test_run_runtime_tests_dict_ok_false(self):
        """ok=False 반환은 실패가 아님 (정상 에러 응답)."""

        @tool(name="search", description="검색")
        async def search(query: str) -> dict:
            return {"ok": False, "error": "결과 없음"}

        tester = SkillTester()
        test_cases = [
            RuntimeTestCase(description="결과 없음", kwargs={"query": "xxx"}),
        ]

        results = await tester.run_runtime_tests(search, test_cases)
        assert len(results) == 1
        assert results[0].passed is True  # ok=False여도 통과

    async def test_generate_test_cases_with_mock_llm(self):
        """LLM mock으로 테스트 케이스 생성 확인."""
        tester = SkillTester()

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='[{"description": "정상 입력", "kwargs": {"query": "삼성전자"}, "expect_error": false}]'
                )
            )
        ]

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            cases = await tester.generate_test_cases(
                tool_name="stock",
                tool_description="주식 조회",
                parameters={"query": {"type": "string", "required": True}},
            )

        assert len(cases) >= 1
        assert cases[0].description == "정상 입력"
        assert cases[0].kwargs == {"query": "삼성전자"}

    async def test_generate_test_cases_fallback(self):
        """LLM 실패 시 기본값 폴백."""
        tester = SkillTester()

        with patch(
            "litellm.acompletion", new_callable=AsyncMock, side_effect=Exception("LLM down")
        ):
            cases = await tester.generate_test_cases(
                tool_name="calc",
                tool_description="계산기",
                parameters={"x": {"type": "integer", "required": True}},
            )

        assert len(cases) >= 1
        assert "x" in cases[0].kwargs

    async def test_test_result_has_runtime_results(self, tmp_path):
        """TestResult에 runtime_results 필드 존재."""
        tool_dir = tmp_path / "calc"
        tool_dir.mkdir()
        (tool_dir / "tool.yaml").write_text('name: calc\nversion: "1.0.0"\ndescription: "계산기"\n')
        (tool_dir / "tool.py").write_text(
            "from jedisos.forge.decorator import tool\n\n"
            '@tool(name="add", description="더하기")\n'
            "async def add(a: int, b: int) -> int:\n"
            "    return a + b\n"
        )

        tester = SkillTester()
        result = await tester.test_skill(tool_dir)
        assert hasattr(result, "runtime_results")
        assert isinstance(result.runtime_results, list)


class TestSkillContext:  # [JS-T012.6]
    """스킬 공유 컨텍스트 (LLM + 메모리) 테스트."""

    def _reset_context(self):
        """테스트 후 컨텍스트를 초기 상태로 복원."""
        skill_context._llm_router = None
        skill_context._memory = None

    def test_context_initialize(self):
        """initialize() 호출 후 is_initialized() True."""
        self._reset_context()
        mock_llm = MagicMock()
        mock_memory = MagicMock()

        skill_context.initialize(llm_router=mock_llm, memory=mock_memory)
        assert skill_context.is_initialized() is True
        self._reset_context()

    async def test_context_not_initialized_llm(self):
        """미초기화 상태에서 llm_complete() 호출 시 RuntimeError."""
        self._reset_context()
        try:
            await skill_context.llm_complete("test")
            raise AssertionError("RuntimeError가 발생해야 합니다")
        except RuntimeError as e:
            assert "llm_router" in str(e)

    async def test_context_not_initialized_memory(self):
        """미초기화 상태에서 memory_retain() 호출 시 RuntimeError."""
        self._reset_context()
        try:
            await skill_context.memory_retain("test")
            raise AssertionError("RuntimeError가 발생해야 합니다")
        except RuntimeError as e:
            assert "memory" in str(e)

    async def test_llm_complete_delegates(self):
        """llm_complete()가 LLMRouter.complete_text()에 위임."""
        self._reset_context()
        mock_llm = AsyncMock()
        mock_llm.complete_text.return_value = "요약 결과입니다"
        skill_context._llm_router = mock_llm

        result = await skill_context.llm_complete("요약해줘", system="요약기")
        assert result == "요약 결과입니다"
        mock_llm.complete_text.assert_called_once_with(
            prompt="요약해줘",
            system="요약기",
            temperature=0.7,
            max_tokens=1024,
        )
        self._reset_context()

    async def test_llm_complete_caps_tokens(self):
        """max_tokens > 2048이면 2048로 캡."""
        self._reset_context()
        mock_llm = AsyncMock()
        mock_llm.complete_text.return_value = "ok"
        skill_context._llm_router = mock_llm

        await skill_context.llm_complete("test", max_tokens=5000)
        call_kwargs = mock_llm.complete_text.call_args.kwargs
        assert call_kwargs["max_tokens"] == 2048
        self._reset_context()

    async def test_llm_complete_clamps_temperature(self):
        """temperature가 범위 밖이면 클램핑."""
        self._reset_context()
        mock_llm = AsyncMock()
        mock_llm.complete_text.return_value = "ok"
        skill_context._llm_router = mock_llm

        # 음수 → 0.0
        await skill_context.llm_complete("test", temperature=-1.0)
        assert mock_llm.complete_text.call_args.kwargs["temperature"] == 0.0

        # 초과 → 1.5
        await skill_context.llm_complete("test", temperature=3.0)
        assert mock_llm.complete_text.call_args.kwargs["temperature"] == 1.5
        self._reset_context()

    async def test_llm_chat_delegates(self):
        """llm_chat()가 LLMRouter.complete()에 위임하고 텍스트 추출."""
        self._reset_context()
        mock_llm = AsyncMock()
        mock_llm.complete.return_value = {"choices": [{"message": {"content": "채팅 응답"}}]}
        skill_context._llm_router = mock_llm

        messages = [{"role": "user", "content": "안녕"}]
        result = await skill_context.llm_chat(messages)
        assert result == "채팅 응답"
        mock_llm.complete.assert_called_once()
        self._reset_context()

    async def test_memory_retain_delegates(self):
        """memory_retain()이 HindsightMemory.retain()에 위임."""
        self._reset_context()
        mock_memory = AsyncMock()
        mock_memory.retain.return_value = {"status": "ok"}
        skill_context._memory = mock_memory

        result = await skill_context.memory_retain(content="중요한 정보", context="테스트")
        assert result == {"status": "ok"}
        mock_memory.retain.assert_called_once_with(
            content="중요한 정보",
            context="테스트",
            bank_id="jedisos-skills",
        )
        self._reset_context()

    async def test_memory_recall_default_bank(self):
        """bank_id 미지정 시 'jedisos-skills' 사용."""
        self._reset_context()
        mock_memory = AsyncMock()
        mock_memory.recall.return_value = {"context": "검색 결과"}
        skill_context._memory = mock_memory

        result = await skill_context.memory_recall(query="테스트")
        mock_memory.recall.assert_called_once_with(
            query="테스트",
            bank_id="jedisos-skills",
        )
        assert result == {"context": "검색 결과"}
        self._reset_context()

    def test_context_in_allowed_imports(self):
        """ALLOWED_IMPORTS에 jedisos.forge.context 포함."""
        assert "jedisos.forge.context" in ALLOWED_IMPORTS
