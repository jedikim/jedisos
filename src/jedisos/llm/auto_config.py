"""
[JS-C003] jedisos.llm.auto_config
멀티티어 LLM 자동 구성 — 프로바이더별 역할 배정 + 크로스 폴백

플로우:
1. OpenAI/Google API로 사용 가능한 모델 목록 조회
2. DDGS로 최신 모델 가격/성능 정보 검색
3. 프로바이더별 각각 LLM 호출 (Pydantic structured output)
   - OpenAI 모델 중 역할 배정
   - Gemini 모델 중 역할 배정
4. 역할별 [openai_model, gemini_model] 폴백 체인 구성
5. model_roles.yaml 캐시 → LLMRouter에 로드

version: 4.0.0
created: 2026-02-19
modified: 2026-02-20
dependencies: litellm>=1.81, httpx>=0.28, pyyaml>=6.0, ddgs>=8.0, pydantic>=2.12
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import litellm
import structlog
import yaml
from pydantic import BaseModel, Field

logger = structlog.get_logger()

# ──────────────────────────────────────
# Pydantic 응답 스키마
# ──────────────────────────────────────


class ProviderRoles(BaseModel):
    """단일 프로바이더의 역할별 모델 배정 결과."""

    reason: str = Field(description="Complex reasoning — smartest, most capable model")
    code: str = Field(description="Code generation — strong coding model")
    chat: str = Field(description="General conversation — balanced speed + cost")
    classify: str = Field(description="Intent classification — cheapest, fastest")
    extract: str = Field(description="Summarization, extraction — cheap, fast")


# ──────────────────────────────────────
# 상수
# ──────────────────────────────────────

ROLES = ("reason", "code", "chat", "classify", "extract")

_OPENAI_MODELS_URL = "https://api.openai.com/v1/models"
_GOOGLE_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_CACHE_FILENAME = "model_roles.yaml"

# chat completions API를 지원하지 않는 특수 모델 접미사 필터
_EXCLUDED_SUFFIXES = (
    "-codex",
    "-customtools",
    "-tuning",
    "-grounding",
    "-imagegeneration",
    "-search",
    "-realtime",
    "-transcribe",
    "-tts",
)


def _is_chat_compatible(model_id: str) -> bool:
    """Chat Completions API 호환 모델인지 확인합니다."""
    mid_lower = model_id.lower()
    return not any(mid_lower.endswith(s) for s in _EXCLUDED_SUFFIXES)


_ROLE_PROMPT = """\
You are an AI infrastructure architect.
Given the available models and pricing research, assign the best model for each role.

## Roles
- reason: Complex reasoning, analysis. Smartest model.
- code: Code generation, skill creation. Strong coding.
- chat: General conversation, tool calling. Balanced speed + cost.
- classify: Intent classification, yes/no. Cheapest, fastest.
- extract: Summarization, memory extraction. Cheap, fast.

## Rules
1. reason/code → largest, most capable.
2. classify/extract → smallest, cheapest.
3. chat → balanced mid-tier.
4. ONLY use models from the list. Do NOT invent names.
5. Prefer newer generations (gemini-3 > gemini-2, gpt-5 > gpt-4).
6. Use the EXACT model ID as shown (including "gemini/" prefix).
7. AVOID specialized variant models with suffixes like -codex, -customtools, -tuning, -grounding, -imagegeneration, -search. Use base/standard models only. Codex models use a different API and cannot be used for chat.

## Available Models
{models_text}

## Pricing Research
{research_text}
"""


# ──────────────────────────────────────
# 모델 조회
# ──────────────────────────────────────


async def discover_available_models() -> dict[str, list[dict[str, Any]]]:  # [JS-C003.1]
    """프로바이더별 사용 가능 모델 조회."""
    result: dict[str, list[dict[str, Any]]] = {"openai": [], "gemini": []}

    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    _OPENAI_MODELS_URL,
                    headers={"Authorization": f"Bearer {openai_key}"},
                )
                resp.raise_for_status()
                data = resp.json()
            for m in data.get("data", []):
                mid = m.get("id", "")
                if any(
                    k in mid for k in ("gpt-", "o1", "o3", "o4", "chatgpt")
                ) and _is_chat_compatible(mid):
                    result["openai"].append({"id": mid, "owned_by": m.get("owned_by", "")})
            logger.info("openai_models_discovered", count=len(result["openai"]))
        except Exception as e:
            logger.warning("openai_models_discovery_failed", error=str(e))

    google_key = os.environ.get("GEMINI_API_KEY", "")
    if google_key:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(_GOOGLE_MODELS_URL, params={"key": google_key})
                resp.raise_for_status()
                data = resp.json()
            for m in data.get("models", []):
                name = m.get("name", "")
                if "gemini" in name:
                    mid = "gemini/" + name.replace("models/", "")
                    methods = m.get("supportedGenerationMethods", [])
                    if "generateContent" in methods and _is_chat_compatible(mid):
                        result["gemini"].append(
                            {"id": mid, "display_name": m.get("displayName", "")}
                        )
            logger.info("google_models_discovered", count=len(result["gemini"]))
        except Exception as e:
            logger.warning("google_models_discovery_failed", error=str(e))

    return result


# ──────────────────────────────────────
# 웹 검색
# ──────────────────────────────────────


def _search_model_pricing() -> str:  # [JS-C003.4]
    """DDGS로 최신 모델 가격/성능 정보 검색."""
    try:
        from ddgs import DDGS
    except ImportError:
        logger.warning("ddgs_not_installed")
        return "(unavailable)"

    queries = [
        "OpenAI API model pricing per token 2026",
        "Google Gemini API model pricing per token 2026",
    ]
    parts: list[str] = []
    try:
        with DDGS() as ddgs:
            for q in queries:
                for hit in ddgs.text(q, max_results=3):
                    parts.append(f"### {hit.get('title', '')}\n{hit.get('body', '')}")
    except Exception as e:
        logger.warning("ddgs_search_failed", error=str(e))
        return "(search failed)"

    text = "\n\n".join(parts)
    if len(text) > 4000:
        text = text[:4000] + "\n...(truncated)"
    logger.info("model_pricing_research_done", result_count=len(parts))
    return text


# ──────────────────────────────────────
# 프로바이더별 역할 배정 (structured output)
# ──────────────────────────────────────


async def _assign_for_provider(  # [JS-C003.5]
    provider: str,
    models: list[dict[str, Any]],
    research_text: str,
    call_model: str,
) -> ProviderRoles | None:
    """단일 프로바이더의 모델 중 역할 배정 (Pydantic structured output).

    Args:
        provider: "openai" | "gemini"
        models: 해당 프로바이더의 모델 리스트
        research_text: 가격 검색 결과
        call_model: LLM 호출에 사용할 모델

    Returns:
        ProviderRoles 또는 None (실패 시)
    """
    if not models:
        return None

    models_text = "\n".join(
        f"- {m['id']}" + (f" ({m['display_name']})" if m.get("display_name") else "")
        for m in models
    )

    from jedisos.llm.prompt_registry import get_registry

    registry = get_registry()
    if registry:
        prompt = registry.get_or_default(
            "auto_config_roles",
            "template",
            default=_ROLE_PROMPT,
            models_text=models_text,
            research_text=research_text,
        )
    else:
        prompt = _ROLE_PROMPT.format(models_text=models_text, research_text=research_text)

    try:
        resp = await litellm.acompletion(
            model=call_model,
            messages=[
                {"role": "system", "content": "Assign roles using ONLY models from the list."},
                {"role": "user", "content": prompt},
            ],
            response_format=ProviderRoles,
            temperature=0.0,
            max_tokens=512,
        )
        content = resp.choices[0].message.content
        roles = ProviderRoles.model_validate_json(content)

        # 유효성 검증
        valid_ids = {m["id"] for m in models}
        for field in ROLES:
            val = getattr(roles, field)
            if val not in valid_ids:
                logger.warning("invalid_model_in_role", provider=provider, role=field, model=val)
                # 첫 번째 모델로 폴백
                setattr(roles, field, models[0]["id"])

        logger.info("provider_roles_assigned", provider=provider, roles=roles.model_dump())
        return roles

    except Exception as e:
        logger.error("provider_role_assignment_failed", provider=provider, error=str(e))
        return None


# ──────────────────────────────────────
# 메인: 프로바이더별 각각 호출 → 합치기
# ──────────────────────────────────────


async def assign_model_roles(  # [JS-C003.2]
    models_by_provider: dict[str, list[dict[str, Any]]],
    llm_router: Any,
) -> dict[str, list[str]]:
    """OpenAI + Gemini 각각 역할 배정 → 역할별 폴백 체인 구성.

    Returns:
        {"reason": ["gpt-5.2-pro", "gemini/gemini-3-pro"], ...}
    """
    openai_models = models_by_provider.get("openai", [])
    gemini_models = models_by_provider.get("gemini", [])

    if not openai_models and not gemini_models:
        return _default_roles(llm_router)

    # 가격 정보 웹 검색 (1회만)
    research = _search_model_pricing()

    # 프로바이더별 각각 호출
    # 호출 모델: 해당 프로바이더의 첫 번째 모델이 아니라, llm_router의 기본 모델 사용
    call_model = llm_router.models[0]

    openai_roles = await _assign_for_provider(
        "openai",
        openai_models,
        research,
        call_model,
    )
    gemini_roles = await _assign_for_provider(
        "gemini",
        gemini_models,
        research,
        call_model,
    )

    # 역할별 폴백 체인 합치기
    mapping: dict[str, list[str]] = {}
    for role in ROLES:
        chain: list[str] = []
        if openai_roles:
            chain.append(getattr(openai_roles, role))
        if gemini_roles:
            chain.append(getattr(gemini_roles, role))
        if not chain:
            chain = list(llm_router.models)
        mapping[role] = chain

    logger.info("model_roles_assigned", mapping=mapping)
    return mapping


def _default_roles(llm_router: Any) -> dict[str, list[str]]:
    """폴백: 모든 역할에 기본 폴백 체인."""
    chain = list(llm_router.models)
    return {role: list(chain) for role in ROLES}


# ──────────────────────────────────────
# 엔트리포인트
# ──────────────────────────────────────


async def auto_configure_roles(  # [JS-C003.3]
    llm_router: Any,
    data_dir: str = "/data",
) -> dict[str, list[str]]:
    """전체 자동 구성.

    Returns:
        {"reason": ["gpt-5.2-pro", "gemini/gemini-3-pro"], ...}
    """
    cache_path = Path(data_dir) / _CACHE_FILENAME

    # 캐시 로드
    if cache_path.exists():
        try:
            cached = yaml.safe_load(cache_path.read_text(encoding="utf-8"))
            if cached and all(role in cached for role in ROLES):
                mapping: dict[str, list[str]] = {}
                for role in ROLES:
                    val = cached[role]
                    mapping[role] = val if isinstance(val, list) else [val]
                logger.info("model_roles_loaded_from_cache", path=str(cache_path))
                return mapping
        except Exception as e:
            logger.warning("cache_load_failed", error=str(e))

    # 모델 조회 + 역할 배정
    by_provider = await discover_available_models()
    total = sum(len(v) for v in by_provider.values())

    if total == 0:
        mapping = _default_roles(llm_router)
    else:
        mapping = await assign_model_roles(by_provider, llm_router)

    # 캐시 저장
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            yaml.dump(mapping, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
        logger.info("model_roles_cached", path=str(cache_path))
    except Exception as e:
        logger.warning("cache_save_failed", error=str(e))

    return mapping
