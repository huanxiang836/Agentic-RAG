import { fetchEventSource } from "@microsoft/fetch-event-source";

import type {
  ConversationDetail,
  ConversationSummary,
  Result,
  SseDeltaPayload,
  SseDonePayload,
  SseErrorPayload,
  SseStartPayload,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function listConversations(): Promise<ConversationSummary[]> {
  const response = await fetch(`${API_BASE_URL}/api/conversations`);
  const result = (await response.json()) as Result<ConversationSummary[]>;
  return result.data;
}

export async function createConversation(): Promise<ConversationSummary> {
  const response = await fetch(`${API_BASE_URL}/api/conversations`, { method: "POST" });
  const result = (await response.json()) as Result<ConversationSummary>;
  return result.data;
}

export async function deleteConversation(conversationId: string): Promise<void> {
  await fetch(`${API_BASE_URL}/api/conversations/${conversationId}`, { method: "DELETE" });
}

export async function getConversationDetail(conversationId: string): Promise<ConversationDetail> {
  const response = await fetch(`${API_BASE_URL}/api/conversations/${conversationId}`);
  const result = (await response.json()) as Result<ConversationDetail>;
  return result.data;
}

interface StreamCallbacks {
  onStart: (payload: SseStartPayload) => void;
  onDelta: (payload: SseDeltaPayload) => void;
  onDone: (payload: SseDonePayload) => void;
  onError: (payload: SseErrorPayload) => void;
}

export async function streamChat(
  conversationId: string,
  message: string,
  callbacks: StreamCallbacks,
): Promise<void> {
  await fetchEventSource(`${API_BASE_URL}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversationId, message }),
    openWhenHidden: true,
    onmessage(event) {
      if (!event.data) {
        return;
      }
      if (event.event === "start") {
        callbacks.onStart(JSON.parse(event.data) as SseStartPayload);
        return;
      }
      if (event.event === "delta") {
        callbacks.onDelta(JSON.parse(event.data) as SseDeltaPayload);
        return;
      }
      if (event.event === "done") {
        callbacks.onDone(JSON.parse(event.data) as SseDonePayload);
        return;
      }
      if (event.event === "error") {
        callbacks.onError(JSON.parse(event.data) as SseErrorPayload);
      }
    },
    onerror(error) {
      callbacks.onError({ message: error instanceof Error ? error.message : "流式请求失败。" });
      throw error;
    },
  });
}
