import React, { useState } from "react";
import { Copy, Check, ShieldAlert } from "lucide-react";
import { API_BASE } from "../../lib/api";

interface Props {
  /** A freshly-created raw token, if the user just generated one. */
  token?: string | null;
}

export default function ConnectClaudeCodePanel({ token }: Props) {
  const [copied, setCopied] = useState(false);
  // API_BASE is often a relative path (e.g. "/api", proxied by Vite/the
  // reverse proxy to the backend) — resolve it against the current origin
  // so the generated command has an absolute URL Claude Code can connect to.
  const apiOrigin = API_BASE.startsWith("/") ? `${window.location.origin}${API_BASE}` : API_BASE;
  const mcpUrl = `${apiOrigin}/ai-assistant/mcp`;
  const tokenPlaceholder = token ?? "<YOUR_TOKEN>";

  const command =
    `claude mcp add --transport http opama ${mcpUrl} ` +
    `--header "Authorization: Bearer ${tokenPlaceholder}"`;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore — clipboard may be unavailable
    }
  };

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
      <h3 className="text-sm font-semibold text-slate-800">Connect Claude Code</h3>
      <p className="text-sm text-slate-600">
        Create a personal access token below, then run this command in your terminal to
        register opama as an MCP server for Claude Code:
      </p>
      <div className="relative">
        <pre className="text-xs bg-slate-900 text-slate-100 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-all">
          {command}
        </pre>
        <button
          onClick={copy}
          title="Copy command"
          className="absolute top-2 right-2 p-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-200"
        >
          {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
        </button>
      </div>

      <div className="flex gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-800">
        <ShieldAlert className="w-4 h-4 flex-shrink-0" />
        <div>
          <strong>Trust boundary:</strong> a personal access token grants the bearer the
          <em> same permissions as your account</em>, including actions that create or modify
          data — with <strong>no confirmation prompt</strong>. This is analogous to giving an
          agent shell access to your account. Name tokens after the agent that uses them, and
          revoke a token immediately if that agent no longer needs access.
        </div>
      </div>
    </div>
  );
}
