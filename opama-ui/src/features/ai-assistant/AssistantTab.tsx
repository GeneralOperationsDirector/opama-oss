/**
 * AssistantTab — chat with the AI Assistant.
 *
 * Thread is persisted to localStorage per user, following the conventions in
 * features/decks/SuggestionPanel.tsx. Unlike that panel, there's no deck
 * scope — this assistant has read access to everything the user's enabled
 * modules expose via services.shared.tool_registry, and mutating actions
 * surface as a PendingActionCard requiring explicit confirmation.
 */
import React, { useEffect, useRef, useState } from "react";
import { Send, Trash2 } from "lucide-react";
import Button from "../../shared/atoms/Button";
import { sendChatMessage } from "./api";
import PendingActionCard from "./PendingActionCard";
import type { ChatMessage } from "./types";

interface Props {
  userId: number;
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
}

const WELCOME: ChatMessage = {
  role: "assistant",
  content:
    "Hi! I can answer questions about your collections, vehicles, insurance policies, and " +
    "property records. I'll ask for confirmation before changing anything.",
};

export default function AssistantTab({ userId, onToast }: Props) {
  const [chat, setChat] = useState<ChatMessage[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef<HTMLDivElement | null>(null);

  const storageKey = `opama-ai-assistant-chat:${userId}`;

  useEffect(() => {
    try {
      const saved = localStorage.getItem(storageKey);
      setChat(saved ? (JSON.parse(saved) as ChatMessage[]) : [WELCOME]);
    } catch {
      setChat([WELCOME]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  useEffect(() => {
    try { localStorage.setItem(storageKey, JSON.stringify(chat)); } catch {}
  }, [chat, storageKey]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat]);

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;

    const next = [...chat, { role: "user" as const, content: text }];
    setChat(next);
    setInput("");
    setLoading(true);

    try {
      const res = await sendChatMessage(next);
      setChat((cur) => [
        ...cur,
        { role: "assistant", content: res.reply, pending_action: res.pending_action ?? null },
      ]);
    } catch {
      onToast("Failed to reach the AI Assistant", "error");
    } finally {
      setLoading(false);
    }
  };

  const resolvePendingAction = (index: number, message: string) => {
    setChat((cur) =>
      cur.map((m, i) =>
        i === index
          ? { ...m, pending_action: null, content: `${m.content}\n\n${message}` }
          : m
      )
    );
  };

  const resetThread = () => setChat([WELCOME]);

  return (
    <div className="grid gap-3">
      <div className="flex justify-end">
        <button
          className="px-3 py-2 rounded-xl border text-sm hover:bg-rose-50 inline-flex items-center gap-2"
          onClick={resetThread}
          title="Clear this conversation"
        >
          <Trash2 className="w-4 h-4" /> Reset Conversation
        </button>
      </div>

      <div className="h-[420px] overflow-auto rounded-xl border bg-white/70 p-3">
        {chat.map((m, i) => (
          <div key={i} className={`mb-3 ${m.role === "user" ? "text-right" : "text-left"}`}>
            <div
              className={`inline-block max-w-[85%] px-3 py-2 rounded-2xl text-left ${
                m.role === "user" ? "bg-indigo-600 text-white" : "bg-white border"
              }`}
            >
              <div className="text-[11px] opacity-70 mb-1">{m.role === "user" ? "You" : "Assistant"}</div>
              <div className="whitespace-pre-wrap text-sm">{m.content}</div>
              {m.pending_action && (
                <PendingActionCard
                  action={m.pending_action}
                  onToast={onToast}
                  onResolved={(message) => resolvePendingAction(i, message)}
                />
              )}
            </div>
          </div>
        ))}
        {loading && <div className="text-sm text-slate-500 px-1">Thinking…</div>}
        <div ref={endRef} />
      </div>

      <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); send(); }}>
        <textarea
          placeholder="Ask about your collections, vehicles, insurance, or property… (Shift+Enter for newline)"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
          className="w-full min-h-[70px] max-h-[200px] px-3 py-2 rounded-xl border outline-none focus:ring-2 focus:ring-indigo-400"
        />
        <Button type="submit" loading={loading} title="Send">
          <Send className="w-4 h-4" />
          Send
        </Button>
      </form>
    </div>
  );
}
