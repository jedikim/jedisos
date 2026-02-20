"""
[JS-T016] tests.unit.test_dspy_modules
DSPy 모듈 단위 테스트 (dspy 미설치 시에도 통과)

version: 1.0.0
created: 2026-02-20
modified: 2026-02-20
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from pathlib import Path


# dspy가 없으면 관련 테스트 스킵
dspy = pytest.importorskip("dspy", reason="dspy not installed")


class TestIntentClassifier:  # [JS-T016.1]
    """IntentClassifier 모듈 테스트."""

    def test_module_creation(self) -> None:
        from jedisos.dspy_modules.intent import IntentClassifier

        classifier = IntentClassifier()
        assert classifier.predict is not None

    def test_signature_fields(self) -> None:
        from jedisos.dspy_modules.intent import IntentClassification

        assert "user_message" in IntentClassification.input_fields
        assert "intent" in IntentClassification.output_fields


class TestFactExtractor:  # [JS-T016.2]
    """FactExtractor 모듈 테스트."""

    def test_module_creation(self) -> None:
        from jedisos.dspy_modules.facts import FactExtractor

        extractor = FactExtractor()
        assert extractor.predict is not None

    def test_signature_fields(self) -> None:
        from jedisos.dspy_modules.facts import FactExtraction

        assert "conversation" in FactExtraction.input_fields
        assert "facts" in FactExtraction.output_fields


class TestDSPyBridge:  # [JS-T016.3]
    """DSPyBridge 테스트."""

    @pytest.fixture
    def mock_router(self) -> MagicMock:
        router = MagicMock()
        router.models = ["gpt-5.2"]
        router.models_for = MagicMock(return_value=["gpt-5.2"])
        return router

    @pytest.fixture
    def bridge(self, mock_router: MagicMock, tmp_path: Path) -> object:
        from jedisos.dspy_modules.bridge import DSPyBridge

        return DSPyBridge(llm_router=mock_router, data_dir=tmp_path)

    def test_bridge_creation(self, bridge: object) -> None:
        assert bridge._intent is None  # type: ignore[attr-defined]
        assert bridge._facts is None  # type: ignore[attr-defined]

    def test_bridge_initialize(self, bridge: object) -> None:
        bridge.initialize()  # type: ignore[attr-defined]
        assert bridge._intent is not None  # type: ignore[attr-defined]
        assert bridge._facts is not None  # type: ignore[attr-defined]
        assert bridge._classify_lm is not None  # type: ignore[attr-defined]
        assert bridge._extract_lm is not None  # type: ignore[attr-defined]

    async def test_classify_intent_returns_chat_before_init(self, bridge: object) -> None:
        """초기화 전에는 "chat" 반환."""
        result = await bridge.classify_intent("안녕하세요")  # type: ignore[attr-defined]
        assert result == "chat"

    async def test_extract_facts_returns_empty_before_init(self, bridge: object) -> None:
        """초기화 전에는 빈 리스트 반환."""
        result = await bridge.extract_facts("테스트")  # type: ignore[attr-defined]
        assert result == []

    async def test_classify_intent_with_mocked_dspy(self, bridge: object) -> None:
        """DSPy 모듈을 mock하여 의도분류 테스트."""
        bridge.initialize()  # type: ignore[attr-defined]

        # IntentClassifier의 predict를 mock
        mock_prediction = MagicMock()
        mock_prediction.intent = "question"
        bridge._intent = MagicMock()  # type: ignore[attr-defined]
        bridge._intent.return_value = mock_prediction  # type: ignore[attr-defined]

        result = await bridge.classify_intent("서울 날씨 어때?")  # type: ignore[attr-defined]
        assert result == "question"

    async def test_classify_intent_invalid_returns_chat(self, bridge: object) -> None:
        """유효하지 않은 의도는 "chat"으로 폴백."""
        bridge.initialize()  # type: ignore[attr-defined]

        mock_prediction = MagicMock()
        mock_prediction.intent = "invalid_intent"
        bridge._intent = MagicMock()  # type: ignore[attr-defined]
        bridge._intent.return_value = mock_prediction  # type: ignore[attr-defined]

        result = await bridge.classify_intent("테스트")  # type: ignore[attr-defined]
        assert result == "chat"

    async def test_extract_facts_with_mocked_dspy(self, bridge: object) -> None:
        """DSPy 모듈을 mock하여 사실추출 테스트."""
        bridge.initialize()  # type: ignore[attr-defined]

        mock_prediction = MagicMock()
        mock_prediction.facts = ["이름: 김제다이", "직업: 개발자"]
        bridge._facts = MagicMock()  # type: ignore[attr-defined]
        bridge._facts.return_value = mock_prediction  # type: ignore[attr-defined]

        result = await bridge.extract_facts("내 이름은 김제다이야")  # type: ignore[attr-defined]
        assert len(result) == 2
        assert "이름: 김제다이" in result

    async def test_extract_facts_filters_short(self, bridge: object) -> None:
        """3자 미만의 사실은 필터링됨."""
        bridge.initialize()  # type: ignore[attr-defined]

        mock_prediction = MagicMock()
        mock_prediction.facts = ["이름: 김제다이", "ab", ""]
        bridge._facts = MagicMock()  # type: ignore[attr-defined]
        bridge._facts.return_value = mock_prediction  # type: ignore[attr-defined]

        result = await bridge.extract_facts("테스트")  # type: ignore[attr-defined]
        assert len(result) == 1
        assert "이름: 김제다이" in result

    async def test_classify_intent_handles_exception(self, bridge: object) -> None:
        """DSPy 호출 실패 시 "chat" 반환."""
        bridge.initialize()  # type: ignore[attr-defined]

        bridge._intent = MagicMock(side_effect=RuntimeError("DSPy error"))  # type: ignore[attr-defined]

        result = await bridge.classify_intent("테스트")  # type: ignore[attr-defined]
        assert result == "chat"

    async def test_extract_facts_handles_exception(self, bridge: object) -> None:
        """DSPy 호출 실패 시 빈 리스트 반환."""
        bridge.initialize()  # type: ignore[attr-defined]

        bridge._facts = MagicMock(side_effect=RuntimeError("DSPy error"))  # type: ignore[attr-defined]

        result = await bridge.extract_facts("테스트")  # type: ignore[attr-defined]
        assert result == []


class TestOptimize:  # [JS-T016.4]
    """최적화 파이프라인 테스트 (학습 데이터 로드만 검증)."""

    def test_load_training_data_intent(self) -> None:
        from pathlib import Path

        from jedisos.dspy_modules.optimize import _load_training_data

        path = Path("data/dspy/training/intent_examples.yaml")
        if path.exists():
            examples = _load_training_data(path)
            assert len(examples) >= 20
            assert all("message" in ex and "intent" in ex for ex in examples)
        else:
            # CI 환경에서 data/ 디렉토리가 없을 수 있음
            pass

    def test_load_training_data_facts(self) -> None:
        from pathlib import Path

        from jedisos.dspy_modules.optimize import _load_training_data

        path = Path("data/dspy/training/fact_examples.yaml")
        if path.exists():
            examples = _load_training_data(path)
            assert len(examples) >= 20
            assert all("conversation" in ex and "facts" in ex for ex in examples)
        else:
            pass

    def test_load_training_data_missing(self, tmp_path: Path) -> None:
        from jedisos.dspy_modules.optimize import _load_training_data

        result = _load_training_data(tmp_path / "nonexistent.yaml")
        assert result == []


class TestReActAgentDSPyIntegration:  # [JS-T016.5]
    """ReActAgent + DSPy 통합 테스트."""

    def test_agent_accepts_dspy_bridge(self) -> None:
        from jedisos.agents.react import ReActAgent

        memory = MagicMock()
        llm = MagicMock()
        bridge = MagicMock()

        agent = ReActAgent(memory=memory, llm=llm, dspy_bridge=bridge)
        assert agent.dspy_bridge is bridge

    def test_agent_without_dspy_bridge(self) -> None:
        from jedisos.agents.react import ReActAgent

        memory = MagicMock()
        llm = MagicMock()

        agent = ReActAgent(memory=memory, llm=llm)
        assert agent.dspy_bridge is None


class TestZvecMemoryDSPyIntegration:  # [JS-T016.6]
    """ZvecMemory + DSPy 통합 테스트."""

    @pytest.fixture
    def memory(self, tmp_path: Path) -> object:
        from jedisos.core.config import MemoryConfig
        from jedisos.memory.zvec_memory import ZvecMemory

        config = MemoryConfig(data_dir=str(tmp_path / "data"), bank_id="test-bank")
        return ZvecMemory(config=config)

    def test_set_dspy_bridge(self, memory: object) -> None:
        bridge = MagicMock()
        memory.set_dspy_bridge(bridge)  # type: ignore[attr-defined]
        assert memory._dspy_bridge is bridge  # type: ignore[attr-defined]

    def test_set_dspy_bridge_none(self, memory: object) -> None:
        memory.set_dspy_bridge(None)  # type: ignore[attr-defined]
        assert memory._dspy_bridge is None  # type: ignore[attr-defined]

    async def test_extract_facts_with_dspy_bridge(self, memory: object) -> None:
        """DSPy 브릿지가 있으면 Tier 1 사용."""
        bridge = MagicMock()
        bridge.extract_facts = AsyncMock(return_value=["이름: 김제다이"])
        memory.set_dspy_bridge(bridge)  # type: ignore[attr-defined]

        facts = await memory._extract_facts_llm("내 이름은 김제다이야")  # type: ignore[attr-defined]
        assert facts == ["이름: 김제다이"]
        bridge.extract_facts.assert_called_once_with("내 이름은 김제다이야")

    async def test_extract_facts_dspy_fails_falls_to_llm(self, memory: object) -> None:
        """DSPy 실패 시 Tier 2 LLM으로 폴백."""
        bridge = MagicMock()
        bridge.extract_facts = AsyncMock(side_effect=RuntimeError("fail"))
        memory.set_dspy_bridge(bridge)  # type: ignore[attr-defined]

        mock_llm = MagicMock()
        mock_llm.complete_text = AsyncMock(return_value='["이름: 김제다이"]')
        memory.set_llm_router(mock_llm)  # type: ignore[attr-defined]

        facts = await memory._extract_facts_llm("내 이름은 김제다이야")  # type: ignore[attr-defined]
        assert facts == ["이름: 김제다이"]
