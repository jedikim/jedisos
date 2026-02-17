"""
[JS-K003] jedisos.forge.decorator
@tool 데코레이터 정의 - 함수를 JediSOS Skill 도구로 등록

version: 1.0.0
created: 2026-02-18
modified: 2026-02-18
"""

from __future__ import annotations

import functools
import inspect
from typing import Any


def tool(  # [JS-K003.1]
    name: str,
    description: str = "",
    tags: list[str] | None = None,
) -> Any:
    """함수를 JediSOS Skill 도구로 등록하는 데코레이터.

    Args:
        name: 도구 이름 (고유 식별자)
        description: 도구 설명
        tags: 도구 태그 목록

    Returns:
        데코레이터 함수

    Example:
        @tool(name="add", description="더하기")
        async def add(a: int, b: int) -> int:
            return a + b
    """

    def decorator(func: Any) -> Any:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if inspect.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            return func(*args, **kwargs)

        # 메타데이터 설정
        wrapper._is_jedisos_tool = True
        wrapper._tool_name = name
        wrapper._tool_description = description or func.__doc__ or ""
        wrapper._tool_tags = tags or []
        wrapper._tool_parameters = _extract_parameters(func)

        return wrapper

    return decorator


def _extract_parameters(func: Any) -> dict[str, dict[str, Any]]:  # [JS-K003.2]
    """함수 시그니처에서 파라미터 정보를 추출합니다.

    Args:
        func: 파라미터를 추출할 함수

    Returns:
        파라미터 이름 → {type, required, default} 매핑
    """
    sig = inspect.signature(func)
    params: dict[str, dict[str, Any]] = {}

    type_map = {
        int: "integer",
        float: "number",
        str: "string",
        bool: "boolean",
        list: "array",
        dict: "object",
    }

    for param_name, param in sig.parameters.items():
        annotation = param.annotation
        param_type = "string"  # 기본값

        if annotation != inspect.Parameter.empty:
            param_type = type_map.get(annotation, str(annotation))

        param_info: dict[str, Any] = {"type": param_type}

        if param.default is inspect.Parameter.empty:
            param_info["required"] = True
        else:
            param_info["required"] = False
            param_info["default"] = param.default

        params[param_name] = param_info

    return params
