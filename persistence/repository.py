"""会话元数据仓储。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from persistence.db import SESSION_FACTORY
from persistence.models import ConversationEntity


DEFAULT_CONVERSATION_TITLE = "新对话"


@dataclass(frozen=True)
class ConversationRecord:
    """统一会话元数据读写结构。"""

    id: str
    userId: str
    title: str
    createdAt: datetime
    updatedAt: datetime


class ConversationRepository:  # pylint: disable=too-few-public-methods
    """管理会话元数据持久化。"""

    def createConversation(self, userId: str, conversationId: str) -> ConversationRecord:
        """创建一条新会话记录。"""

        now = datetime.now()
        entity = ConversationEntity(
            id=conversationId,
            userId=userId,
            title=DEFAULT_CONVERSATION_TITLE,
            createdAt=now,
            updatedAt=now,
        )
        with SESSION_FACTORY() as session:
            with session.begin():
                session.add(entity)
        return self._toRecord(entity)

    def listConversations(self, userId: str) -> list[ConversationRecord]:
        """按更新时间倒序返回会话列表。"""

        statement = (
            select(ConversationEntity)
            .where(ConversationEntity.userId == userId)
            .order_by(ConversationEntity.updatedAt.desc())
        )
        with SESSION_FACTORY() as session:
            entities = list(session.scalars(statement))
        return [self._toRecord(entity) for entity in entities]

    def getConversation(self, userId: str, conversationId: str) -> ConversationRecord | None:
        """按会话 ID 读取单条记录。"""

        with SESSION_FACTORY() as session:
            entity = session.get(ConversationEntity, conversationId)
        if entity is None or entity.userId != userId:
            return None
        return self._toRecord(entity)

    def updateTitle(self, userId: str, conversationId: str, title: str) -> ConversationRecord:
        """更新会话标题。"""

        with SESSION_FACTORY() as session:
            with session.begin():
                entity = session.get(ConversationEntity, conversationId)
                if entity is None or entity.userId != userId:
                    raise KeyError(f"会话不存在: {conversationId}")
                entity.title = title
                entity.updatedAt = datetime.now()
                session.add(entity)
                session.flush()
                session.refresh(entity)
                return self._toRecord(entity)

    def touchConversation(self, userId: str, conversationId: str) -> ConversationRecord:
        """刷新会话更新时间。"""

        with SESSION_FACTORY() as session:
            with session.begin():
                entity = session.get(ConversationEntity, conversationId)
                if entity is None or entity.userId != userId:
                    raise KeyError(f"会话不存在: {conversationId}")
                entity.updatedAt = datetime.now()
                session.add(entity)
                session.flush()
                session.refresh(entity)
                return self._toRecord(entity)

    def deleteConversation(self, userId: str, conversationId: str) -> None:
        """删除一条会话记录。"""

        with SESSION_FACTORY() as session:
            with session.begin():
                entity = session.get(ConversationEntity, conversationId)
                if entity is None or entity.userId != userId:
                    raise KeyError(f"会话不存在: {conversationId}")
                session.delete(entity)

    def _toRecord(self, entity: ConversationEntity) -> ConversationRecord:
        """把 ORM 实体转换为稳定记录结构。"""

        return ConversationRecord(
            id=entity.id,
            userId=entity.userId,
            title=entity.title,
            createdAt=entity.createdAt,
            updatedAt=entity.updatedAt,
        )
