"""
[JS-N000] jedisos.dspy_modules
DSPy 기반 프롬프트 최적화 모듈 패키지

version: 1.1.0
created: 2026-02-20
modified: 2026-02-20
dependencies: dspy>=3.1.0 (optional)
"""


def model_safe_name(model: str) -> str:  # [JS-N000.1]
    """모델 이름을 파일명에 안전한 형태로 변환.

    Args:
        model: LLM 모델 이름 (e.g. "gemini/gemini-2.5-flash")

    Returns:
        파일명 안전 문자열 (e.g. "gemini_gemini-2.5-flash")
    """
    return model.replace("/", "_")
