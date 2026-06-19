# 流式输出异常排障记录

## 背景

在在线聊天场景中，用户发送问题后，前端出现两类异常：

1. 检索过程中页面长时间停住，用户消息气泡和“正在检索知识库”状态没有及时出现。
2. 后端流式输出中混入了模型的思考过程、工具调用轨迹，甚至把内部分析文本当成了可见正文。

这类问题在引入 `query rewrite` 和 `rerank` 后变得更明显，因为整条链路会多次调用模型，LangGraph 的内部事件也更容易被误当成最终输出。

## 排查链路

本次排查按下面的链路逐层定位：

`路由 -> 应用服务 -> RAG Chat Service -> 检索编排 -> LangGraph Agent -> 模型流式事件 -> 前端 SSE`

### 1. 路由层

先从 `POST /api/chat/stream` 入手，确认 FastAPI 只是把 `ChatApplicationService.streamConversation(...)` 包成 `StreamingResponse`，本身不做内容处理。

### 2. 应用服务层

继续看 `application/chat_service.py`，确认 SSE 事件是在这里统一组装的：

- `start`
- `delta`
- `done`
- `error`

这里能说明，前端看到的内容不是随机拼出来的，而是后端生成器逐段吐出的结果。

### 3. RAG Chat Service 层

接着检查 `agents/rag/rag_chat_service.py`。

最初的实现是直接消费 LangGraph 的 `stream(..., stream_mode="messages")` 结果，再把事件里的文本块转成 SSE `delta`。

这个做法的问题是：

- `messages` mode 会暴露 LangGraph 图里每个 LLM 调用的增量消息。
- 在 Agent 场景下，工具调用、推理过程、检索相关中间消息都可能进入同一条流。
- 前端没有能力区分“最终正文”和“内部推理”，只能按收到的文本直接渲染。

### 4. 检索编排层

再看 `agents/rag/rag_retrieval.py`。

引入 `query rewrite` 和 `rerank` 后，检索链路会变成：

`原始问题 -> query rewrite -> hybrid retrieve -> RRF -> rerank -> 最终上下文`

这会增加模型和外部服务调用次数，也会放大 Agent 流里出现内部文本的概率。

### 5. LangGraph 层

进一步打印原始流式事件后确认：

- `stream_mode="messages"` 会持续吐出 `langgraph_node=model`、`langgraph_node=tools` 等事件。
- 这些事件里既有工具调用轨迹，也有模型内部中间文本。
- 这不是前端渲染问题，而是“流式源头”本身就包含了不该展示给用户的内容。

## 根因

根因有两个，互相叠加：

1. 在线聊天流式出口直接接了 LangGraph 的内部 `messages` 流，导致 reasoning / tool call / 中间输出被透传。
2. 引入 `query rewrite` 和 `rerank` 后，Agent 的内部执行路径更复杂，放大了错误输出被前端接收的概率。

## 解决流程

### 第一步：验证最终回答是否存在

先调用 Agent 的非流式 `invoke`，确认模型本身能返回正常答案。

结果表明，最终答案是存在的，问题不在模型“不会答”，而在“流式出口拿错了内容”。

### 第二步：抓原始流事件

再直接打印 LangGraph 的流式事件，发现：

- `messages` mode 中会出现大量内部事件。
- 其中 `tools` 节点会吐出检索查询和文档片段。
- `model` 节点会先输出长段分析性文本，而不是适合前端直接展示的最终正文。

### 第三步：重构流式出口

将在线聊天的 `streamChat` 改为：

1. 先通过 `invoke` 拿到最终回答。
2. 只保留最后一条消息的正文。
3. 再把正文切片成 SSE `delta` 发送给前端。

这样可以保证：

- reasoning 不会再进入前端。
- 工具内部消息不会再进入前端。
- 前端仍然保留流式体验。

### 第四步：补充降级开关

新增在线聊天专用降级开关：

- 默认开启 `query rewrite` 和 `rerank`
- 生产问题发生时，可临时关闭在线聊天增强检索
- 只影响 `POST /api/chat/stream`
- 不影响离线评测和批处理

这样可以把“稳定性兜底”从代码逻辑里拆出来，避免为了临时修复不断引入硬编码分支。

### 第五步：补测试和回归验证

补充测试覆盖：

- 清洗后的消息内容不应包含 `<think>`
- 在线聊天流式输出只应包含最终正文
- 降级开关应只影响在线聊天链路
- 现有 API / 检索测试保持通过

## 最终方案

当前采用的方案是：

- 在线聊天保留默认增强检索能力。
- 需要兜底时，使用环境变量关闭在线聊天增强检索。
- 后端流式接口只输出最终正文，不透传内部 reasoning。
- 前端只负责渲染稳定的阶段态和最终回答。

## 经验教训

1. `LangGraph` 的 `messages` 流不是“最终答案流”，不能直接拿去做 SSE 展示。
2. 当 Agent 引入工具和多步检索后，必须区分“内部过程”和“用户可见正文”。
3. 在线问题排查时，优先沿着 `路由 -> 应用服务 -> Agent -> LangGraph -> 模型事件` 顺着查，能更快定位到底是哪一层在污染输出。
