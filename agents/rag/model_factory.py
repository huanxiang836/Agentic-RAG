"""集中创建 RAG 运行时使用的聊天与评测模型。"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from knowledge.ingest.config import AppConfig


def createChatModel(
    config: AppConfig,
    temperature: float,
    timeoutSeconds: float = 30,
    maxRetries: int = 3,
    modelName: str | None = None,
) -> ChatOpenAI:
    """创建对话模型，统一收口 base URL、Key 与超时配置。"""

    return ChatOpenAI(
        model=modelName or config.chatModel,
        api_key=config.siliconflowApiKey,
        base_url=config.siliconflowBaseUrl.rstrip("/"),
        timeout=timeoutSeconds,
        max_retries=maxRetries,
        temperature=temperature,
    )


def createJudgeModel(config: AppConfig) -> ChatOpenAI:
    """创建用于评测与 judge 的模型实例。"""

    return createChatModel(
        config=config,
        temperature=0.0,
        timeoutSeconds=config.judgeModelTimeoutSeconds,
        maxRetries=3,
        modelName=config.judgeModel,
    )
