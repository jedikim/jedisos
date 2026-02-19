"""
[JS-C001] jedisos.llm.router
LiteLLM 라우터 래퍼 - 멀티 LLM 프로바이더 폴백

version: 2.0.0
created: 2026-02-16
modified: 2026-02-20
dependencies: litellm>=1.81.12
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

import litellm
import structlog
import yaml

from jedisos.core.config import LLMConfig
from jedisos.core.exceptions import LLMError

logger = structlog.get_logger()


class LLMRouter:  # [JS-C001.1]
    """LiteLLM 기반 LLM 라우터.

    폴백 체인을 config.models 리스트 순서로 시도합니다.
    역할별 모델 매핑은 프로바이더별 폴백 체인을 지원합니다:
      {"chat": ["gpt-5-mini", "gemini/gemini-3-flash"], ...}
    """

    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig()
        self._models = self._filter_available_models(self._load_models())
        self._role_models: dict[str, list[str]] = {}
        litellm.set_verbose = False
        litellm.drop_params = True
        if not self._models:
            raise LLMError("사용 가능한 LLM 모델이 없습니다. API 키를 확인하세요.")
        logger.info("llm_router_init", models=self._models)

    def set_role_models(self, mapping: dict[str, list[str]]) -> None:  # [JS-C001.6]
        """역할별 모델 매핑을 설정합니다.

        Args:
            mapping: {"reason": ["gpt-5.2-pro", "gemini/gemini-3-pro"], ...}
        """
        self._role_models = {k: list(v) for k, v in mapping.items()}
        logger.info("llm_role_models_set", mapping=self._role_models)

    def models_for(self, role: str) -> list[str]:  # [JS-C001.7]
        """역할에 맞는 모델 폴백 체인을 반환합니다.

        Args:
            role: reason|code|chat|classify|extract

        Returns:
            모델 ID 리스트 (빈 리스트면 미설정)
        """
        return list(self._role_models.get(role, []))

    def model_for(self, role: str) -> str | None:  # [JS-C001.9]
        """역할에 맞는 첫 번째 모델을 반환합니다 (하위 호환용)."""
        chain = self.models_for(role)
        return chain[0] if chain else None

    @staticmethod
    def _filter_available_models(models: list[str]) -> list[str]:  # [JS-C001.8]
        """API 키가 설정된 프로바이더의 모델만 반환합니다."""
        available: list[str] = []
        for m in models:
            if m.startswith("gemini/"):
                if os.environ.get("GEMINI_API_KEY"):
                    available.append(m)
            elif m.startswith("anthropic/") or m.startswith("claude"):
                if os.environ.get("ANTHROPIC_API_KEY"):
                    available.append(m)
            else:
                # OpenAI 계열 (gpt-*, o1-*, o3-*, etc.)
                if os.environ.get("OPENAI_API_KEY"):
                    available.append(m)
        return available

    def _load_models(self) -> list[str]:  # [JS-C001.2]
        """모델 목록을 로드합니다. YAML 파일 우선, 없으면 config.models 사용."""
        config_path = Path(self.config.config_file)
        if config_path.exists():
            with config_path.open(encoding="utf-8") as f:
                yaml_config = yaml.safe_load(f)
            if yaml_config and "models" in yaml_config:
                models = [m["model"] if isinstance(m, dict) else m for m in yaml_config["models"]]
                logger.info("llm_models_loaded_from_yaml", path=str(config_path), count=len(models))
                return models
        return list(self.config.models)

    def _resolve_models(
        self, model: str | None, role: str | None,
    ) -> list[str]:  # [JS-C001.10]
        """호출에 사용할 모델 리스트를 결정합니다."""
        if model:
            return [model]
        if role:
            chain = self.models_for(role)
            if chain:
                return chain
        return self._models

    async def complete(  # [JS-C001.3]
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        role: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """LLM 호출 (폴백 체인 포함).

        Args:
            messages: 대화 메시지 리스트
            tools: 사용 가능한 도구 정의 (선택)
            model: 특정 모델 지정 (None이면 폴백 체인 사용)
            role: 역할 (reason|code|chat|classify|extract) — model 미지정 시 사용

        Returns:
            LLM 응답 딕셔너리
        """
        models = self._resolve_models(model, role)
        last_error: Exception | None = None

        for m in models:
            try:
                call_kwargs: dict[str, Any] = {
                    "model": m,
                    "messages": messages,
                    "temperature": kwargs.get("temperature", self.config.temperature),
                    "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
                    "timeout": self.config.timeout,
                }
                if tools:
                    call_kwargs["tools"] = tools
                # Forward extra litellm params (response_format, etc.)
                for k in ("response_format",):
                    if k in kwargs:
                        call_kwargs[k] = kwargs[k]

                response = await litellm.acompletion(**call_kwargs)
                logger.info("llm_call_success", model=m, role=role)
                return response.model_dump()
            except Exception as e:
                last_error = e
                logger.warning("llm_call_failed", model=m, role=role, error=str(e))
                continue

        raise LLMError(f"모든 LLM 호출 실패. 마지막 에러: {last_error}") from last_error

    async def stream(  # [JS-C001.5]
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        role: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        """LLM 스트리밍 호출. 토큰 단위로 청크를 yield합니다.

        tool_calls가 포함된 응답은 스트리밍하지 않고 complete()로 폴백합니다.
        """
        models = self._resolve_models(model, role)
        last_error: Exception | None = None

        for m in models:
            try:
                call_kwargs: dict[str, Any] = {
                    "model": m,
                    "messages": messages,
                    "temperature": kwargs.get("temperature", self.config.temperature),
                    "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
                    "timeout": self.config.timeout,
                    "stream": True,
                }
                if tools:
                    call_kwargs["tools"] = tools

                response = await litellm.acompletion(**call_kwargs)
                async for chunk in response:
                    yield chunk.model_dump()
                logger.info("llm_stream_success", model=m, role=role)
                return
            except Exception as e:
                last_error = e
                logger.warning("llm_stream_failed", model=m, role=role, error=str(e))
                continue

        raise LLMError(f"모든 LLM 스트리밍 호출 실패. 마지막 에러: {last_error}") from last_error

    async def complete_text(  # [JS-C001.4]
        self,
        prompt: str,
        system: str = "",
        **kwargs: Any,
    ) -> str:
        """단순 텍스트 응답 (편의 메서드)."""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        result = await self.complete(messages, **kwargs)
        return result["choices"][0]["message"]["content"]

    @property
    def models(self) -> list[str]:
        """현재 폴백 체인 모델 목록."""
        return list(self._models)
