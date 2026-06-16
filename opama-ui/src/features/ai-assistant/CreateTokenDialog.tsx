import React, { useState } from "react";
import { Copy, Check } from "lucide-react";
import Button from "../../shared/atoms/Button";
import { createApiToken } from "./api";
import type { ApiTokenCreated } from "./types";

interface Props {
  onCreated: (token: ApiTokenCreated) => void;
  onCancel: () => void;
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
}

export default function CreateTokenDialog({ onCreated, onCancel, onToast }: Props) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<ApiTokenCreated | null>(null);
  const [copied, setCopied] = useState(false);

  const submit = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    setBusy(true);
    try {
      const token = await createApiToken(trimmed);
      setCreated(token);
      onCreated(token);
    } catch {
      onToast("Failed to create token", "error");
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.token);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore — clipboard may be unavailable
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-6 space-y-4">
        {!created ? (
          <>
            <h2 className="text-base font-semibold text-slate-800">New access token</h2>
            <p className="text-sm text-slate-500">
              Give it a name describing the agent that will use it, e.g. "Claude Code (laptop)".
            </p>
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submit()}
              placeholder="Token name"
              className="w-full border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
            <div className="flex gap-2 justify-end">
              <Button variant="ghost" onClick={onCancel} disabled={busy}>Cancel</Button>
              <Button onClick={submit} disabled={!name.trim()} loading={busy}>Create</Button>
            </div>
          </>
        ) : (
          <>
            <h2 className="text-base font-semibold text-slate-800">Token created</h2>
            <p className="text-sm text-slate-500">
              Copy this token now — it won't be shown again. Treat it like a password.
            </p>
            <div className="relative">
              <pre className="text-xs bg-slate-900 text-slate-100 rounded-lg p-3 overflow-x-auto break-all">
                {created.token}
              </pre>
              <button
                onClick={copy}
                title="Copy token"
                className="absolute top-2 right-2 p-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-200"
              >
                {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
              </button>
            </div>
            <div className="flex justify-end">
              <Button onClick={onCancel}>Done</Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
