# bot-web

`bot-web` 是本项目的独立 React 前端，负责承载 AI Chat 页面。

## 技术栈

- Vite
- React
- TypeScript
- Tailwind CSS
- shadcn/ui
- Radix UI
- `@microsoft/fetch-event-source`
- `react-router-dom`
- `lucide-react`

## 页面职责

- 左侧会话列表
- 新建和删除会话
- 固定传递 `userId=default-user`
- 右侧聊天区
- SSE 流式输出
- Markdown 渲染
- 代码块高亮
- 知识库检索文档气泡
- 回答完成后的操作栏

## 本地启动

```bash
npm install
npm run dev
```

默认访问地址为 `http://127.0.0.1:5173/`。

## 接口依赖

前端依赖后端提供以下接口：

- `GET /api/conversations`
- `POST /api/conversations`
- `DELETE /api/conversations/{conversationId}`
- `GET /api/conversations/{conversationId}`
- `POST /api/chat/stream`

当前前端不实现登录，所有请求统一使用 `default-user`。后续接入认证后，只需要替换 API 层的用户 ID 来源。
