"""聊天应用服务测试。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pytest

from application import chat_service
from application.chat_service import ChatApplicationService
from persistence.repository import ConversationRecord


@dataclass
class FakeRagChatService:
    """记录删除调用，验证应用层不会越权清理 checkpoint。"""

    deletedConversationId: str | None = None

    def deleteConversation(self, conversationId: str) -> None:
        """记录被删除的 LangGraph thread。"""

        self.deletedConversationId = conversationId


class FakeConversationRepository:
    """按用户维度模拟会话元数据仓储。"""

    def __init__(self) -> None:
        now = datetime(2026, 6, 15, 10, 0, 0)
        self._record = ConversationRecord(
            id="c1",
            userId="u1",
            title="测试会话",
            createdAt=now,
            updatedAt=now,
        )

    def getConversation(self, userId: str, conversationId: str) -> ConversationRecord | None:
        """只允许正确用户读取会话。"""

        if userId == self._record.userId and conversationId == self._record.id:
            return self._record
        return None

    def deleteConversation(self, userId: str, conversationId: str) -> None:
        """模拟仓储删除。"""

        if self.getConversation(userId, conversationId) is None:
            raise KeyError(f"会话不存在: {conversationId}")


def testDeleteConversationShouldNotDeleteCheckpointWhenUserMismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """跨用户删除应在应用层被拦截，避免误删 LangGraph thread。"""

    monkeypatch.setattr(chat_service, "initDatabase", lambda: None)
    ragService = FakeRagChatService()
    service = ChatApplicationService(
        ragChatService=ragService,  # type: ignore[arg-type]
        conversationRepository=FakeConversationRepository(),  # type: ignore[arg-type]
    )

    with pytest.raises(KeyError):
        service.deleteConversation("u2", "c1")

    assert ragService.deletedConversationId is None
