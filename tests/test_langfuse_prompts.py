"""Langfuse Prompt 管理测试。"""

# pylint: disable=invalid-name,too-few-public-methods

from __future__ import annotations

from typing import Any

from common import langfuse_prompts
from common.langfuse_prompts import (
    DEFAULT_RAG_SYSTEM_PROMPT,
    getRagSystemPrompt,
    syncRagSystemPromptToLangfuse,
)


class FakePromptVersion:
    """模拟 Langfuse Prompt 版本。"""

    def __init__(self, prompt: str) -> None:
        self.prompt = prompt


class FakePromptsApi:  # pylint: disable=too-few-public-methods,invalid-name
    """模拟 Langfuse Prompt API。"""

    def __init__(self, prompt: str | None) -> None:
        self._prompt = prompt
        self.createdPrompts: list[dict[str, object]] = []

    def get(self, *_args: Any, **_kwargs: Any) -> FakePromptVersion:
        """返回已存在的 Prompt 或抛错。"""

        if self._prompt is None:
            raise RuntimeError("prompt not found")
        return FakePromptVersion(self._prompt)

    def create(self, **kwargs: object) -> object:
        """记录新建 Prompt。"""

        self.createdPrompts.append(kwargs)
        self._prompt = str(kwargs.get("prompt", ""))
        return object()


class FakeLangfuseClient:  # pylint: disable=invalid-name
    """模拟 Langfuse 客户端。"""

    def __init__(self, prompt: str | None) -> None:
        self.prompts = FakePromptsApi(prompt)

    def get_prompt(self, *_args: Any, **_kwargs: Any) -> FakePromptVersion:
        """直接返回 Prompt 版本。"""

        return self.prompts.get()

    def create_prompt(self, **kwargs: object) -> object:
        """直接创建 Prompt。"""

        return self.prompts.create(**kwargs)


def testGetRagSystemPromptShouldReturnDefaultWhenDisabled(monkeypatch: Any) -> None:
    """未配置 Langfuse 时，应回退到本地默认 Prompt。"""

    for name in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL"):
        monkeypatch.delenv(name, raising=False)

    assert getRagSystemPrompt() == DEFAULT_RAG_SYSTEM_PROMPT


def testSyncRagSystemPromptShouldCreatePromptWhenMissing(monkeypatch: Any) -> None:
    """Langfuse 中没有 Prompt 时，应创建 production 版本。"""

    fakeClient = FakeLangfuseClient(prompt=None)
    _setLangfuseEnv(monkeypatch)
    monkeypatch.setattr(langfuse_prompts, "_getLangfuseClient", lambda: fakeClient)

    synced = syncRagSystemPromptToLangfuse()

    assert synced is True
    createdPrompt = fakeClient.prompts.createdPrompts[0]
    assert createdPrompt["name"] == "rag-system-prompt"
    assert createdPrompt["labels"] == ["production"]
    assert createdPrompt["prompt"] == DEFAULT_RAG_SYSTEM_PROMPT


def testSyncRagSystemPromptShouldSkipWhenAlreadySynced(monkeypatch: Any) -> None:
    """Langfuse 中已存在相同 Prompt 时，不应重复创建版本。"""

    fakeClient = FakeLangfuseClient(prompt=DEFAULT_RAG_SYSTEM_PROMPT)
    _setLangfuseEnv(monkeypatch)
    monkeypatch.setattr(langfuse_prompts, "_getLangfuseClient", lambda: fakeClient)

    synced = syncRagSystemPromptToLangfuse()

    assert synced is False
    assert not fakeClient.prompts.createdPrompts


def _setLangfuseEnv(monkeypatch: Any) -> None:
    """设置测试用 Langfuse 环境变量。"""

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "http://127.0.0.1:3000")
