/**
 * AiAssistantModule — chat across all of the user's data, plus connection
 * management for external agents (Claude Code via MCP). Backend:
 * services/ai_assistant.
 */
import React, { useState } from "react";
import { Bot, Plug } from "lucide-react";
import AssistantTab from "./AssistantTab";
import ConnectionsTab from "./ConnectionsTab";

interface Props {
  userId: number;
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
}

type TabKey = "assistant" | "connections";

export default function AiAssistantModule({ userId, onToast }: Props) {
  const [tab, setTab] = useState<TabKey>("assistant");

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
          🤖 AI Assistant
        </h2>
        <p className="text-sm text-slate-500 mt-0.5">
          Ask questions about your data, or connect external agents like Claude Code.
        </p>
      </div>

      <div className="flex gap-1 border-b border-slate-200">
        <button
          onClick={() => setTab("assistant")}
          className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
            tab === "assistant"
              ? "border-indigo-600 text-indigo-600"
              : "border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300"
          }`}
        >
          <Bot className="w-4 h-4" /> Assistant
        </button>
        <button
          onClick={() => setTab("connections")}
          className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
            tab === "connections"
              ? "border-indigo-600 text-indigo-600"
              : "border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300"
          }`}
        >
          <Plug className="w-4 h-4" /> Connections
        </button>
      </div>

      <div>
        {tab === "assistant" ? (
          <AssistantTab userId={userId} onToast={onToast} />
        ) : (
          <ConnectionsTab onToast={onToast} />
        )}
      </div>
    </div>
  );
}
