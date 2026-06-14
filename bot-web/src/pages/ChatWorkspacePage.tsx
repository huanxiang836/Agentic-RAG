import {
  ArrowUp,
  Bot,
  ChevronDown,
  ChevronUp,
  Copy,
  RefreshCcw,
  PlusCircle,
  Share2,
  Search,
  ThumbsDown,
  ThumbsUp,
  Trash2,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { LightAsync as SyntaxHighlighter } from "react-syntax-highlighter";
import atomOneLight from "react-syntax-highlighter/dist/esm/styles/hljs/atom-one-light";
import bash from "react-syntax-highlighter/dist/esm/languages/hljs/bash";
import javascript from "react-syntax-highlighter/dist/esm/languages/hljs/javascript";
import java from "react-syntax-highlighter/dist/esm/languages/hljs/java";
import json from "react-syntax-highlighter/dist/esm/languages/hljs/json";
import markdown from "react-syntax-highlighter/dist/esm/languages/hljs/markdown";
import python from "react-syntax-highlighter/dist/esm/languages/hljs/python";
import typescript from "react-syntax-highlighter/dist/esm/languages/hljs/typescript";
import xml from "react-syntax-highlighter/dist/esm/languages/hljs/xml";

import {
  createConversation,
  deleteConversation,
  getConversationDetail,
  listConversations,
  streamChat,
} from "../api";
import type { ChatMessage, ConversationSummary } from "../types";

SyntaxHighlighter.registerLanguage("javascript", javascript);
SyntaxHighlighter.registerLanguage("typescript", typescript);
SyntaxHighlighter.registerLanguage("java", java);
SyntaxHighlighter.registerLanguage("bash", bash);
SyntaxHighlighter.registerLanguage("json", json);
SyntaxHighlighter.registerLanguage("markdown", markdown);
SyntaxHighlighter.registerLanguage("python", python);
SyntaxHighlighter.registerLanguage("xml", xml);


const EXAMPLE_PROMPTS = [
  "写一个模拟 Analog Clock 的 React 组件。",
  "用当前知识库解释 LangGraph memory 如何接入项目。",
  "总结多 Agent 和单 Agent 在项目里的取舍。",
];

/** 聊天工作台页面。 */
export function ChatWorkspacePage() {
  const navigate = useNavigate();
  const { conversationId = "new" } = useParams();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [searchKeyword, setSearchKeyword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [streamingAssistantId, setStreamingAssistantId] = useState<string | null>(null);
  const threadScrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    void refreshConversations();
  }, []);

  useEffect(() => {
    if (conversationId === "new") {
      return;
    }
    void loadConversation(conversationId);
  }, [conversationId]);

  const filteredConversations = useMemo(() => {
    const normalizedKeyword = searchKeyword.trim().toLowerCase();
    const sortedConversations = [...conversations].sort((left, right) =>
      right.updatedAt.localeCompare(left.updatedAt),
    );
    if (!normalizedKeyword) {
      return sortedConversations;
    }
    return sortedConversations.filter((conversation) =>
      conversation.title.toLowerCase().includes(normalizedKeyword),
    );
  }, [conversations, searchKeyword]);
  const latestUserMessage = [...messages].reverse().find((message) => message.role === "user");
  const visibleMessages = conversationId === "new" ? [] : messages;

  function handleCreateNewChat() {
    setMessages([]);
    setDraft("");
    navigate("/chat/new");
  }

  async function refreshConversations() {
    const records = await listConversations();
    setConversations(records);
  }

  async function loadConversation(targetConversationId: string) {
    const detail = await getConversationDetail(targetConversationId);
    setMessages(detail.messages);
  }

  async function handleDeleteConversation(targetConversationId: string) {
    await deleteConversation(targetConversationId);
    if (targetConversationId === conversationId) {
      setMessages([]);
      setDraft("");
      navigate("/chat/new");
    }
    await refreshConversations();
  }

  async function ensureConversationId(): Promise<string> {
    if (conversationId && conversationId !== "new") {
      return conversationId;
    }
    const createdConversation = await createConversation();
    setConversations((current) => [createdConversation, ...current]);
    navigate(`/chat/${createdConversation.id}`);
    return createdConversation.id;
  }

  async function handleSubmit(rawMessage: string) {
    const normalizedMessage = rawMessage.trim();
    if (!normalizedMessage || isLoading) {
      return;
    }
    setDraft("");
    setIsLoading(true);
    const targetConversationId = await ensureConversationId();
    await streamChat(targetConversationId, normalizedMessage, {
      onStart(payload) {
        setStreamingAssistantId(payload.assistantMessageId);
        setMessages((current) => [
          ...current,
          { id: payload.userMessageId, role: "user", content: normalizedMessage },
          {
            id: payload.assistantMessageId,
            role: "assistant",
            content: "",
            retrievedContexts: payload.retrievedContexts,
          },
        ]);
      },
      onDelta(payload) {
        setMessages((current) =>
          current.map((message) =>
            message.id === payload.assistantMessageId
              ? { ...message, content: message.content + payload.text }
              : message,
          ),
        );
      },
      onDone() {
        setIsLoading(false);
        setStreamingAssistantId(null);
        void refreshConversations();
      },
      onError(payload) {
        setMessages((current) => [
          ...current,
          { id: crypto.randomUUID(), role: "system", content: payload.message },
        ]);
        setIsLoading(false);
        setStreamingAssistantId(null);
      },
    });
  }

  return (
    <main className="chat-app-shell">
      <aside className="app-sidebar">
        <div className="sidebar-head">
          <div className="sidebar-title">
            <Bot size={16} />
            <span>Flippy chats</span>
          </div>
          <button
            className="plain-icon-button"
            type="button"
            onClick={handleCreateNewChat}
            aria-label="新建对话"
          >
            <PlusCircle size={17} />
          </button>
        </div>

        <label className="sidebar-searchbar">
          <input
            value={searchKeyword}
            onChange={(event) => setSearchKeyword(event.target.value)}
            aria-label="search"
            placeholder="Search"
          />
          <Search size={14} />
        </label>

        <div className="sidebar-section">
          <p className="sidebar-section-title">Chats</p>
          <div className="conversation-list">
            {filteredConversations.map((conversation) => (
              <div
                key={conversation.id}
                className={
                  conversation.id === conversationId
                    ? "conversation-row conversation-row-active"
                    : "conversation-row"
                }
              >
                <button
                  className="conversation-open-button"
                  type="button"
                  onClick={() => navigate(`/chat/${conversation.id}`)}
                >
                  <span className="conversation-title-text">{conversation.title}</span>
                </button>
                <button
                  className="conversation-delete-button"
                  type="button"
                  aria-label={`删除会话 ${conversation.title}`}
                  onClick={async () => {
                    if (!window.confirm(`确定删除会话「${conversation.title}」吗？`)) {
                      return;
                    }
                    await handleDeleteConversation(conversation.id);
                  }}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
            {filteredConversations.length === 0 && conversations.length === 0 ? (
              EXAMPLE_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  className="conversation-row"
                  type="button"
                  onClick={() => void handleSubmit(prompt)}
                >
                  <span>{buildConversationTitle(prompt)}</span>
                </button>
              ))
            ) : null}
            {filteredConversations.length === 0 && conversations.length > 0 ? (
              <div className="conversation-empty">没有匹配的会话。</div>
            ) : null}
          </div>
        </div>

        <div className="sidebar-footer">
          <div className="sidebar-avatar">f</div>
          <span>flippy@figma.com</span>
        </div>
      </aside>

      <section className="chat-workspace">
        <div className="workspace-thread">
          {conversationId !== "new" && latestUserMessage ? (
            <header className="thread-topline">
              <div className="top-prompt-pill">{latestUserMessage.content}</div>
            </header>
          ) : null}

          <div ref={threadScrollRef} className="thread-scroll">
            {visibleMessages.length === 0 ? (
              <section className="empty-thread">
                <div className="assistant-inline">
                  <Bot size={15} />
                  <div className="assistant-copy">
                    <p>
                      选择左侧历史会话，或者直接发送一个问题开始新对话。
                    </p>
                  </div>
                </div>

                <div className="example-stack">
                  {EXAMPLE_PROMPTS.map((prompt) => (
                    <button
                      key={prompt}
                      className="example-chip"
                      type="button"
                      onClick={() => void handleSubmit(prompt)}
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </section>
            ) : (
              <section className="thread-messages">
                {visibleMessages.map((message) => (
                  <MessageCard
                    key={message.id}
                    message={message}
                    isStreaming={streamingAssistantId === message.id}
                  />
                ))}
              </section>
            )}
          </div>

          <form
            className="chat-composer"
            onSubmit={(event) => {
              event.preventDefault();
              void handleSubmit(draft);
            }}
          >
            <textarea
              className="chat-composer-input"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void handleSubmit(draft);
                }
              }}
              placeholder="What would you like to know?"
            />
            <div className="chat-composer-toolbar">
              <button className="composer-submit" type="submit" disabled={isLoading} aria-label="send">
                <ArrowUp size={16} />
              </button>
            </div>
          </form>
        </div>
      </section>
    </main>
  );
}


function buildConversationTitle(message: string): string {
  const normalizedMessage = message.trim().replace(/\s+/g, " ");
  if (normalizedMessage.length <= 24) {
    return normalizedMessage;
  }
  return `${normalizedMessage.slice(0, 24)}...`;
}

/** 对话消息卡片。 */
function MessageCard({
  message,
  isStreaming,
}: {
  message: ChatMessage;
  isStreaming: boolean;
}) {
  if (message.role === "user") {
    return <div className="user-inline-bubble">{message.content}</div>;
  }

  const retrievalContexts = message.retrievedContexts ?? [];
  const answerContent = message.content;

  return (
    <article className={message.role === "system" ? "assistant-card system-card" : "assistant-card"}>
          <div className="assistant-inline">
            <Bot size={15} />
            <div className="assistant-copy">
              <RetrievalBubble contexts={retrievalContexts} />
              {answerContent ? <MarkdownContent content={answerContent} /> : <p>{isStreaming ? "正在生成回答..." : ""}</p>}
              {!isStreaming && message.role === "assistant" ? <AssistantFooter /> : null}
            </div>
          </div>
        </article>
      );
}

function RetrievalBubble({
  contexts,
}: {
  contexts: string[];
}) {
  const isVisible = contexts.length > 0;
  const [expanded, setExpanded] = useState(true);

  if (!isVisible) {
    return null;
  }

  return (
    <section className={expanded ? "retrieval-bubble retrieval-bubble-expanded" : "retrieval-bubble"}>
      <button
        className="retrieval-toggle"
        type="button"
        onClick={() => setExpanded((current) => !current)}
        aria-label="切换检索上下文显示"
      >
        <span className="retrieval-toggle-title">知识库检索文档（{contexts.length}）</span>
        {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>
      {expanded ? (
        <div className="retrieval-content">
          {contexts.map((context, index) => (
            <article key={`${index}`} className="retrieval-item">
              <RetrievalItem content={context} index={index + 1} />
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function RetrievalItem({ content, index }: { content: string; index: number }) {
  const { title, source, body } = parseRetrievedContext(content, index);

  return (
    <div className="retrieval-card">
      <div className="retrieval-card-head">
        <span className="retrieval-card-index">{title}</span>
      </div>
      <div className="retrieval-card-source">{source}</div>
      <div className="retrieval-card-body">
        <MarkdownContent content={body} />
      </div>
    </div>
  );
}

function AssistantFooter() {
  return (
    <div className="assistant-footer">
      <p className="assistant-disclaimer">本回答由 AI 生成，内容仅供参考，请仔细甄别。</p>
      <div className="assistant-actions" aria-label="assistant actions">
        <button className="assistant-action-button" type="button" aria-label="复制">
          <Copy size={18} />
        </button>
        <button className="assistant-action-button" type="button" aria-label="重新生成">
          <RefreshCcw size={18} />
        </button>
        <button className="assistant-action-button" type="button" aria-label="赞同">
          <ThumbsUp size={18} />
        </button>
        <button className="assistant-action-button" type="button" aria-label="不赞同">
          <ThumbsDown size={18} />
        </button>
        <button className="assistant-action-button" type="button" aria-label="分享">
          <Share2 size={18} />
        </button>
      </div>
    </div>
  );
}

function MarkdownContent({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        pre: ({ children }) => <>{children}</>,
        p: ({ children }) => {
          const text = stringifyNode(children).trim();
          if (looksLikeCodeParagraph(text)) {
            return <SyntaxCodeBlock code={text} />;
          }
          return <p>{children}</p>;
        },
        table: ({ children }) => (
          <div className="markdown-table-wrap">
            <table>{children}</table>
          </div>
        ),
        code: ({ className, children, ...props }) => {
          const rawCode = String(children).replace(/\n$/, "");
          const languageMatch = /language-([\w-]+)/.exec(className ?? "");
          const inline = !className;
          if (inline) {
            return (
              <code className="markdown-inline-code" {...props}>
                {children}
              </code>
            );
          }
          return <SyntaxCodeBlock code={rawCode} language={normalizeLanguage(languageMatch?.[1])} />;
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

function SyntaxCodeBlock({
  code,
  language,
}: {
  code: string;
  language?: string;
}) {
  return (
    <SyntaxHighlighter
      language={guessCodeLanguage(code, language)}
      style={atomOneLight}
      showLineNumbers
      wrapLines
      wrapLongLines
      customStyle={CODE_BLOCK_STYLE}
      lineNumberStyle={LINE_NUMBER_STYLE}
      codeTagProps={{ className: "syntax-code-text" }}
    >
      {code}
    </SyntaxHighlighter>
  );
}

function normalizeLanguage(language?: string): string {
  if (!language) {
    return "markdown";
  }
  if (language === "tsx" || language === "jsx") {
    return "typescript";
  }
  if (language === "shell") {
    return "bash";
  }
  return language;
}

function guessCodeLanguage(code: string, language?: string): string {
  if (language) {
    return language;
  }
  if (/^\s*(import|package|public|private|class|interface|@)/m.test(code)) {
    return "java";
  }
  if (/^\s*(const|let|var|function|export|import|type|interface)\b/m.test(code)) {
    return "typescript";
  }
  if (/^\s*(def|import|from)\b/m.test(code)) {
    return "python";
  }
  if (/^\s*(#!\/bin|echo |cd |npm |pnpm |yarn )/m.test(code)) {
    return "bash";
  }
  return "markdown";
}

function stringifyNode(node: unknown): string {
  if (typeof node === "string") {
    return node;
  }
  if (Array.isArray(node)) {
    return node.map((item) => stringifyNode(item)).join("");
  }
  if (node && typeof node === "object" && "props" in node) {
    return stringifyNode((node as { props?: { children?: unknown } }).props?.children);
  }
  return "";
}

function looksLikeCodeParagraph(text: string): boolean {
  const normalizedText = text.trim();
  if (!normalizedText) {
    return false;
  }
  if (normalizedText.length < 60) {
    return false;
  }
  if (/^\s*(import|package|public|private|class|interface|const|let|var|function|def)\b/.test(normalizedText)) {
    return true;
  }
  if (normalizedText.includes("=>") || normalizedText.includes("class ") || normalizedText.includes("builder()")) {
    return true;
  }
  const symbolMatches = Array.from(normalizedText).filter((character) =>
    "{}[]();=<>./\\".includes(character),
  ).length;
  return symbolMatches >= 10;
}

function parseRetrievedContext(content: string, fallbackIndex: number): {
  title: string;
  source: string;
  body: string;
} {
  const titleMatch = content.match(/^文档\s*(\d+)/m);
  const sourceMatch = content.match(/^来源:\s*(.+)$/m);
  const bodyIndex = content.indexOf("内容:");
  const body = bodyIndex >= 0 ? content.slice(bodyIndex + "内容:".length).trim() : content.trim();
  return {
    title: titleMatch ? `文档 ${titleMatch[1]}` : `文档 ${fallbackIndex}`,
    source: sourceMatch ? `来源: ${sourceMatch[1]}` : "来源: 未知",
    body,
  };
}

const CODE_BLOCK_STYLE = {
  margin: 0,
  padding: "18px 20px",
  border: "1px solid #ecece8",
  borderRadius: "16px",
  background: "#fcfcfb",
  fontSize: "14px",
  lineHeight: "1.75",
  fontFamily: '"JetBrains Mono", monospace',
  overflowX: "auto",
  boxShadow: "0 8px 20px rgba(17, 17, 14, 0.04)",
} as const;

const LINE_NUMBER_STYLE = {
  minWidth: "2.6em",
  paddingRight: "1.4em",
  color: "#c2beb6",
  userSelect: "none",
} as const;
