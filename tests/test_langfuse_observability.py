"""Langfuse 观测配置测试。"""

from __future__ import annotations

from typing import Any

from common import langfuse_observability
from common.langfuse_observability import buildLangfuseRunnableConfig, isLangfuseEnabled


def testBuildLangfuseRunnableConfigShouldKeepThreadWhenDisabled(monkeypatch: Any) -> None:
    """未配置 Langfuse 时，应保留 LangGraph thread_id 且不注入 callback。"""

    for name in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL"):
        monkeypatch.delenv(name, raising=False)

    config = buildLangfuseRunnableConfig(
        conversationId="c1",
        baseConfig={"configurable": {"thread_id": "c1"}},
    )

    assert not isLangfuseEnabled()
    assert config["configurable"]["thread_id"] == "c1"
    assert "callbacks" not in config
    assert config["metadata"]["langfuse_session_id"] == "c1"


def testBuildLangfuseRunnableConfigShouldAppendHandlerWhenEnabled(monkeypatch: Any) -> None:
    """配置完整时，应注入 Langfuse callback 和 session metadata。"""

    handler = object()
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "http://127.0.0.1:3000")
    monkeypatch.setattr(langfuse_observability, "createLangfuseHandler", lambda: handler)

    config = buildLangfuseRunnableConfig(
        conversationId="c1",
        baseConfig={"configurable": {"thread_id": "c1"}},
        tags=["online-chat"],
        metadata={"mode": "online-chat"},
    )

    assert isLangfuseEnabled()
    assert config["callbacks"] == [handler]
    assert config["metadata"]["conversationId"] == "c1"
    assert config["metadata"]["langfuse_session_id"] == "c1"
    assert "online-chat" in config["metadata"]["langfuse_tags"]
