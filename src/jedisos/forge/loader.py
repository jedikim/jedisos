"""
[JS-K005] jedisos.forge.loader
importlib 기반 도구 핫로더 - tool.py에서 @tool 함수를 동적 로드

version: 1.0.0
created: 2026-02-18
modified: 2026-02-18
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger()


class ToolMeta:  # [JS-K005.1]
    """로드된 도구의 메타데이터."""

    def __init__(self, name: str, version: str, description: str, author: str) -> None:
        self.name = name
        self.version = version
        self.description = description
        self.author = author


class ToolLoader:  # [JS-K005.2]
    """도구 디렉토리에서 @tool 함수를 동적 로드."""

    def __init__(self, tools_dir: Path | None = None) -> None:
        self.tools_dir = tools_dir or Path("tools")
        self._load_counter = 0

    def load_tool(self, tool_dir: Path) -> list[Any]:  # [JS-K005.3]
        """tool.py에서 @tool 데코레이터 함수들을 로드합니다.

        Args:
            tool_dir: 도구 디렉토리 경로 (tool.yaml + tool.py 포함)

        Returns:
            @tool 데코레이터가 적용된 함수 목록

        Raises:
            FileNotFoundError: tool.py가 없는 경우
            ImportError: 모듈 로드 실패
        """
        tool_py = tool_dir / "tool.py"
        if not tool_py.exists():
            msg = f"tool.py를 찾을 수 없습니다: {tool_py}"
            raise FileNotFoundError(msg)

        # exec()로 직접 실행하여 캐시 문제를 우회
        # 보안: CodeSecurityChecker가 exec 전에 정적분석(금지패턴/import화이트리스트)을 수행함
        import types

        code = tool_py.read_text()
        module = types.ModuleType(f"jedisos_tool_{tool_dir.name}")
        module.__file__ = str(tool_py)

        exec(compile(code, str(tool_py), "exec"), module.__dict__)  # nosec B102 - pre-validated by CodeSecurityChecker

        # @tool 데코레이터가 등록한 함수들을 수집
        tools = [
            getattr(module, name)
            for name in dir(module)
            if hasattr(getattr(module, name), "_is_jedisos_tool")
        ]

        logger.info("tool_loaded", tool_dir=str(tool_dir), tool_count=len(tools))
        return tools

    def load_meta(self, tool_dir: Path) -> ToolMeta | None:  # [JS-K005.4]
        """tool.yaml에서 메타데이터를 로드합니다.

        Args:
            tool_dir: 도구 디렉토리 경로

        Returns:
            ToolMeta 또는 None (파일 없는 경우)
        """
        yaml_path = tool_dir / "tool.yaml"
        if not yaml_path.exists():
            return None

        data = yaml.safe_load(yaml_path.read_text())
        return ToolMeta(
            name=data.get("name", tool_dir.name),
            version=data.get("version", "0.0.0"),
            description=data.get("description", ""),
            author=data.get("author", "unknown"),
        )

    def load_all(self) -> dict[str, list[Any]]:  # [JS-K005.5]
        """tools/ 디렉토리의 모든 도구를 로드합니다.

        Returns:
            도구 디렉토리 이름 → 도구 함수 리스트 매핑
        """
        if not self.tools_dir.exists():
            logger.warning("tools_dir_not_found", path=str(self.tools_dir))
            return {}

        result: dict[str, list[Any]] = {}

        for sub_dir in sorted(self.tools_dir.iterdir()):
            if not sub_dir.is_dir():
                continue
            if sub_dir.name.startswith(".") or sub_dir.name == "__pycache__":
                continue

            tool_py = sub_dir / "tool.py"
            if not tool_py.exists():
                # generated/ 디렉토리는 하위 디렉토리 검색
                if sub_dir.name == "generated":
                    for gen_dir in sorted(sub_dir.iterdir()):
                        if gen_dir.is_dir() and (gen_dir / "tool.py").exists():
                            try:
                                tools = self.load_tool(gen_dir)
                                if tools:
                                    result[gen_dir.name] = tools
                            except (ImportError, FileNotFoundError) as e:
                                logger.error(
                                    "tool_load_failed", tool_dir=str(gen_dir), error=str(e)
                                )
                continue

            try:
                tools = self.load_tool(sub_dir)
                if tools:
                    result[sub_dir.name] = tools
            except (ImportError, FileNotFoundError) as e:
                logger.error("tool_load_failed", tool_dir=str(sub_dir), error=str(e))

        logger.info("all_tools_loaded", total_dirs=len(result))
        return result

    def reload_tool(self, tool_dir: Path) -> list[Any]:  # [JS-K005.6]
        """도구를 다시 로드합니다 (핫리로드).

        Args:
            tool_dir: 도구 디렉토리 경로

        Returns:
            새로 로드된 도구 함수 목록
        """
        logger.info("tool_reloading", tool_dir=str(tool_dir))
        return self.load_tool(tool_dir)
