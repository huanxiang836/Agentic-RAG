"""消息内容处理测试。"""

from __future__ import annotations

from common.message_content import normalizeMessageContent, stripThinkingContent
from agents.rag.rag_chat_service import _extractVisibleTextChunks


def testStripThinkingContentShouldRemoveThinkBlocks() -> None:
    """推理块应从最终可见内容中移除。"""

    assert stripThinkingContent("前文<think>内部推理</think>结尾") == "前文结尾"


def testNormalizeMessageContentShouldRemoveThinkBlocksFromList() -> None:
    """列表形式的消息内容也应统一清洗。"""

    content = [
        {"type": "text", "text": "前文<think>内部推理</think>结尾"},
        {"type": "reasoning", "reasoning": "内部推理"},
    ]

    assert normalizeMessageContent(content) == "前文结尾"


def testExtractVisibleTextChunksShouldHideSplitThinkBlocks() -> None:
    """跨多个流式片段的推理内容也应被过滤。"""

    visibleChunks, inThinkingBlock = _extractVisibleTextChunks("前文<think>内部", False)
    assert visibleChunks == ["前文"]
    assert inThinkingBlock is True

    visibleChunks, inThinkingBlock = _extractVisibleTextChunks("推理</think>结尾", inThinkingBlock)
    assert visibleChunks == ["结尾"]
    assert inThinkingBlock is False
