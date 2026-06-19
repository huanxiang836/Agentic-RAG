"""基于 ragas 的 RAG 评测模块。"""

from __future__ import annotations

from dataclasses import dataclass
import csv
import argparse
import json
import logging
from time import perf_counter
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, cast

from ragas import EvaluationDataset, evaluate
from ragas.dataset_schema import EvaluationResult
from ragas.run_config import RunConfig
from ragas.metrics import (
    Faithfulness,
    LLMContextRecall,
)

from agents.rag.model_factory import createJudgeModel
from agents.rag.rag_chat_service import RagAnswer
from evals.ragas_shared import normalizeMetricValue, safeMean
from knowledge.ingest.config import AppConfig
from knowledge.ingest.vector_store import createEmbeddings


LOGGER = logging.getLogger(__name__)
SMOKE_EVALUATION_SAMPLE_LIMIT = 12


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


@dataclass(frozen=True)
class SingleCaseEvaluationContext:
    """执行单条评测时所需的共享依赖。"""

    metrics: list[object]
    judgeModel: object
    embeddings: object
    timeoutSeconds: int


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
    ) -> RagEvaluationReport:
        """执行评测并返回聚合后的结果。"""

        if not cases:
            raise ValueError("评测样本不能为空。")
        config = AppConfig.fromEnv()
        judgeModel = createJudgeModel(config)
        embeddings = createEmbeddings(config)
        metrics = _buildMetrics()
        records: list[dict[str, Any]] = []
        scoreRows: list[dict[str, Any]] = []
        totalCases = len(cases)
        for index, case in enumerate(cases, start=1):
            print(f"开始评测样本 {index}/{totalCases}：{case.userInput}", flush=True)
            startedAt = perf_counter()
            record = self._buildRecord(case)
            records.append(record)
            scoreRow = self._evaluateSingleCase(
                record=record,
                context=SingleCaseEvaluationContext(
                    metrics=metrics,
                    judgeModel=judgeModel,
                    embeddings=embeddings,
                    timeoutSeconds=int(config.ragasEvaluationTimeoutSeconds),
                ),
            )
            scoreRows.append(scoreRow)
            elapsedSeconds = perf_counter() - startedAt
            print(
                "结束评测样本 "
                f"{index}/{totalCases}，耗时={elapsedSeconds:.2f}s，指标="
                f"{json.dumps(scoreRow, ensure_ascii=False)}",
                flush=True,
            )
        LOGGER.info(
            "ragas 评测完成，样本数=%s，指标=%s",
            len(cases),
            list(_collectMetricNames(scoreRows)),
        )
        return _buildEvaluationReport(scores=scoreRows, records=records)

    def _buildRecord(self, case: RagEvaluationCase) -> dict[str, Any]:
        """把单条样本转成 ragas 所需的记录结构。"""

        answer = self._answerProvider.answerWithContexts(case.userInput)
        return {
            "user_input": case.userInput,
            "response": answer.answer,
            "retrieved_contexts": answer.retrievedContexts,
            "reference": case.reference,
        }

    def _evaluateSingleCase(
        self,
        record: dict[str, Any],
        context: SingleCaseEvaluationContext,
    ) -> dict[str, Any]:
        """对单条记录执行 ragas 评测。"""

        singleResult = cast(
            EvaluationResult,
            evaluate(
                dataset=EvaluationDataset.from_list([record]),
                metrics=context.metrics,
                llm=context.judgeModel,
                embeddings=context.embeddings,
                run_config=RunConfig(timeout=context.timeoutSeconds),
                raise_exceptions=False,
                show_progress=False,
            ),
        )
        return singleResult.scores[0] if singleResult.scores else {}


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
) -> list[RagEvaluationCase]:
    """按固定 smoke 档位截取样本，降低日常评测成本。"""

    return cases[:SMOKE_EVALUATION_SAMPLE_LIMIT]


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
    scores: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> RagEvaluationReport:
    """把 ragas 结果整理为稳定的项目内输出结构。"""

    metricNames = sorted(_collectMetricNames(scores))
    rows = [
        RagEvaluationRow(
            userInput=str(record["user_input"]),
            reference=str(record["reference"]),
            response=str(record["response"]),
            retrievedContexts=list(record["retrieved_contexts"]),
            metricScores={
                metricName: normalizeMetricValue(score.get(metricName))
                for metricName in metricNames
            },
        )
        for record, score in zip(records, scores, strict=True)
    ]
    metrics = {
        metricName: safeMean(score.get(metricName) for score in scores)
        for metricName in metricNames
    }
    return RagEvaluationReport(metrics=metrics, rows=rows)


def _collectMetricNames(scores: list[dict[str, Any]]) -> set[str]:
    """从 ragas 返回值中提取实际指标列名。"""

    metricNames: set[str] = set()
    for score in scores:
        metricNames.update(score.keys())
    return metricNames
def _buildArgumentParser() -> argparse.ArgumentParser:
    """构造命令行参数解析器，方便直接跑 smoke 评测。"""

    parser = argparse.ArgumentParser(description="运行 ragas 离线评测。")
    parser.add_argument(
        "--dataset",
        default="data/evaluate/ragas_eval_dataset.csv",
        help="评测数据集路径，默认使用静态 CSV。",
    )
    return parser


def main() -> None:
    """提供最小可执行入口，便于直接运行评测。"""

    parser = _buildArgumentParser()
    args = parser.parse_args()
    cases = loadEvaluationCases(args.dataset)
    selectedCases = selectEvaluationCases(cases)
    print(
        f"开始 smoke 评测，样本数={len(selectedCases)}，指标=context_recall, faithfulness",
        flush=True,
    )
    try:
        report = RagasEvaluator(_createDefaultAnswerProvider()).evaluateCases(selectedCases)
        jsonPath, mdPath = _writeEvaluationReport(report)
        print(json.dumps(report.metrics, ensure_ascii=False, indent=2), flush=True)
        print(f"评测成功，报告已生成: {jsonPath}", flush=True)
        print(f"评测成功，Markdown 报告已生成: {mdPath}", flush=True)
    except Exception as error:  # pylint: disable=broad-except
        LOGGER.exception("评测失败: %s", error)
        print(f"评测失败: {error}", flush=True)
        raise


def _createDefaultAnswerProvider() -> RagAnswerProvider:
    """延迟初始化默认问答服务，避免导入阶段立即连接外部依赖。"""

    from agents.rag.rag_chat_service import getRagChatService  # pylint: disable=import-outside-toplevel

    return getRagChatService()


def _buildMetrics() -> list[object]:
    """smoke 档位只计算上下文召回和忠实度，降低评测成本。"""

    return [LLMContextRecall(), Faithfulness()]


def _writeEvaluationReport(report: RagEvaluationReport) -> tuple[Path, Path]:
    """把评测结果落盘，便于后续对比与回归查看。"""

    reportDir = Path("reports")
    reportDir.mkdir(parents=True, exist_ok=True)
    profile = "smoke"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    jsonPath = reportDir / f"ragas_report_smoke_cr-faithfulness_{stamp}.json"
    mdPath = reportDir / f"ragas_report_smoke_cr-faithfulness_{stamp}.md"
    jsonPath.write_text(
        json.dumps(
            {
                "profile": "smoke",
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
    return jsonPath, mdPath


if __name__ == "__main__":
    main()
