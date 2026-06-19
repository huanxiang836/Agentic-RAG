"""消息内容处理工具。"""

from __future__ import annotations

import re


THINK_BLOCK_PATTERN = re.compile(r"<think>[\s\S]*?</think>")
THINK_TAG_PATTERN = re.compile(r"</?think>")


def normalizeMessageContent(content: object) -> str:
    """把 LangChain 消息内容统一整理为字符串。"""

    if isinstance(content, str):
        return stripThinkingContent(content)
    if isinstance(content, list):
        normalizedParts = []
        for item in content:
            if isinstance(item, dict):
                normalizedParts.append(stripThinkingContent(str(item.get("text", ""))))
            else:
                normalizedParts.append(stripThinkingContent(str(item)))
        return "".join(normalizedParts)
    return stripThinkingContent(str(content))


def stripThinkingContent(content: str) -> str:
    """移除模型输出中包裹在 `<think>` 标记里的推理内容。"""

    cleanedContent = THINK_BLOCK_PATTERN.sub("", content)
    return THINK_TAG_PATTERN.sub("", cleanedContent)
