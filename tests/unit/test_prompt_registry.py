"""
[JS-T015] tests.unit.test_prompt_registry
PromptRegistry 단위 테스트

version: 1.0.0
created: 2026-02-20
modified: 2026-02-20
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml

from jedisos.llm.prompt_registry import PromptRegistry, get_registry, set_registry

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    """테스트용 프롬프트 디렉토리를 생성합니다."""
    d = tmp_path / "prompts"
    d.mkdir()

    # identity.yaml
    (d / "identity.yaml").write_text(
        yaml.dump(
            {
                "meta": {"name": "test_identity", "version": "1.0.0"},
                "prompts": {
                    "identity": "당신은 테스트 AI입니다.",
                    "system_base": "기본 시스템 프롬프트.",
                },
            },
            allow_unicode=True,
        )
    )

    # intent_classifier.yaml
    (d / "intent_classifier.yaml").write_text(
        yaml.dump(
            {
                "meta": {"name": "intent", "version": "1.0.0"},
                "prompts": {
                    "classify": "의도를 분류하세요: {options}",
                },
            },
            allow_unicode=True,
        )
    )

    # forge_code_gen.yaml with format variables
    (d / "forge_code_gen.yaml").write_text(
        yaml.dump(
            {
                "meta": {"name": "forge", "version": "1.0.0"},
                "prompts": {
                    "template": "생성 요청: {request}\n참조: {reference_section}",
                },
            },
            allow_unicode=True,
        )
    )

    return d


@pytest.fixture
def registry(prompts_dir: Path) -> PromptRegistry:
    return PromptRegistry(prompts_dir=prompts_dir)


class TestPromptRegistryGet:  # [JS-T015.1]
    """get() 테스트."""

    def test_get_existing_prompt(self, registry: PromptRegistry) -> None:
        result = registry.get("identity", "identity")
        assert result == "당신은 테스트 AI입니다."

    def test_get_with_format(self, registry: PromptRegistry) -> None:
        result = registry.get("intent_classifier", "classify", options="chat, question")
        assert "chat, question" in result

    def test_get_missing_file_raises(self, registry: PromptRegistry) -> None:
        with pytest.raises(FileNotFoundError):
            registry.get("nonexistent", "key")

    def test_get_missing_key_raises(self, registry: PromptRegistry) -> None:
        with pytest.raises(KeyError):
            registry.get("identity", "nonexistent_key")


class TestPromptRegistryGetOrDefault:  # [JS-T015.2]
    """get_or_default() 테스트."""

    def test_returns_yaml_value(self, registry: PromptRegistry) -> None:
        result = registry.get_or_default("identity", "identity", default="기본값")
        assert result == "당신은 테스트 AI입니다."

    def test_returns_default_on_missing_file(self, registry: PromptRegistry) -> None:
        result = registry.get_or_default("nonexistent", "key", default="기본값")
        assert result == "기본값"

    def test_returns_default_on_missing_key(self, registry: PromptRegistry) -> None:
        result = registry.get_or_default("identity", "nonexistent", default="기본값")
        assert result == "기본값"

    def test_default_with_format(self, registry: PromptRegistry) -> None:
        result = registry.get_or_default("nonexistent", "key", default="Hello {name}", name="World")
        assert result == "Hello World"

    def test_yaml_with_format(self, registry: PromptRegistry) -> None:
        result = registry.get_or_default(
            "forge_code_gen",
            "template",
            default="fallback",
            request="날씨 도구",
            reference_section="없음",
        )
        assert "날씨 도구" in result
        assert "없음" in result


class TestPromptRegistryReload:  # [JS-T015.3]
    """reload() 테스트."""

    def test_reload_single_file(self, registry: PromptRegistry, prompts_dir: Path) -> None:
        # 첫 로드
        registry.get("identity", "identity")

        # 파일 수정
        (prompts_dir / "identity.yaml").write_text(
            yaml.dump(
                {
                    "meta": {"name": "updated", "version": "2.0.0"},
                    "prompts": {"identity": "수정된 프롬프트"},
                },
                allow_unicode=True,
            )
        )

        # 리로드 전 — 캐시된 값
        # mtime이 같을 수 있어서 reload 호출
        registry.reload("identity")
        result = registry.get("identity", "identity")
        assert result == "수정된 프롬프트"

    def test_reload_all(self, registry: PromptRegistry) -> None:
        registry.get("identity", "identity")
        registry.reload()
        # 재로드 후에도 정상 동작
        result = registry.get("identity", "identity")
        assert result == "당신은 테스트 AI입니다."


class TestPromptRegistryListPrompts:  # [JS-T015.4]
    """list_prompts() 테스트."""

    def test_list_all_prompts(self, registry: PromptRegistry) -> None:
        result = registry.list_prompts()
        assert "identity" in result
        assert "intent_classifier" in result
        assert "forge_code_gen" in result
        assert "identity" in result["identity"]
        assert "system_base" in result["identity"]

    def test_list_prompts_empty_dir(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        r = PromptRegistry(prompts_dir=empty_dir)
        assert r.list_prompts() == {}

    def test_list_prompts_nonexistent_dir(self, tmp_path: Path) -> None:
        r = PromptRegistry(prompts_dir=tmp_path / "nonexistent")
        assert r.list_prompts() == {}


class TestPromptRegistrySingleton:  # [JS-T015.5]
    """모듈 레벨 싱글턴 테스트."""

    def test_set_and_get_registry(self, registry: PromptRegistry) -> None:
        from jedisos.llm import prompt_registry as pr_mod

        old = pr_mod._registry
        try:
            set_registry(registry)
            assert get_registry() is registry
        finally:
            pr_mod._registry = old


class TestPromptRegistryHotReload:  # [JS-T015.6]
    """파일 변경 감지 테스트."""

    def test_detects_mtime_change(self, registry: PromptRegistry, prompts_dir: Path) -> None:
        import time

        # 첫 로드
        v1 = registry.get("identity", "identity")
        assert v1 == "당신은 테스트 AI입니다."

        # 파일 수정 (mtime 변경 보장을 위해 약간 대기)
        time.sleep(0.01)
        (prompts_dir / "identity.yaml").write_text(
            yaml.dump(
                {
                    "meta": {"name": "hot", "version": "3.0.0"},
                    "prompts": {"identity": "핫리로드 프롬프트"},
                },
                allow_unicode=True,
            )
        )

        # mtime이 변경되었으므로 자동 리로드
        v2 = registry.get("identity", "identity")
        assert v2 == "핫리로드 프롬프트"


class TestPromptsHelpers:  # [JS-T015.7]
    """llm/prompts.py 헬퍼 함수 테스트."""

    def test_get_identity_prompt_without_registry(self) -> None:
        from jedisos.llm import prompt_registry as pr_mod
        from jedisos.llm.prompts import JEDISOS_IDENTITY, get_identity_prompt

        # 레지스트리 없음 → 상수 반환
        old = pr_mod._registry
        pr_mod._registry = None
        try:
            result = get_identity_prompt()
            assert result == JEDISOS_IDENTITY
        finally:
            pr_mod._registry = old

    def test_get_identity_prompt_with_registry(self, registry: PromptRegistry) -> None:
        from jedisos.llm import prompt_registry as pr_mod
        from jedisos.llm.prompts import get_identity_prompt

        old = pr_mod._registry
        pr_mod._registry = registry
        try:
            result = get_identity_prompt()
            assert result == "당신은 테스트 AI입니다."
        finally:
            pr_mod._registry = old

    def test_get_intent_prompt(self) -> None:
        from jedisos.llm.prompts import get_intent_prompt

        result = get_intent_prompt()
        assert "chat" in result
        assert "question" in result

    def test_get_fact_prompt(self) -> None:
        from jedisos.llm.prompts import get_fact_prompt

        result = get_fact_prompt()
        assert "JSON" in result or "배열" in result
