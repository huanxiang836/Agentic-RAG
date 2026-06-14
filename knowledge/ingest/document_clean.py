"""负责文档轻量清洗。"""

from __future__ import annotations

import re

from langchain_core.documents import Document


ZERO_WIDTH_PATTERN = re.compile(r"[\u200b-\u200d\uFEFF]")
MULTI_BLANK_LINE_PATTERN = re.compile(r"\n{3,}")


def cleanDocuments(documents: list[Document]) -> list[Document]:
    """批量清洗文档，确保切分前文本噪声尽量稳定。"""

    return [cleanDocument(document) for document in documents]


def cleanDocument(document: Document) -> Document:
    """清洗单个文档，同时保留原始 metadata。"""

    cleanedContent = document.page_content.replace("\r\n", "\n").replace("\r", "\n")
    cleanedContent = ZERO_WIDTH_PATTERN.sub("", cleanedContent)
    cleanedContent = "\n".join(line.rstrip() for line in cleanedContent.split("\n"))
    cleanedContent = MULTI_BLANK_LINE_PATTERN.sub("\n\n", cleanedContent).strip()
    cleanedMetadata = dict(document.metadata)
    cleanedMetadata["is_cleaned"] = True
    return Document(page_content=cleanedContent, metadata=cleanedMetadata)


def buildCleanPreview(document: Document, cleanedDocument: Document, maxLength: int = 240) -> str:
    """生成清洗前后预览，便于先观察预处理效果再继续入库。"""

    originalSnippet = _toPreviewText(document.page_content, maxLength=maxLength)
    cleanedSnippet = _toPreviewText(cleanedDocument.page_content, maxLength=maxLength)
    source = cleanedDocument.metadata.get("source", "未知来源")
    return (
        f"文件: {source}\n"
        f"清洗前: {originalSnippet}\n"
        f"清洗后: {cleanedSnippet}"
    )


def _toPreviewText(text: str, maxLength: int) -> str:
    """把多行文本压成一行预览，避免控制台输出过长。"""

    compactText = text.replace("\n", " ").strip()
    if len(compactText) <= maxLength:
        return compactText
    return f"{compactText[:maxLength]}..."
