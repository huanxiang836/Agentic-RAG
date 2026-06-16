"""数据库初始化与会话工厂。"""

from __future__ import annotations

from pathlib import Path
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from persistence.base import Base
from persistence.models import ConversationEntity

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _requireDatabaseUrl() -> str:
    """读取 PostgreSQL 连接串，避免运行期隐式降级。"""

    databaseUrl = os.getenv("DATABASE_URL", "").strip()
    if not databaseUrl:
        raise ValueError("缺少 DATABASE_URL 配置。")
    if databaseUrl.startswith("postgresql://"):
        return databaseUrl.replace("postgresql://", "postgresql+psycopg://", 1)
    return databaseUrl


ENGINE = create_engine(_requireDatabaseUrl(), future=True)
SESSION_FACTORY = sessionmaker(
    bind=ENGINE,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def initDatabase() -> None:
    """初始化业务元数据表。"""

    _ = ConversationEntity
    Base.metadata.create_all(ENGINE)
    _ensureUserIdColumn()


def _ensureUserIdColumn() -> None:
    """项目初期允许轻量迁移，避免旧会话表缺少用户维度。"""

    inspector = inspect(ENGINE)
    columns = {column["name"] for column in inspector.get_columns("chat_conversations")}
    if "user_id" in columns:
        return
    with ENGINE.begin() as connection:
        connection.execute(
            text("ALTER TABLE chat_conversations ADD COLUMN user_id VARCHAR(64)")
        )
        connection.execute(
            text("UPDATE chat_conversations SET user_id = 'default-user' WHERE user_id IS NULL")
        )
        connection.execute(
            text("ALTER TABLE chat_conversations ALTER COLUMN user_id SET NOT NULL")
        )
