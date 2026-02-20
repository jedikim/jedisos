"""
[JS-N001] jedisos.dspy_modules.intent
DSPy 기반 의도분류 모듈

version: 1.0.0
created: 2026-02-20
modified: 2026-02-20
dependencies: dspy>=3.1.0
"""

from __future__ import annotations

import dspy


class IntentClassification(dspy.Signature):  # [JS-N001.1]
    """Classify user message intent into exactly one category."""

    user_message: str = dspy.InputField(desc="User's chat message")
    intent: str = dspy.OutputField(
        desc="Exactly one of: chat, question, remember, skill_request, complex"
    )


class IntentClassifier(dspy.Module):  # [JS-N001.2]
    """DSPy 의도분류 모듈.

    사용자 메시지를 5가지 카테고리 중 하나로 분류합니다:
    - chat: 순수 인사, 잡담, 감사 표현
    - question: 사실 확인, 정보 질문
    - remember: 개인정보 저장 요청
    - skill_request: 도구/스킬 생성/수정 요청
    - complex: 분석, 비교, 추론이 필요한 복잡한 질문
    """

    def __init__(self) -> None:
        super().__init__()
        self.predict = dspy.Predict(IntentClassification)

    def forward(self, user_message: str) -> dspy.Prediction:  # [JS-N001.2.1]
        """동기 의도분류."""
        return self.predict(user_message=user_message)
