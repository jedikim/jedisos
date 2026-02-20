"""
[JS-N004] jedisos.dspy_modules.optimize
GEPA 기반 DSPy 모듈 자동 최적화 파이프라인

version: 1.1.0
created: 2026-02-20
modified: 2026-02-20
dependencies: dspy>=3.1.0, gepa>=0.0.26
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
import yaml

if TYPE_CHECKING:
    import pathlib

logger = structlog.get_logger()


def _patched_dspy_adapter():
    """dspy 3.1.3+ 호환 DspyAdapter를 반환합니다.

    gepa 0.0.26의 DspyAdapter.evaluate()가 dspy 3.1.3에서 제거된
    return_outputs, return_all_scores 파라미터를 사용하므로 패치합니다.
    """
    from gepa.adapters.dspy_adapter.dspy_adapter import DspyAdapter, EvaluationBatch

    class PatchedDspyAdapter(DspyAdapter):
        def evaluate(self, batch, candidate, capture_traces=False):
            if capture_traces:
                return super().evaluate(batch, candidate, capture_traces=True)

            from dspy.evaluate.evaluate import Evaluate

            program = self.build_program(candidate)

            evaluator = Evaluate(
                devset=batch,
                metric=self.metric_fn,
                num_threads=self.num_threads,
                failure_score=self.failure_score,
                provide_traceback=True,
                max_errors=len(batch) * 100,
            )
            res = evaluator(program)

            outputs = [r[1] for r in res.results]
            raw_scores = [r[2] for r in res.results]

            scores = []
            subscores = []
            for raw_score in raw_scores:
                score_val, subscore_dict = self._extract_score_and_subscores(raw_score)
                if score_val is None:
                    score_val = self.failure_score
                scores.append(score_val)
                subscores.append(subscore_dict)

            has_subscores = any(subscores)
            return EvaluationBatch(
                outputs=outputs,
                scores=scores,
                trajectories=None,
                objective_scores=subscores if has_subscores else None,
            )

    return PatchedDspyAdapter


# GEPA auto 프리셋: metric call 횟수 기준
_AUTO_PRESETS: dict[str, int] = {
    "light": 50,
    "medium": 150,
    "heavy": 500,
}


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


def _split_train_val(trainset: list, val_ratio: float = 0.2, min_val: int = 3) -> tuple[list, list]:
    """학습 데이터를 train/val로 분할합니다."""
    import random

    shuffled = trainset.copy()
    random.shuffle(shuffled)
    val_size = max(min_val, int(len(shuffled) * val_ratio))
    val_size = min(val_size, len(shuffled) // 2)
    return shuffled[val_size:], shuffled[:val_size]


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
    import gepa

    from jedisos.dspy_modules.intent import IntentClassifier

    adapter_cls = _patched_dspy_adapter()

    training_path = data_dir / "training" / "intent_examples.yaml"
    examples = _load_training_data(training_path)
    if not examples:
        return {"success": False, "error": "학습 데이터 없음", "path": str(training_path)}

    # DSPy Example 변환
    all_examples = []
    for ex in examples:
        if "message" in ex and "intent" in ex:
            all_examples.append(
                dspy.Example(
                    user_message=ex["message"],
                    intent=ex["intent"],
                ).with_inputs("user_message")
            )

    if len(all_examples) < 5:
        return {
            "success": False,
            "error": f"학습 데이터 부족 ({len(all_examples)}개, 최소 5개 필요)",
        }

    trainset, valset = _split_train_val(all_examples)

    # 메트릭 정의
    def intent_metric(
        gold: dspy.Example,
        pred: dspy.Prediction,
        trace: Any = None,
    ) -> float:
        pred_intent = (pred.intent or "").strip().lower()
        gold_intent = gold.intent.strip().lower()
        return 1.0 if pred_intent == gold_intent else 0.0

    # 피드백 함수 (GEPA reflective mutation용)
    def intent_feedback(**kwargs: Any) -> dict[str, Any]:
        gold = kwargs.get("module_inputs")
        pred = kwargs.get("module_outputs")
        pred_intent = ((pred.intent if pred else "") or "").strip().lower()
        gold_intent = (gold.intent if gold else "").strip().lower()
        if pred_intent == gold_intent:
            return {"score": 1.0, "feedback": "Correct."}
        msg = gold.user_message if gold else "?"
        return {
            "score": 0.0,
            "feedback": f"Expected '{gold_intent}' for '{msg}', got '{pred_intent}'.",
        }

    # LM 설정
    task_lm = dspy.LM(model=model, temperature=0.0, max_tokens=1000)
    max_calls = _AUTO_PRESETS.get(auto, 50)

    # GEPA 최적화
    with dspy.context(lm=task_lm):
        classifier = IntentClassifier()

        # seed candidate: 현재 instruction
        seed = {}
        for name, pred in classifier.named_predictors():
            seed[name] = pred.signature.instructions

        adapter = adapter_cls(
            student_module=classifier,
            metric_fn=intent_metric,
            feedback_map={"predict": intent_feedback},
        )

        run_dir = str(data_dir / "logs" / "intent_optimization")

        result = gepa.optimize(
            seed_candidate=seed,
            trainset=trainset,
            valset=valset,
            adapter=adapter,
            reflection_lm=model,
            max_metric_calls=max_calls,
            run_dir=run_dir,
            display_progress_bar=True,
            seed=42,
        )

    # 최적화된 프로그램 저장
    best_candidate = result.best_candidate
    optimized = adapter.build_program(best_candidate)
    best_score = max(result.val_aggregate_scores) if result.val_aggregate_scores else 0.0

    from jedisos.dspy_modules import model_safe_name

    safe = model_safe_name(model)
    output_path = data_dir / f"intent_classifier_{safe}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    optimized.save(str(output_path))

    logger.info(
        "intent_classifier_optimized",
        examples=len(all_examples),
        train=len(trainset),
        val=len(valset),
        best_score=best_score,
        output=str(output_path),
    )

    return {
        "success": True,
        "examples": len(all_examples),
        "best_score": best_score,
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
    import gepa

    from jedisos.dspy_modules.facts import FactExtractor

    adapter_cls = _patched_dspy_adapter()

    training_path = data_dir / "training" / "fact_examples.yaml"
    examples = _load_training_data(training_path)
    if not examples:
        return {"success": False, "error": "학습 데이터 없음", "path": str(training_path)}

    # DSPy Example 변환
    all_examples = []
    for ex in examples:
        if "conversation" in ex and "facts" in ex:
            all_examples.append(
                dspy.Example(
                    conversation=ex["conversation"],
                    facts=ex["facts"],
                ).with_inputs("conversation")
            )

    if len(all_examples) < 5:
        return {
            "success": False,
            "error": f"학습 데이터 부족 ({len(all_examples)}개, 최소 5개 필요)",
        }

    trainset, valset = _split_train_val(all_examples)

    # F1 메트릭
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

    # 피드백 함수 (GEPA reflective mutation용)
    def fact_feedback(**kwargs: Any) -> dict[str, Any]:
        gold = kwargs.get("module_inputs")
        pred = kwargs.get("module_outputs")
        gold_facts = gold.facts if gold and isinstance(gold.facts, list) else []
        pred_facts = pred.facts if pred and isinstance(pred.facts, list) else []
        score = fact_metric(gold, pred) if gold and pred else 0.0
        if score >= 1.0:
            return {"score": 1.0, "feedback": "Perfect extraction."}
        missing = [f for f in gold_facts if not any(f in p or p in f for p in pred_facts)]
        extra = [f for f in pred_facts if not any(f in g or g in f for g in gold_facts)]
        parts = [f"F1={score:.2f}."]
        if missing:
            parts.append(f"Missing: {missing}")
        if extra:
            parts.append(f"Extra: {extra}")
        return {"score": score, "feedback": " ".join(parts)}

    # LM 설정
    task_lm = dspy.LM(model=model, temperature=0.0, max_tokens=500)
    max_calls = _AUTO_PRESETS.get(auto, 150)

    # GEPA 최적화
    with dspy.context(lm=task_lm):
        extractor = FactExtractor()

        seed = {}
        for name, pred in extractor.named_predictors():
            seed[name] = pred.signature.instructions

        adapter = adapter_cls(
            student_module=extractor,
            metric_fn=fact_metric,
            feedback_map={"predict": fact_feedback},
        )

        run_dir = str(data_dir / "logs" / "fact_optimization")

        result = gepa.optimize(
            seed_candidate=seed,
            trainset=trainset,
            valset=valset,
            adapter=adapter,
            reflection_lm=model,
            max_metric_calls=max_calls,
            run_dir=run_dir,
            display_progress_bar=True,
            seed=42,
        )

    # 최적화된 프로그램 저장
    best_candidate = result.best_candidate
    optimized = adapter.build_program(best_candidate)
    best_score = max(result.val_aggregate_scores) if result.val_aggregate_scores else 0.0

    from jedisos.dspy_modules import model_safe_name

    safe = model_safe_name(model)
    output_path = data_dir / f"fact_extractor_{safe}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    optimized.save(str(output_path))

    logger.info(
        "fact_extractor_optimized",
        examples=len(all_examples),
        train=len(trainset),
        val=len(valset),
        best_score=best_score,
        output=str(output_path),
    )

    return {
        "success": True,
        "examples": len(all_examples),
        "best_score": best_score,
        "output_path": str(output_path),
        "auto": auto,
    }
