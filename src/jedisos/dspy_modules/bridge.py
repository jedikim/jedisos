"""
[JS-N003] jedisos.dspy_modules.bridge
LLMRouter ↔ DSPy 브릿지 — LiteLLM 모델을 DSPy에서 사용

version: 1.0.0
created: 2026-02-20
modified: 2026-02-20
dependencies: dspy>=3.1.0
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import dspy
import structlog

from jedisos.dspy_modules.facts import FactExtractor
from jedisos.dspy_modules.intent import IntentClassifier

if TYPE_CHECKING:
    import pathlib

    from jedisos.llm.router import LLMRouter

logger = structlog.get_logger()

_VALID_INTENTS = frozenset({"chat", "question", "remember", "skill_request", "complex"})


class DSPyBridge:  # [JS-N003.1]
    """LLMRouter의 모델을 DSPy LM으로 변환하여 DSPy 모듈을 실행합니다.

    3-Tier 폴백:
    1. GEPA 최적화된 DSPy 모듈 (data/dspy/*.json 존재 시)
    2. 기본 DSPy 모듈 (최적화 없이)
    3. 실패 시 기본값 반환 (호출자가 Tier 2 YAML/상수 폴백 처리)
    """

    def __init__(self, llm_router: LLMRouter, data_dir: pathlib.Path) -> None:  # [JS-N003.1.1]
        self._router = llm_router
        self._dspy_dir = data_dir / "dspy"
        self._intent: IntentClassifier | None = None
        self._facts: FactExtractor | None = None
        self._classify_lm: dspy.LM | None = None
        self._extract_lm: dspy.LM | None = None

    def initialize(self) -> None:  # [JS-N003.2]
        """LLMRouter의 classify/extract 모델로 DSPy LM 구성 + 최적화 상태 로드."""
        classify_models = self._router.models_for("classify") or self._router.models
        extract_models = self._router.models_for("extract") or self._router.models

        self._classify_lm = dspy.LM(model=classify_models[0], temperature=0.0, max_tokens=20)
        self._extract_lm = dspy.LM(model=extract_models[0], temperature=0.0, max_tokens=300)

        self._intent = IntentClassifier()
        self._facts = FactExtractor()

        # GEPA 최적화 상태 로드 (있으면)
        intent_path = self._dspy_dir / "intent_classifier.json"
        if intent_path.exists():
            try:
                self._intent.load(str(intent_path))
                logger.info("dspy_intent_optimized_loaded", path=str(intent_path))
            except Exception as e:
                logger.warning("dspy_intent_load_failed", error=str(e))

        fact_path = self._dspy_dir / "fact_extractor.json"
        if fact_path.exists():
            try:
                self._facts.load(str(fact_path))
                logger.info("dspy_facts_optimized_loaded", path=str(fact_path))
            except Exception as e:
                logger.warning("dspy_facts_load_failed", error=str(e))

        logger.info(
            "dspy_bridge_ready",
            classify_model=classify_models[0],
            extract_model=extract_models[0],
        )

    async def classify_intent(self, user_message: str) -> str:  # [JS-N003.3]
        """DSPy로 의도분류. 실패 시 "chat" 반환.

        Args:
            user_message: 사용자 메시지

        Returns:
            의도 문자열 (chat, question, remember, skill_request, complex 중 하나)
        """
        if self._intent is None or self._classify_lm is None:
            return "chat"

        try:
            with dspy.context(lm=self._classify_lm):
                result = self._intent(user_message=user_message)
            raw = result.intent.strip().lower().split()[0]
            return raw if raw in _VALID_INTENTS else "chat"
        except Exception as e:
            logger.debug("dspy_classify_failed", error=str(e))
            return "chat"

    async def extract_facts(self, conversation: str) -> list[str]:  # [JS-N003.4]
        """DSPy로 사실추출. 실패 시 빈 리스트.

        Args:
            conversation: 대화 텍스트

        Returns:
            추출된 사실 리스트
        """
        if self._facts is None or self._extract_lm is None:
            return []

        try:
            with dspy.context(lm=self._extract_lm):
                result = self._facts(conversation=conversation)
            if isinstance(result.facts, list):
                return [
                    f.strip() for f in result.facts if isinstance(f, str) and len(f.strip()) >= 3
                ]
        except Exception as e:
            logger.debug("dspy_extract_failed", error=str(e))

        return []

    def reload(self) -> None:  # [JS-N003.5]
        """최적화 완료 후 상태 재로드."""
        self.initialize()

    def _get_models_for(self, role: str) -> list[str]:
        """LLMRouter에서 역할별 모델을 가져옵니다."""
        models = self._router.models_for(role) if hasattr(self._router, "models_for") else None
        return models or list(self._router.models)
