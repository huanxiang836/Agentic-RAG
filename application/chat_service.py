"""聊天会话应用服务。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
import json
from typing import Iterator
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from agents.rag.rag_chat_service import RagChatService, getRagChatService
from common.message_content import normalizeMessageContent
from persistence.db import initDatabase
from persistence.repository import (
    ConversationRecord,
    ConversationRepository,
    DEFAULT_CONVERSATION_TITLE,
)


@dataclass(frozen=True)
class ChatMessage:
    """统一返回给 API 和前端的消息结构。"""

    id: str
    role: str
    content: str


@dataclass(frozen=True)
class ConversationDetail:
    """会话详情与消息历史。"""

    id: str
    title: str
    createdAt: str
    updatedAt: str
    messages: list[ChatMessage]


class ChatApplicationService:  # pylint: disable=too-few-public-methods
    """编排会话 CRUD 与流式问答。"""

    def __init__(
        self,
        ragChatService: RagChatService,
        conversationRepository: ConversationRepository,
    ) -> None:
        initDatabase()
        self._ragChatService = ragChatService
        self._conversationRepository = conversationRepository

    def createConversation(self) -> ConversationRecord:
        """创建新会话。"""

        return self._conversationRepository.createConversation(str(uuid4()))

    def listConversations(self) -> list[ConversationRecord]:
        """返回会话摘要列表。"""

        return self._conversationRepository.listConversations()

    def deleteConversation(self, conversationId: str) -> None:
        """删除会话元数据与 LangGraph 线程状态。"""

        self._ragChatService.deleteConversation(conversationId)
        self._conversationRepository.deleteConversation(conversationId)

    def getConversationDetail(self, conversationId: str) -> ConversationDetail:
        """读取会话详情与消息历史。"""

        record = self._conversationRepository.getConversation(conversationId)
        if record is None:
            raise KeyError(f"会话不存在: {conversationId}")
        messages = [
            self._toChatMessage(message)
            for message in self._ragChatService.getConversationMessages(conversationId)
        ]
        return ConversationDetail(
            id=record.id,
            title=record.title,
            createdAt=_formatDateTime(record.createdAt),
            updatedAt=_formatDateTime(record.updatedAt),
            messages=messages,
        )

    def streamConversation(self, conversationId: str, message: str) -> Iterator[str]:
        """执行流式问答并产出 SSE 事件。"""

        record = self._conversationRepository.getConversation(conversationId)
        if record is None:
            raise KeyError(f"会话不存在: {conversationId}")

        if record.title == DEFAULT_CONVERSATION_TITLE:
            self._conversationRepository.updateTitle(
                conversationId,
                _buildConversationTitle(message),
            )

        assistantMessageId = str(uuid4())
        userMessageId = str(uuid4())
        retrievedContexts = self._ragChatService.retrieveContexts(message)
        yield _formatSseEvent(
            "start",
            {
                "conversationId": conversationId,
                "userMessageId": userMessageId,
                "assistantMessageId": assistantMessageId,
                "retrievedContexts": retrievedContexts,
            },
        )
        try:
            for textChunk in self._ragChatService.streamChat(conversationId, message):
                yield _formatSseEvent(
                    "delta",
                    {
                        "assistantMessageId": assistantMessageId,
                        "text": textChunk,
                    },
                )
            self._conversationRepository.touchConversation(conversationId)
            yield _formatSseEvent(
                "done",
                {
                    "assistantMessageId": assistantMessageId,
                },
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            yield _formatSseEvent("error", {"message": str(exc)})

    def _toChatMessage(self, message: BaseMessage) -> ChatMessage:
        """把 LangChain 消息转换为前端可消费结构。"""

        if isinstance(message, HumanMessage):
            role = "user"
        elif isinstance(message, AIMessage):
            role = "assistant"
        else:
            role = "system"
        return ChatMessage(
            id=str(message.id or uuid4()),
            role=role,
            content=normalizeMessageContent(message.content),
        )


@lru_cache(maxsize=1)
def getChatApplicationService() -> ChatApplicationService:
    """复用应用服务单例。"""

    return ChatApplicationService(
        ragChatService=getRagChatService(),
        conversationRepository=ConversationRepository(),
    )


def _formatSseEvent(event: str, payload: dict[str, object]) -> str:
    """统一格式化 SSE 文本。"""

    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _buildConversationTitle(message: str) -> str:
    """使用首条消息生成简洁标题。"""

    normalizedMessage = " ".join(message.strip().split())
    if len(normalizedMessage) <= 24:
        return normalizedMessage
    return normalizedMessage[:24].rstrip() + "..."


def _formatDateTime(value: object) -> str:
    """统一日期时间字符串格式。"""

    if not isinstance(value, datetime):
        raise TypeError("日期时间字段类型错误。")
    return value.strftime("%Y-%m-%d %H:%M:%S")
