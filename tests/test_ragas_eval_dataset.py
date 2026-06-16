"""静态 ragas 评测集校验。"""

from __future__ import annotations

from pathlib import Path

from evals.ragas_evaluator import loadEvaluationCases


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = PROJECT_ROOT / "data" / "evaluate" / "ragas_eval_dataset.csv"


def testStaticRagasDatasetShouldContainExpectedSampleCount() -> None:
    """静态评测集应固定为 36 条。"""

    cases = loadEvaluationCases(DATASET_PATH)

    assert len(cases) == 36
    assert any("比较" in case.userInput for case in cases)
    assert any("区别" in case.userInput for case in cases)
    assert any("应" in case.reference or "适合" in case.reference for case in cases)


def testStaticRagasDatasetShouldCoverMajorTopics() -> None:
    """静态评测集应覆盖当前项目的关键主题。"""

    cases = loadEvaluationCases(DATASET_PATH)
    topics = {case.userInput for case in cases}

    assert any("A2A" in item for item in topics)
    assert any("Multi-agent" in item for item in topics)
    assert any("Memory" in item or "内存" in item for item in topics)
    assert any("RAG" in item for item in topics)
    assert any("Graph" in item or "子图" in item for item in topics)
