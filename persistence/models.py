"""会话元数据 ORM 模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from persistence.base import Base


class ConversationEntity(Base):  # pylint: disable=too-few-public-methods
    """保存会话元数据，消息正文由 LangGraph memory 承担。"""

    __tablename__ = "chat_conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    createdAt: Mapped[datetime] = mapped_column("created_at", DateTime, nullable=False)
    updatedAt: Mapped[datetime] = mapped_column("updated_at", DateTime, nullable=False)
