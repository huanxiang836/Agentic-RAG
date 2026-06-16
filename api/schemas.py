"""定义 API 请求与响应模型。"""
# pylint: disable=duplicate-code

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class Result(BaseModel, Generic[T]):
    """统一响应结构。"""

    code: int = 0
    msg: str = "success"
    data: T


class ConversationResponse(BaseModel):
    """会话摘要响应。"""

    id: str
    userId: str
    title: str
    createdAt: str
    updatedAt: str


class ChatMessageResponse(BaseModel):
    """聊天消息响应。"""

    id: str
    role: str
    content: str


class ConversationDetailResponse(BaseModel):
    """会话详情响应。"""

    id: str
    userId: str
    title: str
    createdAt: str
    updatedAt: str
    messages: list[ChatMessageResponse]


class CreateConversationRequest(BaseModel):
    """创建会话请求。"""

    userId: str


class ChatStreamRequest(BaseModel):
    """流式聊天请求。"""

    userId: str
    conversationId: str
    message: str
