"""基于 ragas 的 RAG 评测模块。"""

from __future__ import annotations

from dataclasses import dataclass
import csv
import argparse
import json
import logging
from math import isnan
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol, cast

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
EVALUATION_PROFILE_LIMITS: dict[str, int] = {
    "smoke": 12,
    "full": 25,
}
EvaluationProfile = Literal["smoke", "full"]


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

    def evaluateCases(
        self,
        cases: list[RagEvaluationCase],
        profile: EvaluationProfile = "full",
    ) -> RagEvaluationReport:
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
                metrics=_buildMetrics(profile),
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
    """从 JSON 或 CSV 文件加载评测样本。"""

    path = Path(filePath)
    rawItems = _loadRawEvaluationItems(path)
    if not isinstance(rawItems, list):
        raise ValueError("评测文件内容必须是数组。")
    return [
        _parseEvaluationCase(index, rawItem)
        for index, rawItem in enumerate(rawItems, start=1)
    ]


def selectEvaluationCases(
    cases: list[RagEvaluationCase],
    profile: EvaluationProfile,
) -> list[RagEvaluationCase]:
    """按固定评测档位截取样本，降低日常评测成本。"""

    limit = EVALUATION_PROFILE_LIMITS[profile]
    return cases[:limit]


def _loadRawEvaluationItems(path: Path) -> list[object]:
    """按文件后缀读取评测样本，便于直接使用静态 CSV 数据集。"""

    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as file:
            return list(csv.DictReader(file))
    if suffix == ".json":
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    raise ValueError(f"不支持的评测文件格式: {suffix}")


def _parseEvaluationCase(index: int, rawItem: object) -> RagEvaluationCase:
    """把原始节点解析为评测样本。"""

    if not isinstance(rawItem, dict):
        raise ValueError(f"第 {index} 条评测样本必须是对象。")
    userInput = _requireStringField(
        rawItem,
        "userInput" if "userInput" in rawItem else "user_input",
        index,
    )
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


def _buildArgumentParser() -> argparse.ArgumentParser:
    """构造命令行参数解析器，方便直接跑 smoke 或 full 评测。"""

    parser = argparse.ArgumentParser(description="运行 ragas 离线评测。")
    parser.add_argument(
        "--dataset",
        default="data/evaluate/ragas_eval_dataset.csv",
        help="评测数据集路径，默认使用静态 CSV。",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(EVALUATION_PROFILE_LIMITS.keys()),
        default="full",
        help="评测档位，smoke 为 12 条，full 为 25 条。",
    )
    return parser


def main() -> None:
    """提供最小可执行入口，便于直接运行评测。"""

    parser = _buildArgumentParser()
    args = parser.parse_args()
    cases = loadEvaluationCases(args.dataset)
    selectedCases = selectEvaluationCases(cases, cast(EvaluationProfile, args.profile))
    report = RagasEvaluator(_createDefaultAnswerProvider()).evaluateCases(selectedCases)
    _writeEvaluationReport(report, cast(EvaluationProfile, args.profile))
    print(json.dumps(report.metrics, ensure_ascii=False, indent=2))


def _createDefaultAnswerProvider() -> RagAnswerProvider:
    """延迟初始化默认问答服务，避免导入阶段立即连接外部依赖。"""

    from agents.rag.rag_chat_service import getRagChatService

    return getRagChatService()


def _buildMetrics(profile: EvaluationProfile) -> list[object]:
    """按评测档位选择指标集合，降低 smoke 评测成本。"""

    if profile == "smoke":
        return [LLMContextRecall(), Faithfulness()]
    return [
        LLMContextPrecisionWithoutReference(),
        LLMContextRecall(),
        Faithfulness(),
        ResponseRelevancy(strictness=1),
        FactualCorrectness(),
    ]


def _writeEvaluationReport(report: RagEvaluationReport, profile: EvaluationProfile) -> None:
    """把评测结果落盘，便于后续对比与回归查看。"""

    reportDir = Path("reports")
    reportDir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    metricTag = "cr-faithfulness" if profile == "smoke" else "full"
    jsonPath = reportDir / f"ragas_report_{profile}_{metricTag}_{stamp}.json"
    mdPath = reportDir / f"ragas_report_{profile}_{metricTag}_{stamp}.md"
    jsonPath.write_text(
        json.dumps(
            {
                "profile": profile,
                "sample_count": len(report.rows),
                "metrics": report.metrics,
                "rows": [
                    {
                        "userInput": row.userInput,
                        "reference": row.reference,
                        "response": row.response,
                        "retrievedContexts": row.retrievedContexts,
                        "metricScores": row.metricScores,
                    }
                    for row in report.rows
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    lines = [
        f"# ragas 评估报告（{profile}）",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 样本数量：{len(report.rows)}",
        "",
        "## 指标汇总",
        "",
    ]
    for key, value in report.metrics.items():
        lines.append(f"- {key}: {value if value is not None else 'N/A'}")
    lines.extend(["", "## 样本明细", ""])
    for index, row in enumerate(report.rows, start=1):
        lines.extend(
            [
                f"### 样本 {index}",
                "",
                f"- 问题：{row.userInput}",
                f"- 参考答案：{row.reference}",
                f"- 模型回答：{row.response}",
                f"- 检索上下文数量：{len(row.retrievedContexts)}",
                f"- 指标：{json.dumps(row.metricScores, ensure_ascii=False)}",
                "",
            ]
        )
    mdPath.write_text("\n".join(lines), encoding="utf-8")
    LOGGER.info("评测报告已落盘：%s, %s", jsonPath, mdPath)


if __name__ == "__main__":
    main()
