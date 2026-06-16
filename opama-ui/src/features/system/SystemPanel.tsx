import React, { useEffect, useState } from "react";
import { Activity, Database, HardDrive, Layers, Package, Microscope, RefreshCw, Server, ShieldCheck } from "lucide-react";
import { API_BASE, api } from "../../lib/api";
import { useHealthCheck } from "../../lib/useHealthCheck";

interface SystemInfo {
  uptime: string;
  api_version: string;
  python: string;
  uploads_mb: number;
  your_data: {
    inventory_items: number;
    decks: number;
    collection_items: number;
    grading_results: number;
  };
}

interface AuditEntry {
  id: number;
  user_id: number | null;
  user_email: string | null;
  action: string;
  target: string | null;
  ip_address: string | null;
  success: boolean;
  detail: string | null;
  created_at: string;
}

function StatRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-slate-100 last:border-0">
      <div className="flex items-center gap-2.5 text-sm text-slate-600">
        <span className="text-slate-400">{icon}</span>
        {label}
      </div>
      <span className="text-sm font-medium text-slate-800">{value}</span>
    </div>
  );
}

export default function SystemPanel() {
  const health = useHealthCheck();
  const [info, setInfo] = useState<SystemInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);
  const [audit, setAudit] = useState<AuditEntry[] | null>(null);
  const [auditLoading, setAuditLoading] = useState(false);
  const [isRestarting, setIsRestarting] = useState(false);
  const [restartError, setRestartError] = useState<string | null>(null);

  const handleRestart = async () => {
    setIsRestarting(true);
    setRestartError(null);
    try {
      await api("/plugin-store/restart", { method: "POST" });
    } catch {
      /* expected — server drops the connection on exit */
    }
    for (let i = 0; i < 60; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      try {
        const r = await fetch(`${API_BASE}/healthz`);
        if (r.ok) { window.location.reload(); return; }
      } catch {/* still down */}
    }
    setIsRestarting(false);
    setRestartError("Server did not come back within 2 minutes — check logs.");
  };

  useEffect(() => {
    api<SystemInfo>("/system/info")
      .then(setInfo)
      .catch(() => {})
      .finally(() => setLoading(false));

    api<{ is_admin: boolean }>("/auth/me")
      .then((profile) => setIsAdmin(profile.is_admin))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!isAdmin) return;
    setAuditLoading(true);
    api<{ items: AuditEntry[] }>("/system/audit?limit=25")
      .then((data) => setAudit(data.items))
      .catch(() => setAudit(null))
      .finally(() => setAuditLoading(false));
  }, [isAdmin]);

  const healthLabel = health === "ok" ? "Connected" : health === "down" ? "Unreachable" : "Checking…";
  const healthColour = health === "ok" ? "text-emerald-600" : health === "down" ? "text-red-500" : "text-amber-500";
  const healthDot = health === "ok" ? "bg-emerald-400" : health === "down" ? "bg-red-400" : "bg-amber-400";

  return (
    <div className="max-w-xl mx-auto px-4 py-8 space-y-6">

      {/* Restarting overlay */}
      {isRestarting && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-slate-900/80 backdrop-blur-sm gap-5">
          <RefreshCw className="w-10 h-10 text-white animate-spin" />
          <div className="text-center space-y-1">
            <p className="text-white font-semibold text-lg">Restarting server…</p>
            <p className="text-slate-300 text-sm">The page will reload automatically when it's back up.</p>
          </div>
        </div>
      )}

      <div>
        <h2 className="text-xl font-bold text-slate-800">System</h2>
        <p className="text-sm text-slate-500 mt-0.5">API status and your data summary</p>
      </div>

      {/* API health */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-1">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">API</p>
        <div className="flex items-center justify-between py-2">
          <div className="flex items-center gap-2.5 text-sm text-slate-600">
            <Activity className="w-4 h-4 text-slate-400" />
            Status
          </div>
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${healthDot}`} />
            <span className={`text-sm font-medium ${healthColour}`}>{healthLabel}</span>
          </div>
        </div>

        {loading ? (
          <div className="py-4 text-center text-sm text-slate-400">Loading…</div>
        ) : info ? (
          <>
            <StatRow icon={<Server className="w-4 h-4" />}    label="Uptime"          value={info.uptime} />
            <StatRow icon={<Server className="w-4 h-4" />}    label="Version"         value={info.api_version} />
            <StatRow icon={<HardDrive className="w-4 h-4" />} label="Uploads on disk" value={`${info.uploads_mb} MB`} />
          </>
        ) : (
          <p className="text-sm text-slate-400 py-2">Could not load system info — API may be offline.</p>
        )}
      </div>

      {/* Your data */}
      {info && (
        <div className="bg-white rounded-2xl border border-slate-200 p-5">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Your Data</p>
          <StatRow icon={<Package   className="w-4 h-4" />} label="Inventory items"     value={info.your_data.inventory_items} />
          <StatRow icon={<Layers    className="w-4 h-4" />} label="Decks"               value={info.your_data.decks} />
          <StatRow icon={<Database  className="w-4 h-4" />} label="Collection items"    value={info.your_data.collection_items} />
          <StatRow icon={<Microscope className="w-4 h-4" />} label="Grading results"   value={info.your_data.grading_results} />
        </div>
      )}

      {/* Audit log — admin only */}
      {isAdmin && (
        <div className="bg-white rounded-2xl border border-slate-200 p-5">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
            <ShieldCheck className="w-3.5 h-3.5" />
            Audit Log
          </p>
          {auditLoading ? (
            <div className="py-4 text-center text-sm text-slate-400">Loading…</div>
          ) : audit && audit.length > 0 ? (
            <div className="space-y-1.5 max-h-96 overflow-y-auto">
              {audit.map((entry) => (
                <div
                  key={entry.id}
                  className="flex items-start justify-between gap-3 py-2 border-b border-slate-100 last:border-0 text-sm"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`w-1.5 h-1.5 rounded-full ${entry.success ? "bg-emerald-400" : "bg-red-400"}`} />
                      <span className="font-medium text-slate-700">{entry.action}</span>
                      {entry.target && <span className="text-slate-400 truncate">→ {entry.target}</span>}
                    </div>
                    {entry.detail && <p className="text-xs text-slate-500 mt-0.5 truncate">{entry.detail}</p>}
                    <p className="text-xs text-slate-400 mt-0.5">
                      {entry.user_email || "system"}{entry.ip_address ? ` · ${entry.ip_address}` : ""}
                    </p>
                  </div>
                  <span className="text-xs text-slate-400 whitespace-nowrap">
                    {new Date(entry.created_at).toLocaleString()}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-400 py-2">No privileged actions recorded yet.</p>
          )}
        </div>
      )}

      {/* Quick actions */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Maintenance</p>
        <div className="space-y-4 text-sm text-slate-600">

          {/* Restart server */}
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="font-medium text-slate-700">Restart Services</p>
              <p className="text-xs text-slate-400 mt-0.5">
                Apply module changes or recover from errors. The page reloads automatically.
              </p>
              {restartError && (
                <p className="text-xs text-red-500 mt-1">{restartError}</p>
              )}
            </div>
            <button
              onClick={handleRestart}
              disabled={isRestarting}
              className="flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Restart
            </button>
          </div>

          <div className="border-t border-slate-100 pt-4 space-y-2">
            <p>To back up your database, run from the project directory:</p>
            <pre className="bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-xs font-mono text-slate-700 select-all">
              ./opama.sh backup
            </pre>
            <p className="mt-3">To update to the latest version:</p>
            <pre className="bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-xs font-mono text-slate-700 select-all">
              ./opama.sh update
            </pre>
          </div>
        </div>
      </div>

    </div>
  );
}
