"""会话元数据仓储测试。"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from persistence.base import Base
from persistence.repository import ConversationRepository


@pytest.fixture(name="repository")
def repositoryFixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[ConversationRepository]:
    """使用内存数据库验证仓储行为，避免依赖本地 PostgreSQL。"""

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    sessionFactory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr("persistence.repository.SESSION_FACTORY", sessionFactory)
    yield ConversationRepository()
    Base.metadata.drop_all(engine)


def testRepositoryShouldIsolateConversationsByUserId(
    repository: ConversationRepository,
) -> None:
    """不同用户只能看到自己的会话元数据。"""

    repository.createConversation("u1", "c1")
    repository.createConversation("u2", "c2")

    userOneRecords = repository.listConversations("u1")
    userTwoRecords = repository.listConversations("u2")

    assert [record.id for record in userOneRecords] == ["c1"]
    assert [record.id for record in userTwoRecords] == ["c2"]
    assert repository.getConversation("u1", "c2") is None


def testRepositoryShouldRejectCrossUserDelete(
    repository: ConversationRepository,
) -> None:
    """删除会话时必须同时匹配用户 ID 和会话 ID。"""

    repository.createConversation("u1", "c1")

    with pytest.raises(KeyError):
        repository.deleteConversation("u2", "c1")

    assert repository.getConversation("u1", "c1") is not None
