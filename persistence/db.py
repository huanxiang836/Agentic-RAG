"""数据库初始化与会话工厂。"""

from __future__ import annotations

from pathlib import Path
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
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
