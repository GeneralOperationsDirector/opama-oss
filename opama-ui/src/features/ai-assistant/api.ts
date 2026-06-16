import { api } from "../../lib/api";
import type {
  ApiTokenCreated,
  ApiTokenOut,
  ChatMessage,
  ChatResponse,
  ConfirmActionResponse,
} from "./types";

export function listApiTokens() {
  return api<ApiTokenOut[]>("/ai-assistant/tokens");
}

export function createApiToken(name: string) {
  return api<ApiTokenCreated>("/ai-assistant/tokens", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export function revokeApiToken(tokenId: number) {
  return api<void>(`/ai-assistant/tokens/${tokenId}`, { method: "DELETE" });
}

export function sendChatMessage(messages: ChatMessage[]) {
  return api<ChatResponse>("/ai-assistant/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      messages: messages.map((m) => ({ role: m.role, content: m.content })),
    }),
  });
}

export function confirmPendingAction(pendingActionId: string, approve: boolean) {
  return api<ConfirmActionResponse>("/ai-assistant/chat/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pending_action_id: pendingActionId, approve }),
  });
}
