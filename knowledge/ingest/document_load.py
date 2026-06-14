"""负责发现并加载 Markdown 文档。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import logging

from langchain_core.documents import Document
from langchain_docling import DoclingLoader
from langchain_docling.loader import ExportType


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoadFailure:
    """记录单个文件加载失败信息。"""

    filePath: str
    reason: str


def discoverMarkdownFiles(dataDir: Path) -> list[Path]:
    """递归发现 Markdown 文件，并按路径排序保持结果稳定。"""

    return sorted(path for path in dataDir.rglob("*.md") if path.is_file())


def loadMarkdownDocuments(filePaths: Iterable[Path]) -> tuple[list[Document], list[LoadFailure]]:
    """逐文件加载 Markdown，避免单文件失败拖垮整批任务。"""

    documents: list[Document] = []
    failures: list[LoadFailure] = []
    for filePath in filePaths:
        try:
            loader = DoclingLoader(
                file_path=str(filePath),
                export_type=ExportType.MARKDOWN,
            )
            loadedDocuments = loader.load()
            for document in loadedDocuments:
                document.metadata.update(
                    {
                        "source": str(filePath),
                        "file_name": filePath.name,
                        "file_path": str(filePath),
                        "file_type": "markdown",
                    }
                )
                documents.append(document)
        except Exception as error:  # pylint: disable=broad-except
            LOGGER.exception("加载 Markdown 失败: %s", filePath)
            failures.append(LoadFailure(filePath=str(filePath), reason=str(error)))
    return documents, failures
