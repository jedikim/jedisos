"""
[JS-N004] jedisos.dspy_modules.optimize
GEPA 기반 DSPy 모듈 자동 최적화 파이프라인

version: 1.0.0
created: 2026-02-20
modified: 2026-02-20
dependencies: dspy>=3.1.0
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
import yaml

if TYPE_CHECKING:
    import pathlib

logger = structlog.get_logger()


def _load_training_data(path: pathlib.Path) -> list[dict[str, Any]]:
    """YAML 형식의 학습 데이터를 로드합니다.

    Args:
        path: YAML 파일 경로

    Returns:
        예시 딕셔너리 리스트
    """
    if not path.exists():
        logger.warning("training_data_not_found", path=str(path))
        return []

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return []
    return data.get("examples", [])


def optimize_intent_classifier(  # [JS-N004.1]
    data_dir: pathlib.Path,
    model: str = "gpt-5.2",
    auto: str = "light",
) -> dict[str, Any]:
    """의도분류 모듈을 GEPA로 최적화합니다.

    Args:
        data_dir: 데이터 디렉토리 (data/dspy/)
        model: 최적화에 사용할 LLM 모델
        auto: GEPA 자동 수준 ("light", "medium", "heavy")

    Returns:
        최적화 결과 딕셔너리
    """
    import dspy

    from jedisos.dspy_modules.intent import IntentClassifier

    training_path = data_dir / "training" / "intent_examples.yaml"
    examples = _load_training_data(training_path)
    if not examples:
        return {"success": False, "error": "학습 데이터 없음", "path": str(training_path)}

    # DSPy Example 변환
    trainset = []
    for ex in examples:
        if "message" in ex and "intent" in ex:
            trainset.append(
                dspy.Example(
                    user_message=ex["message"],
                    intent=ex["intent"],
                ).with_inputs("user_message")
            )

    if len(trainset) < 5:
        return {"success": False, "error": f"학습 데이터 부족 ({len(trainset)}개, 최소 5개 필요)"}

    # 메트릭 정의
    def intent_metric(
        gold: dspy.Example,
        pred: dspy.Prediction,
        trace: Any = None,
    ) -> float:
        return 1.0 if pred.intent.strip().lower() == gold.intent.strip().lower() else 0.0

    # LM 설정
    lm = dspy.LM(model=model, temperature=0.0, max_tokens=20)

    # GEPA 최적화
    with dspy.context(lm=lm):
        classifier = IntentClassifier()

        optimizer = dspy.MIPROv2(
            metric=intent_metric,
            auto=auto,
        )

        optimized = optimizer.compile(
            classifier,
            trainset=trainset,
        )

    # 결과 저장
    output_path = data_dir / "intent_classifier.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    optimized.save(str(output_path))

    logger.info(
        "intent_classifier_optimized",
        examples=len(trainset),
        output=str(output_path),
    )

    return {
        "success": True,
        "examples": len(trainset),
        "output_path": str(output_path),
        "auto": auto,
    }


def optimize_fact_extractor(  # [JS-N004.2]
    data_dir: pathlib.Path,
    model: str = "gpt-5.2",
    auto: str = "medium",
) -> dict[str, Any]:
    """사실추출 모듈을 GEPA로 최적화합니다.

    Args:
        data_dir: 데이터 디렉토리 (data/dspy/)
        model: 최적화에 사용할 LLM 모델
        auto: GEPA 자동 수준 ("light", "medium", "heavy")

    Returns:
        최적화 결과 딕셔너리
    """
    import dspy

    from jedisos.dspy_modules.facts import FactExtractor

    training_path = data_dir / "training" / "fact_examples.yaml"
    examples = _load_training_data(training_path)
    if not examples:
        return {"success": False, "error": "학습 데이터 없음", "path": str(training_path)}

    # DSPy Example 변환
    trainset = []
    for ex in examples:
        if "conversation" in ex and "facts" in ex:
            trainset.append(
                dspy.Example(
                    conversation=ex["conversation"],
                    facts=ex["facts"],
                ).with_inputs("conversation")
            )

    if len(trainset) < 5:
        return {"success": False, "error": f"학습 데이터 부족 ({len(trainset)}개, 최소 5개 필요)"}

    # 메트릭: F1 기반
    def fact_metric(
        gold: dspy.Example,
        pred: dspy.Prediction,
        trace: Any = None,
    ) -> float:
        gold_set = set(gold.facts) if isinstance(gold.facts, list) else set()
        pred_facts = pred.facts if isinstance(pred.facts, list) else []
        pred_set = {f.strip() for f in pred_facts if isinstance(f, str)}

        if not gold_set and not pred_set:
            return 1.0
        if not gold_set or not pred_set:
            return 0.0

        # 부분 매칭 (키워드 포함 여부)
        matches = 0
        for gf in gold_set:
            for pf in pred_set:
                if gf in pf or pf in gf:
                    matches += 1
                    break

        precision = matches / len(pred_set) if pred_set else 0.0
        recall = matches / len(gold_set) if gold_set else 0.0
        if precision + recall == 0:
            return 0.0
        return 2 * precision * recall / (precision + recall)

    # LM 설정
    lm = dspy.LM(model=model, temperature=0.0, max_tokens=300)

    # GEPA 최적화
    with dspy.context(lm=lm):
        extractor = FactExtractor()

        optimizer = dspy.MIPROv2(
            metric=fact_metric,
            auto=auto,
        )

        optimized = optimizer.compile(
            extractor,
            trainset=trainset,
        )

    # 결과 저장
    output_path = data_dir / "fact_extractor.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    optimized.save(str(output_path))

    logger.info(
        "fact_extractor_optimized",
        examples=len(trainset),
        output=str(output_path),
    )

    return {
        "success": True,
        "examples": len(trainset),
        "output_path": str(output_path),
        "auto": auto,
    }
