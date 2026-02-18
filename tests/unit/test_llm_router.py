"""
[JS-T004] tests.unit.test_llm_router
LLMRouter 단위 테스트 (mock 기반)

version: 1.0.0
created: 2026-02-16
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jedisos.core.config import LLMConfig
from jedisos.core.exceptions import LLMError
from jedisos.llm.prompts import SYSTEM_BASE, build_system_prompt
from jedisos.llm.router import LLMRouter


def _make_llm_response(content: str = "Hello!") -> MagicMock:
    """mock LLM 응답 생성."""
    response = MagicMock()
    response.model_dump.return_value = {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "model": "gpt-5.2",
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }
    return response


@pytest.fixture
def router():
    config = LLMConfig(
        models=["gpt-5.2", "gemini/gemini-3-flash"],
        config_file="nonexistent.yaml",
    )
    return LLMRouter(config=config)


class TestLLMRouterInit:  # [JS-T004.1]
    def test_models_from_config(self, router):
        assert router.models == ["gpt-5.2", "gemini/gemini-3-flash"]

    def test_models_from_yaml(self, tmp_path):
        yaml_file = tmp_path / "llm_config.yaml"
        yaml_file.write_text(
            "models:\n  - model: custom-model-1\n  - model: custom-model-2\n",
            encoding="utf-8",
        )
        config = LLMConfig(models=["default"], config_file=str(yaml_file))
        router = LLMRouter(config=config)
        assert router.models == ["custom-model-1", "custom-model-2"]


class TestLLMRouterComplete:  # [JS-T004.2]
    @pytest.mark.asyncio
    async def test_complete_success(self, router):
        mock_resp = _make_llm_response("안녕하세요!")
        with patch(
            "jedisos.llm.router.litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await router.complete([{"role": "user", "content": "hi"}])
            assert result["choices"][0]["message"]["content"] == "안녕하세요!"

    @pytest.mark.asyncio
    async def test_fallback_on_failure(self, router):
        """1차 모델 실패 시 2차 모델로 폴백."""
        mock_resp = _make_llm_response("from gemini")

        call_count = 0

        async def mock_acompletion(**kwargs):
            nonlocal call_count
            call_count += 1
            if kwargs["model"] == "gpt-5.2":
                raise Exception("OpenAI rate limited")
            return mock_resp

        with patch("jedisos.llm.router.litellm.acompletion", side_effect=mock_acompletion):
            result = await router.complete([{"role": "user", "content": "test"}])
            assert result["choices"][0]["message"]["content"] == "from gemini"
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_all_models_fail_raises(self, router):
        """모든 모델 실패 시 LLMError."""
        with (
            patch(
                "jedisos.llm.router.litellm.acompletion",
                new_callable=AsyncMock,
                side_effect=Exception("all fail"),
            ),
            pytest.raises(LLMError, match="모든 LLM 호출 실패"),
        ):
            await router.complete([{"role": "user", "content": "test"}])

    @pytest.mark.asyncio
    async def test_specific_model_override(self, router):
        """특정 모델을 직접 지정하면 폴백 체인 무시."""
        mock_resp = _make_llm_response("specific")

        async def mock_acompletion(**kwargs):
            assert kwargs["model"] == "custom-model"
            return mock_resp

        with patch("jedisos.llm.router.litellm.acompletion", side_effect=mock_acompletion):
            result = await router.complete(
                [{"role": "user", "content": "test"}], model="custom-model"
            )
            assert result["choices"][0]["message"]["content"] == "specific"


class TestLLMRouterCompleteText:  # [JS-T004.3]
    @pytest.mark.asyncio
    async def test_complete_text(self, router):
        mock_resp = _make_llm_response("답변입니다")
        with patch(
            "jedisos.llm.router.litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp
        ):
            text = await router.complete_text("질문입니다")
            assert text == "답변입니다"

    @pytest.mark.asyncio
    async def test_complete_text_with_system(self, router):
        mock_resp = _make_llm_response("시스템 답변")

        async def mock_acompletion(**kwargs):
            assert kwargs["messages"][0]["role"] == "system"
            assert kwargs["messages"][1]["role"] == "user"
            return mock_resp

        with patch("jedisos.llm.router.litellm.acompletion", side_effect=mock_acompletion):
            text = await router.complete_text("질문", system="시스템 프롬프트")
            assert text == "시스템 답변"


class TestPrompts:  # [JS-T004.4]
    def test_build_system_prompt_default(self):
        prompt = build_system_prompt()
        assert prompt == SYSTEM_BASE

    def test_build_system_prompt_with_identity(self):
        prompt = build_system_prompt(identity="나는 JediSOS입니다")
        assert "JediSOS" in prompt

    def test_build_system_prompt_with_memory(self):
        prompt = build_system_prompt(memory_context="Alice는 엔지니어입니다")
        assert "Alice" in prompt

    def test_build_system_prompt_with_identity_and_memory(self):
        prompt = build_system_prompt(
            identity="나는 JediSOS입니다",
            memory_context="Bob은 디자이너입니다",
        )
        assert "JediSOS" in prompt
        assert "Bob" in prompt

    def test_build_system_prompt_no_identity(self):
        prompt = build_system_prompt()
        assert "JediSOS" in prompt


class TestYAMLConfigChange:  # [JS-T004.5]
    """llm_config.yaml 변경만으로 모델 순서가 바뀌는지 확인."""

    def test_yaml_config_changes_model_order(self, tmp_path):
        yaml_v1 = tmp_path / "v1.yaml"
        yaml_v1.write_text(
            "models:\n  - model: model-a\n  - model: model-b\n",
            encoding="utf-8",
        )
        router1 = LLMRouter(LLMConfig(config_file=str(yaml_v1)))
        assert router1.models == ["model-a", "model-b"]

        yaml_v2 = tmp_path / "v2.yaml"
        yaml_v2.write_text(
            "models:\n  - model: model-b\n  - model: model-a\n  - model: model-c\n",
            encoding="utf-8",
        )
        router2 = LLMRouter(LLMConfig(config_file=str(yaml_v2)))
        assert router2.models == ["model-b", "model-a", "model-c"]
