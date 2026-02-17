"""
[JS-T012] tests.unit.test_forge
Forge 자가 코딩 엔진 단위 테스트 - decorator, security, generator, tester

version: 1.0.0
created: 2026-02-18
"""

from jedisos.forge.decorator import tool
from jedisos.forge.generator import SkillGenerator
from jedisos.forge.security import (
    ALLOWED_IMPORTS,
    FORBIDDEN_PATTERNS,
    CodeSecurityChecker,
)
from jedisos.forge.tester import SkillTester


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
