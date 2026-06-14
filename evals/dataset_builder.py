"""基于 Markdown 文档生成可复用的 ragas 评测数据集。"""

from __future__ import annotations

from dataclasses import dataclass
import csv
import logging
from pathlib import Path
import re

from knowledge.ingest.config import AppConfig


LOGGER = logging.getLogger(__name__)

HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
WHITESPACE_PATTERN = re.compile(r"\s+")
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[。！？!?])")
LIST_MARKER_PATTERN = re.compile(r"^\s*[-*+]\s+")
ORDERED_LIST_PATTERN = re.compile(r"^\s*\d+\.\s+")
MIN_REFERENCE_LENGTH = 30
MAX_REFERENCE_LENGTH = 220
MAX_DATASET_SIZE = 80
QUESTION_SUFFIX_RULES = [
    ("最佳实践", "时有哪些关键做法？"),
    ("设计原则", "应遵循哪些原则？"),
    ("核心功能", "包含哪些关键能力？"),
    ("前置条件", "前需要满足哪些条件？"),
    ("配置 API Key", "应该怎么配置？"),
    ("环境要求", "需要满足哪些环境要求？"),
    ("安装", "应该按什么步骤完成？"),
    ("架构", "是如何组织的？"),
    ("概念与定义", "的关键点是什么？"),
    ("运行时特性", "体现在哪些方面？"),
    ("支持", "覆盖了哪些能力？"),
]
QUESTION_KEYWORD_RULES = [
    (("区别", "差异"), "分别适用于什么场景？"),
    (("验证", "检查"), "应该如何验证是否生效？"),
    (("使用",), "应该怎么用？"),
    (("配置", "接入", "集成", "启用"), "应该怎么做？"),
    (("实现",), "应该怎么实现？"),
    (("选择",), "应该如何选择？"),
    (("控制",), "应该如何控制？"),
    (("自定义",), "可以如何定制？"),
    (("模式",), "有哪些模式和适用场景？"),
    (("简介", "概述", "介绍"), "主要解决什么问题？"),
    (("安装", "部署", "发布"), "应该按什么步骤完成？"),
    (("排查", "故障", "失败", "无法", "异常", "没有"), "应该如何排查处理？"),
    (("示例",), "体现了什么实现方式？"),
]


@dataclass(frozen=True)
class DatasetRow:
    """定义一条可写入 CSV 的评测样本。"""

    caseId: str
    source: str
    sectionTitle: str
    userInput: str
    reference: str


@dataclass(frozen=True)
class SectionBlock:
    """保存单个 Markdown 标题节点及其正文。"""

    source: str
    headingLevel: int
    sectionTitle: str
    content: str


class RagasDatasetBuilder:  # pylint: disable=too-few-public-methods
    """从知识库 Markdown 文档中抽取问答样本并导出 CSV。"""

    def __init__(self, dataDir: Path) -> None:
        self._dataDir = dataDir

    def buildRows(self, maxDatasetSize: int = MAX_DATASET_SIZE) -> list[DatasetRow]:
        """扫描 Markdown 文档并构建评测样本。"""

        if maxDatasetSize <= 0:
            raise ValueError("maxDatasetSize 必须大于 0。")
        rows: list[DatasetRow] = []
        for markdownPath in sorted(self._dataDir.glob("*.md")):
            for sectionIndex, section in enumerate(_parseMarkdownSections(markdownPath), start=1):
                row = _buildRowFromSection(section=section, sectionIndex=sectionIndex)
                if row is None:
                    continue
                rows.append(row)
                if len(rows) >= maxDatasetSize:
                    LOGGER.info("评测数据集样本数已达到上限 %s。", maxDatasetSize)
                    return rows
        LOGGER.info("评测数据集生成完成，样本数=%s。", len(rows))
        return rows

    def writeCsv(
        self,
        outputPath: Path,
        maxDatasetSize: int = MAX_DATASET_SIZE,
    ) -> list[DatasetRow]:
        """生成评测样本并写入 CSV 文件。"""

        rows = self.buildRows(maxDatasetSize=maxDatasetSize)
        outputPath.parent.mkdir(parents=True, exist_ok=True)
        with outputPath.open("w", encoding="utf-8", newline="") as file:
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
            for row in rows:
                writer.writerow(
                    {
                        "case_id": row.caseId,
                        "source": row.source,
                        "section_title": row.sectionTitle,
                        "user_input": row.userInput,
                        "reference": row.reference,
                    }
                )
        return rows


def buildDefaultRagasDataset(
    outputPath: str | Path,
    maxDatasetSize: int = MAX_DATASET_SIZE,
) -> list[DatasetRow]:
    """基于项目默认数据目录生成 ragas 评测 CSV。"""

    config = AppConfig.fromEnv()
    builder = RagasDatasetBuilder(config.dataDir / "md")
    return builder.writeCsv(
        Path(outputPath),
        maxDatasetSize=maxDatasetSize,
    )


def _parseMarkdownSections(markdownPath: Path) -> list[SectionBlock]:
    """按标题切分 Markdown 文档，保留每个标题下的正文。"""

    lines = markdownPath.read_text(encoding="utf-8").splitlines()
    sections: list[SectionBlock] = []
    currentTitle = markdownPath.stem
    currentLevel = 1
    currentLines: list[str] = []
    insideCodeBlock = False
    for line in lines:
        if line.strip().startswith("```"):
            insideCodeBlock = not insideCodeBlock
            continue
        if insideCodeBlock:
            continue
        headingMatch = HEADING_PATTERN.match(line)
        if headingMatch is not None:
            _appendSection(
                sections=sections,
                source=markdownPath.name,
                headingLevel=currentLevel,
                sectionTitle=currentTitle,
                contentLines=currentLines,
            )
            currentLevel = len(headingMatch.group(1))
            currentTitle = headingMatch.group(2).strip()
            currentLines = []
            continue
        currentLines.append(line)
    _appendSection(
        sections=sections,
        source=markdownPath.name,
        headingLevel=currentLevel,
        sectionTitle=currentTitle,
        contentLines=currentLines,
    )
    return sections


def _appendSection(
    sections: list[SectionBlock],
    source: str,
    headingLevel: int,
    sectionTitle: str,
    contentLines: list[str],
) -> None:
    """清洗标题正文后追加到 section 列表。"""

    normalizedContent = _normalizeSectionContent(contentLines)
    if not normalizedContent:
        return
    sections.append(
        SectionBlock(
            source=source,
            headingLevel=headingLevel,
            sectionTitle=sectionTitle,
            content=normalizedContent,
        )
    )


def _normalizeSectionContent(contentLines: list[str]) -> str:
    """移除图片、表格和无效空白，保留可用于评测的正文。"""

    normalizedLines: list[str] = []
    for rawLine in contentLines:
        strippedLine = rawLine.strip()
        if not strippedLine:
            continue
        if strippedLine.startswith("![") or strippedLine.startswith(":::"):
            continue
        if strippedLine.startswith("|") and strippedLine.endswith("|"):
            continue
        if strippedLine.startswith(">"):
            strippedLine = strippedLine.lstrip(">").strip()
        normalizedLines.append(strippedLine)
    return "\n".join(normalizedLines)


def _buildRowFromSection(section: SectionBlock, sectionIndex: int) -> DatasetRow | None:
    """把一个 section 转换为问答样本。"""

    reference = _buildReference(section.content)
    if reference is None:
        return None
    userInput = _buildQuestion(section)
    caseId = f"{Path(section.source).stem}-{sectionIndex:03d}"
    return DatasetRow(
        caseId=caseId,
        source=section.source,
        sectionTitle=section.sectionTitle,
        userInput=userInput,
        reference=reference,
    )


def _buildReference(content: str) -> str | None:
    """抽取可复用的参考答案正文。"""

    normalizedContent = WHITESPACE_PATTERN.sub(" ", content).strip()
    if len(normalizedContent) < MIN_REFERENCE_LENGTH:
        return None
    sentences = [
        sentence.strip()
        for sentence in SENTENCE_SPLIT_PATTERN.split(normalizedContent)
        if sentence.strip()
    ]
    if not sentences:
        return None
    selectedParts: list[str] = []
    currentLength = 0
    for sentence in sentences:
        currentLength += len(sentence)
        selectedParts.append(sentence)
        if currentLength >= MAX_REFERENCE_LENGTH:
            break
    reference = " ".join(selectedParts).strip()
    if len(reference) < max(MIN_REFERENCE_LENGTH // 2, 30):
        return None
    if len(reference) > MAX_REFERENCE_LENGTH:
        return reference[:MAX_REFERENCE_LENGTH].rstrip("，、；： ") + "。"
    return reference


def _buildQuestion(section: SectionBlock) -> str:
    """根据标题和正文生成更有区分度的评测问题。"""

    normalizedTitle = _normalizeTitle(section.sectionTitle)
    if normalizedTitle == "注意事项":
        return "这一部分有哪些关键注意点？"
    if normalizedTitle.startswith("什么是"):
        return normalizedTitle + "？"
    for suffix, questionSuffix in QUESTION_SUFFIX_RULES:
        if normalizedTitle.endswith(suffix):
            return normalizedTitle + _joinQuestionSuffix(normalizedTitle, questionSuffix)
    for keywords, questionSuffix in QUESTION_KEYWORD_RULES:
        if any(keyword in normalizedTitle for keyword in keywords):
            return normalizedTitle + _joinQuestionSuffix(normalizedTitle, questionSuffix)
    return normalizedTitle + _joinQuestionSuffix(
        normalizedTitle,
        _inferQuestionSuffixFromContent(section.content),
    )


def _inferQuestionSuffixFromContent(content: str) -> str:
    """利用正文结构提升问题复杂度，避免样本长期停留在定义层。"""

    contentLines = content.splitlines()
    if _hasStepLikeContent(contentLines):
        return "需要哪些关键步骤？"
    if _hasParallelListContent(contentLines):
        return "有哪些关键要点？"
    return "的核心内容是什么？"


def _hasStepLikeContent(contentLines: list[str]) -> bool:
    """步骤型内容更适合生成过程类问题。"""

    return any(
        ORDERED_LIST_PATTERN.match(line) or "步骤" in line or "首先" in line or "然后" in line
        for line in contentLines
    )


def _hasParallelListContent(contentLines: list[str]) -> bool:
    """并列型内容更适合生成归纳类问题。"""

    return sum(
        1
        for line in contentLines
        if LIST_MARKER_PATTERN.match(line) or ORDERED_LIST_PATTERN.match(line)
    ) >= 2


def _normalizeTitle(sectionTitle: str) -> str:
    """清洗标题文本，避免把序号和多余符号带入问题。"""

    title = sectionTitle.strip()
    title = ORDERED_LIST_PATTERN.sub("", title)
    title = LIST_MARKER_PATTERN.sub("", title)
    return title.rstrip("：: ")


def _shouldInsertSpaceBeforeQuestionSuffix(title: str) -> bool:
    """为中英文混排标题保留必要空格，避免生成别扭的问题文本。"""

    return bool(title) and title[-1].isascii() and title[-1].isalnum()


def _joinQuestionSuffix(title: str, suffix: str) -> str:
    """在需要时为标题和问句后缀补一个空格。"""

    separator = " " if _shouldInsertSpaceBeforeQuestionSuffix(title) else ""
    return separator + suffix
