"""负责 Embedding 与 Milvus 写入。"""

from __future__ import annotations

from itertools import islice
from typing import Iterator
import logging
import warnings

from langchain_core.documents import Document
from langchain_milvus import Milvus
from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr
from pymilvus import (  # type: ignore[import-untyped]
    MilvusClient,
    PyMilvusDeprecationWarning,
    connections,
    utility,
)

from .config import AppConfig


LOGGER = logging.getLogger(__name__)
MILVUS_ADMIN_ALIAS = "rag_milvus_admin"
MILVUS_INDEX_PARAMS = {
    "index_type": "HNSW",
    "metric_type": "COSINE",
    "params": {"M": 8, "efConstruction": 64},
}
MILVUS_SEARCH_PARAMS = {
    "metric_type": "COSINE",
    "params": {"ef": 64},
}

warnings.filterwarnings("ignore", category=PyMilvusDeprecationWarning)


def createEmbeddings(config: AppConfig) -> OpenAIEmbeddings:
    """创建与切分、入库共用的 Embeddings，避免语义空间漂移。"""

    return OpenAIEmbeddings(
        model=config.embeddingModel,
        api_key=SecretStr(config.embeddingApiKey),
        base_url=config.openaiBaseUrl,
        timeout=config.embeddingTimeoutSeconds,
        max_retries=config.embeddingMaxRetries,
        tiktoken_enabled=False,
        check_embedding_ctx_length=False,
    )


def validateEmbeddingDimension(config: AppConfig, embeddings: OpenAIEmbeddings) -> None:
    """启动阶段先做维度校验，避免错误 schema 写进 Milvus。"""

    try:
        vector = embeddings.embed_query("维度检查")
    except Exception as error:  # pylint: disable=broad-except
        raise RuntimeError(f"Embedding 接口调用失败: {error}") from error
    actualDimension = len(vector)
    if actualDimension != config.milvusEmbeddingDimension:
        raise ValueError(
            "Embedding 向量维度不匹配，"
            f"期望 {config.milvusEmbeddingDimension}，实际 {actualDimension}。"
        )


def openMilvusVectorStore(
    config: AppConfig,
    embeddings: OpenAIEmbeddings,
    recreateCollection: bool = False,
) -> Milvus:
    """打开 Milvus 集合；当 `recreateCollection=True` 时先删除旧集合后再重建。"""

    try:
        connectionArgs = {
            "uri": config.milvusUri,
            "token": f"{config.milvusUsername}:{config.milvusPassword}",
            "db_name": config.milvusDatabase,
        }
        # 当前 langchain-milvus 会在部分路径回退到 PyMilvus ORM Collection，
        # 但不会自动把 alias 注册到 connections 中。这里补齐注册，保持外层仍遵循官方集成用法。
        connections.connect(
            alias=MilvusClient(**connectionArgs)._using,  # pylint: disable=protected-access
            **connectionArgs,
        )
        if recreateCollection:
            _dropCollectionIfExists(config, connectionArgs["token"])
        return Milvus(
            embedding_function=embeddings,
            collection_name=config.milvusCollection,
            connection_args=connectionArgs,
            index_params=MILVUS_INDEX_PARAMS,
            search_params=MILVUS_SEARCH_PARAMS,
            drop_old=False,
            auto_id=True,
            enable_dynamic_field=True,
        )
    except Exception as error:  # pylint: disable=broad-except
        raise RuntimeError(f"Milvus 初始化失败: {error}") from error


def writeDocumentsToMilvus(
    vectorStore: Milvus,
    documents: list[Document],
    batchSize: int,
) -> int:
    """分批写入 Milvus，降低单次请求体过大带来的失败概率。"""

    totalInserted = 0
    for batchIndex, batch in enumerate(_batched(documents, batchSize), start=1):
        try:
            vectorStore.add_documents(documents=batch)
            totalInserted += len(batch)
            LOGGER.info("第 %s 批写入完成，本批 %s 条。", batchIndex, len(batch))
        except Exception as error:  # pylint: disable=broad-except
            raise RuntimeError(f"Milvus 写入失败，第 {batchIndex} 批异常: {error}") from error
    return totalInserted


def _dropCollectionIfExists(config: AppConfig, token: str) -> None:
    """在重建集合前先显式删除旧集合，避免上游 drop_old 路径的异步警告。"""

    connections.connect(
        alias=MILVUS_ADMIN_ALIAS,
        uri=config.milvusUri,
        token=token,
        db_name=config.milvusDatabase,
    )
    if utility.has_collection(config.milvusCollection, using=MILVUS_ADMIN_ALIAS):
        utility.drop_collection(config.milvusCollection, using=MILVUS_ADMIN_ALIAS)


def _batched(items: list[Document], batchSize: int) -> Iterator[list[Document]]:
    """按固定批大小切片，保持实现简单且无额外依赖。"""

    if batchSize <= 0:
        raise ValueError("batchSize 必须大于 0。")
    iterator = iter(items)
    while True:
        batch = list(islice(iterator, batchSize))
        if not batch:
            break
        yield batch
