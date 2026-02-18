"""
[JS-C001] jedisos.llm.router
LiteLLM 라우터 래퍼 - 멀티 LLM 프로바이더 폴백

version: 1.0.0
created: 2026-02-16
modified: 2026-02-17
dependencies: litellm>=1.81.12
"""

from __future__ import annotations

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
    llm_config.yaml 파일이 있으면 환경변수보다 우선합니다.
    """

    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig()
        self._models = self._load_models()
        litellm.set_verbose = False
        logger.info("llm_router_init", models=self._models)

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

    async def complete(  # [JS-C001.3]
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """LLM 호출 (폴백 체인 포함).

        Args:
            messages: 대화 메시지 리스트
            tools: 사용 가능한 도구 정의 (선택)
            model: 특정 모델 지정 (None이면 폴백 체인 사용)

        Returns:
            LLM 응답 딕셔너리
        """
        models = [model] if model else self._models
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

                response = await litellm.acompletion(**call_kwargs)
                logger.info("llm_call_success", model=m)
                return response.model_dump()
            except Exception as e:
                last_error = e
                logger.warning("llm_call_failed", model=m, error=str(e))
                continue

        raise LLMError(f"모든 LLM 호출 실패. 마지막 에러: {last_error}") from last_error

    async def stream(  # [JS-C001.5]
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        """LLM 스트리밍 호출. 토큰 단위로 청크를 yield합니다.

        tool_calls가 포함된 응답은 스트리밍하지 않고 complete()로 폴백합니다.
        """
        models = [model] if model else self._models
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
                logger.info("llm_stream_success", model=m)
                return
            except Exception as e:
                last_error = e
                logger.warning("llm_stream_failed", model=m, error=str(e))
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
