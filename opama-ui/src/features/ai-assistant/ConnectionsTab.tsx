import React, { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import Button from "../../shared/atoms/Button";
import ConfirmModal from "../../shared/atoms/ConfirmModal";
import { listApiTokens, revokeApiToken } from "./api";
import ConnectClaudeCodePanel from "./ConnectClaudeCodePanel";
import CreateTokenDialog from "./CreateTokenDialog";
import TokenList from "./TokenList";
import type { ApiTokenCreated, ApiTokenOut } from "./types";

interface Props {
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
}

export default function ConnectionsTab({ onToast }: Props) {
  const [tokens, setTokens] = useState<ApiTokenOut[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState<ApiTokenOut | null>(null);
  const [lastCreatedToken, setLastCreatedToken] = useState<string | null>(null);

  const load = () => {
    listApiTokens()
      .then(setTokens)
      .catch(() => onToast("Failed to load access tokens", "error"));
  };

  useEffect(load, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleCreated = (token: ApiTokenCreated) => {
    setLastCreatedToken(token.token);
    setTokens((cur) => [token, ...cur]);
  };

  const handleRevoke = async () => {
    if (!revokeTarget) return;
    try {
      await revokeApiToken(revokeTarget.id);
      setTokens((cur) =>
        cur.map((t) => (t.id === revokeTarget.id ? { ...t, revoked_at: new Date().toISOString() } : t))
      );
      onToast("Token revoked", "success");
    } catch {
      onToast("Failed to revoke token", "error");
    } finally {
      setRevokeTarget(null);
    }
  };

  return (
    <div className="grid gap-5">
      <div>
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-800">Personal access tokens</h3>
          <Button size="sm" onClick={() => setShowCreate(true)}>
            <Plus className="w-3.5 h-3.5" /> New Token
          </Button>
        </div>
        <p className="text-sm text-slate-500 mt-1 mb-3">
          Tokens let external agents authenticate to opama's MCP endpoint as you.
        </p>
        <TokenList tokens={tokens} onRevoke={setRevokeTarget} />
      </div>

      <ConnectClaudeCodePanel token={lastCreatedToken} />

      {showCreate && (
        <CreateTokenDialog
          onCreated={handleCreated}
          onCancel={() => setShowCreate(false)}
          onToast={onToast}
        />
      )}

      {revokeTarget && (
        <ConfirmModal
          title="Revoke access token?"
          message={`"${revokeTarget.name}" will no longer be able to connect. This can't be undone.`}
          confirmLabel="Revoke"
          destructive
          onConfirm={handleRevoke}
          onCancel={() => setRevokeTarget(null)}
        />
      )}
    </div>
  );
}
