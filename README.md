# Agentic RAG

一个基于 LangChain、LangGraph、Milvus、FastAPI 和 React 的中文 Agentic RAG 示例项目。

项目当前已经落地一条可实际联调的主链路：Markdown 知识库入库、向量检索、带 PostgreSQL 短期记忆的 Agent 问答、SSE 流式聊天、React AI Chat 前端，以及 `ragas` 离线评测。

## 项目目标

- 基于本地 Markdown 文档构建知识库。
- 使用 Milvus 存储向量并完成相似度检索。
- 使用 LangChain Agent 将检索能力作为工具接入问答流程。
- 使用 LangGraph PostgreSQL memory 维护会话级短期记忆，并通过 Store 保存用户画像。
- 通过 FastAPI 提供会话接口、删除接口与 SSE 聊天流。
- 通过 React 前端提供多会话聊天界面、Markdown 渲染、代码块高亮和检索文档气泡。
- 使用手工整理的 `ragas` 评测数据集执行离线 RAG 效果评测。

## 当前特性

- 支持扫描 `data/md/` 下的 Markdown 文档并完成清洗、切分、向量化和写入 Milvus。
- 支持基于知识库的多轮中文问答。
- 支持查询改写、Milvus 原生 BM25 混合召回、RRF 融合和专用 rerank 的检索链路。
- 支持独立 React 前端与 FastAPI 分离部署。
- 支持 PostgreSQL 持久化会话元数据与 LangGraph thread memory。
- 支持固定 `userId=default-user` 的用户维度隔离，后续可替换为登录态用户。
- 支持短期记忆压缩、滑动窗口和跨会话用户画像。
- 支持会话删除，删除时同时清理会话元数据与 LangGraph checkpoint。
- 支持流式回答、Markdown 渲染、代码块高亮、知识库检索文档气泡，以及回答完成后的交互栏。
- 支持在线聊天专用降级开关，必要时可临时关闭 query rewrite / rerank，保留基础召回链路。
- 流式输出只透传最终正文，后端会过滤 reasoning / `<think>` 等内部推理内容，避免前端渲染乱序。
- 支持基于静态 `ragas` 评测数据集执行离线评测。
- 支持基于 `ragas` 计算 `faithfulness`、`context_recall` 等指标。

## 项目结构

```text
api/
  main.py                  FastAPI 入口
  schemas.py               请求和统一响应模型

application/
  chat_service.py          会话编排与 SSE 聊天入口

agents/
  rag/
    rag_chat_service.py    RAG Agent、Retriever、LangGraph memory/store

knowledge/
  ingest/
    config.py              环境变量和运行配置
    document_load.py       Markdown 发现与加载
    document_clean.py      文档清洗
    document_chunk.py      文档切分
    vector_store.py        Embedding 与 Milvus 读写
    ingest_markdown.py     知识库入库入口

evals/
  ragas_evaluator.py       ragas 评测执行

persistence/
  db.py                    PostgreSQL engine / session
  models.py                带 user_id 的会话元数据模型
  repository.py            会话元数据仓储

bot-web/
  src/                     React AI Chat 前端

data/
  md/                      知识库 Markdown 文档
  evaluate/                评测样本和生成结果

tests/                     测试代码
start_api.py               本地开发启动脚本
structure.md               当前架构说明
```

## 技术栈

- Python 3.8+
- FastAPI
- LangGraph
- LangChain
- langchain-openai
- langchain-milvus
- Milvus
- PostgreSQL
- React
- Vite
- `BAAI/bge-m3` Embedding
- Milvus `BM25BuiltInFunction`
- `自行在.env中配置`  ChatModel+RerankModel
- `ragas`

## 环境准备

### 1. 创建虚拟环境

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. 安装依赖

```powershell
pip install -r requirements.txt
```

### 3. 配置环境变量

项目通过 `.env` 读取运行配置。

最少需要配置以下变量：

```env
CHAT_MODEL=your_chat_model
CHAT_MODEL_TIMEOUT_SECONDS=180
JUDGE_MODEL=your_judge_model
JUDGE_MODEL_TIMEOUT_SECONDS=180
EMBEDDING_MODEL=BAAI/bge-m3
SILICONFLOW_API_KEY=your_siliconflow_api_key
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
RERANK_MODEL=BAAI/bge-reranker-v2-m3
RAG_ONLINE_CHAT_RETRIEVAL_ENHANCED_ENABLED=true
RAG_QUERY_REWRITE_ENABLED=true
RAG_QUERY_REWRITE_TIMEOUT_SECONDS=30
RAG_RERANK_ENABLED=true
RAG_RERANK_TIMEOUT_SECONDS=30
RAGAS_EVALUATION_TIMEOUT_SECONDS=600

MILVUS_HOST=127.0.0.1
MILVUS_PORT=19530
MILVUS_USERNAME=root
MILVUS_PASSWORD=Milvus
MILVUS_DATABASE=default
MILVUS_COLLECTION=agentic_rag
MILVUS_EMBEDDING_DIMENSION=1024

DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres?sslmode=disable
BOT_WEB_ORIGIN=http://127.0.0.1:5173,http://localhost:5173
```

说明：

- `EMBEDDING_MODEL` 当前被代码限制为 `BAAI/bge-m3`。
- `CHAT_MODEL` 直接读取 `.env`，项目不会再强制限定具体模型名。
- `JUDGE_MODEL` 专用于评测和 Langfuse 的 ragas judge，不和聊天模型混用。
- `SILICONFLOW_BASE_URL` 用于 Embedding、对话和 rerank 服务，内部会自动补齐 `/v1`。
- `SILICONFLOW_API_KEY` 用于 Embedding、对话和 rerank 服务。
- `RERANK_MODEL` 用于检索重排，当前默认 `BAAI/bge-reranker-v2-m3`。
- `RAG_ONLINE_CHAT_RETRIEVAL_ENHANCED_ENABLED` 用于控制在线聊天是否启用 query rewrite 和 rerank，默认开启，必要时可临时关闭作为兜底降级。
- `RAG_QUERY_REWRITE_ENABLED` 和 `RAG_RERANK_ENABLED` 用于控制检索链路是否启用 query rewrite / rerank。
- `RAGAS_EVALUATION_TIMEOUT_SECONDS` 控制 `ragas` 单轮评测的超时时间，默认 600 秒。
- 在线聊天降级开关只影响 `POST /api/chat/stream` 这条链路，不影响离线评测和批处理入口。

## 知识库入库

将 Markdown 文档放到 `data/md/` 下，然后执行：

```powershell
cd D:\PythonProject\Agentic RAG
.\.venv\Scripts\Activate.ps1
python -m knowledge.ingest.ingest_markdown
```

这条命令就是“文档向量化到数据库”的入口：它会读取 `data/md/` 下的 Markdown，清洗、切分、调用 `BAAI/bge-m3` 生成向量，并写入 `.env` 中 `MILVUS_COLLECTION` 指定的 Milvus collection。Milvus 侧同时会启用原生 `BM25BuiltInFunction`，因此文本检索不再依赖本地 BM25 索引。

入库流程包括：

1. 发现 Markdown 文件。
2. 加载文档并记录失败项。
3. 执行文档清洗，并输出部分预览日志。
4. 执行文档切分。
5. 生成向量并写入 Milvus。

当前写入策略会重建目标 Milvus collection，适合项目初期反复调整切分和 embedding 参数。重新执行该命令会覆盖旧的向量数据。

## PostgreSQL 表说明

当前 PostgreSQL 主要保存聊天会话元数据、LangGraph 短期记忆 checkpoint，以及 LangGraph Store 长期记忆。

| 表名 | 来源 | 用途 |
| --- | --- | --- |
| `chat_conversations` | 项目业务表 | 保存会话元数据，只存 `id`、`user_id`、标题和创建/更新时间，不保存消息正文。 |
| `checkpoints` | LangGraph `PostgresSaver` | 保存每个 `thread_id` 的 checkpoint 主记录，用于恢复同一会话的短期记忆状态。 |
| `checkpoint_blobs` | LangGraph `PostgresSaver` | 保存 checkpoint 中较大的序列化状态数据，例如消息列表和中间状态。 |
| `checkpoint_writes` | LangGraph `PostgresSaver` | 保存 LangGraph 每个节点/通道的写入记录，用于恢复图执行过程。 |
| `checkpoint_migrations` | LangGraph `PostgresSaver` | 记录 LangGraph checkpoint 表结构迁移版本，避免重复执行内部迁移。 |

说明：

- 这 4 张 `checkpoint_*` / `checkpoints` 表由 LangGraph 在 `checkpointer.setup()` 时自动创建和维护，业务代码不直接读写。
- 会话详情接口读取消息历史时走 LangGraph state，不查 `chat_messages`，因为项目没有单独建消息表。
- 长期用户画像由 LangGraph `PostgresStore` 管理，底层表也由 Store 初始化维护；当前项目只通过 Agent 工具读写用户画像。

## 启动后端

开发模式启动：

```powershell
.venv\Scripts\python start_api.py
```

指定端口启动：

```powershell
.venv\Scripts\python start_api.py 9000
```

启动后可访问：

- API 地址：`http://127.0.0.1:8000/`
- 聊天接口：`POST /api/chat/stream`
- 会话列表：`GET /api/conversations?userId=default-user`
- 会话创建：`POST /api/conversations`
- 会话删除：`DELETE /api/conversations/{conversationId}?userId=default-user`

当前聊天和会话接口都带 `userId`。前端先统一使用 `default-user`，后续接登录系统时由认证层提供真实用户 ID。

创建会话请求示例：

```json
{
  "userId": "default-user"
}
```

流式聊天请求示例：

```json
{
  "userId": "default-user",
  "conversationId": "会话 ID",
  "message": "你的问题"
}
```

## 启动前端

```powershell
cd bot-web
npm run dev
```

前端默认地址：

- 页面地址：`http://127.0.0.1:5173/`

## 评测

### 1. 执行 ragas 评测

当前只保留 `smoke` 档位：

- `smoke`：12 条，只跑 `context_recall` 和 `faithfulness`，适合日常快速验证。

直接运行命令：

```powershell
@'
from evals.ragas_evaluator import RagasEvaluator, loadEvaluationCases, selectEvaluationCases
from agents.rag.rag_chat_service import getRagChatService

cases = loadEvaluationCases("data/evaluate/ragas_eval_dataset.csv")
cases = selectEvaluationCases(cases)
report = RagasEvaluator(getRagChatService()).evaluateCases(cases)
print(report.metrics)
'@ | .venv\Scripts\python -
```

当前 `data/evaluate/ragas_eval_dataset.csv` 是一份手工整理的静态评测集，共 36 条，覆盖 A2A、Multi-agent、Context Engineering、Memory、Persistence、RAG、Workflow、Streaming、Cancellation、Human-in-the-loop 等核心主题。

当前接入的指标包括：

- `context_recall`
- `faithfulness`

也可以直接通过命令行运行：

```powershell
.venv\Scripts\python -m evals.ragas_evaluator
```

## 测试

运行测试：

```powershell
.venv\Scripts\python -m pytest tests -q
```

如果需要检查类型和代码规范：

```powershell
.venv\Scripts\python -m mypy agents api application knowledge evals tests
.venv\Scripts\python -m pylint agents api application knowledge evals tests
```

## 当前限制

- 当前用户体系只有固定 `default-user`，还没有登录、权限和多用户 UI。
- 长期记忆只保存简单用户画像，还没有语义检索、过期策略和用户可编辑入口。
- `rag_chat_service.py` 仍承担了较多职责，后续适合继续拆分为 tools、prompts、memory、retrieval。
- 当前评测流程以离线调用为主，尚未形成完整回归评测流水线。
- 当前前端的检索文档展示和代码识别依赖启发式解析，后续可以继续提高准确率。

## 问题排障

这次关于流式输出和思考过程泄露的排查记录，已单独整理到 [barrier.md](D:/PythonProject/Agentic%20RAG/barrier.md)。

## 后续建议

- 拆分 Agent 运行时职责，逐步向 LangGraph 结构演进。
- 为 `knowledge` 层补充 retrieval、rerank、post-process 抽象。
- 将固定 `userId` 替换为真实登录态，并补充用户画像管理入口。
- 为长期记忆引入语义检索、总结和过期策略。
- 为 `evals` 增加批量评测入口和结果落盘能力。
- 继续优化前端检索文档展示、代码块识别和流式状态展示。

## 参考文档

- [structure.md](D:/PythonProject/Agentic%20RAG/structure.md)
- [rag_chat_service.py](D:/PythonProject/Agentic%20RAG/agents/rag/rag_chat_service.py)
- [ingest_markdown.py](D:/PythonProject/Agentic%20RAG/knowledge/ingest/ingest_markdown.py)
- [ragas_evaluator.py](D:/PythonProject/Agentic%20RAG/evals/ragas_evaluator.py)
- [ragas_eval_dataset.csv](D:/PythonProject/Agentic%20RAG/data/evaluate/ragas_eval_dataset.csv)
