"""Langfuse ragas 实验模块测试。"""

# pylint: disable=invalid-name,too-few-public-methods,protected-access

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
import csv

import pytest

from agents.rag.rag_chat_service import RagAnswer
from evals import langfuse_experiment
from evals.langfuse_experiment import (
    loadRagasCsvCases,
    runLangfuseRagasExperiment,
    syncRagasCsvToLangfuseDataset,
)


class FakeLangfuseClient:  # pylint: disable=invalid-name
    """记录 Langfuse Dataset 同步调用。"""

    def __init__(self, dataset: object | None = None) -> None:
        self.createdDatasets: list[dict[str, object]] = []
        self.createdItems: list[dict[str, object]] = []
        self._dataset = dataset

    def get_dataset(self, _datasetName: str) -> object:
        """返回预设 Dataset，或模拟 Dataset 不存在。"""

        if self._dataset is None:
            raise RuntimeError("dataset not found")
        return self._dataset

    def create_dataset(self, **kwargs: object) -> object:
        """记录 Dataset 创建。"""

        self.createdDatasets.append(cast(dict[str, object], kwargs))
        return object()

    def create_dataset_item(self, **kwargs: object) -> object:
        """记录 Dataset Item 创建。"""

        self.createdItems.append(cast(dict[str, object], kwargs))
        return object()

class FakeDataset:  # pylint: disable=too-few-public-methods,invalid-name
    """记录 experiment 调用。"""

    def __init__(self) -> None:
        self.experimentCalls: list[dict[str, object]] = []

    def run_experiment(self, **kwargs: object) -> object:
        """记录 experiment 参数。"""

        self.experimentCalls.append(kwargs)
        return {"dataset_run_id": "run-1"}


class FakeRagChatService:  # pylint: disable=too-few-public-methods
    """返回稳定 RAG 回答。"""

    def answerWithContexts(
        self,
        query: str,
        traceMetadata: dict[str, object] | None = None,  # pylint: disable=unused-argument
    ) -> RagAnswer:
        """模拟带上下文的问答。"""

        return RagAnswer(
            answer=f"回答: {query}",
            retrievedContexts=[f"上下文: {query}"],
        )


@dataclass(frozen=True)
class FakeEvaluation:
    """模拟 Langfuse Evaluation 对象。"""

    name: str
    value: float | None


@dataclass(frozen=True)
class FakeItemResult:
    """模拟 Langfuse experiment item result。"""

    evaluations: list[FakeEvaluation]


def testLoadRagasCsvCasesShouldReadExpectedColumns(
    tmpPath: Path,  # pylint: disable=redefined-outer-name
) -> None:
    """应读取 ragas CSV 的固定列。"""

    csvPath = _writeCsv(tmpPath)

    cases = loadRagasCsvCases(csvPath)

    assert cases[0].caseId == "case-001"
    assert cases[0].userInput == "LangGraph 是什么？"
    assert cases[0].reference == "LangGraph 用于构建有状态 Agent。"


def testSyncRagasCsvToLangfuseDatasetShouldMapFields(
    tmpPath: Path,  # pylint: disable=redefined-outer-name
    monkeypatch: Any,
) -> None:
    """同步 Dataset 时应正确映射 input、expected_output 和 metadata。"""

    fakeClient = FakeLangfuseClient()
    csvPath = _writeCsv(tmpPath)
    _setLangfuseEnv(monkeypatch)
    monkeypatch.setattr(langfuse_experiment, "_getLangfuseClient", lambda: fakeClient)
    monkeypatch.setattr(langfuse_experiment, "flushLangfuse", lambda: None)

    count = syncRagasCsvToLangfuseDataset(csvPath, datasetName="test-dataset")

    assert count == 1
    assert fakeClient.createdDatasets[0]["name"] == "test-dataset"
    assert fakeClient.createdItems[0]["id"] == "case-001"
    assert fakeClient.createdItems[0]["input"] == {"user_input": "LangGraph 是什么？"}
    assert fakeClient.createdItems[0]["expected_output"] == {
        "reference": "LangGraph 用于构建有状态 Agent。"
    }
    assert fakeClient.createdItems[0]["metadata"] == {
        "source": "langgraph.md",
        "sectionTitle": "概念",
    }
    assert fakeClient.createdItems[0]["dataset_name"] == "test-dataset"


def testExperimentTaskShouldReturnRagasOutput() -> None:
    """experiment task 应把 RAG 输出转换为评测字段。"""

    task = langfuse_experiment._buildExperimentTask(FakeRagChatService())  # pylint: disable=protected-access

    output = task(item={"id": "case-001", "input": {"user_input": "LangGraph 是什么？"}})

    assert output == {
        "response": "回答: LangGraph 是什么？",
        "retrieved_contexts": ["上下文: LangGraph 是什么？"],
    }


def testRagasRunEvaluatorShouldIgnoreMissingScores() -> None:
    """run 级平均分应忽略缺失分数。"""

    result = langfuse_experiment._evaluateRagasRun(  # pylint: disable=protected-access
        item_results=[
            FakeItemResult([FakeEvaluation("faithfulness", 0.8)]),
            FakeItemResult([FakeEvaluation("faithfulness", 1.0)]),
            FakeItemResult([FakeEvaluation("context_recall", None)]),
        ]
    )

    assert len(result) == 1
    assert result[0].name == "avg_faithfulness"
    assert result[0].value == 0.9


def testRunLangfuseRagasExperimentShouldSyncDatasetBeforeRun(monkeypatch: Any) -> None:
    """执行 experiment 前应先同步本地 CSV 到 Langfuse Dataset。"""

    fakeDataset = FakeDataset()
    fakeClient = FakeLangfuseClient(dataset=fakeDataset)
    syncCalls: list[tuple[object, object | None]] = []
    _setLangfuseEnv(monkeypatch)

    def fakeGetLangfuseClient() -> FakeLangfuseClient:
        """返回测试用 Langfuse 客户端。"""

        return fakeClient

    def fakeFlushLangfuse() -> None:
        """跳过真实刷新。"""

        return None

    def fakeSyncRagasCsvToLangfuseDataset(
        csvPath: object,
        datasetName: object | None = None,
    ) -> int:
        """记录同步调用。"""

        syncCalls.append((csvPath, datasetName))
        return 1

    monkeypatch.setattr(
        langfuse_experiment,
        "_getLangfuseClient",
        fakeGetLangfuseClient,
    )
    monkeypatch.setattr(
        langfuse_experiment,
        "flushLangfuse",
        fakeFlushLangfuse,
    )
    monkeypatch.setattr(
        langfuse_experiment,
        "syncRagasCsvToLangfuseDataset",
        fakeSyncRagasCsvToLangfuseDataset,
    )
    monkeypatch.setattr(
        langfuse_experiment,
        "getRagChatService",
        fakeGetRagChatService,
    )

    result = runLangfuseRagasExperiment(datasetName="test-dataset", runName="run-1")

    assert syncCalls[0][1] == "test-dataset"
    assert isinstance(result, dict)
    assert fakeDataset.experimentCalls[0]["name"] == "ragas-rag-evaluation"


def fakeGetRagChatService() -> FakeRagChatService:
    """返回测试用 RAG 服务。"""

    return FakeRagChatService()


def _writeCsv(tmpPath: Path) -> Path:
    """写入最小 ragas CSV 样本。"""

    csvPath = tmpPath / "ragas.csv"
    with csvPath.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "case_id",
                "source",
                "section_title",
                "user_input",
                "reference",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "case_id": "case-001",
                "source": "langgraph.md",
                "section_title": "概念",
                "user_input": "LangGraph 是什么？",
                "reference": "LangGraph 用于构建有状态 Agent。",
            }
        )
    return csvPath


def _setLangfuseEnv(monkeypatch: Any) -> None:
    """设置测试用 Langfuse 环境变量。"""

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "http://127.0.0.1:3000")


@pytest.fixture(name="tmpPath")
def fixtureTmpPath(
    tmp_path: Path,  # pylint: disable=invalid-name
) -> Path:
    """适配 pytest 内置临时目录夹具与项目命名约束。"""

    return tmp_path
