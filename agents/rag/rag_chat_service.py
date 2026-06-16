"""负责创建并调用 RAG Agent。"""

from __future__ import annotations

import atexit
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
import logging
import os
from typing import Any, Iterator, cast
from uuid import uuid4

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware, before_model
from langchain.agents.middleware.types import AgentState
from langchain.tools import tool
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.prebuilt import ToolRuntime
from langgraph.runtime import Runtime
from langgraph.store.postgres import PostgresStore
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from common.langfuse_observability import buildLangfuseRunnableConfig
from common.langfuse_prompts import getRagSystemPrompt, syncRagSystemPromptToLangfuse
from common.message_content import normalizeMessageContent
from knowledge.ingest.config import AppConfig
from knowledge.ingest.vector_store import (
    createEmbeddings,
    openMilvusVectorStore,
    validateEmbeddingDimension,
)


LOGGER = logging.getLogger(__name__)
SHORT_MEMORY_TRIGGER_MESSAGES = 12
SHORT_MEMORY_KEEP_MESSAGES = 6
MODEL_WINDOW_KEEP_MESSAGES = 8
USER_PROFILE_NAMESPACE = ("users",)
CHAT_MODEL_TIMEOUT_SECONDS = 180


@dataclass(frozen=True)
class AgentContext:
    """携带运行期用户信息，供 LangGraph Store 做跨会话记忆隔离。"""

    userId: str


@dataclass(frozen=True)
class RagAnswer:
    """封装一次 RAG 问答的回答与检索上下文，供评测等场景复用。"""

    answer: str
    retrievedContexts: list[str]


class RagChatService:  # pylint: disable=too-few-public-methods
    """对外提供统一问答入口，避免 API 层直接处理 Agent 细节。"""

    def __init__(self) -> None:
        load_dotenv()
        config = AppConfig.fromEnv()
        embeddings = createEmbeddings(config)
        validateEmbeddingDimension(config, embeddings)
        vectorStore = openMilvusVectorStore(config, embeddings)
        self._checkpointerContext = PostgresSaver.from_conn_string(_requireDatabaseUrl())
        self._checkpointer = self._checkpointerContext.__enter__()
        self._checkpointer.setup()
        self._storeContext = PostgresStore.from_conn_string(_requireDatabaseUrl())
        self._store = self._storeContext.__enter__()
        self._store.setup()
        atexit.register(self._closeMemoryResources)
        self._retriever = vectorStore.as_retriever(search_type="similarity", search_kwargs={"k": 3})
        syncRagSystemPromptToLangfuse()

        @tool
        def searchKnowledgeBase(query: str) -> str:
            """搜索知识库，获取与当前问题相关的资料。"""

            return self.formatRetrievedContexts(query)

        @tool
        def getUserProfile(runtime: ToolRuntime[AgentContext]) -> str:
            """读取当前用户的长期画像。"""

            if runtime.store is None:
                return "未找到用户画像。"
            item = runtime.store.get(USER_PROFILE_NAMESPACE, runtime.context.userId)
            if item is None:
                return "未找到用户画像。"
            profile = str(item.value.get("profile", "")).strip()
            return profile or "未找到用户画像。"

        @tool
        def updateUserProfile(memory: str, runtime: ToolRuntime[AgentContext]) -> str:
            """当用户明确表达长期偏好、身份或约束时，更新用户画像。"""

            if runtime.store is None:
                return "用户画像更新失败：Store 未初始化。"
            runtime.store.put(
                USER_PROFILE_NAMESPACE,
                runtime.context.userId,
                {
                    "profile": memory.strip(),
                    "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                },
            )
            return "用户画像已更新。"

        model = createChatModel(
            config=config,
            temperature=0.2,
            timeoutSeconds=CHAT_MODEL_TIMEOUT_SECONDS,
        )
        summaryModel = createChatModel(config=config, temperature=0)
        self._agent = create_agent(
            model=model,
            tools=[searchKnowledgeBase, getUserProfile, updateUserProfile],
            middleware=[
                SummarizationMiddleware(
                    model=summaryModel,
                    trigger=("messages", SHORT_MEMORY_TRIGGER_MESSAGES),
                    keep=("messages", SHORT_MEMORY_KEEP_MESSAGES),
                ),
                trimModelMessages,
            ],
            context_schema=AgentContext,
            checkpointer=self._checkpointer,
            store=self._store,
            system_prompt=getRagSystemPrompt(),
        )

    def streamChat(self, userId: str, conversationId: str, query: str) -> Iterator[str]:
        """以流式方式执行问答，并逐段产出回答文本。"""
        for event in cast(Any, self._agent).stream(
            cast(dict[str, Any], {"messages": [{"role": "user", "content": query}]}),
            config=self._buildConversationConfig(
                conversationId,
                tags=["online-chat"],
                metadata={"mode": "online-chat"},
            ),
            context=AgentContext(userId=userId),
            stream_mode="messages",
            version="v2",
        ):
            if not isinstance(event, dict) or event.get("type") != "messages":
                continue
            rawData = event.get("data")
            if not isinstance(rawData, tuple) or len(rawData) != 2:
                continue
            messageChunk, metadata = rawData
            if not isinstance(metadata, dict) or metadata.get("langgraph_node") != "model":
                continue
            if not isinstance(messageChunk, BaseMessage):
                continue
            for textChunk in _extractMessageTextChunks(messageChunk):
                if textChunk:
                    yield textChunk

    def answerWithContexts(
        self,
        query: str,
        userId: str = "default-user",
        traceMetadata: dict[str, object] | None = None,
    ) -> RagAnswer:
        """执行一次问答，并返回回答及对应检索上下文。"""

        retrievedContexts = self.retrieveContexts(query)
        conversationId = f"eval-{uuid4()}"
        metadata = {
            "mode": "eval",
            "retrieved_context_count": len(retrievedContexts),
            **(traceMetadata or {}),
        }
        result = cast(Any, self._agent).invoke(
            cast(dict[str, Any], {"messages": [{"role": "user", "content": query}]}),
            config=self._buildConversationConfig(
                conversationId,
                tags=["eval"],
                metadata=metadata,
            ),
            context=AgentContext(userId=userId),
        )
        messages = result.get("messages", [])
        if not messages:
            LOGGER.warning("问题未生成回答，将返回默认文案。query=%s", query)
            return RagAnswer(answer="未生成回答。", retrievedContexts=retrievedContexts)
        return RagAnswer(
            answer=normalizeMessageContent(messages[-1].content),
            retrievedContexts=retrievedContexts,
        )

    def getConversationMessages(self, conversationId: str) -> list[BaseMessage]:
        """读取指定会话的历史消息。"""

        state = self._agent.get_state(self._buildConversationConfig(conversationId))
        messages = state.values.get("messages", [])
        return [message for message in messages if isinstance(message, BaseMessage)]

    def deleteConversation(self, conversationId: str) -> None:
        """删除指定会话的全部线程状态。"""

        self._checkpointer.delete_thread(conversationId)

    def retrieveContexts(self, query: str) -> list[str]:
        """检索与问题相关的上下文，供评测与调试复用。"""

        documents = self._retriever.invoke(query)
        return [
            _formatDocumentContext(index, document)
            for index, document in enumerate(documents, start=1)
        ]

    def formatRetrievedContexts(self, query: str) -> str:
        """把检索结果整理为工具可消费的文本，避免重复格式化逻辑。"""

        retrievedContexts = self.retrieveContexts(query)
        if not retrievedContexts:
            return "未找到相关文档。"
        return "\n\n".join(retrievedContexts)

    def _buildConversationConfig(
        self,
        conversationId: str,
        tags: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> RunnableConfig:
        """统一构造 LangGraph 线程配置。"""

        return buildLangfuseRunnableConfig(
            conversationId=conversationId,
            baseConfig=cast(RunnableConfig, {"configurable": {"thread_id": conversationId}}),
            tags=tags,
            metadata=metadata,
        )

    def _closeMemoryResources(self) -> None:
        """在进程结束时关闭 PostgreSQL memory 资源。"""

        self._checkpointerContext.__exit__(None, None, None)
        self._storeContext.__exit__(None, None, None)


@lru_cache(maxsize=1)
def getRagChatService() -> RagChatService:
    """复用单例 Agent，避免每次请求重复初始化向量检索链。"""

    return RagChatService()


def createChatModel(
    config: AppConfig,
    temperature: float,
    timeoutSeconds: float = 30,
    maxRetries: int = 3,
) -> ChatOpenAI:
    """按项目统一配置创建聊天模型，避免问答与评测参数漂移。"""

    return ChatOpenAI(
        model=config.chatModel,
        api_key=SecretStr(_requireChatApiKey()),
        base_url=_resolveChatBaseUrl(),
        timeout=timeoutSeconds,
        max_retries=maxRetries,
        temperature=temperature,
    )


@before_model
def trimModelMessages(
    state: AgentState,
    runtime: Runtime[AgentContext],
) -> dict[str, list[BaseMessage | RemoveMessage]] | None:
    """限制每次模型调用看到的最近消息，避免长会话上下文持续膨胀。"""

    _ = runtime
    messages = [
        message for message in state.get("messages", []) if isinstance(message, BaseMessage)
    ]
    if len(messages) <= MODEL_WINDOW_KEEP_MESSAGES:
        return None
    return {
        "messages": [
            RemoveMessage(id=REMOVE_ALL_MESSAGES),
            *messages[-MODEL_WINDOW_KEEP_MESSAGES:],
        ]
    }


def _extractMessageTextChunks(message: BaseMessage | Any) -> list[str]:
    """从流式消息块中提取可直接返回给前端的文本片段。"""

    content = message.content
    if isinstance(content, str):
        return [content] if content else []
    if not isinstance(content, list):
        return [str(content)] if content else []
    extractedChunks: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            extractedChunks.append(str(item))
            continue
        if item.get("type") == "text":
            text = str(item.get("text", ""))
            if text:
                extractedChunks.append(text)
    return extractedChunks


def _formatDocumentContext(index: int, document: Document) -> str:
    """统一整理检索文档文本，保证问答与评测看到相同上下文。"""

    source = document.metadata.get("source", "未知来源")
    return f"文档 {index}\n来源: {source}\n内容: {document.page_content}"


def _requireChatApiKey() -> str:
    """按聊天模型实际调用地址选择兼容的 API Key。"""

    baseUrl = _resolveChatBaseUrl()
    if "dashscope.aliyuncs.com" in baseUrl:
        apiKey = os.getenv("DASHSCOPE_API_KEY", "").strip()
    else:
        apiKey = os.getenv("OPENAI_API_KEY", "").strip()
    if not apiKey:
        raise ValueError("缺少聊天模型 API Key，请检查 OPENAI_API_KEY 或 DASHSCOPE_API_KEY。")
    return apiKey


def _requireDatabaseUrl() -> str:
    """读取 LangGraph memory 的 PostgreSQL 连接串。"""

    databaseUrl = os.getenv("DATABASE_URL", "").strip()
    if not databaseUrl:
        raise ValueError("缺少 DATABASE_URL，请检查 PostgreSQL 配置。")
    return databaseUrl


def _resolveChatBaseUrl() -> str:
    """优先读取聊天模型专用地址，避免和 Embedding 服务混用。"""

    rawBaseUrl = os.getenv("OPENAI_API_BASE", "").strip()
    if not rawBaseUrl:
        rawBaseUrl = os.getenv("DASHSCOPE_BASE_URL", "").strip()
    if not rawBaseUrl:
        rawBaseUrl = os.getenv("OPENAI_BASE_URL", "").strip()
    if not rawBaseUrl:
        raise ValueError("缺少聊天模型 Base URL，请设置 OPENAI_API_BASE 或 DASHSCOPE_BASE_URL。")
    return rawBaseUrl.rstrip("/")
