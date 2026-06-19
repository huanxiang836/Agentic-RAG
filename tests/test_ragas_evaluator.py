"""ragas 评测模块测试。"""

# pylint: disable=duplicate-code

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import pytest

from evals.ragas_evaluator import (
    RagEvaluationCase,
    RagasEvaluator,
    loadEvaluationCases,
    selectEvaluationCases,
)
from agents.rag.rag_chat_service import RagAnswer


@dataclass(frozen=True)
class FakeEvaluationResult:
    """模拟 ragas 返回对象，避免测试依赖真实模型。"""

    scores: list[dict[str, Any]]


class FakeAnswerProvider:  # pylint: disable=too-few-public-methods
    """提供稳定回答和上下文，便于验证评测流程。"""

    def answerWithContexts(self, query: str) -> RagAnswer:
        """返回固定格式的问答结果。"""

        return RagAnswer(
            answer=f"回答: {query}",
            retrievedContexts=[f"文档 1\n来源: test.md\n内容: {query} 的检索结果"],
        )


def _fakeConfig() -> object:
    """返回评测测试所需的最小配置对象。"""

    return type(
        "Config",
        (),
        {
            "ragasEvaluationTimeoutSeconds": 600.0,
            "chatModel": "qwen3.5-plus-2026-04-20",
            "judgeModel": "THUDM/GLM-Z1-9B-0414",
            "judgeModelTimeoutSeconds": 600.0,
            "embeddingModel": "BAAI/bge-m3",
            "siliconflowApiKey": "test-key",
            "siliconflowBaseUrl": "https://api.siliconflow.cn/v1",
        },
    )()


def testLoadEvaluationCasesShouldReadUtf8JsonFile(
    tmpPath: Path,  # pylint: disable=redefined-outer-name
) -> None:
    """应从 UTF-8 JSON 文件中正确加载评测样本。"""

    filePath = tmpPath / "cases.json"
    filePath.write_text(
        json.dumps(
            [{"userInput": "什么是 Agentic RAG？", "reference": "Agentic RAG 是带推理与工具能力的 RAG。"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    cases = loadEvaluationCases(filePath)

    assert cases == [
        RagEvaluationCase(
            userInput="什么是 Agentic RAG？",
            reference="Agentic RAG 是带推理与工具能力的 RAG。",
        )
    ]


def testEvaluateCasesShouldBuildReportFromRagasResult(monkeypatch: Any) -> None:
    """应把 ragas 结果整理为稳定的评测报告结构。"""

    capturedDataset: dict[str, Any] = {}
    capturedRunConfig: dict[str, Any] = {}

    def fakeEvaluate(**kwargs: Any) -> FakeEvaluationResult:
        capturedDataset["dataset"] = kwargs["dataset"]
        capturedRunConfig["run_config"] = kwargs["run_config"]
        return FakeEvaluationResult(
            scores=[
                {
                    "context_recall": 0.7,
                    "faithfulness": 0.9,
                }
            ]
        )

    monkeypatch.setattr("evals.ragas_evaluator.evaluate", fakeEvaluate)

    def fakeCreateRagasLlm(_config: object) -> object:
        return object()

    def fakeCreateEmbeddings(_config: object) -> object:
        return object()

    monkeypatch.setattr("evals.ragas_evaluator.createJudgeModel", fakeCreateRagasLlm)
    monkeypatch.setattr(
        "evals.ragas_evaluator.createEmbeddings",
        fakeCreateEmbeddings,
    )
    monkeypatch.setattr(
        "evals.ragas_evaluator.AppConfig.fromEnv",
        _fakeConfig,
    )
    evaluator = RagasEvaluator(FakeAnswerProvider())

    report = evaluator.evaluateCases(
        [RagEvaluationCase(userInput="LangGraph 是什么？", reference="LangGraph 用于构建有状态 Agent 流程。")]
    )

    assert list(capturedDataset["dataset"].to_list()) == [
        {
            "user_input": "LangGraph 是什么？",
            "response": "回答: LangGraph 是什么？",
            "retrieved_contexts": ["文档 1\n来源: test.md\n内容: LangGraph 是什么？ 的检索结果"],
            "reference": "LangGraph 用于构建有状态 Agent 流程。",
        }
    ]
    assert capturedRunConfig["run_config"].timeout == 600
    assert report.metrics == {"context_recall": 0.7, "faithfulness": 0.9}
    assert report.rows[0].metricScores["faithfulness"] == 0.9


def testSmokeEvaluationShouldUseReducedMetrics(monkeypatch: Any) -> None:
    """smoke 评测应只使用低成本的两个指标。"""

    capturedMetrics: dict[str, Any] = {}

    def fakeEvaluate(**kwargs: Any) -> FakeEvaluationResult:
        capturedMetrics["metrics"] = kwargs["metrics"]
        return FakeEvaluationResult(
            scores=[
                {
                    "context_recall": 0.6,
                    "faithfulness": 0.7,
                }
            ]
        )

    monkeypatch.setattr("evals.ragas_evaluator.evaluate", fakeEvaluate)
    monkeypatch.setattr(
        "evals.ragas_evaluator.createJudgeModel",
        lambda _config: object(),
    )
    monkeypatch.setattr(
        "evals.ragas_evaluator.createEmbeddings",
        lambda _config: object(),
    )
    monkeypatch.setattr(
        "evals.ragas_evaluator.AppConfig.fromEnv",
        _fakeConfig,
    )

    report = RagasEvaluator(FakeAnswerProvider()).evaluateCases(
        [
            RagEvaluationCase(
                userInput="LangGraph 是什么？",
                reference="LangGraph 用于构建有状态 Agent 流程。",
            )
        ],
    )

    assert [metric.__class__.__name__ for metric in capturedMetrics["metrics"]] == [
        "LLMContextRecall",
        "Faithfulness",
    ]
    assert report.metrics == {
        "context_recall": 0.6,
        "faithfulness": 0.7,
    }


def testSelectEvaluationCasesShouldRespectSmokeLimit() -> None:
    """smoke 评测应固定截取 12 条样本。"""

    cases = [
        RagEvaluationCase(userInput=f"问题 {index}", reference=f"参考 {index}")
        for index in range(1, 40)
    ]

    smokeCases = selectEvaluationCases(cases)

    assert len(smokeCases) == 12
    assert smokeCases[0].userInput == "问题 1"


@pytest.fixture(name="tmpPath")
def fixtureTmpPath(
    tmp_path: Path,  # pylint: disable=invalid-name
) -> Path:
    """适配 pytest 内置临时目录夹具与项目命名约束。"""

    return tmp_path
