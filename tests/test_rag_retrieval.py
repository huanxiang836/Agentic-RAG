"""RAG 检索编排测试。"""

from __future__ import annotations

from typing import Any

from langchain_core.documents import Document

from agents.rag.rag_retrieval import RagRetrievalPipeline


class FakeRewriteModel:  # pylint: disable=too-few-public-methods
    """模拟 query rewrite 模型。"""

    def invoke(self, _messages: list[Any]) -> Any:
        """返回固定改写结果。"""

        return type("FakeMessage", (), {"content": "检索改写关键词"})()


class FakeVectorStore:  # pylint: disable=too-few-public-methods,invalid-name
    """模拟 Milvus 混合检索。"""

    def __init__(self, docsByQuery: dict[str, list[Document]]) -> None:
        self._docsByQuery = docsByQuery
        self.calls: list[dict[str, Any]] = []

    def similarity_search(self, query: str, **kwargs: Any) -> list[Document]:
        """按 query 返回固定召回结果。"""

        self.calls.append({"query": query, **kwargs})
        return self._docsByQuery.get(query, [])


class FakeResponse:  # pylint: disable=too-few-public-methods,invalid-name
    """模拟 rerank API 响应。"""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        """测试中不抛出 HTTP 错误。"""

    def json(self) -> dict[str, Any]:
        """返回预置 JSON。"""

        return self._payload


def testRetrieveDocumentsShouldRewriteHybridAndRerank(monkeypatch: Any) -> None:
    """检索链路应按 rewrite -> hybrid -> RRF -> rerank 的顺序工作。"""

    documents = [
        Document(
            page_content="A2A 与 Multi-agent 的区别",
            metadata={"file_path": "a.md", "chunk_index": 0},
        ),
        Document(
            page_content="Checkpoint 与 Store 的边界",
            metadata={"file_path": "b.md", "chunk_index": 0},
        ),
        Document(
            page_content="RAG 与 Query Rewrite",
            metadata={"file_path": "c.md", "chunk_index": 0},
        ),
        Document(
            page_content="Streaming 与 Cancellation",
            metadata={"file_path": "d.md", "chunk_index": 0},
        ),
    ]

    vectorStore = FakeVectorStore(
        {
            "原始问题": [documents[0], documents[1], documents[2], documents[3]],
            "检索改写关键词": [documents[2], documents[1], documents[3], documents[0]],
        }
    )

    monkeypatch.setattr(
        "agents.rag.rag_retrieval.httpx.post",
        lambda *_args, **_kwargs: FakeResponse(
            {
                "results": [
                    {"index": 2, "document": {"text": documents[2].page_content}},
                    {"index": 1, "document": {"text": documents[1].page_content}},
                    {"index": 0, "document": {"text": documents[0].page_content}},
                ]
            }
        ),
    )

    config = type(
        "Config",
        (),
        {
            "siliconflowBaseUrl": "https://api.siliconflow.cn/v1",
            "siliconflowApiKey": "test-key",
            "rerankModel": "BAAI/bge-reranker-v2-m3",
            "onlineChatRetrievalEnhancedEnabled": True,
            "queryRewriteEnabled": True,
            "rerankEnabled": True,
            "rerankTimeoutSeconds": 30.0,
        },
    )()

    pipeline = RagRetrievalPipeline(
        config=config,
        rewriteModel=FakeRewriteModel(),
        vectorStore=vectorStore,
    )

    result = pipeline.retrieveDocuments("原始问题")

    assert result.rewrittenQuery == "检索改写关键词"
    assert [call["query"] for call in vectorStore.calls] == ["原始问题", "检索改写关键词"]
    assert all(call["ranker_type"] == "rrf" for call in vectorStore.calls)
    assert [document.page_content for document in result.documents] == [
        "A2A 与 Multi-agent 的区别",
        "Checkpoint 与 Store 的边界",
        "RAG 与 Query Rewrite",
    ]


def testRetrieveDocumentsShouldSkipRewriteAndRerankWhenEnhancementsDisabled(
    monkeypatch: Any,
) -> None:
    """调用级降级后，检索链路应直接使用原 query 和 RRF 结果。"""

    documents = [
        Document(
            page_content="A2A 与 Multi-agent 的区别",
            metadata={"file_path": "a.md", "chunk_index": 0},
        ),
        Document(
            page_content="Checkpoint 与 Store 的边界",
            metadata={"file_path": "b.md", "chunk_index": 0},
        ),
        Document(
            page_content="RAG 与 Query Rewrite",
            metadata={"file_path": "c.md", "chunk_index": 0},
        ),
    ]

    vectorStore = FakeVectorStore({"原始问题": documents})

    config = type(
        "Config",
        (),
        {
            "siliconflowBaseUrl": "https://api.siliconflow.cn/v1",
            "siliconflowApiKey": "test-key",
            "rerankModel": "BAAI/bge-reranker-v2-m3",
            "onlineChatRetrievalEnhancedEnabled": True,
            "queryRewriteEnabled": True,
            "rerankEnabled": True,
            "rerankTimeoutSeconds": 30.0,
        },
    )()

    def failIfCalled(*_args: Any, **_kwargs: Any) -> FakeResponse:
        """降级模式下不应触发 rerank 请求。"""

        raise AssertionError("rerank 不应在降级模式下被调用。")

    monkeypatch.setattr("agents.rag.rag_retrieval.httpx.post", failIfCalled)

    pipeline = RagRetrievalPipeline(
        config=config,
        rewriteModel=FakeRewriteModel(),
        vectorStore=vectorStore,
    )

    result = pipeline.retrieveDocuments("原始问题", useEnhancements=False)

    assert result.rewrittenQuery == "原始问题"
    assert [call["query"] for call in vectorStore.calls] == ["原始问题"]
    assert [document.page_content for document in result.documents] == [
        "A2A 与 Multi-agent 的区别",
        "Checkpoint 与 Store 的边界",
        "RAG 与 Query Rewrite",
    ]
