"""RAG 聊天服务模式开关测试。"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.documents import Document

from agents.rag.rag_chat_service import RagChatService


@dataclass
class FakeRetrieval:
    """记录检索调用参数。"""

    calls: list[tuple[str, bool]] | None = None

    def retrieveDocuments(self, query: str, useEnhancements: bool = True) -> object:
        """返回固定文档，并记录是否启用增强检索。"""

        if self.calls is None:
            self.calls = []
        self.calls.append((query, useEnhancements))
        return type(
            "RetrievalResult",
            (),
            {
                "rewrittenQuery": query,
                "documents": [
                    Document(
                        page_content="测试内容",
                        metadata={"source": "test.md", "file_path": "test.md", "chunk_index": 0},
                    )
                ],
            },
        )()


def testRetrieveContextsShouldFollowOnlineChatSwitch() -> None:
    """在线聊天默认应跟随开关，评测场景可显式保留增强检索。"""

    service = RagChatService.__new__(RagChatService)
    service._onlineChatRetrievalEnhancedEnabled = False
    service._retrieval = FakeRetrieval()

    assert service.retrieveContexts("原始问题") == ["文档 1\n来源: test.md\n内容: 测试内容"]
    assert service._retrieval.calls == [("原始问题", False)]

    assert service.retrieveContexts("原始问题", useEnhancements=True) == [
        "文档 1\n来源: test.md\n内容: 测试内容"
    ]
    assert service._retrieval.calls == [("原始问题", False), ("原始问题", True)]
