"""Langfuse 观测集成工具。"""

from __future__ import annotations

import logging
import os
from typing import Any, cast

from langchain_core.runnables import RunnableConfig


LOGGER = logging.getLogger(__name__)
LANGFUSE_REQUIRED_ENV_NAMES = (
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_BASE_URL",
)
DEFAULT_LANGFUSE_ENV = "dev"


def isLangfuseEnabled() -> bool:
    """检查 Langfuse 关键配置是否完整。"""

    return all(os.getenv(name, "").strip() for name in LANGFUSE_REQUIRED_ENV_NAMES)


def createLangfuseHandler() -> Any | None:
    """创建 LangChain CallbackHandler；未配置 Langfuse 时返回空值。"""

    if not isLangfuseEnabled():
        return None
    try:
        from langfuse.langchain import CallbackHandler  # pylint: disable=import-outside-toplevel

        return CallbackHandler()
    except Exception as error:  # pylint: disable=broad-exception-caught
        LOGGER.exception("初始化 Langfuse CallbackHandler 失败: %s", error)
        return None


def buildLangfuseRunnableConfig(
    conversationId: str,
    baseConfig: RunnableConfig,
    tags: list[str] | None = None,
    metadata: dict[str, object] | None = None,
) -> RunnableConfig:
    """合并 LangGraph 线程配置与 Langfuse tracing 配置。"""

    mergedConfig = dict(baseConfig)
    mergedMetadata = dict(metadata or {})
    mergedMetadata.update(
        {
            "conversationId": conversationId,
            "langfuse_session_id": conversationId,
            "langfuse_tags": _buildLangfuseTags(tags),
            "environment": os.getenv("LANGFUSE_ENV", DEFAULT_LANGFUSE_ENV).strip()
            or DEFAULT_LANGFUSE_ENV,
        }
    )
    mergedConfig["metadata"] = mergedMetadata

    handler = createLangfuseHandler()
    if handler is not None:
        callbacks = list(cast(list[Any], mergedConfig.get("callbacks", [])))
        callbacks.append(handler)
        mergedConfig["callbacks"] = callbacks
    return cast(RunnableConfig, mergedConfig)


def flushLangfuse() -> None:
    """同步刷新 Langfuse 队列，供短进程评测结束前调用。"""

    if not isLangfuseEnabled():
        return
    try:
        from langfuse import get_client  # pylint: disable=import-outside-toplevel

        get_client().flush()
    except Exception as error:  # pylint: disable=broad-exception-caught
        LOGGER.exception("刷新 Langfuse 数据失败: %s", error)


def requireLangfuseConfigured() -> None:
    """强制要求 Langfuse 配置完整，供评测实验入口使用。"""

    missingNames = [name for name in LANGFUSE_REQUIRED_ENV_NAMES if not os.getenv(name, "").strip()]
    if missingNames:
        raise ValueError(f"缺少 Langfuse 配置: {', '.join(missingNames)}")


def _buildLangfuseTags(tags: list[str] | None) -> list[str]:
    """生成稳定 tags，方便在 Langfuse UI 中筛选。"""

    environment = os.getenv("LANGFUSE_ENV", DEFAULT_LANGFUSE_ENV).strip() or DEFAULT_LANGFUSE_ENV
    return [environment, *(tags or [])]
