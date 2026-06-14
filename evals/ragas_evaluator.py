"""基于 ragas 的 RAG 评测模块。"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from math import isnan
from pathlib import Path
from typing import Any, Protocol, cast

from ragas import EvaluationDataset, evaluate
from ragas.dataset_schema import EvaluationResult
from ragas.metrics import (
    Faithfulness,
    FactualCorrectness,
    LLMContextPrecisionWithoutReference,
    LLMContextRecall,
    ResponseRelevancy,
)

from knowledge.ingest.config import AppConfig
from knowledge.ingest.vector_store import createEmbeddings
from agents.rag.rag_chat_service import RagAnswer, createChatModel


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RagEvaluationCase:
    """定义单条评测样本，保证评测输入结构固定。"""

    userInput: str
    reference: str


@dataclass(frozen=True)
class RagEvaluationRow:
    """保存单条样本的问答结果、检索上下文与指标分数。"""

    userInput: str
    reference: str
    response: str
    retrievedContexts: list[str]
    metricScores: dict[str, float | None]


@dataclass(frozen=True)
class RagEvaluationReport:
    """汇总 ragas 评测结果，便于上层打印或落盘。"""

    metrics: dict[str, float | None]
    rows: list[RagEvaluationRow]


class RagAnswerProvider(Protocol):  # pylint: disable=too-few-public-methods
    """约束评测阶段依赖的最小问答能力。"""

    def answerWithContexts(self, query: str) -> RagAnswer:
        """返回问题对应的回答与检索上下文。"""


class RagasEvaluator:  # pylint: disable=too-few-public-methods
    """执行基于 ragas 的 RAG 效果评测。"""

    def __init__(self, answerProvider: RagAnswerProvider) -> None:
        self._answerProvider = answerProvider

    def evaluateCases(self, cases: list[RagEvaluationCase]) -> RagEvaluationReport:
        """执行评测并返回聚合后的结果。"""

        if not cases:
            raise ValueError("评测样本不能为空。")
        config = AppConfig.fromEnv()
        records = []
        for case in cases:
            answer = self._answerProvider.answerWithContexts(case.userInput)
            records.append(
                {
                    "user_input": case.userInput,
                    "response": answer.answer,
                    "retrieved_contexts": answer.retrievedContexts,
                    "reference": case.reference,
                }
            )
        dataset = EvaluationDataset.from_list(records)
        result = cast(
            EvaluationResult,
            evaluate(
                dataset=dataset,
                metrics=[
                    LLMContextPrecisionWithoutReference(),
                    LLMContextRecall(),
                    Faithfulness(),
                    ResponseRelevancy(strictness=1),
                    FactualCorrectness(),
                ],
                llm=createChatModel(
                    config=config,
                    temperature=0.0,
                    timeoutSeconds=120,
                    maxRetries=3,
                ),
                embeddings=createEmbeddings(config),
                raise_exceptions=False,
                show_progress=False,
            ),
        )
        LOGGER.info(
            "ragas 评测完成，样本数=%s，指标=%s",
            len(cases),
            list(_collectMetricNames(result)),
        )
        return _buildEvaluationReport(result=result, records=records)


def loadEvaluationCases(filePath: str | Path) -> list[RagEvaluationCase]:
    """从 JSON 文件加载评测样本。"""

    path = Path(filePath)
    with path.open("r", encoding="utf-8") as file:
        rawItems = json.load(file)
    if not isinstance(rawItems, list):
        raise ValueError("评测文件内容必须是 JSON 数组。")
    return [
        _parseEvaluationCase(index, rawItem)
        for index, rawItem in enumerate(rawItems, start=1)
    ]


def _parseEvaluationCase(index: int, rawItem: object) -> RagEvaluationCase:
    """把原始 JSON 节点解析为评测样本。"""

    if not isinstance(rawItem, dict):
        raise ValueError(f"第 {index} 条评测样本必须是 JSON 对象。")
    userInput = _requireStringField(rawItem, "userInput", index)
    reference = _requireStringField(rawItem, "reference", index)
    return RagEvaluationCase(userInput=userInput, reference=reference)


def _requireStringField(rawItem: dict[str, object], fieldName: str, index: int) -> str:
    """读取并校验非空字符串字段，尽早暴露样本问题。"""

    value = rawItem.get(fieldName)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"第 {index} 条评测样本缺少有效字段 {fieldName}。")
    return value.strip()


def _buildEvaluationReport(
    result: EvaluationResult,
    records: list[dict[str, Any]],
) -> RagEvaluationReport:
    """把 ragas 结果整理为稳定的项目内输出结构。"""

    metricNames = sorted(_collectMetricNames(result))
    rows = [
        RagEvaluationRow(
            userInput=str(record["user_input"]),
            reference=str(record["reference"]),
            response=str(record["response"]),
            retrievedContexts=list(record["retrieved_contexts"]),
            metricScores={
                metricName: _normalizeMetricValue(score.get(metricName))
                for metricName in metricNames
            },
        )
        for record, score in zip(records, result.scores, strict=True)
    ]
    metrics = {
        metricName: _safeMean(
            _normalizeMetricValue(score.get(metricName)) for score in result.scores
        )
        for metricName in metricNames
    }
    return RagEvaluationReport(metrics=metrics, rows=rows)


def _collectMetricNames(result: EvaluationResult) -> set[str]:
    """从 ragas 返回值中提取实际指标列名。"""

    metricNames: set[str] = set()
    for score in result.scores:
        metricNames.update(score.keys())
    return metricNames


def _normalizeMetricValue(value: object) -> float | None:
    """把 ragas 返回的指标值规范为可序列化数字。"""

    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        normalizedValue = float(value)
        if isnan(normalizedValue):
            return None
        return normalizedValue
    raise TypeError(f"不支持的指标值类型: {type(value)!r}")


def _safeMean(values: Any) -> float | None:
    """对指标列执行忽略空值的平均，避免单条失败污染整体结果。"""

    normalizedValues = [value for value in values if value is not None]
    if not normalizedValues:
        return None
    return sum(normalizedValues) / len(normalizedValues)
