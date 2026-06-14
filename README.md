# Agentic RAG

一个基于 LangChain、LangGraph、Milvus、FastAPI 和 React 的中文 Agentic RAG 示例项目。

项目当前已经落地一条可实际联调的主链路：Markdown 知识库入库、向量检索、带 PostgreSQL 短期记忆的 Agent 问答、SSE 流式聊天、React AI Chat 前端，以及 `ragas` 离线评测。

## 项目目标

- 基于本地 Markdown 文档构建知识库。
- 使用 Milvus 存储向量并完成相似度检索。
- 使用 LangChain Agent 将检索能力作为工具接入问答流程。
- 使用 LangGraph PostgreSQL memory 维护会话级短期记忆。
- 通过 FastAPI 提供会话接口、删除接口与 SSE 聊天流。
- 通过 React 前端提供多会话聊天界面、Markdown 渲染、代码块高亮和检索文档气泡。
- 生成可复用的 `ragas` 评测数据集，并执行离线 RAG 效果评测。

## 当前特性

- 支持扫描 `data/md/` 下的 Markdown 文档并完成清洗、切分、向量化和写入 Milvus。
- 支持基于知识库的多轮中文问答。
- 支持独立 React 前端与 FastAPI 分离部署。
- 支持 PostgreSQL 持久化会话元数据与 LangGraph thread memory。
- 支持会话删除，删除时同时清理会话元数据与 LangGraph checkpoint。
- 支持流式回答、Markdown 渲染、代码块高亮、知识库检索文档气泡，以及回答完成后的交互栏。
- 支持生成 `ragas` CSV 评测数据集。
- 支持基于 `ragas` 计算 `faithfulness`、`context_recall`、`answer_relevancy` 等指标。

## 项目结构

```text
api/
  main.py                  FastAPI 入口
  schemas.py               请求和统一响应模型

application/
  chat_service.py          会话编排与 SSE 聊天入口

agents/
  rag/
    rag_chat_service.py    RAG Agent、Retriever、LangGraph memory

knowledge/
  ingest/
    config.py              环境变量和运行配置
    document_load.py       Markdown 发现与加载
    document_clean.py      文档清洗
    document_chunk.py      文档切分
    vector_store.py        Embedding 与 Milvus 读写
    ingest_markdown.py     知识库入库入口

evals/
  dataset_builder.py       ragas 评测数据集生成
  ragas_evaluator.py       ragas 评测执行

persistence/
  db.py                    PostgreSQL engine / session
  models.py                会话元数据模型
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
- `qwen3.6-plus` ChatModel
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
CHAT_MODEL=qwen3.6-plus
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_API_KEY=your_embedding_api_key
OPENAI_BASE_URL=your_openai_compatible_base_url

OPENAI_API_BASE=your_chat_api_base_url
OPENAI_API_KEY=your_chat_api_key
# 如果聊天模型走 DashScope，也可以改用：
# DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
# DASHSCOPE_API_KEY=your_dashscope_api_key

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
- `CHAT_MODEL` 当前被代码限制为 `qwen3.6-plus`。
- `OPENAI_BASE_URL` 用于 Embedding 服务，内部会自动补齐 `/v1`。
- `OPENAI_API_BASE` 或 `DASHSCOPE_BASE_URL` 用于聊天模型地址，避免和 Embedding 服务混用。

## 知识库入库

将 Markdown 文档放到 `data/md/` 下，然后执行：

```powershell
.venv\Scripts\python -m knowledge.ingest.ingest_markdown
```

入库流程包括：

1. 发现 Markdown 文件。
2. 加载文档并记录失败项。
3. 执行文档清洗，并输出部分预览日志。
4. 执行文档切分。
5. 生成向量并写入 Milvus。

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
- 会话列表：`GET /api/conversations`
- 会话创建：`POST /api/conversations`
- 会话删除：`DELETE /api/conversations/{conversationId}`

## 启动前端

```powershell
cd bot-web
npm run dev
```

前端默认地址：

- 页面地址：`http://127.0.0.1:5173/`

## 评测

### 1. 生成 ragas 评测数据集

示例：

```powershell
@'
from pathlib import Path
from evals.dataset_builder import buildDefaultRagasDataset

outputPath = Path("data/evaluate/ragas_eval_dataset.csv")
rows = buildDefaultRagasDataset(outputPath, maxDatasetSize=80)
print(f"生成样本数: {len(rows)}")
'@ | .venv\Scripts\python -
```

### 2. 执行 ragas 评测

示例：

```powershell
@'
from evals.ragas_evaluator import RagEvaluationCase, RagasEvaluator
from agents.rag.rag_chat_service import getRagChatService

cases = [
    RagEvaluationCase(
        userInput="RAG 主要解决大型语言模型的哪两个关键限制？",
        reference="RAG 主要解决大型语言模型的有限上下文和静态知识这两个关键限制。",
    ),
]

report = RagasEvaluator(getRagChatService()).evaluateCases(cases)
print(report.metrics)
'@ | .venv\Scripts\python -
```

当前接入的指标包括：

- `llm_context_precision_without_reference`
- `context_recall`
- `faithfulness`
- `answer_relevancy`
- `factual_correctness`

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

- 当前记忆只覆盖会话级短期记忆，还没有长期记忆或记忆压缩。
- `rag_chat_service.py` 仍承担了较多职责，后续适合继续拆分为 tools、prompts、memory、retrieval。
- 当前没有引入 rerank、query rewrite、上下文压缩等检索后处理能力。
- 当前评测流程以离线调用为主，尚未形成完整回归评测流水线。
- 当前前端的检索文档展示和代码识别依赖启发式解析，后续可以继续提高准确率。

## 后续建议

- 拆分 Agent 运行时职责，逐步向 LangGraph 结构演进。
- 为 `knowledge` 层补充 retrieval、rerank、post-process 抽象。
- 引入长期记忆、语义 memory 和 message trim。
- 为 `evals` 增加批量评测入口和结果落盘能力。
- 继续优化前端检索文档展示、代码块识别和流式状态展示。

## 参考文档

- [structure.md](D:/PythonProject/Agentic%20RAG/structure.md)
- [rag_chat_service.py](D:/PythonProject/Agentic%20RAG/agents/rag/rag_chat_service.py)
- [ingest_markdown.py](D:/PythonProject/Agentic%20RAG/knowledge/ingest/ingest_markdown.py)
- [dataset_builder.py](D:/PythonProject/Agentic%20RAG/evals/dataset_builder.py)
- [ragas_evaluator.py](D:/PythonProject/Agentic%20RAG/evals/ragas_evaluator.py)
