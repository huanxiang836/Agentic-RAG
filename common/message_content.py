"""消息内容处理工具。"""

from __future__ import annotations


def normalizeMessageContent(content: object) -> str:
    """把 LangChain 消息内容统一整理为字符串。"""

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        normalizedParts = []
        for item in content:
            if isinstance(item, dict):
                normalizedParts.append(str(item.get("text", "")))
            else:
                normalizedParts.append(str(item))
        return "".join(normalizedParts)
    return str(content)
