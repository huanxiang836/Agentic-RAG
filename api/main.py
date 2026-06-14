"""FastAPI 应用入口。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
import sys

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

try:
    from api.schemas import (
        ChatMessageResponse,
        ChatStreamRequest,
        ConversationDetailResponse,
        ConversationResponse,
        Result,
    )
    from application.chat_service import (
        ChatApplicationService,
        ConversationDetail,
        getChatApplicationService,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    # pylint: disable=ungrouped-imports
    from api.schemas import (
        ChatMessageResponse,
        ChatStreamRequest,
        ConversationDetailResponse,
        ConversationResponse,
        Result,
    )
    from application.chat_service import (
        ChatApplicationService,
        ConversationDetail,
        getChatApplicationService,
    )


def _loadAllowedOrigins() -> list[str]:
    """读取允许访问 API 的前端来源。"""

    rawOrigins = os.getenv("BOT_WEB_ORIGIN", "http://127.0.0.1:5173,http://localhost:5173")
    return [origin.strip() for origin in rawOrigins.split(",") if origin.strip()]


def _formatDateTimeString(value: object) -> str:
    """把 datetime 格式化为统一字符串。"""

    if not isinstance(value, datetime):
        raise TypeError("日期时间字段类型错误。")
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _toConversationDetailResponse(detail: ConversationDetail) -> ConversationDetailResponse:
    """把应用层会话详情转换为 API 响应。"""

    return ConversationDetailResponse(
        id=detail.id,
        title=detail.title,
        createdAt=detail.createdAt,
        updatedAt=detail.updatedAt,
        messages=[
            ChatMessageResponse(id=message.id, role=message.role, content=message.content)
            for message in detail.messages
        ],
    )


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


app = FastAPI(title="Agentic RAG API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_loadAllowedOrigins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/conversations", response_model=Result[list[ConversationResponse]])
def listConversations(
    chatService: ChatApplicationService = Depends(getChatApplicationService),
) -> Result[list[ConversationResponse]]:
    """返回会话列表。"""

    records = chatService.listConversations()
    return Result(
        data=[
            ConversationResponse(
                id=record.id,
                title=record.title,
                createdAt=_formatDateTimeString(record.createdAt),
                updatedAt=_formatDateTimeString(record.updatedAt),
            )
            for record in records
        ]
    )


@app.post("/api/conversations", response_model=Result[ConversationResponse])
def createConversation(
    chatService: ChatApplicationService = Depends(getChatApplicationService),
) -> Result[ConversationResponse]:
    """创建新会话。"""

    record = chatService.createConversation()
    return Result(
        data=ConversationResponse(
            id=record.id,
            title=record.title,
            createdAt=_formatDateTimeString(record.createdAt),
            updatedAt=_formatDateTimeString(record.updatedAt),
        )
    )


@app.delete("/api/conversations/{conversationId}", response_model=Result[None])
def deleteConversation(
    conversationId: str,
    chatService: ChatApplicationService = Depends(getChatApplicationService),
) -> Result[None]:
    """删除会话及其历史。"""

    try:
        chatService.deleteConversation(conversationId)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Result(data=None)


@app.get("/api/conversations/{conversationId}", response_model=Result[ConversationDetailResponse])
def getConversationDetail(
    conversationId: str,
    chatService: ChatApplicationService = Depends(getChatApplicationService),
) -> Result[ConversationDetailResponse]:
    """返回会话详情和消息历史。"""

    try:
        detail = chatService.getConversationDetail(conversationId)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Result(data=_toConversationDetailResponse(detail))


@app.post("/api/chat/stream")
def streamChat(
    request: ChatStreamRequest,
    chatService: ChatApplicationService = Depends(getChatApplicationService),
) -> StreamingResponse:
    """以 SSE 方式返回流式聊天结果。"""

    eventStream = chatService.streamConversation(request.conversationId, request.message)
    return StreamingResponse(eventStream, media_type="text/event-stream")
