"""RAG 聊天流式输出测试。"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.messages import AIMessage

from agents.rag.rag_chat_service import RagChatService


@dataclass
class FakeAgent:
    """模拟 LangGraph Agent 的最小接口。"""

    invokeResult: dict[str, object]
    callCount: int = 0

    def invoke(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        """返回预设结果并记录调用次数。"""

        self.callCount += 1
        return self.invokeResult


def testStreamChatShouldOnlyEmitSanitizedFinalAnswer() -> None:
    """流式输出应只包含最终正文，不应暴露推理过程。"""

    service = RagChatService.__new__(RagChatService)
    service._agent = FakeAgent(  # type: ignore[attr-defined]
        {
            "messages": [
                AIMessage(content="<think>内部推理</think>最终答案\n第二行"),
            ]
        }
    )

    chunks = list(service.streamChat("user-1", "conv-1", "问题"))

    assert service._agent.callCount == 1  # type: ignore[attr-defined]
    assert "".join(chunks) == "最终答案\n第二行"
    assert "<think>" not in "".join(chunks)
    assert "内部推理" not in "".join(chunks)
