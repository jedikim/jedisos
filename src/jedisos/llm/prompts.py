"""
[JS-C002] jedisos.llm.prompts
프롬프트 템플릿 관리

version: 1.0.0
created: 2026-02-16
modified: 2026-02-17
"""

from __future__ import annotations

SYSTEM_BASE = """당신은 JediSOS AI 어시스턴트입니다.
사용자의 질문에 정확하고 친절하게 답변합니다.
한국어와 영어를 모두 지원합니다."""


SYSTEM_WITH_MEMORY = """당신은 JediSOS AI 어시스턴트입니다.
사용자의 질문에 정확하고 친절하게 답변합니다.
한국어와 영어를 모두 지원합니다.

아래는 이전 대화에서 기억한 관련 정보입니다:
{memory_context}

이 정보를 참고하되, 확실하지 않은 정보는 사용하지 마세요."""


SYSTEM_WITH_TOOLS = """당신은 JediSOS AI 어시스턴트입니다.
사용자의 질문에 정확하고 친절하게 답변합니다.
필요하면 도구를 사용하여 정보를 검색하거나 작업을 수행합니다.

사용 가능한 도구가 있을 때:
1. 질문에 답하기 위해 도구가 필요한지 판단합니다.
2. 필요하면 적절한 도구를 호출합니다.
3. 도구 결과를 바탕으로 답변합니다."""


def build_system_prompt(  # [JS-C002.1]
    identity: str = "",
    memory_context: str = "",
    has_tools: bool = False,
) -> str:
    """시스템 프롬프트를 조합합니다.

    Args:
        identity: 에이전트 정체성 텍스트
        memory_context: 메모리에서 검색된 관련 컨텍스트
        has_tools: 도구 사용 가능 여부

    Returns:
        조합된 시스템 프롬프트
    """
    parts: list[str] = []

    if identity:
        parts.append(identity)
    elif has_tools:
        parts.append(SYSTEM_WITH_TOOLS)
    elif memory_context:
        parts.append(SYSTEM_WITH_MEMORY.format(memory_context=memory_context))
    else:
        parts.append(SYSTEM_BASE)

    if identity and memory_context:
        parts.append(f"\n관련 기억:\n{memory_context}")

    return "\n".join(parts)
