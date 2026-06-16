import React, { useState } from "react";
import { AlertTriangle, Check, X } from "lucide-react";
import Button from "../../shared/atoms/Button";
import { confirmPendingAction } from "./api";
import type { PendingAction } from "./types";

interface Props {
  action: PendingAction;
  onResolved: (message: string) => void;
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
}

function humanize(name: string): string {
  return name
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export default function PendingActionCard({ action, onResolved, onToast }: Props) {
  const [busy, setBusy] = useState(false);
  const args = Object.entries(action.arguments ?? {});

  const respond = async (approve: boolean) => {
    setBusy(true);
    try {
      const res = await confirmPendingAction(action.id, approve);
      onResolved(res.message);
      if (approve) onToast(res.message, "success");
    } catch {
      onToast("Failed to resolve the pending action", "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm">
      <div className="flex items-center gap-2 font-medium text-amber-800">
        <AlertTriangle className="w-4 h-4" />
        Confirm action: {humanize(action.tool_name)}
      </div>
      <div className="mt-1 text-slate-700">{action.description}</div>
      {args.length > 0 && (
        <table className="mt-2 w-full text-xs">
          <tbody>
            {args.map(([k, v]) => (
              <tr key={k} className="border-t border-amber-200/70">
                <td className="py-1 pr-2 font-medium text-slate-600 align-top whitespace-nowrap">{k}</td>
                <td className="py-1 text-slate-800 break-all">{String(v)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="mt-3 flex gap-2">
        <Button size="sm" onClick={() => respond(true)} loading={busy}>
          <Check className="w-3.5 h-3.5" /> Confirm
        </Button>
        <Button size="sm" variant="ghost" onClick={() => respond(false)} disabled={busy}>
          <X className="w-3.5 h-3.5" /> Cancel
        </Button>
      </div>
    </div>
  );
}
