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

from common.langfuse_observability import buildLangfuseRunnableConfig
from common.langfuse_prompts import getRagSystemPrompt, syncRagSystemPromptToLangfuse
from common.rag_assets import RagAssets
from common.message_content import normalizeMessageContent, stripThinkingContent
from agents.rag.model_factory import createChatModel
from agents.rag.rag_retrieval import RagRetrievalPipeline
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
        rewriteModel = createChatModel(
            config=config,
            temperature=0.0,
            timeoutSeconds=config.queryRewriteTimeoutSeconds,
            maxRetries=1,
        )
        self._retrieval = RagRetrievalPipeline(
            config=config,
            rewriteModel=rewriteModel,
            vectorStore=vectorStore,
        )
        self._onlineChatRetrievalEnhancedEnabled = config.onlineChatRetrievalEnhancedEnabled
        self._checkpointerContext = PostgresSaver.from_conn_string(_requireDatabaseUrl())
        self._checkpointer = self._checkpointerContext.__enter__()
        self._checkpointer.setup()
        self._storeContext = PostgresStore.from_conn_string(_requireDatabaseUrl())
        self._store = self._storeContext.__enter__()
        self._store.setup()
        atexit.register(self._closeMemoryResources)
        syncRagSystemPromptToLangfuse()

        @tool(description=RagAssets.SEARCH_KNOWLEDGE_BASE_TOOL_DESCRIPTION)
        def searchKnowledgeBase(query: str) -> str:
            return self.formatRetrievedContexts(query)

        @tool(description=RagAssets.GET_USER_PROFILE_TOOL_DESCRIPTION)
        def getUserProfile(runtime: ToolRuntime[AgentContext]) -> str:
            if runtime.store is None:
                return "未找到用户画像。"
            item = runtime.store.get(USER_PROFILE_NAMESPACE, runtime.context.userId)
            if item is None:
                return "未找到用户画像。"
            profile = str(item.value.get("profile", "")).strip()
            return profile or "未找到用户画像。"

        @tool(description=RagAssets.UPDATE_USER_PROFILE_TOOL_DESCRIPTION)
        def updateUserProfile(memory: str, runtime: ToolRuntime[AgentContext]) -> str:
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
            timeoutSeconds=config.chatModelTimeoutSeconds,
        )
        summaryModel = createChatModel(
            config=config,
            temperature=0,
            timeoutSeconds=config.chatModelTimeoutSeconds,
        )
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
        """以流式方式执行问答，并逐段产出最终回答文本。

        当前在线聊天采用“先检索、再一次性生成、再切片输出”的稳定路径，
        避免把 LangGraph 内部的工具调用、推理过程或无效中间块直接暴露给前端。
        """

        LOGGER.info("在线聊天开始：conversationId=%s, userId=%s", conversationId, userId)
        result = cast(
            Any,
            self._agent.invoke(
                cast(dict[str, Any], {"messages": [{"role": "user", "content": query}]}),
                config=self._buildConversationConfig(
                    conversationId,
                    tags=["online-chat"],
                    metadata={"mode": "online-chat"},
                ),
                context=AgentContext(userId=userId),
            ),
        )
        messages = result.get("messages", [])
        if not messages:
            LOGGER.warning("在线聊天未生成回答：conversationId=%s, query=%s", conversationId, query)
            return
        finalMessage = messages[-1]
        if not isinstance(finalMessage, BaseMessage):
            LOGGER.warning(
                "在线聊天最终消息类型异常：conversationId=%s, messageType=%s",
                conversationId,
                type(finalMessage).__name__,
            )
            return

        finalAnswer = normalizeMessageContent(finalMessage.content).strip()
        if not finalAnswer:
            LOGGER.warning("在线聊天最终回答为空：conversationId=%s, query=%s", conversationId, query)
            return

        for textChunk in _splitStreamChunks(finalAnswer):
            visibleChunks, _ = _extractVisibleTextChunks(textChunk, False)
            for visibleChunk in visibleChunks:
                if visibleChunk:
                    yield visibleChunk
        LOGGER.info(
            "在线聊天完成：conversationId=%s, answerLength=%s",
            conversationId,
            len(finalAnswer),
        )

    def answerWithContexts(
        self,
        query: str,
        userId: str = "default-user",
        traceMetadata: dict[str, object] | None = None,
    ) -> RagAnswer:
        """执行一次问答，并返回回答及对应检索上下文。"""

        retrievedContexts = self.retrieveContexts(query, useEnhancements=True)
        conversationId = f"eval-{uuid4()}"
        metadata = {
            "mode": "eval",
            "retrieved_context_count": str(len(retrievedContexts)),
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

    def retrieveContexts(
        self,
        query: str,
        useEnhancements: bool | None = None,
    ) -> list[str]:
        """检索与问题相关的上下文，供评测与调试复用。"""

        retrievalResult = self._retrieval.retrieveDocuments(
            query,
            useEnhancements=self._resolveUseEnhancements(useEnhancements),
        )
        documents = retrievalResult.documents
        return [
            _formatDocumentContext(index, document)
            for index, document in enumerate(documents, start=1)
        ]

    def formatRetrievedContexts(
        self,
        query: str,
        useEnhancements: bool | None = None,
    ) -> str:
        """把检索结果整理为工具可消费的文本，避免重复格式化逻辑。"""

        retrievedContexts = self.retrieveContexts(query, useEnhancements=useEnhancements)
        if not retrievedContexts:
            return "未找到相关文档。"
        return "\n\n".join(retrievedContexts)

    def isOnlineChatRetrievalEnhancedEnabled(self) -> bool:
        """返回在线聊天是否启用增强检索。"""

        return self._onlineChatRetrievalEnhancedEnabled

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

    def _resolveUseEnhancements(self, useEnhancements: bool | None) -> bool:
        """解析当前调用应使用的检索模式。"""

        if useEnhancements is None:
            return self._onlineChatRetrievalEnhancedEnabled
        return useEnhancements


@lru_cache(maxsize=1)
def getRagChatService() -> RagChatService:
    """复用单例 Agent，避免每次请求重复初始化向量检索链。"""

    return RagChatService()


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

    contentBlocks = getattr(message, "content_blocks", None)
    if isinstance(contentBlocks, list) and contentBlocks:
        extractedChunks: list[str] = []
        for block in contentBlocks:
            blockType: str | None = None
            blockText = ""
            if isinstance(block, dict):
                blockType = str(block.get("type", "")) if block.get("type") is not None else None
                blockText = str(block.get("text", ""))
            else:
                blockType = str(getattr(block, "type", "")) if getattr(block, "type", None) else None
                blockText = str(getattr(block, "text", ""))
            if blockType == "reasoning":
                continue
            if blockType == "text":
                extractedChunks.append(blockText)
        if extractedChunks:
            return extractedChunks
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


def _extractVisibleTextChunks(textChunk: str, inThinkingBlock: bool) -> tuple[list[str], bool]:
    """从文本片段中移除 `<think>` 推理段落，保留可见回答。"""

    normalizedChunk = stripThinkingContent(textChunk)
    if "<think>" not in textChunk and "</think>" not in textChunk:
        if inThinkingBlock:
            closingIndex = textChunk.find("</think>")
            if closingIndex == -1:
                return [], True
            remainingText = textChunk[closingIndex + len("</think>") :]
            return ([remainingText] if remainingText else []), False
        return ([normalizedChunk] if normalizedChunk else []), False

    visibleChunks: list[str] = []
    remainingText = textChunk
    while remainingText:
        if inThinkingBlock:
            closingIndex = remainingText.find("</think>")
            if closingIndex == -1:
                return visibleChunks, True
            remainingText = remainingText[closingIndex + len("</think>") :]
            inThinkingBlock = False
            continue
        openingIndex = remainingText.find("<think>")
        if openingIndex == -1:
            visibleText = stripThinkingContent(remainingText)
            if visibleText:
                visibleChunks.append(visibleText)
            return visibleChunks, False
        if openingIndex > 0:
            visibleText = stripThinkingContent(remainingText[:openingIndex])
            if visibleText:
                visibleChunks.append(visibleText)
        remainingText = remainingText[openingIndex + len("<think>") :]
        inThinkingBlock = True
    return visibleChunks, inThinkingBlock


def _splitStreamChunks(text: str, maxChunkSize: int = 120) -> list[str]:
    """把最终正文切成适合 SSE 逐段发送的片段。

    在线聊天先等待模型完成，再把结果切片输出，这样可以保留 markdown 结构，
    同时避免前端直接接收到工具调用和推理块。
    """

    if not text:
        return []
    chunks: list[str] = []
    for line in text.splitlines(keepends=True):
        if len(line) <= maxChunkSize:
            chunks.append(line)
            continue
        chunks.extend(line[index : index + maxChunkSize] for index in range(0, len(line), maxChunkSize))
    return chunks


def _formatDocumentContext(index: int, document: Document) -> str:
    """统一整理检索文档文本，保证问答与评测看到相同上下文。"""

    source = document.metadata.get("source", "未知来源")
    return f"文档 {index}\n来源: {source}\n内容: {document.page_content}"


def _requireDatabaseUrl() -> str:
    """读取 LangGraph memory 的 PostgreSQL 连接串。"""

    databaseUrl = os.getenv("DATABASE_URL", "").strip()
    if not databaseUrl:
        raise ValueError("缺少 DATABASE_URL，请检查 PostgreSQL 配置。")
    return databaseUrl
