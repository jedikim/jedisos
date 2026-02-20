"""
[JS-N002] jedisos.dspy_modules.facts
DSPy 기반 사실추출 모듈

version: 1.0.0
created: 2026-02-20
modified: 2026-02-20
dependencies: dspy>=3.1.0
"""

from __future__ import annotations

import dspy


class FactExtraction(dspy.Signature):  # [JS-N002.1]
    """Extract memorable personal facts from conversation text."""

    conversation: str = dspy.InputField(desc="Conversation text to extract facts from")
    facts: list[str] = dspy.OutputField(
        desc='Clean personal facts list. Empty if none. e.g. ["이름: 김제다이", "주소: 서울시 강남구"]'
    )


class FactExtractor(dspy.Module):  # [JS-N002.2]
    """DSPy 사실추출 모듈.

    대화 텍스트에서 장기 기억할 가치가 있는 개인 사실을 추출합니다.
    추출 대상: 이름, 주소, 생일, 전화번호, 이메일, 선호도, 중요한 개인정보
    """

    def __init__(self) -> None:
        super().__init__()
        self.predict = dspy.Predict(FactExtraction)

    def forward(self, conversation: str) -> dspy.Prediction:  # [JS-N002.2.1]
        """동기 사실추출."""
        return self.predict(conversation=conversation)
