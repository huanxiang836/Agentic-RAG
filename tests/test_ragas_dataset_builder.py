"""ragas 评测数据集生成测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from evals.dataset_builder import RagasDatasetBuilder


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "md"


def testBuildRowsShouldExtractQuestionAnswerPairsFromMarkdown(tmpPath: Path) -> None:
    """应从 Markdown 标题和正文中提取评测样本。"""

    markdownPath = tmpPath / "sample.md"
    markdownPath.write_text(
        "# ReactAgent 快速开始\n\n"
        "## 前置条件\n\n"
        "### 环境要求\n\n"
        "* JDK 17+\n"
        "* Maven 3.8+\n"
        "* 需要准备模型 API Key。\n\n"
        "### 配置 API Key\n\n"
        "在使用之前，需要配置你的 API Key。推荐通过环境变量设置，"
        "也可以在应用配置文件中设置，但不推荐在生产环境中硬编码。\n",
        encoding="utf-8",
    )

    rows = RagasDatasetBuilder(tmpPath).buildRows(maxDatasetSize=10)

    assert len(rows) == 2
    assert rows[0].source == "sample.md"
    assert rows[0].sectionTitle == "环境要求"
    assert rows[0].userInput == "环境要求需要满足哪些环境要求？"
    assert "JDK 17+" in rows[0].reference
    assert rows[1].userInput == "配置 API Key 应该怎么配置？"


def testWriteCsvShouldCreateReusableRagasColumns(tmpPath: Path) -> None:
    """应写出兼容 ragas 评测使用的 CSV 列。"""

    markdownPath = tmpPath / "sample.md"
    markdownPath.write_text(
        "# 概览\n\n"
        "## 核心功能\n\n"
        "ReactAgent 用于构建具有推理和行动能力的智能代理。"
        "系统还支持多代理编排、上下文工程和人机协同。\n",
        encoding="utf-8",
    )
    outputPath = tmpPath / "dataset.csv"

    rows = RagasDatasetBuilder(tmpPath).writeCsv(outputPath, maxDatasetSize=10)

    assert len(rows) == 1
    csvText = outputPath.read_text(encoding="utf-8")
    assert "case_id,source,section_title,user_input,reference" in csvText
    assert "核心功能包含哪些关键能力？" in csvText


def testBuildRowsShouldPreferProceduralAndTroubleshootingQuestions(tmpPath: Path) -> None:
    """应优先生成步骤类和排查类问题，而不是泛化定义问法。"""

    markdownPath = tmpPath / "sample.md"
    markdownPath.write_text(
        "# 故障处理\n\n"
        "## 验证 Nacos 注册\n\n"
        "1. 打开 Nacos 控制台。\n"
        "2. 查看 A2A 服务注册维度。\n"
        "3. 确认目标 Agent 已注册成功。\n\n"
        "## 远程调用失败\n\n"
        "- 检查目标 Agent 的 REST API 端点是否可访问。\n"
        "- 检查网络连接和防火墙配置。\n"
        "- 查看消息传输日志。\n",
        encoding="utf-8",
    )

    rows = RagasDatasetBuilder(tmpPath).buildRows(maxDatasetSize=10)

    assert [row.userInput for row in rows] == [
        "验证 Nacos 注册应该如何验证是否生效？",
        "远程调用失败应该如何排查处理？",
    ]


def testBuildRowsShouldReadRealProjectMarkdownDocuments() -> None:
    """应能直接从项目 data 目录读取真实 Markdown 文档。"""

    rows = RagasDatasetBuilder(DATA_DIR).buildRows(maxDatasetSize=20)

    assert len(rows) == 20
    assert all(row.source.endswith(".md") for row in rows)
    assert len({row.source for row in rows}) >= 2
    assert any(row.source == "a2a.md" for row in rows)
    assert any(row.source == "agent-tool.md" for row in rows)
    assert any("怎么" in row.userInput or "步骤" in row.userInput for row in rows)
    assert any("排查" in row.userInput or "验证" in row.userInput for row in rows)
    assert any("适用场景" in row.userInput or "解决什么问题" in row.userInput for row in rows)


@pytest.fixture(name="tmpPath")
def fixtureTmpPath(
    tmp_path: Path,  # pylint: disable=invalid-name
) -> Path:
    """适配 pytest 内置临时目录夹具与项目命名约束。"""

    return tmp_path
