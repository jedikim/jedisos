"""
[JS-T013] tests.unit.test_tool_loader
도구 핫로더 단위 테스트 - importlib 동적 로드

version: 1.0.0
created: 2026-02-18
"""

import pytest

from jedisos.forge.loader import ToolLoader


class TestToolLoader:  # [JS-T013.1]
    """ToolLoader 기본 기능 테스트."""

    def test_load_single_tool(self, tmp_path):
        """단일 도구 로드."""
        tool_dir = tmp_path / "calc"
        tool_dir.mkdir()
        (tool_dir / "tool.py").write_text(
            "from jedisos.forge.decorator import tool\n\n"
            '@tool(name="add", description="더하기")\n'
            "async def add(a: int, b: int) -> int:\n"
            "    return a + b\n"
        )

        loader = ToolLoader()
        tools = loader.load_tool(tool_dir)
        assert len(tools) == 1
        assert tools[0]._tool_name == "add"
        assert tools[0]._is_jedisos_tool is True

    def test_load_multiple_tools(self, tmp_path):
        """여러 도구 함수 로드."""
        tool_dir = tmp_path / "math_tools"
        tool_dir.mkdir()
        (tool_dir / "tool.py").write_text(
            "from jedisos.forge.decorator import tool\n\n"
            '@tool(name="add", description="더하기")\n'
            "async def add(a: int, b: int) -> int:\n"
            "    return a + b\n\n"
            '@tool(name="multiply", description="곱하기")\n'
            "async def multiply(a: int, b: int) -> int:\n"
            "    return a * b\n"
        )

        loader = ToolLoader()
        tools = loader.load_tool(tool_dir)
        assert len(tools) == 2
        names = {t._tool_name for t in tools}
        assert names == {"add", "multiply"}

    def test_load_missing_file(self, tmp_path):
        """tool.py 없으면 FileNotFoundError."""
        tool_dir = tmp_path / "empty"
        tool_dir.mkdir()

        loader = ToolLoader()
        with pytest.raises(FileNotFoundError):
            loader.load_tool(tool_dir)

    def test_load_invalid_module(self, tmp_path):
        """유효하지 않은 코드는 에러."""
        tool_dir = tmp_path / "bad"
        tool_dir.mkdir()
        (tool_dir / "tool.py").write_text("def bad(:\n  pass")

        loader = ToolLoader()
        with pytest.raises(SyntaxError):
            loader.load_tool(tool_dir)

    def test_load_no_tools(self, tmp_path):
        """@tool이 없는 모듈은 빈 리스트."""
        tool_dir = tmp_path / "no_tools"
        tool_dir.mkdir()
        (tool_dir / "tool.py").write_text("def plain_func():\n    return 42\n")

        loader = ToolLoader()
        tools = loader.load_tool(tool_dir)
        assert len(tools) == 0


class TestToolMeta:  # [JS-T013.2]
    """도구 메타데이터 로드 테스트."""

    def test_load_meta(self, tmp_path):
        tool_dir = tmp_path / "with_meta"
        tool_dir.mkdir()
        (tool_dir / "tool.yaml").write_text(
            'name: weather\nversion: "1.0.0"\ndescription: "날씨 조회"\nauthor: jedi\n'
        )

        loader = ToolLoader()
        meta = loader.load_meta(tool_dir)
        assert meta is not None
        assert meta.name == "weather"
        assert meta.version == "1.0.0"
        assert meta.description == "날씨 조회"
        assert meta.author == "jedi"

    def test_load_meta_missing(self, tmp_path):
        tool_dir = tmp_path / "no_meta"
        tool_dir.mkdir()

        loader = ToolLoader()
        meta = loader.load_meta(tool_dir)
        assert meta is None


class TestLoadAll:  # [JS-T013.3]
    """전체 도구 로드 테스트."""

    def test_load_all(self, tmp_path):
        """tools/ 내 모든 도구 로드."""
        # 도구 1
        t1 = tmp_path / "calc"
        t1.mkdir()
        (t1 / "tool.py").write_text(
            "from jedisos.forge.decorator import tool\n\n"
            '@tool(name="add", description="더하기")\n'
            "async def add(a: int, b: int) -> int:\n"
            "    return a + b\n"
        )

        # 도구 2
        t2 = tmp_path / "greeter"
        t2.mkdir()
        (t2 / "tool.py").write_text(
            "from jedisos.forge.decorator import tool\n\n"
            '@tool(name="greet", description="인사")\n'
            "async def greet(name: str) -> str:\n"
            '    return f"안녕 {name}"\n'
        )

        loader = ToolLoader(tools_dir=tmp_path)
        result = loader.load_all()
        assert len(result) == 2
        assert "calc" in result
        assert "greeter" in result

    def test_load_all_empty(self, tmp_path):
        loader = ToolLoader(tools_dir=tmp_path)
        result = loader.load_all()
        assert len(result) == 0

    def test_load_all_nonexistent(self, tmp_path):
        loader = ToolLoader(tools_dir=tmp_path / "nonexistent")
        result = loader.load_all()
        assert len(result) == 0

    def test_load_all_with_generated(self, tmp_path):
        """generated/ 하위 디렉토리도 로드."""
        gen_dir = tmp_path / "generated" / "auto_tool"
        gen_dir.mkdir(parents=True)
        (gen_dir / "tool.py").write_text(
            "from jedisos.forge.decorator import tool\n\n"
            '@tool(name="auto", description="자동 생성")\n'
            "async def auto(x: int) -> int:\n"
            "    return x\n"
        )

        loader = ToolLoader(tools_dir=tmp_path)
        result = loader.load_all()
        assert "auto_tool" in result

    def test_load_all_skips_hidden(self, tmp_path):
        """숨김 디렉토리(.xxx)는 건너뜀."""
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "tool.py").write_text(
            "from jedisos.forge.decorator import tool\n\n"
            '@tool(name="h", description="h")\n'
            "async def h() -> str:\n"
            '    return ""\n'
        )

        loader = ToolLoader(tools_dir=tmp_path)
        result = loader.load_all()
        assert ".hidden" not in result


class TestReloadTool:  # [JS-T013.4]
    """핫리로드 테스트."""

    def test_reload(self, tmp_path):
        tool_dir = tmp_path / "reloadable"
        tool_dir.mkdir()
        (tool_dir / "tool.py").write_text(
            "from jedisos.forge.decorator import tool\n\n"
            '@tool(name="v1", description="버전1")\n'
            "async def v1() -> str:\n"
            '    return "v1"\n'
        )

        loader = ToolLoader()
        tools = loader.load_tool(tool_dir)
        assert tools[0]._tool_name == "v1"

        # 코드 수정 후 리로드
        (tool_dir / "tool.py").write_text(
            "from jedisos.forge.decorator import tool\n\n"
            '@tool(name="v2", description="버전2")\n'
            "async def v2() -> str:\n"
            '    return "v2"\n'
        )

        tools = loader.reload_tool(tool_dir)
        assert tools[0]._tool_name == "v2"
