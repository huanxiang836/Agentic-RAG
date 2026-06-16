export interface ConversationSummary {
  id: string;
  userId: string;
  title: string;
  createdAt: string;
  updatedAt: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  retrievedContexts?: string[];
}

export interface ConversationDetail extends ConversationSummary {
  messages: ChatMessage[];
}

export interface Result<T> {
  code: number;
  msg: string;
  data: T;
}

export interface SseStartPayload {
  conversationId: string;
  userId: string;
  userMessageId: string;
  assistantMessageId: string;
  retrievedContexts: string[];
}

export interface SseDeltaPayload {
  assistantMessageId: string;
  text: string;
}

export interface SseDonePayload {
  assistantMessageId: string;
}

export interface SseErrorPayload {
  message: string;
}
