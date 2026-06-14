# 项目架构说明

## 当前阶段

项目当前已经从“FastAPI 挂一个静态页面”升级为“前后端分离的 AI Chat 应用”。

当前主链路包括：

- Markdown 知识库入库
- Milvus 检索
- 基于 LangChain Agent 的问答
- LangGraph PostgreSQL 短期记忆
- FastAPI 会话接口、删除接口与 SSE 聊天流
- React 多会话聊天前端
- 检索文档气泡、Markdown 渲染、代码块高亮、回答完成后的操作栏

## 当前结构

```text
api/
  main.py                  FastAPI 入口
  schemas.py               API 请求响应模型

application/
  chat_service.py          会话编排、SSE 输出、标题更新、删除编排

agents/
  rag/
    rag_chat_service.py    Agent、Retriever、LangGraph memory 接入

knowledge/
  ingest/                  Markdown 入库链路

persistence/
  base.py                  SQLAlchemy Base
  db.py                    PostgreSQL engine / session
  models.py                会话元数据模型
  repository.py            会话元数据仓储

evals/
  dataset_builder.py       ragas 数据集构建
  ragas_evaluator.py       ragas 评测执行

bot-web/
  src/
    pages/                 React 聊天页面
    api.ts                 前端 API 与 SSE 调用
    styles.css             页面样式

data/
  md/                      知识库 Markdown
  evaluate/                评测数据
```

## 分层职责

### api

只负责：

- HTTP 路由
- `Result` 响应封装
- SSE 输出
- CORS 配置

不承担 Agent 或记忆实现细节。

### application

负责聊天用例编排：

- 创建会话
- 查询会话列表
- 查询会话详情
- 删除会话
- 调用 Agent 流式输出
- 更新会话标题与更新时间

### agents

负责 Agent 运行时：

- 创建聊天模型
- 接入知识库检索工具
- 接入 `PostgresSaver`
- 基于 `thread_id` 提供会话级短期记忆
- 返回流式文本片段

### persistence

负责业务元数据持久化：

- PostgreSQL 连接
- 会话元数据表
- 会话仓储

说明：

- 消息正文不单独建业务消息表
- 会话历史由 LangGraph checkpointer 保存
- 业务库只存会话元数据
- 删除会话时同时删除元数据和 LangGraph thread checkpoint

### bot-web

负责前端多会话体验：

- 左侧会话 sidebar
- 右侧聊天主区域
- SSE 实时渲染
- 检索文档气泡
- Markdown 渲染
- 代码块高亮
- 回答完成后的免责声明与交互栏
- 刷新后恢复历史消息

## 当前关键约束

- 前端与 FastAPI 分开启动
- FastAPI 不再托管静态页面
- 聊天接口统一走 `POST /api/chat/stream`
- 会话 CRUD 继续使用统一 `Result`
- 记忆只做短期记忆，使用 LangGraph 官方 PostgreSQL checkpointer
- PostgreSQL 不可用时不做 SQLite、内存或 mock 降级

## 下一步方向

后续如果继续演进，优先顺序建议为：

1. 把 `rag_chat_service.py` 继续拆分为 retriever、tools、prompts、memory
2. 增加长期记忆或语义 memory
3. 引入 rerank、query rewrite、context compression
4. 增加 LangGraph 更复杂的多 Agent 编排
5. 继续细化前端消息卡片、文档气泡和代码块展示
