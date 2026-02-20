"""
[JS-C004] jedisos.llm.prompt_registry
YAML 파일 기반 프롬프트 레지스트리 — 핫리로드 지원

version: 1.0.0
created: 2026-02-20
modified: 2026-02-20
dependencies: pyyaml>=6.0.2
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
import yaml

if TYPE_CHECKING:
    import pathlib

logger = structlog.get_logger()


class PromptRegistry:  # [JS-C004.1]
    """YAML 파일 기반 프롬프트 레지스트리. 핫리로드 지원.

    config/prompts/ 디렉토리의 YAML 파일에서 프롬프트를 로드합니다.
    파일 mtime 변경 시 자동 리로드합니다.

    YAML 포맷:
        meta:
          name: prompt_name
          version: "1.0.0"
        prompts:
          key1: |
            프롬프트 내용...
          key2: |
            다른 프롬프트...
    """

    def __init__(self, prompts_dir: pathlib.Path) -> None:  # [JS-C004.1.1]
        self._dir = prompts_dir
        self._cache: dict[str, dict[str, Any]] = {}
        self._mtimes: dict[str, float] = {}

    def get(self, file_key: str, prompt_key: str, **fmt: str) -> str:  # [JS-C004.2]
        """프롬프트 로드. fmt로 {변수} 치환.

        Args:
            file_key: YAML 파일명 (확장자 없이)
            prompt_key: prompts 섹션의 키
            **fmt: format() 치환 변수

        Returns:
            프롬프트 문자열

        Raises:
            KeyError: 파일이나 키가 없으면
        """
        self._ensure_loaded(file_key)
        prompts = self._cache[file_key].get("prompts", {})
        if prompt_key not in prompts:
            msg = f"Prompt key '{prompt_key}' not found in '{file_key}.yaml'"
            raise KeyError(msg)
        template = prompts[prompt_key]
        if fmt:
            return template.format(**fmt)
        return template

    def get_or_default(
        self, file_key: str, prompt_key: str, default: str, **fmt: str
    ) -> str:  # [JS-C004.3]
        """YAML 없으면 default 반환 (하위호환).

        Args:
            file_key: YAML 파일명 (확장자 없이)
            prompt_key: prompts 섹션의 키
            default: YAML 파일/키가 없을 때 반환할 기본값
            **fmt: format() 치환 변수

        Returns:
            프롬프트 문자열 또는 default
        """
        try:
            return self.get(file_key, prompt_key, **fmt)
        except (KeyError, FileNotFoundError, yaml.YAMLError):
            if fmt:
                return default.format(**fmt)
            return default

    def reload(self, file_key: str | None = None) -> None:  # [JS-C004.4]
        """파일 변경 감지 + 리로드.

        Args:
            file_key: 특정 파일만 리로드. None이면 전체.
        """
        if file_key:
            self._cache.pop(file_key, None)
            self._mtimes.pop(file_key, None)
        else:
            self._cache.clear()
            self._mtimes.clear()

    def list_prompts(self) -> dict[str, list[str]]:  # [JS-C004.5]
        """관리 UI용 프롬프트 목록.

        Returns:
            {파일키: [프롬프트키 목록]} 딕셔너리
        """
        result: dict[str, list[str]] = {}
        if not self._dir.exists():
            return result
        for yaml_file in sorted(self._dir.glob("*.yaml")):
            file_key = yaml_file.stem
            try:
                self._ensure_loaded(file_key)
                prompts = self._cache.get(file_key, {}).get("prompts", {})
                result[file_key] = list(prompts.keys())
            except Exception:
                result[file_key] = []
        return result

    def _ensure_loaded(self, file_key: str) -> None:
        """파일이 로드되지 않았거나 변경되었으면 로드합니다."""
        yaml_path = self._dir / f"{file_key}.yaml"
        if not yaml_path.exists():
            msg = f"Prompt file not found: {yaml_path}"
            raise FileNotFoundError(msg)

        mtime = yaml_path.stat().st_mtime
        if file_key in self._cache and self._mtimes.get(file_key) == mtime:
            return

        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            msg = f"Invalid YAML format in {yaml_path}"
            raise yaml.YAMLError(msg)

        self._cache[file_key] = data
        self._mtimes[file_key] = mtime
        logger.debug("prompt_loaded", file_key=file_key, path=str(yaml_path))


# 모듈 레벨 싱글턴
_registry: PromptRegistry | None = None


def get_registry() -> PromptRegistry | None:  # [JS-C004.6]
    """글로벌 PromptRegistry 인스턴스를 반환합니다."""
    return _registry


def set_registry(registry: PromptRegistry) -> None:  # [JS-C004.7]
    """글로벌 PromptRegistry 인스턴스를 설정합니다."""
    global _registry
    _registry = registry
    logger.info("prompt_registry_set", prompts_dir=str(registry._dir))
