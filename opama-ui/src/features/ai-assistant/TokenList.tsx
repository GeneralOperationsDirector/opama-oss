import React from "react";
import { KeyRound, Trash2 } from "lucide-react";
import type { ApiTokenOut } from "./types";

interface Props {
  tokens: ApiTokenOut[];
  onRevoke: (token: ApiTokenOut) => void;
}

function fmtDate(s?: string | null): string {
  if (!s) return "—";
  return new Date(s).toLocaleString();
}

export default function TokenList({ tokens, onRevoke }: Props) {
  if (tokens.length === 0) {
    return (
      <div className="text-sm text-slate-500 border border-dashed border-slate-300 rounded-xl p-4 text-center">
        No access tokens yet. Create one to connect an external agent.
      </div>
    );
  }

  return (
    <ul className="space-y-2">
      {tokens.map((t) => {
        const revoked = !!t.revoked_at;
        return (
          <li
            key={t.id}
            className={`flex items-center justify-between gap-3 p-3 border rounded-xl bg-white ${
              revoked ? "opacity-60" : ""
            }`}
          >
            <div className="flex items-center gap-3 min-w-0">
              <KeyRound className="w-4 h-4 text-slate-400 flex-shrink-0" />
              <div className="min-w-0">
                <div className="font-medium text-sm text-slate-800 truncate">
                  {t.name}
                  {revoked && <span className="ml-2 text-xs text-rose-600">(revoked)</span>}
                </div>
                <div className="text-xs text-slate-500 font-mono">{t.hint}</div>
                <div className="text-xs text-slate-400">
                  Created {fmtDate(t.created_at)} • Last used {fmtDate(t.last_used_at)}
                </div>
              </div>
            </div>
            {!revoked && (
              <button
                onClick={() => onRevoke(t)}
                title="Revoke token"
                className="p-2 rounded-lg hover:bg-rose-50 text-rose-600 flex-shrink-0"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
