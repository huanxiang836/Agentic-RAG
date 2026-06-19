"""RAG 检索编排：query rewrite + Milvus hybrid search + RRF + rerank。"""

# pylint: disable=too-few-public-methods

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import logging
import re
from typing import Any

import httpx
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_milvus import Milvus
from langchain_openai import ChatOpenAI

from common.message_content import normalizeMessageContent
from knowledge.ingest.config import AppConfig


LOGGER = logging.getLogger(__name__)
VECTOR_RETRIEVAL_K = 5
HIT_FETCH_K = 10
RRF_FUSION_K = 60
RRF_CANDIDATE_LIMIT = 10
FINAL_CONTEXT_LIMIT = 3
RERANK_ENDPOINT_PATH = "/rerank"
RERANK_REQUEST_TIMEOUT_SECONDS = 30.0
QUERY_REWRITE_SYSTEM_PROMPT = (
    "你是一个检索查询改写器。"
    "请把用户问题改写成更适合知识库检索的短查询，尽量保留专有名词、模型名、接口名、字段名和关键约束。"
    "只输出改写后的检索 query，不要解释，不要列表，不要 Markdown。"
)


@dataclass(frozen=True)
class RetrievalResult:
    """保存最终检索结果，便于问答与评测复用。"""

    rewrittenQuery: str
    documents: list[Document]


class RagRetrievalPipeline:
    """把查询改写、Milvus 混合召回、RRF 和 rerank 串成一条稳定链路。"""

    def __init__(
        self,
        config: AppConfig,
        rewriteModel: ChatOpenAI,
        vectorStore: Milvus,
    ) -> None:
        self._config = config
        self._rewriteModel = rewriteModel
        self._vectorStore = vectorStore

    def retrieveDocuments(self, query: str, useEnhancements: bool = True) -> RetrievalResult:
        """执行检索链路，必要时启用 query rewrite 与 rerank。"""

        normalizedQuery = query.strip()
        if useEnhancements:
            rewrittenQuery = self._rewriteQuery(query)
            queryVariants = _uniqueNonEmpty([normalizedQuery, rewrittenQuery])
        else:
            rewrittenQuery = normalizedQuery
            queryVariants = [normalizedQuery] if normalizedQuery else []
        candidateLists = [self._hybridRetrieve(queryVariant) for queryVariant in queryVariants]
        fusedDocuments = self._rrfFuse(candidateLists)[:RRF_CANDIDATE_LIMIT]
        if useEnhancements:
            finalDocuments = self._rerank(query=rewrittenQuery or normalizedQuery, documents=fusedDocuments)[
                :FINAL_CONTEXT_LIMIT
            ]
        else:
            finalDocuments = fusedDocuments[:FINAL_CONTEXT_LIMIT]
        if useEnhancements and rewrittenQuery != normalizedQuery:
            LOGGER.info("query rewrite 完成：%s -> %s", query, rewrittenQuery)
        LOGGER.info(
            "检索完成：模式=%s，候选=%s，最终=%s",
            "enhanced" if useEnhancements else "basic",
            len(fusedDocuments),
            len(finalDocuments),
        )
        return RetrievalResult(rewrittenQuery=rewrittenQuery, documents=finalDocuments)

    def _rewriteQuery(self, query: str) -> str:
        """把自然语言问题改写成更利于召回的检索 query。"""

        if not self._config.queryRewriteEnabled:
            return query.strip()
        try:
            response = self._rewriteModel.invoke(
                [
                    SystemMessage(content=QUERY_REWRITE_SYSTEM_PROMPT),
                    HumanMessage(content=query),
                ]
            )
            rewrittenQuery = _normalizeQueryRewrite(normalizeMessageContent(response.content))
            if rewrittenQuery and rewrittenQuery != query.strip():
                return rewrittenQuery
        except Exception as error:  # pylint: disable=broad-except
            LOGGER.warning("query rewrite 失败，回退原问题。query=%s, error=%s", query, error)
        return query.strip()

    def _hybridRetrieve(self, query: str) -> list[Document]:
        """调用 Milvus 原生混合检索，融合 dense 和 BM25 sparse 召回。"""

        try:
            documents = self._vectorStore.similarity_search(
                query=query,
                k=VECTOR_RETRIEVAL_K,
                fetch_k=HIT_FETCH_K,
                ranker_type="rrf",
            )
            return [document for document in documents if isinstance(document, Document)]
        except Exception as error:  # pylint: disable=broad-except
            LOGGER.warning("Milvus 混合召回失败，回退空结果。query=%s, error=%s", query, error)
            return []

    def _rrfFuse(self, rankedDocumentsLists: list[list[Document]]) -> list[Document]:
        """用 Reciprocal Rank Fusion 合并多个召回列表。"""

        if not rankedDocumentsLists:
            return []
        scores: dict[str, float] = defaultdict(float)
        documentsByKey: dict[str, Document] = {}
        for documents in rankedDocumentsLists:
            for rank, document in enumerate(documents, start=1):
                key = _documentKey(document)
                scores[key] += 1.0 / (RRF_FUSION_K + rank)
                if key not in documentsByKey:
                    documentsByKey[key] = document
        orderedKeys = sorted(scores.keys(), key=lambda key: scores[key], reverse=True)
        return [documentsByKey[key] for key in orderedKeys]

    def _rerank(self, query: str, documents: list[Document]) -> list[Document]:
        """调用 SiliconFlow rerank 接口对候选文档重排。"""

        if not self._config.rerankEnabled:
            return documents[:FINAL_CONTEXT_LIMIT]
        if not documents:
            return []
        try:
            response = httpx.post(
                f"{self._config.siliconflowBaseUrl}{RERANK_ENDPOINT_PATH}",
                headers={
                    "Authorization": f"Bearer {self._config.siliconflowApiKey}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._config.rerankModel,
                    "query": query,
                    "documents": [document.page_content for document in documents],
                    "top_n": FINAL_CONTEXT_LIMIT,
                    "return_documents": True,
                },
                timeout=self._config.rerankTimeoutSeconds,
            )
            response.raise_for_status()
            payload = response.json()
            results = payload.get("results", [])
            if not isinstance(results, list) or not results:
                return documents[:FINAL_CONTEXT_LIMIT]
            selectedDocuments: list[Document] = []
            usedKeys: set[str] = set()
            for result in results:
                document = _resolveRerankDocument(result, documents, usedKeys)
                if document is None:
                    continue
                documentKey = _documentKey(document)
                if documentKey in usedKeys:
                    continue
                usedKeys.add(documentKey)
                selectedDocuments.append(document)
            if selectedDocuments:
                return selectedDocuments
        except Exception as error:  # pylint: disable=broad-except
            LOGGER.warning("rerank 失败，回退 RRF 结果。query=%s, error=%s", query, error)
        return documents[:FINAL_CONTEXT_LIMIT]


def _resolveRerankDocument(
    result: dict[str, Any],
    documents: list[Document],
    usedKeys: set[str],
) -> Document | None:
    """根据 rerank 结果解析回原始 Document。"""

    index = result.get("index")
    if isinstance(index, int):
        candidateIndexes = []
        if 0 <= index < len(documents):
            candidateIndexes.append(index)
        if 1 <= index <= len(documents):
            candidateIndexes.append(index - 1)
        for candidateIndex in candidateIndexes:
            document = documents[candidateIndex]
            if _documentKey(document) not in usedKeys:
                return document

    documentPayload = result.get("document")
    if isinstance(documentPayload, dict):
        rerankText = str(documentPayload.get("text", "")).strip()
        if rerankText:
            for document in documents:
                if _documentKey(document) in usedKeys:
                    continue
                if document.page_content.strip() == rerankText:
                    return document

    for document in documents:
        if _documentKey(document) not in usedKeys:
            return document
    return None


def _documentKey(document: Document) -> str:
    """构造稳定的文档去重键。"""

    metadata = document.metadata
    filePath = str(metadata.get("file_path", metadata.get("source", "")))
    chunkIndex = str(metadata.get("chunk_index", ""))
    return "||".join([filePath, chunkIndex, document.page_content.strip()])


def _normalizeQueryRewrite(text: str) -> str:
    """清理 query rewrite 输出，避免模型附带解释性文本。"""

    cleanedText = text.strip().strip("`").strip('"').strip("'")
    cleanedText = re.sub(
        r"^(改写后的查询|检索查询|查询|rewrite query|rewritten query)[:：]\s*",
        "",
        cleanedText,
        flags=re.IGNORECASE,
    )
    lines = [line.strip() for line in cleanedText.splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[0]


def _uniqueNonEmpty(items: list[str]) -> list[str]:
    """按原始顺序去重，避免重复 query 增加噪音。"""

    seen: set[str] = set()
    uniqueItems: list[str] = []
    for item in items:
        normalizedItem = item.strip()
        if not normalizedItem or normalizedItem in seen:
            continue
        seen.add(normalizedItem)
        uniqueItems.append(normalizedItem)
    return uniqueItems
