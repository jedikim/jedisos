"""
[JS-C003] jedisos.llm.auto_config
멀티티어 LLM 자동 구성 — 사용 가능한 모델 조회 → 대형 모델에게 역할 배정 요청

앱 시작 시:
1. OpenAI/Google API로 사용 가능한 모델 목록 조회
2. 가장 큰 모델에게 "어떤 모델이 어떤 역할에 적합한지" 구조화 질의
3. 응답 JSON을 파싱 → model_roles.yaml 캐시
4. LLMRouter에 역할별 모델 매핑 로드

version: 1.0.0
created: 2026-02-19
modified: 2026-02-19
dependencies: litellm>=1.81, httpx>=0.28, pyyaml>=6.0
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
import structlog
import yaml

logger = structlog.get_logger()

# 역할 정의
ROLES = ("reason", "code", "chat", "classify", "extract")

# 모델 목록 조회용 API 엔드포인트
_OPENAI_MODELS_URL = "https://api.openai.com/v1/models"
_GOOGLE_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# 캐시 파일명
_CACHE_FILENAME = "model_roles.yaml"

# 역할 배정 프롬프트
_ROLE_ASSIGNMENT_PROMPT = """\
You are an AI infrastructure architect. Given the list of available LLM models below, \
assign each role to the most appropriate model.

## Roles
- reason: Complex reasoning, analysis, deep thinking. Needs the smartest, most capable model.
- code: Code generation, skill creation. Needs strong coding ability.
- chat: General conversation, tool calling. Needs good speed and reasonable cost.
- classify: Intent classification, yes/no decisions. Needs the cheapest, fastest model.
- extract: Summarization, memory extraction, search query generation. Needs cheap, fast model.

## Rules
1. Prefer using DIFFERENT models for different tiers to optimize cost.
2. reason and code should use the largest/most capable models.
3. classify and extract should use the smallest/cheapest models.
4. chat should be a balanced mid-tier model.
5. Each role MUST be assigned exactly one model from the available list.
6. For Google models, use the "gemini/" prefix (e.g., "gemini/gemini-2.0-flash").

## Available Models
{models_text}

## Response Format
Return ONLY a JSON object, no markdown, no explanation:
{{"reason": "model-name", "code": "model-name", "chat": "model-name", "classify": "model-name", "extract": "model-name"}}
"""


async def discover_available_models() -> list[dict[str, Any]]:  # [JS-C003.1]
    """OpenAI + Google API에서 사용 가능한 모델 목록을 조회합니다.

    Returns:
        모델 정보 리스트: [{"id": "gpt-4o", "provider": "openai"}, ...]
    """
    models: list[dict[str, Any]] = []

    # OpenAI 모델 조회
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
                model_id = m.get("id", "")
                # chat completion 가능한 모델만 필터
                if any(k in model_id for k in ("gpt-", "o1", "o3", "o4", "chatgpt", "codex")):
                    models.append(
                        {
                            "id": model_id,
                            "provider": "openai",
                            "owned_by": m.get("owned_by", ""),
                        }
                    )
            logger.info(
                "openai_models_discovered",
                count=len([m for m in models if m["provider"] == "openai"]),
            )
        except Exception as e:
            logger.warning("openai_models_discovery_failed", error=str(e))

    # Google Gemini 모델 조회
    google_key = os.environ.get("GEMINI_API_KEY", "")
    if google_key:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    _GOOGLE_MODELS_URL,
                    params={"key": google_key},
                )
                resp.raise_for_status()
                data = resp.json()

            for m in data.get("models", []):
                name = m.get("name", "")
                # "models/gemini-2.0-flash" → "gemini/gemini-2.0-flash"
                if "gemini" in name:
                    model_id = "gemini/" + name.replace("models/", "")
                    # generateContent 지원 모델만
                    methods = m.get("supportedGenerationMethods", [])
                    if "generateContent" in methods:
                        models.append(
                            {
                                "id": model_id,
                                "provider": "google",
                                "display_name": m.get("displayName", ""),
                            }
                        )
            logger.info(
                "google_models_discovered",
                count=len([m for m in models if m["provider"] == "google"]),
            )
        except Exception as e:
            logger.warning("google_models_discovery_failed", error=str(e))

    return models


async def assign_model_roles(  # [JS-C003.2]
    available_models: list[dict[str, Any]],
    llm_router: Any,
) -> dict[str, str]:
    """가장 큰 모델에게 역할 배정을 요청합니다.

    Args:
        available_models: discover_available_models()의 결과
        llm_router: LLMRouter 인스턴스

    Returns:
        {"reason": "model-id", "code": "model-id", ...}
    """
    if not available_models:
        logger.warning("no_models_available_for_assignment")
        return _default_roles(llm_router)

    # 모델 목록 텍스트 구성
    lines: list[str] = []
    for m in available_models:
        extra = ""
        if m.get("display_name"):
            extra = f" ({m['display_name']})"
        lines.append(f"- {m['id']}{extra} [provider: {m['provider']}]")
    models_text = "\n".join(lines)

    prompt = _ROLE_ASSIGNMENT_PROMPT.format(models_text=models_text)

    try:
        response_text = await llm_router.complete_text(
            prompt=prompt,
            system="You are a precise JSON-only responder. No markdown, no explanation.",
            temperature=0.0,
            max_tokens=256,
        )

        # JSON 파싱 (마크다운 코드블록 제거)
        clean = response_text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean
            clean = clean.rsplit("```", 1)[0] if "```" in clean else clean
            clean = clean.strip()

        mapping = json.loads(clean)

        # 유효성 검증: 모든 역할이 있는지
        valid_ids = {m["id"] for m in available_models}
        for role in ROLES:
            if role not in mapping or mapping[role] not in valid_ids:
                logger.warning(
                    "invalid_role_assignment",
                    role=role,
                    assigned=mapping.get(role),
                )
                mapping[role] = llm_router.models[0]  # 폴백

        logger.info("model_roles_assigned", mapping=mapping)
        return mapping

    except Exception as e:
        logger.error("model_role_assignment_failed", error=str(e))
        return _default_roles(llm_router)


def _default_roles(llm_router: Any) -> dict[str, str]:
    """폴백: 모든 역할에 기본 모델 사용."""
    models = llm_router.models
    primary = models[0] if models else "gpt-4o"
    secondary = models[1] if len(models) > 1 else primary
    return {
        "reason": primary,
        "code": primary,
        "chat": secondary,
        "classify": secondary,
        "extract": secondary,
    }


async def auto_configure_roles(  # [JS-C003.3]
    llm_router: Any,
    data_dir: str = "/data",
) -> dict[str, str]:
    """전체 자동 구성 플로우.

    1. 캐시 파일이 있으면 로드하여 반환
    2. 없으면 모델 조회 → 역할 배정 → 캐시 저장

    Args:
        llm_router: LLMRouter 인스턴스
        data_dir: 데이터 디렉토리 (캐시 저장용)

    Returns:
        역할별 모델 매핑
    """
    cache_path = Path(data_dir) / _CACHE_FILENAME

    # 캐시 로드
    if cache_path.exists():
        try:
            cached = yaml.safe_load(cache_path.read_text(encoding="utf-8"))
            if cached and all(role in cached for role in ROLES):
                logger.info("model_roles_loaded_from_cache", path=str(cache_path))
                return cached
        except Exception as e:
            logger.warning("model_roles_cache_load_failed", error=str(e))

    # 모델 조회
    available = await discover_available_models()
    if not available:
        logger.warning("no_models_discovered_using_defaults")
        mapping = _default_roles(llm_router)
    else:
        # 역할 배정
        mapping = await assign_model_roles(available, llm_router)

    # 캐시 저장
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            yaml.dump(mapping, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
        logger.info("model_roles_cached", path=str(cache_path))
    except Exception as e:
        logger.warning("model_roles_cache_save_failed", error=str(e))

    return mapping
