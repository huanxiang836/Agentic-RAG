"""Markdown 语义切分并写入 Milvus 的 CLI 入口。（废弃方案，已经改为递归切分）"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

try:
    from .config import AppConfig
    from .document_chunk import chunkDocuments
    from .document_clean import buildCleanPreview, cleanDocuments
    from .document_load import discoverMarkdownFiles, loadMarkdownDocuments
    from .vector_store import (
        createEmbeddings,
        openMilvusVectorStore,
        validateEmbeddingDimension,
        writeDocumentsToMilvus,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
    from knowledge.ingest.config import AppConfig
    from knowledge.ingest.document_chunk import chunkDocuments
    from knowledge.ingest.document_clean import buildCleanPreview, cleanDocuments
    from knowledge.ingest.document_load import (
        discoverMarkdownFiles,
        loadMarkdownDocuments,
    )
    from knowledge.ingest.vector_store import (
        createEmbeddings,
        openMilvusVectorStore,
        validateEmbeddingDimension,
        writeDocumentsToMilvus,
    )


LOGGER = logging.getLogger(__name__)


def main() -> int:
    """执行完整导入流程，并返回进程退出码。"""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    try:
        config = AppConfig.fromEnv()
        filePaths = discoverMarkdownFiles(config.dataDir)
        if not filePaths:
            LOGGER.warning("未在 %s 下发现 Markdown 文件。", config.dataDir)
            return 0

        LOGGER.info("发现 %s 个 Markdown 文件。", len(filePaths))
        loadedDocuments, loadFailures = loadMarkdownDocuments(filePaths)
        LOGGER.info(
            "成功加载 %s 个文档，失败 %s 个。", len(loadedDocuments), len(loadFailures)
        )
        if loadFailures:
            for failure in loadFailures:
                LOGGER.warning("跳过文件 %s，原因: %s", failure.filePath, failure.reason)
        if not loadedDocuments:
            LOGGER.error("没有可继续处理的文档，导入终止。")
            return 1

        cleanedDocuments = cleanDocuments(loadedDocuments)
        _logCleanPreview(loadedDocuments=loadedDocuments, cleanedDocuments=cleanedDocuments)

        embeddings = createEmbeddings(config)
        validateEmbeddingDimension(config, embeddings)
        chunkedDocuments = chunkDocuments(cleanedDocuments)
        LOGGER.info("语义切分完成，得到 %s 个分片。", len(chunkedDocuments))

        LOGGER.info("开始初始化 Milvus 集合。")
        vectorStore = openMilvusVectorStore(
            config,
            embeddings,
            recreateCollection=True,
        )
        LOGGER.info("Milvus 集合初始化完成，开始写入分片。")
        insertedCount = writeDocumentsToMilvus(
            vectorStore=vectorStore,
            documents=chunkedDocuments,
            batchSize=config.milvusInsertBatchSize,
        )
        LOGGER.info("Milvus 写入完成，共写入 %s 个分片。", insertedCount)
        return 0
    except Exception as error:  # pylint: disable=broad-except
        LOGGER.exception("Markdown 入库失败: %s", error)
        return 1


def _logCleanPreview(loadedDocuments: list, cleanedDocuments: list) -> None:
    """先输出清洗预览，便于观察预处理是否过度。"""

    previewCount = min(2, len(cleanedDocuments))
    for index in range(previewCount):
        preview = buildCleanPreview(loadedDocuments[index], cleanedDocuments[index])
        LOGGER.info("文档清洗预览 %s/%s:\n%s", index + 1, previewCount, preview)


if __name__ == "__main__":
    sys.exit(main())
