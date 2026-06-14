"""把 ragas 评测样本同步到 Langfuse 并运行实验。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import csv
import logging
from math import isnan
import os
from pathlib import Path
from typing import Any, cast

from dotenv import load_dotenv
from langfuse import Evaluation
from ragas import EvaluationDataset, evaluate
from ragas.dataset_schema import EvaluationResult
from ragas.metrics import (
    Faithfulness,
    FactualCorrectness,
    LLMContextPrecisionWithoutReference,
    LLMContextRecall,
    ResponseRelevancy,
)

from agents.rag.rag_chat_service import getRagChatService, createChatModel
from common.langfuse_observability import flushLangfuse, requireLangfuseConfigured
from knowledge.ingest.config import AppConfig
from knowledge.ingest.vector_store import createEmbeddings


LOGGER = logging.getLogger(__name__)
DEFAULT_LANGFUSE_DATASET_NAME = "ragas-eval-dataset"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class LangfuseRagasCase:
    """定义同步到 Langfuse Dataset 的 ragas 样本。"""

    caseId: str
    source: str
    sectionTitle: str
    userInput: str
    reference: str


def syncRagasCsvToLangfuseDataset(
    csvPath: str | Path,
    datasetName: str | None = None,
) -> int:
    """把 ragas CSV 样本同步到自建 Langfuse Dataset。"""

    _loadProjectEnv()
    requireLangfuseConfigured()
    cases = loadRagasCsvCases(csvPath)
    langfuse = _getLangfuseClient()
    resolvedDatasetName = _resolveDatasetName(datasetName)
    _ensureDatasetExists(langfuse, resolvedDatasetName)
    for case in cases:
        langfuse.create_dataset_item(
            id=case.caseId,
            dataset_name=resolvedDatasetName,
            input={"user_input": case.userInput},
            expected_output={"reference": case.reference},
            metadata={
                "source": case.source,
                "sectionTitle": case.sectionTitle,
            },
        )
    flushLangfuse()
    LOGGER.info("Langfuse Dataset 同步完成，dataset=%s，样本数=%s。", resolvedDatasetName, len(cases))
    return len(cases)


def runLangfuseRagasExperiment(
    datasetName: str | None = None,
    runName: str | None = None,
) -> object:
    """基于自建 Langfuse Dataset 运行 ragas 实验。"""

    _loadProjectEnv()
    requireLangfuseConfigured()
    langfuse = _getLangfuseClient()
    resolvedDatasetName = _resolveDatasetName(datasetName)
    dataset = langfuse.get_dataset(resolvedDatasetName)
    result = dataset.run_experiment(
        name="ragas-rag-evaluation",
        run_name=runName or f"ragas-rag-evaluation-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        description="基于 ragas 指标评估 Agentic RAG 问答效果。",
        task=_buildExperimentTask(getRagChatService()),
        evaluators=[_evaluateRagasItem],
        run_evaluators=[_evaluateRagasRun],
        max_concurrency=1,
        metadata={
            "dataset": resolvedDatasetName,
            "environment": os.getenv("LANGFUSE_ENV", "dev").strip() or "dev",
        },
    )
    flushLangfuse()
    return result


def loadRagasCsvCases(csvPath: str | Path) -> list[LangfuseRagasCase]:
    """读取 ragas CSV 并转换为 Langfuse Dataset 样本。"""

    path = Path(csvPath)
    with path.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    cases: list[LangfuseRagasCase] = []
    for rowIndex, row in enumerate(rows, start=1):
        caseId = _requireCsvValue(row, "case_id", rowIndex)
        cases.append(
            LangfuseRagasCase(
                caseId=caseId,
                source=_requireCsvValue(row, "source", rowIndex),
                sectionTitle=_requireCsvValue(row, "section_title", rowIndex),
                userInput=_requireCsvValue(row, "user_input", rowIndex),
                reference=_requireCsvValue(row, "reference", rowIndex),
            )
        )
    return cases


def _buildExperimentTask(ragChatService: Any) -> Any:
    """构造 Langfuse experiment task，复用当前 RAG 问答服务。"""

    def task(*, item: Any, **_kwargs: Any) -> dict[str, object]:
        inputData = _getItemField(item, "input")
        userInput = _requireMappingString(inputData, "user_input")
        answer = ragChatService.answerWithContexts(
            userInput,
            traceMetadata={
                "mode": "langfuse-experiment",
                "datasetItemId": str(getattr(item, "id", "")),
            },
        )
        return {
            "response": answer.answer,
            "retrieved_contexts": answer.retrievedContexts,
        }

    return task


def _evaluateRagasItem(
    *,
    input: object,  # pylint: disable=redefined-builtin
    output: object,
    expected_output: object | None = None,
    **_kwargs: Any,
) -> list[Evaluation]:
    """对单条 Langfuse Dataset item 计算 ragas 指标。"""

    userInput = _requireMappingString(input, "user_input")
    reference = _requireMappingString(expected_output, "reference")
    if not isinstance(output, dict):
        raise TypeError("实验 task 输出必须是 JSON 对象。")
    response = _requireMappingString(output, "response")
    retrievedContexts = output.get("retrieved_contexts")
    if not isinstance(retrievedContexts, list):
        raise TypeError("实验 task 输出缺少 retrieved_contexts 列表。")
    scores = _evaluateRagasRecord(
        {
            "user_input": userInput,
            "response": response,
            "retrieved_contexts": [str(context) for context in retrievedContexts],
            "reference": reference,
        }
    )
    return [
        Evaluation(name=metricName, value=score, data_type="NUMERIC")
        for metricName, score in scores.items()
        if score is not None
    ]


def _evaluateRagasRun(*, item_results: list[Any], **_kwargs: Any) -> list[Evaluation]:
    """计算 experiment run 级别的 ragas 平均分。"""

    groupedScores: dict[str, list[float]] = {}
    for itemResult in item_results:
        for evaluation in getattr(itemResult, "evaluations", []):
            value = getattr(evaluation, "value", None)
            if isinstance(value, int | float):
                groupedScores.setdefault(str(evaluation.name), []).append(float(value))
    return [
        Evaluation(
            name=f"avg_{metricName}",
            value=sum(values) / len(values),
            data_type="NUMERIC",
        )
        for metricName, values in sorted(groupedScores.items())
        if values
    ]


def _evaluateRagasRecord(record: dict[str, object]) -> dict[str, float | None]:
    """复用项目模型配置计算单条 ragas 指标。"""

    config = AppConfig.fromEnv()
    result = cast(
        EvaluationResult,
        evaluate(
            dataset=EvaluationDataset.from_list([record]),
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
    if not result.scores:
        return {}
    return {
        metricName: _normalizeMetricValue(value)
        for metricName, value in result.scores[0].items()
    }


def _ensureDatasetExists(langfuse: Any, datasetName: str) -> None:
    """确保 Langfuse Dataset 存在。"""

    try:
        langfuse.get_dataset(datasetName)
    except Exception:  # pylint: disable=broad-exception-caught
        langfuse.create_dataset(
            name=datasetName,
            description="Agentic RAG 的 ragas 评测数据集。",
            metadata={"source": "data/evaluate/ragas_eval_dataset.csv"},
        )


def _getLangfuseClient() -> Any:
    """在环境变量加载后获取 Langfuse 单例客户端。"""

    from langfuse import get_client  # pylint: disable=import-outside-toplevel

    return get_client()


def _loadProjectEnv() -> None:
    """加载项目根目录 .env，确保短脚本能读取 Langfuse 配置。"""

    load_dotenv(PROJECT_ROOT / ".env")


def _resolveDatasetName(datasetName: str | None) -> str:
    """解析 Langfuse Dataset 名称。"""

    return (
        datasetName
        or os.getenv("LANGFUSE_EVAL_DATASET_NAME", "").strip()
        or DEFAULT_LANGFUSE_DATASET_NAME
    )


def _requireCsvValue(row: dict[str, str | None], fieldName: str, rowIndex: int) -> str:
    """读取 CSV 必填字段。"""

    value = row.get(fieldName)
    if value is None or not value.strip():
        raise ValueError(f"第 {rowIndex} 行缺少字段 {fieldName}。")
    return value.strip()


def _requireMappingString(value: object, fieldName: str) -> str:
    """从映射对象中读取非空字符串字段。"""

    if not isinstance(value, dict):
        raise TypeError("评测输入必须是 JSON 对象。")
    fieldValue = value.get(fieldName)
    if not isinstance(fieldValue, str) or not fieldValue.strip():
        raise ValueError(f"评测输入缺少字段 {fieldName}。")
    return fieldValue.strip()


def _getItemField(item: Any, fieldName: str) -> object:
    """兼容 Langfuse DatasetItem 与本地 dict item。"""

    if isinstance(item, dict):
        return item.get(fieldName)
    return getattr(item, fieldName)


def _normalizeMetricValue(value: object) -> float | None:
    """把 ragas 指标值规范为可写入 Langfuse 的数字。"""

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
