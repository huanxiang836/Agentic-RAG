"""API 模块测试。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterator

from fastapi.testclient import TestClient

from api.main import app
from application.chat_service import (
    ChatApplicationService,
    ChatMessage,
    ConversationDetail,
    getChatApplicationService,
)
from persistence.repository import ConversationRecord


@dataclass(frozen=True)
class FakeStreamConversation:
    """测试用会话元数据。"""

    id: str
    title: str
    createdAt: datetime
    updatedAt: datetime


class FakeChatApplicationService:  # pylint: disable=too-few-public-methods
    """测试用替身应用服务。"""

    def listConversations(self, userId: str) -> list[ConversationRecord]:
        """返回稳定会话列表。"""

        now = datetime(2026, 6, 13, 21, 0, 0)
        return [
            ConversationRecord(
                id="c1",
                userId=userId,
                title="测试会话",
                createdAt=now,
                updatedAt=now,
            )
        ]

    def createConversation(self, userId: str) -> ConversationRecord:
        """返回新建会话结果。"""

        now = datetime(2026, 6, 13, 21, 5, 0)
        return ConversationRecord(
            id="c2",
            userId=userId,
            title="新对话",
            createdAt=now,
            updatedAt=now,
        )

    def getConversationDetail(self, userId: str, conversationId: str) -> ConversationDetail:
        """返回稳定会话详情。"""

        return ConversationDetail(
            id=conversationId,
            userId=userId,
            title="测试会话",
            createdAt="2026-06-13 21:00:00",
            updatedAt="2026-06-13 21:00:10",
            messages=[
                ChatMessage(id="m1", role="user", content="你好"),
                ChatMessage(id="m2", role="assistant", content="你好，我在。"),
            ],
        )

    def deleteConversation(self, userId: str, conversationId: str) -> None:
        """删除测试会话。"""

        _ = (userId, conversationId)

    def streamConversation(self, userId: str, conversationId: str, message: str) -> Iterator[str]:
        """返回稳定 SSE 事件流。"""

        yield (
            "event: start\n"
            "data: "
            f"{{\"conversationId\": \"{conversationId}\", "
            f"\"userId\": \"{userId}\", "
            "\"userMessageId\": \"u1\", "
            "\"assistantMessageId\": \"a1\"}}\n\n"
        )
        yield (
            "event: delta\n"
            f"data: {{\"assistantMessageId\": \"a1\", \"text\": \"收到 {message}\"}}\n\n"
        )
        yield "event: done\ndata: {\"assistantMessageId\": \"a1\"}\n\n"


def testListConversationsShouldReturnUnifiedResult() -> None:
    """会话列表接口应返回统一 Result 结构。"""

    client = _createClient()
    response = client.get("/api/conversations?userId=u1")

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"][0]["id"] == "c1"
    assert response.json()["data"][0]["userId"] == "u1"


def testCreateConversationShouldReturnUnifiedResult() -> None:
    """创建会话接口应返回统一 Result 结构。"""

    client = _createClient()
    response = client.post("/api/conversations", json={"userId": "u1"})

    assert response.status_code == 200
    assert response.json()["data"]["id"] == "c2"
    assert response.json()["data"]["userId"] == "u1"
    assert response.json()["data"]["title"] == "新对话"


def testConversationDetailShouldReturnMessages() -> None:
    """会话详情接口应返回消息历史。"""

    client = _createClient()
    response = client.get("/api/conversations/c1?userId=u1")

    assert response.status_code == 200
    assert response.json()["data"]["userId"] == "u1"
    assert response.json()["data"]["messages"][1]["content"] == "你好，我在。"


def testChatStreamShouldReturnSsePayload() -> None:
    """流式聊天接口应返回 SSE 文本。"""

    client = _createClient()
    response = client.post(
        "/api/chat/stream",
        json={"userId": "u1", "conversationId": "c1", "message": "测试问题"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: start" in response.text
    assert '"userId": "u1"' in response.text
    assert "event: delta" in response.text
    assert "收到 测试问题" in response.text


def _createClient() -> TestClient:
    """创建带依赖覆盖的测试客户端。"""

    def overrideChatService() -> ChatApplicationService:
        """返回测试替身服务。"""

        return FakeChatApplicationService()  # type: ignore[return-value]

    app.dependency_overrides[getChatApplicationService] = overrideChatService
    return TestClient(app)
