"""Langfuse Prompt 管理工具。"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langfuse import Langfuse

from common.langfuse_observability import isLangfuseEnabled
from common.rag_assets import RagAssets


LOGGER = logging.getLogger(__name__)
RAG_SYSTEM_PROMPT_NAME = RagAssets.RAG_SYSTEM_PROMPT_NAME
PROJECT_ROOT = Path(__file__).resolve().parents[1]
LANGFUSE_PROMPT_FETCH_TIMEOUT_SECONDS = 30
LANGFUSE_PROMPT_SYNC_TIMEOUT_SECONDS = 120
DEFAULT_RAG_SYSTEM_PROMPT = RagAssets.DEFAULT_RAG_SYSTEM_PROMPT


def getRagSystemPrompt() -> str:
    """优先从 Langfuse 读取系统 Prompt，失败时回退到本地默认值。"""

    _loadProjectEnv()
    if not isLangfuseEnabled():
        return DEFAULT_RAG_SYSTEM_PROMPT
    try:
        prompt = _getLangfuseClient().get_prompt(
            RAG_SYSTEM_PROMPT_NAME,
            label="production",
            max_retries=1,
            fetch_timeout_seconds=LANGFUSE_PROMPT_FETCH_TIMEOUT_SECONDS,
        )
        normalizedPrompt = str(getattr(prompt, "prompt", "")).strip()
        if normalizedPrompt:
            return normalizedPrompt
    except Exception as error:  # pylint: disable=broad-exception-caught
        LOGGER.exception("读取 Langfuse Prompt 失败，回退到本地默认值: %s", error)
    return DEFAULT_RAG_SYSTEM_PROMPT


def syncRagSystemPromptToLangfuse() -> bool:
    """把当前代码中的系统 Prompt 同步到 Langfuse。"""

    _loadProjectEnv()
    if not isLangfuseEnabled():
        return False
    client = _getLangfuseClient()
    promptVersion = _findProductionPromptVersion(client)
    if (
        promptVersion is not None
        and _normalizePromptText(getattr(promptVersion, "prompt", "")) == DEFAULT_RAG_SYSTEM_PROMPT
    ):
        return False
    labels = ["production"]
    tags = [os.getenv("LANGFUSE_ENV", "dev").strip() or "dev"]
    client.create_prompt(
        name=RAG_SYSTEM_PROMPT_NAME,
        prompt=DEFAULT_RAG_SYSTEM_PROMPT,
        labels=labels,
        tags=tags,
        commit_message="Sync Agentic RAG system prompt from code",
    )
    if hasattr(client, "clear_prompt_cache"):
        client.clear_prompt_cache()
    LOGGER.info("Langfuse Prompt 已同步: %s", RAG_SYSTEM_PROMPT_NAME)
    return True


def _findProductionPromptVersion(client: Any) -> Any | None:
    """获取当前生产态 Prompt 版本。"""

    try:
        return client.get_prompt(
            RAG_SYSTEM_PROMPT_NAME,
            label="production",
            max_retries=1,
            fetch_timeout_seconds=LANGFUSE_PROMPT_FETCH_TIMEOUT_SECONDS,
        )
    except Exception:  # pylint: disable=broad-exception-caught
        return None


def _normalizePromptText(promptText: object) -> str:
    """规范化 Prompt 文本，避免空白差异导致重复版本。"""

    return str(promptText).strip()


def _getLangfuseClient() -> Any:
    """延迟导入 Langfuse 客户端，避免环境变量尚未加载时初始化失败。"""

    return Langfuse(timeout=LANGFUSE_PROMPT_SYNC_TIMEOUT_SECONDS)


def _loadProjectEnv() -> None:
    """加载项目根目录 .env，确保脚本入口可用。"""

    load_dotenv(PROJECT_ROOT / ".env")
