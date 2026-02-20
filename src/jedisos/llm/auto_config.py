"""
[JS-C003] jedisos.llm.auto_config
하드코딩 LLM 역할 배정 — Gemini 우선, GPT 폴백

역할별 모델 매핑:
- reason → gpt-5.2 (gemini-3.1-pro-preview 다운으로 대체)
- code → gpt-5.2-codex (폴백: gpt-5.2)
- chat, classify, extract → gemini-3-flash-preview (폴백: gpt-5.2)

version: 5.0.0
created: 2026-02-19
modified: 2026-02-20
dependencies: pyyaml>=6.0
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger()

# ──────────────────────────────────────
# 상수
# ──────────────────────────────────────

ROLES = ("reason", "code", "chat", "classify", "extract")

_CACHE_FILENAME = "model_roles.yaml"

_HARDCODED_ROLES: dict[str, list[str]] = {
    "reason": ["gpt-5.2"],
    "code": ["gpt-5.2-codex", "gpt-5.2"],
    "chat": ["gemini/gemini-3-flash-preview", "gpt-5.2"],
    "classify": ["gemini/gemini-3-flash-preview", "gpt-5.2"],
    "extract": ["gemini/gemini-3-flash-preview", "gpt-5.2"],
}


# ──────────────────────────────────────
# 엔트리포인트
# ──────────────────────────────────────


async def auto_configure_roles(  # [JS-C003.3]
    llm_router: Any,
    data_dir: str = "/data",
) -> dict[str, list[str]]:
    """역할별 모델 매핑 반환 (하드코딩).

    1. 캐시 파일(model_roles.yaml) 있으면 로드
    2. 없으면 _HARDCODED_ROLES 사용 + 캐시 저장

    Returns:
        {"reason": ["gemini/gemini-2.5-pro", "gpt-5.2"], ...}
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

    # 하드코딩 매핑 사용
    mapping = {role: list(chain) for role, chain in _HARDCODED_ROLES.items()}
    logger.info("model_roles_hardcoded", mapping=mapping)

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
