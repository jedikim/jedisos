"""
[JS-K006] jedisos.forge.context
스킬 공유 리소스 - 메인 프로세스의 LLM 라우터 + Hindsight 메모리를 스킬에 제공

version: 1.0.0
created: 2026-02-18
modified: 2026-02-18
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger()

# 싱글톤 인스턴스 (lifespan에서 초기화)
_llm_router: Any = None  # LLMRouter
_memory: Any = None  # ZvecMemory

# 스킬 전용 메모리 뱅크 (에이전트 대화 "jedisos-default"와 분리)
SKILL_MEMORY_BANK = "jedisos-skills"

# 스킬 LLM 호출 제한
_MAX_TOKENS_CAP = 2048
_TEMPERATURE_MIN = 0.0
_TEMPERATURE_MAX = 1.5


def initialize(llm_router: Any, memory: Any) -> None:  # [JS-K006.1]
    """메인 프로세스에서 LLM/메모리 리소스를 등록합니다.

    Args:
        llm_router: LLMRouter 인스턴스
        memory: ZvecMemory 인스턴스
    """
    global _llm_router, _memory
    _llm_router = llm_router
    _memory = memory
    logger.info("skill_context_initialized")


def is_initialized() -> bool:  # [JS-K006.2]
    """컨텍스트가 초기화되었는지 확인합니다."""
    return _llm_router is not None and _memory is not None


async def llm_complete(  # [JS-K006.3]
    prompt: str,
    system: str = "",
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> str:
    """LLM 텍스트 완성. 메인 프로세스의 API 키와 모델 폴백 체인을 사용합니다.

    Args:
        prompt: 사용자 프롬프트
        system: 시스템 프롬프트 (선택)
        temperature: 0.0~1.5 (범위 밖이면 클램핑)
        max_tokens: 최대 토큰 수 (2048 상한)

    Returns:
        LLM 응답 텍스트

    Raises:
        RuntimeError: 컨텍스트가 초기화되지 않은 경우
    """
    if _llm_router is None:
        msg = "스킬 컨텍스트가 초기화되지 않았습니다. (llm_router 없음)"
        raise RuntimeError(msg)

    temperature = max(_TEMPERATURE_MIN, min(_TEMPERATURE_MAX, temperature))
    max_tokens = min(max_tokens, _MAX_TOKENS_CAP)

    return await _llm_router.complete_text(
        prompt=prompt,
        system=system,
        temperature=temperature,
        max_tokens=max_tokens,
    )


async def llm_chat(  # [JS-K006.4]
    messages: list[dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> str:
    """LLM 멀티턴 채팅.

    Args:
        messages: 대화 메시지 리스트. [{"role": "user", "content": "..."}, ...]
        temperature: 0.0~1.5 (범위 밖이면 클램핑)
        max_tokens: 최대 토큰 수 (2048 상한)

    Returns:
        어시스턴트 응답 텍스트

    Raises:
        RuntimeError: 컨텍스트가 초기화되지 않은 경우
    """
    if _llm_router is None:
        msg = "스킬 컨텍스트가 초기화되지 않았습니다. (llm_router 없음)"
        raise RuntimeError(msg)

    temperature = max(_TEMPERATURE_MIN, min(_TEMPERATURE_MAX, temperature))
    max_tokens = min(max_tokens, _MAX_TOKENS_CAP)

    result = await _llm_router.complete(
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return result["choices"][0]["message"]["content"]


async def memory_retain(  # [JS-K006.5]
    content: str,
    context: str = "",
    bank_id: str | None = None,
) -> dict[str, Any]:
    """Hindsight 메모리에 내용을 저장합니다.

    Args:
        content: 저장할 내용
        context: 추가 컨텍스트 (선택)
        bank_id: 메모리 뱅크 ID (기본: "jedisos-skills")

    Returns:
        Hindsight API 응답

    Raises:
        RuntimeError: 컨텍스트가 초기화되지 않은 경우
    """
    if _memory is None:
        msg = "스킬 컨텍스트가 초기화되지 않았습니다. (memory 없음)"
        raise RuntimeError(msg)

    return await _memory.retain(
        content=content,
        context=context,
        bank_id=bank_id or SKILL_MEMORY_BANK,
    )


async def memory_recall(  # [JS-K006.6]
    query: str,
    bank_id: str | None = None,
) -> dict[str, Any]:
    """Hindsight 메모리에서 관련 내용을 검색합니다.

    Args:
        query: 검색 쿼리
        bank_id: 메모리 뱅크 ID (기본: "jedisos-skills")

    Returns:
        검색 결과 (Hindsight API 응답)

    Raises:
        RuntimeError: 컨텍스트가 초기화되지 않은 경우
    """
    if _memory is None:
        msg = "스킬 컨텍스트가 초기화되지 않았습니다. (memory 없음)"
        raise RuntimeError(msg)

    return await _memory.recall(
        query=query,
        bank_id=bank_id or SKILL_MEMORY_BANK,
    )
