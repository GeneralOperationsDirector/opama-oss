export interface ApiTokenOut {
  id: number;
  name: string;
  hint: string;
  created_at: string;
  last_used_at?: string | null;
  revoked_at?: string | null;
}

export interface ApiTokenCreated extends ApiTokenOut {
  token: string;
}

export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  role: ChatRole;
  content: string;
  pending_action?: PendingAction | null;
}

export interface PendingAction {
  id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  description: string;
}

export interface ChatResponse {
  reply: string;
  usage?: Record<string, unknown> | null;
  pending_action?: PendingAction | null;
}

export interface ConfirmActionResponse {
  result?: unknown;
  message: string;
}
