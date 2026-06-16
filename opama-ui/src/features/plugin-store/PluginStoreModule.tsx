/**
 * PluginStoreModule — browse, install, and manage optional modules/plugins.
 *
 * The in-app face of the plugin system (backend: app/plugin_installer.py).
 * Lists available plugins from the marketplace and installed ones, and drives
 * the three install channels — marketplace `type=local` download, pip package,
 * and local dev path. Installs/uninstalls hit the backend then prompt to
 * reload so the module/nav registry picks up the change. The largest module in
 * the app; sections are split by install source and lifecycle state.
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Clock,
  Code2,
  Download,
  ExternalLink,
  Globe,
  Key,
  Layers,
  Package,
  Plus,
  RefreshCw,
  Server,
  Shield,
  Tag,
  Trash2,
  X,
  Zap,
} from "lucide-react";
import { api, API_BASE } from "../../lib/api";

// ── Types ────────────────────────────────────────────────────────────────────

interface MarketplaceEntry {
  id: string;
  name: string;
  description: string;
  version: string;
  tier: string;
  type: string;
  icon: string;
  author: string;
  repo: string;
  manifest_url: string;
  category: string;
  tags: string[];
  enable_plugins?: string;  // for type=builtin: comma-separated service IDs
  package_name?: string;    // for type=pip: the PyPI package name to install
}

interface InstalledPlugin {
  plugin_id: string;
  name: string;
  description: string;
  type: string;
  tier: string;
  icon: string;
  version: string;
  remote_url: string;
  auth_type: string;
  api_prefix: string;
  tags: string[];
  scopes: string[];
  manifest_url: string;
  enabled: boolean;
  installed_at: string;
  status: string;
}

interface InstallResult {
  plugin_id: string;
  name: string;
  status: string;
  message: string;
}

interface PipModuleEntry {
  plugin_id: string;
  name: string;
  description: string;
  version: string;
  tier: string;
  icon: string;
  package: string;
  package_version: string;
  status: string;  // "active" | "restart_required"
}

interface PluginStoreModuleProps {
  userId: string;
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
}

// ── Tier badge ───────────────────────────────────────────────────────────────

const TIER_STYLES: Record<string, string> = {
  core: "bg-slate-100 text-slate-600 border border-slate-200",
  free: "bg-emerald-50 text-emerald-700 border border-emerald-200",
  premium: "bg-violet-50 text-violet-700 border border-violet-200",
  enterprise: "bg-amber-50 text-amber-700 border border-amber-200",
};

function TierBadge({ tier }: { tier: string }) {
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide ${TIER_STYLES[tier] ?? TIER_STYLES.free}`}>
      {tier}
    </span>
  );
}

// ── Status badge ─────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  if (status === "active") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
        Active
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200">
      <Clock className="w-3 h-3" />
      Restart Required
    </span>
  );
}

// ── Skeleton loader ───────────────────────────────────────────────────────────

function CardSkeleton() {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 animate-pulse space-y-3">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-lg bg-slate-100 flex-shrink-0" />
        <div className="flex-1 space-y-2">
          <div className="h-4 bg-slate-100 rounded w-3/5" />
          <div className="h-3 bg-slate-100 rounded w-2/5" />
        </div>
      </div>
      <div className="h-3 bg-slate-100 rounded w-full" />
      <div className="h-3 bg-slate-100 rounded w-4/5" />
      <div className="flex gap-2 pt-1">
        <div className="h-5 w-14 bg-slate-100 rounded" />
        <div className="h-5 w-14 bg-slate-100 rounded" />
      </div>
    </div>
  );
}

// ── Install modal ─────────────────────────────────────────────────────────────

interface InstallModalProps {
  initial: string;
  onClose: () => void;
  onSuccess: (result: InstallResult) => void;
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
}

function InstallModal({ initial, onClose, onSuccess, onToast }: InstallModalProps) {
  const [url, setUrl] = useState(initial);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  const handleInstall = async () => {
    const trimmed = url.trim();
    if (!trimmed) {
      onToast("Enter a manifest URL", "error");
      return;
    }
    setLoading(true);
    try {
      const result = await api<InstallResult>("/plugin-store/install", {
        method: "POST",
        body: JSON.stringify({ manifest_url: trimmed }),
      });
      onSuccess(result);
    } catch (err: any) {
      onToast(err?.message ?? "Install failed", "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-lg mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-slate-900 flex items-center justify-center">
              <Download className="w-4 h-4 text-white" />
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-900">Install Module</p>
              <p className="text-xs text-slate-500">Provide a plugin.yaml manifest URL</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-600 uppercase tracking-wide">
              Manifest URL
            </label>
            <input
              ref={inputRef}
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleInstall()}
              placeholder="https://raw.githubusercontent.com/<owner>/<repo>/main/plugin.yaml"
              className="w-full px-3 py-2.5 text-sm bg-slate-50 border border-slate-200 rounded-lg text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900/20 focus:border-slate-400 font-mono"
            />
          </div>

          <div className="flex items-start gap-2.5 p-3 bg-amber-50 rounded-lg border border-amber-100">
            <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
            <p className="text-xs text-amber-800 leading-relaxed">
              Only install modules from sources you trust. Remote modules receive proxied requests and the user's auth token.
              The API server must be restarted to activate newly installed modules.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-100 flex items-center justify-end gap-2.5">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-slate-600 hover:text-slate-900 rounded-lg hover:bg-slate-100 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleInstall}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-slate-900 hover:bg-slate-800 rounded-lg transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {loading ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Download className="w-3.5 h-3.5" />
            )}
            {loading ? "Installing…" : "Install Module"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Uninstall confirm modal ───────────────────────────────────────────────────

interface UninstallModalProps {
  plugin: InstalledPlugin;
  onClose: () => void;
  onConfirm: () => void;
  loading: boolean;
}

function UninstallModal({ plugin, onClose, onConfirm, loading }: UninstallModalProps) {
  const isBuiltin = plugin.type === "builtin";
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-sm mx-4 overflow-hidden">
        <div className="px-6 py-5 space-y-3">
          <div className="w-10 h-10 rounded-full bg-red-50 border border-red-100 flex items-center justify-center mx-auto">
            <Trash2 className="w-5 h-5 text-red-500" />
          </div>
          <div className="text-center space-y-1">
            <p className="text-sm font-semibold text-slate-900">
              {isBuiltin ? `Disable "${plugin.name}"?` : `Remove "${plugin.name}"?`}
            </p>
            <p className="text-xs text-slate-500 leading-relaxed">
              {isBuiltin
                ? "This will disable the module on next restart. You can re-enable it from the Marketplace tab."
                : "This removes the module from the database. It will stop responding after the next restart."}
            </p>
          </div>
        </div>
        <div className="px-6 pb-5 flex gap-2.5">
          <button
            onClick={onClose}
            className="flex-1 py-2 text-sm text-slate-600 hover:text-slate-900 border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="flex-1 py-2 text-sm font-medium text-white bg-red-500 hover:bg-red-600 rounded-lg transition-colors disabled:opacity-60 flex items-center justify-center gap-1.5"
          >
            {loading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
            {isBuiltin ? "Disable" : "Remove"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Marketplace card ─────────────────────────────────────────────────────────

function TypeBadge({ type }: { type: string }) {
  if (type === "builtin") {
    return (
      <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium text-indigo-600 bg-indigo-50 border border-indigo-100">
        <Server className="w-2.5 h-2.5" />
        built-in
      </span>
    );
  }
  if (type === "pip") {
    return (
      <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-100">
        <Package className="w-2.5 h-2.5" />
        pip
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium text-slate-500 bg-slate-50 border border-slate-100">
      {type === "remote" ? <Globe className="w-2.5 h-2.5" /> : <Code2 className="w-2.5 h-2.5" />}
      {type}
    </span>
  );
}

type BuiltinStatus = "active" | "pending" | "pending_disable" | "available";

type PipStatus = "active" | "restart_required" | undefined;

interface MarketplaceCardProps {
  entry: MarketplaceEntry;
  builtinStatus?: BuiltinStatus;
  pipStatus?: PipStatus;
  onInstall: (entry: MarketplaceEntry) => void;
  onEnable: (entry: MarketplaceEntry) => Promise<void>;
  onPipInstall: (entry: MarketplaceEntry) => Promise<void>;
  onRestartNow: () => void;
}

function MarketplaceCard({ entry, builtinStatus = "available", pipStatus, onInstall, onEnable, onPipInstall, onRestartNow }: MarketplaceCardProps) {
  const [enabling, setEnabling] = useState(false);
  const [pipInstalling, setPipInstalling] = useState(false);

  const handleEnable = async () => {
    setEnabling(true);
    try {
      await onEnable(entry);
    } finally {
      setEnabling(false);
    }
  };

  const handlePipInstall = async () => {
    setPipInstalling(true);
    try {
      await onPipInstall(entry);
    } finally {
      setPipInstalling(false);
    }
  };

  return (
    <div className="group bg-white border border-slate-200 rounded-xl p-5 hover:border-slate-300 hover:shadow-md transition-all duration-200 flex flex-col gap-3">
      {/* Icon + Name */}
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-lg bg-slate-50 border border-slate-100 flex items-center justify-center flex-shrink-0 text-xl">
          {entry.icon || <Package className="w-5 h-5 text-slate-400" />}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-slate-900 truncate">{entry.name}</p>
          <p className="text-xs text-slate-400">
            {entry.author ? `by ${entry.author}` : "community"} · v{entry.version}
          </p>
        </div>
        {/* Active / pending badge inline with name */}
        {entry.type === "builtin" && builtinStatus === "active" && (
          <span className="flex-shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            Active
          </span>
        )}
        {entry.type === "builtin" && builtinStatus === "pending" && (
          <span className="flex-shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-amber-50 text-amber-700 border border-amber-200">
            <Clock className="w-3 h-3" />
            Restart required
          </span>
        )}
        {entry.type === "builtin" && builtinStatus === "pending_disable" && (
          <span className="flex-shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-amber-50 text-amber-700 border border-amber-200">
            <Clock className="w-3 h-3" />
            Restart to deactivate
          </span>
        )}
        {entry.type === "pip" && pipStatus === "restart_required" && (
          <span className="flex-shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-amber-50 text-amber-700 border border-amber-200">
            <Clock className="w-3 h-3" />
            Restart required
          </span>
        )}
        {entry.type === "pip" && pipStatus === "active" && (
          <span className="flex-shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            Active
          </span>
        )}
      </div>

      {/* Description */}
      <p className="text-xs text-slate-600 leading-relaxed line-clamp-2 flex-1">
        {entry.description || "No description provided."}
      </p>

      {/* Tags */}
      <div className="flex flex-wrap items-center gap-1.5">
        <TierBadge tier={entry.tier} />
        <TypeBadge type={entry.type} />
        {entry.category && (
          <span className="px-1.5 py-0.5 rounded text-[10px] text-slate-500 bg-slate-50 border border-slate-100">
            {entry.category}
          </span>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 pt-1 border-t border-slate-100">
        {entry.repo && (
          <a
            href={entry.repo}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 transition-colors"
          >
            <ExternalLink className="w-3 h-3" />
            Source
          </a>
        )}
        {entry.type === "builtin" ? (
          <>
            {builtinStatus === "active" && (
              <span className="ml-auto text-xs text-slate-400 italic">Enabled</span>
            )}
            {(builtinStatus === "pending" || builtinStatus === "pending_disable") && (
              <button
                onClick={onRestartNow}
                className="ml-auto flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-amber-700 bg-amber-50 hover:bg-amber-100 border border-amber-200 rounded-lg transition-colors"
              >
                <RefreshCw className="w-3 h-3" />
                Restart Now
              </button>
            )}
            {builtinStatus === "available" && (
              <button
                onClick={handleEnable}
                disabled={enabling}
                className="ml-auto flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-indigo-700 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 rounded-lg transition-colors disabled:opacity-60"
              >
                {enabling ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Server className="w-3 h-3" />}
                Enable
              </button>
            )}
          </>
        ) : entry.type === "pip" ? (
          <>
            {pipStatus === "active" ? (
              <span className="ml-auto text-xs text-slate-400 italic">Installed</span>
            ) : pipStatus === "restart_required" ? (
              <button
                onClick={onRestartNow}
                className="ml-auto flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-amber-700 bg-amber-50 hover:bg-amber-100 border border-amber-200 rounded-lg transition-colors"
              >
                <RefreshCw className="w-3 h-3" />
                Restart Now
              </button>
            ) : (
              <button
                onClick={handlePipInstall}
                disabled={pipInstalling}
                className="ml-auto flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-emerald-700 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 rounded-lg transition-colors disabled:opacity-60"
              >
                {pipInstalling ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Package className="w-3 h-3" />}
                {pipInstalling ? "Installing…" : "Install"}
              </button>
            )}
          </>
        ) : (
          <button
            onClick={() => onInstall(entry)}
            className="ml-auto flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-slate-900 hover:bg-slate-800 rounded-lg transition-colors"
          >
            <Download className="w-3 h-3" />
            Install
          </button>
        )}
      </div>
    </div>
  );
}

// ── Installed module row ──────────────────────────────────────────────────────

interface InstalledRowProps {
  plugin: InstalledPlugin;
  onUninstall: (plugin: InstalledPlugin) => void;
}

function InstalledRow({ plugin, onUninstall }: InstalledRowProps) {
  const [expanded, setExpanded] = useState(false);
  const isBuiltin = plugin.type === "builtin";

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      {/* Main row */}
      <div className="flex items-center gap-3 px-5 py-4">
        <div className="w-9 h-9 rounded-lg bg-slate-50 border border-slate-100 flex items-center justify-center flex-shrink-0 text-lg">
          {plugin.icon || <Package className="w-4 h-4 text-slate-400" />}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-semibold text-slate-900">{plugin.name}</p>
            <StatusBadge status={plugin.status} />
            <TierBadge tier={plugin.tier} />
            {isBuiltin && (
              <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium text-indigo-600 bg-indigo-50 border border-indigo-100">
                <Server className="w-2.5 h-2.5" />
                built-in
              </span>
            )}
          </div>
          {!isBuiltin && (
            <div className="flex items-center gap-3 mt-0.5">
              <span className="text-xs text-slate-400 font-mono">{plugin.api_prefix}</span>
              {plugin.remote_url && (
                <span className="text-xs text-slate-400 truncate max-w-[200px]">{plugin.remote_url}</span>
              )}
            </div>
          )}
          {plugin.description && isBuiltin && (
            <p className="text-xs text-slate-400 mt-0.5 truncate">{plugin.description}</p>
          )}
        </div>

        <div className="flex items-center gap-1.5 flex-shrink-0">
          {!isBuiltin && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="w-7 h-7 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
            >
              <ChevronRight className={`w-4 h-4 transition-transform duration-200 ${expanded ? "rotate-90" : ""}`} />
            </button>
          )}
          <button
            onClick={() => onUninstall(plugin)}
            title={isBuiltin ? "Disable module" : "Remove module"}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
            {isBuiltin ? "Disable" : "Remove"}
          </button>
        </div>
      </div>

      {/* Expanded detail (dynamic modules only) */}
      {expanded && !isBuiltin && (
        <div className="border-t border-slate-100 px-5 py-4 bg-slate-50 space-y-3">
          {plugin.description && (
            <p className="text-xs text-slate-600 leading-relaxed">{plugin.description}</p>
          )}
          <div className="grid grid-cols-2 gap-3 text-xs">
            <Detail icon={<Globe className="w-3.5 h-3.5" />} label="Type" value={plugin.type} />
            <Detail icon={<Key className="w-3.5 h-3.5" />} label="Auth" value={plugin.auth_type} />
            <Detail icon={<Zap className="w-3.5 h-3.5" />} label="Version" value={plugin.version} />
            <Detail
              icon={<Clock className="w-3.5 h-3.5" />}
              label="Installed"
              value={new Date(plugin.installed_at).toLocaleDateString()}
            />
          </div>
          {plugin.scopes.length > 0 && (
            <div className="space-y-1">
              <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold flex items-center gap-1">
                <Shield className="w-3 h-3" /> Scopes
              </p>
              <div className="flex flex-wrap gap-1">
                {plugin.scopes.map((s) => (
                  <span key={s} className="px-1.5 py-0.5 rounded text-[10px] bg-white border border-slate-200 text-slate-600 font-mono">
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}
          {plugin.manifest_url && (
            <div className="space-y-1">
              <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">Manifest</p>
              <a
                href={plugin.manifest_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-slate-500 hover:text-slate-900 font-mono break-all flex items-start gap-1"
              >
                <ExternalLink className="w-3 h-3 flex-shrink-0 mt-0.5" />
                {plugin.manifest_url}
              </a>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Detail({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-start gap-1.5">
      <span className="text-slate-400 mt-0.5">{icon}</span>
      <div>
        <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">{label}</p>
        <p className="text-slate-700 font-mono">{value}</p>
      </div>
    </div>
  );
}

// ── Pip module row ────────────────────────────────────────────────────────────

interface PipModuleRowProps {
  module: PipModuleEntry;
  onUninstall: (module: PipModuleEntry) => void;
}

function PipModuleRow({ module, onUninstall }: PipModuleRowProps) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      <div className="flex items-center gap-3 px-5 py-4">
        <div className="w-9 h-9 rounded-lg bg-slate-50 border border-slate-100 flex items-center justify-center flex-shrink-0 text-lg">
          {module.icon || <Package className="w-4 h-4 text-slate-400" />}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-semibold text-slate-900">{module.name}</p>
            <StatusBadge status={module.status} />
            <TierBadge tier={module.tier} />
            <TypeBadge type="pip" />
          </div>
          <div className="flex items-center gap-3 mt-0.5">
            <span className="text-xs text-slate-400 font-mono">{module.package}=={module.package_version}</span>
          </div>
          {module.description && (
            <p className="text-xs text-slate-400 mt-0.5 truncate">{module.description}</p>
          )}
        </div>

        <div className="flex items-center gap-1.5 flex-shrink-0">
          <button
            onClick={() => onUninstall(module)}
            title="Remove module"
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Remove
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Pip uninstall confirm modal ───────────────────────────────────────────────

interface PipUninstallModalProps {
  module: PipModuleEntry;
  onClose: () => void;
  onConfirm: () => void;
  loading: boolean;
}

function PipUninstallModal({ module, onClose, onConfirm, loading }: PipUninstallModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-sm mx-4 overflow-hidden">
        <div className="px-6 py-5 space-y-3">
          <div className="w-10 h-10 rounded-full bg-red-50 border border-red-100 flex items-center justify-center mx-auto">
            <Trash2 className="w-5 h-5 text-red-500" />
          </div>
          <div className="text-center space-y-1">
            <p className="text-sm font-semibold text-slate-900">Remove "{module.name}"?</p>
            <p className="text-xs text-slate-500 leading-relaxed">
              Deletes the <span className="font-mono">{module.package}</span> package from disk and removes it
              from requirements-modules.txt. It stops responding after the next restart.
            </p>
          </div>
        </div>
        <div className="px-6 pb-5 flex gap-2.5">
          <button
            onClick={onClose}
            className="flex-1 py-2 text-sm text-slate-600 hover:text-slate-900 border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="flex-1 py-2 text-sm font-medium text-white bg-red-500 hover:bg-red-600 rounded-lg transition-colors disabled:opacity-60 flex items-center justify-center gap-1.5"
          >
            {loading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
            Remove
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Empty states ──────────────────────────────────────────────────────────────

function MarketplaceEmpty({ onManual }: { onManual: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="w-16 h-16 rounded-2xl bg-slate-100 border border-slate-200 flex items-center justify-center mb-5">
        <Layers className="w-8 h-8 text-slate-400" />
      </div>
      <p className="text-sm font-semibold text-slate-700 mb-1">Registry coming soon</p>
      <p className="text-xs text-slate-500 max-w-xs leading-relaxed mb-6">
        The community module registry is being built. Once live, community-contributed modules will appear here.
        In the meantime, install from any manifest URL directly.
      </p>
      <button
        onClick={onManual}
        className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-slate-900 hover:bg-slate-800 rounded-lg transition-colors"
      >
        <Plus className="w-4 h-4" />
        Install from URL
      </button>
    </div>
  );
}

function InstalledEmpty() {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="w-16 h-16 rounded-2xl bg-slate-100 border border-slate-200 flex items-center justify-center mb-5">
        <Server className="w-8 h-8 text-slate-400" />
      </div>
      <p className="text-sm font-semibold text-slate-700 mb-1">No modules installed</p>
      <p className="text-xs text-slate-500 max-w-xs leading-relaxed">
        Enable built-in modules from the Marketplace tab, or install community modules via a manifest URL.
        Modules activate on the next server restart.
      </p>
    </div>
  );
}

// ── Main module ───────────────────────────────────────────────────────────────

type ActiveTab = "marketplace" | "installed";

export default function PluginStoreModule({ userId, onToast }: PluginStoreModuleProps) {
  const [activeTab, setActiveTab] = useState<ActiveTab>("marketplace");

  // Marketplace
  const [entries, setEntries] = useState<MarketplaceEntry[]>([]);
  const [loadingMarket, setLoadingMarket] = useState(true);

  // Built-in plugin activation state
  const [activePluginIds, setActivePluginIds] = useState<string[]>([]);
  const [pendingPluginIds, setPendingPluginIds] = useState<string[]>([]);
  const [pendingDisabledIds, setPendingDisabledIds] = useState<string[]>([]);
  // Pip packages installed this session (not yet restarted to activate)
  const [pipInstalledIds, setPipInstalledIds] = useState<string[]>([]);
  const [isRestarting, setIsRestarting] = useState(false);

  // Installed
  const [installed, setInstalled] = useState<InstalledPlugin[]>([]);
  const [loadingInstalled, setLoadingInstalled] = useState(true);

  // Pip-installed modules (entry_points in the 'opama.modules' group)
  const [pipModules, setPipModules] = useState<PipModuleEntry[]>([]);

  // Modals
  const [installTarget, setInstallTarget] = useState<string | null>(null);
  const [uninstallTarget, setUninstallTarget] = useState<InstalledPlugin | null>(null);
  const [uninstalling, setUninstalling] = useState(false);
  const [pipUninstallTarget, setPipUninstallTarget] = useState<PipModuleEntry | null>(null);
  const [pipUninstalling, setPipUninstalling] = useState(false);

  const fetchActivePlugins = useCallback(async () => {
    try {
      const data = await api<{ active: string[]; pending: string[] }>("/plugin-store/active-plugins");
      setActivePluginIds(data.active ?? []);
      setPendingPluginIds(data.pending ?? []);
    } catch {
      /* non-fatal */
    }
  }, []);

  const fetchMarketplace = useCallback(async () => {
    setLoadingMarket(true);
    try {
      const data = await api<MarketplaceEntry[]>("/plugin-store/marketplace");
      setEntries(data);
    } catch {
      setEntries([]);
    } finally {
      setLoadingMarket(false);
    }
  }, []);

  const fetchInstalled = useCallback(async () => {
    setLoadingInstalled(true);
    try {
      const data = await api<InstalledPlugin[]>("/plugin-store/installed");
      setInstalled(data);
    } catch {
      setInstalled([]);
    } finally {
      setLoadingInstalled(false);
    }
  }, []);

  const fetchPipModules = useCallback(async () => {
    try {
      const data = await api<PipModuleEntry[]>("/plugin-store/pip-modules");
      setPipModules(data);
    } catch {
      setPipModules([]);
    }
  }, []);

  useEffect(() => {
    if (!userId) return;
    fetchActivePlugins();
    fetchMarketplace();
    fetchInstalled();
    fetchPipModules();
  }, [userId, fetchActivePlugins, fetchMarketplace, fetchInstalled, fetchPipModules]);

  // Determine builtin status for a marketplace entry by its module ID
  const getBuiltinStatus = (entry: MarketplaceEntry): BuiltinStatus => {
    if (entry.type !== "builtin") return "available";
    if (pendingDisabledIds.includes(entry.id)) return "pending_disable";
    if (activePluginIds.includes(entry.id)) return "active";
    if (pendingPluginIds.includes(entry.id)) return "pending";
    return "available";
  };

  // Determine pip status for a marketplace entry by cross-referencing
  // /plugin-store/pip-modules (entry_points already on disk) and this
  // session's just-installed packages (not yet discoverable as "active").
  const getPipStatus = (entry: MarketplaceEntry): PipStatus => {
    if (entry.type !== "pip") return undefined;
    if (pipInstalledIds.includes(entry.id)) return "restart_required";
    const match = pipModules.find(
      (m) => m.plugin_id === entry.id || m.package === (entry.package_name || entry.id)
    );
    return match?.status as PipStatus;
  };

  const handleEnableBuiltin = async (entry: MarketplaceEntry) => {
    await api(`/plugin-store/enable/${entry.id}`, { method: "POST" });
    setPendingDisabledIds((prev) => prev.filter((id) => id !== entry.id));
    onToast(`${entry.name} enabled — restart to activate`, "success");
    await fetchActivePlugins();
    await fetchInstalled();
  };

  const handlePipInstall = async (entry: MarketplaceEntry) => {
    const pkg = entry.package_name || entry.id;
    try {
      await api<{ package: string; status: string; message: string }>("/plugin-store/pip-install", {
        method: "POST",
        body: JSON.stringify({ package: pkg }),
      });
      setPipInstalledIds((prev) => [...prev, entry.id]);
      onToast(`"${entry.name}" installed — restart to activate`, "success");
      fetchPipModules();
    } catch (err: any) {
      onToast(err?.message ?? "pip install failed", "error");
    }
  };

  const handlePipUninstall = async () => {
    if (!pipUninstallTarget) return;
    setPipUninstalling(true);
    try {
      await api(`/plugin-store/pip-modules/${encodeURIComponent(pipUninstallTarget.package)}`, { method: "DELETE" });
      onToast(`"${pipUninstallTarget.name}" removed`, "success");
      setPipUninstallTarget(null);
      fetchPipModules();
    } catch (err: any) {
      onToast(err?.message ?? "Remove failed", "error");
    } finally {
      setPipUninstalling(false);
    }
  };

  const handleRestartNow = async () => {
    setIsRestarting(true);
    try {
      await api("/plugin-store/restart", { method: "POST" });
    } catch {
      /* expected — server drops the connection */
    }
    // Poll /healthz until the server is back up, then reload
    const poll = async () => {
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        try {
          const r = await fetch(`${API_BASE}/healthz`);
          if (r.ok) { window.location.reload(); return; }
        } catch {/* still down */}
      }
      setIsRestarting(false);
      onToast("Server did not come back within 2 minutes — check logs", "error");
    };
    poll();
  };

  const handleInstallSuccess = (result: InstallResult) => {
    setInstallTarget(null);
    const isUpdate = result.status.startsWith("updated");
    onToast(result.message, "success");
    if (isUpdate || result.status === "installed_restart_required") {
      fetchInstalled();
      setActiveTab("installed");
    }
  };

  const handleUninstall = async () => {
    if (!uninstallTarget) return;
    setUninstalling(true);
    try {
      if (uninstallTarget.type === "builtin") {
        await api(`/plugin-store/enable/${uninstallTarget.plugin_id}`, { method: "DELETE" });
        setPendingDisabledIds((prev) => [...prev, uninstallTarget.plugin_id]);
        onToast(`"${uninstallTarget.name}" will deactivate on next restart`, "success");
      } else {
        await api(`/plugin-store/${uninstallTarget.plugin_id}`, { method: "DELETE" });
        onToast(`"${uninstallTarget.name}" removed`, "success");
      }
      setUninstallTarget(null);
      fetchInstalled();
      fetchActivePlugins();
    } catch (err: any) {
      onToast(err?.message ?? "Remove failed", "error");
    } finally {
      setUninstalling(false);
    }
  };

  const hasPendingBuiltins = entries.some((e) => getBuiltinStatus(e) === "pending");
  const needsRestart =
    hasPendingBuiltins ||
    pendingDisabledIds.length > 0 ||
    pipInstalledIds.length > 0 ||
    installed.some((p) => p.status === "restart_required") ||
    pipModules.some((m) => m.status === "restart_required");

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">

      {/* Restarting overlay */}
      {isRestarting && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-slate-900/80 backdrop-blur-sm gap-5">
          <RefreshCw className="w-10 h-10 text-white animate-spin" />
          <div className="text-center space-y-1">
            <p className="text-white font-semibold text-lg">Restarting server…</p>
            <p className="text-slate-300 text-sm">Your new plugins will be active momentarily.</p>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5 mb-1">
            <div className="w-8 h-8 rounded-lg bg-slate-900 flex items-center justify-center">
              <Package className="w-4 h-4 text-white" />
            </div>
            <h1 className="text-xl font-bold text-slate-900 tracking-tight">Modules</h1>
          </div>
          <p className="text-sm text-slate-500">
            Enable built-in modules, or install community modules from a manifest URL.
          </p>
        </div>
        <button
          onClick={() => setInstallTarget("")}
          className="flex-shrink-0 flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-slate-900 hover:bg-slate-800 rounded-xl transition-colors shadow-sm"
        >
          <Plus className="w-4 h-4" />
          Install from URL
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-slate-100 rounded-xl w-fit">
        {(["marketplace", "installed"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-1.5 text-sm font-medium rounded-lg transition-colors capitalize ${
              activeTab === tab
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            {tab}
            {tab === "installed" && installed.length + pipModules.length > 0 && (
              <span className="ml-1.5 px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-slate-200 text-slate-600">
                {installed.length + pipModules.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ── Marketplace tab ── */}
      {activeTab === "marketplace" && (
        <div className="space-y-4">
          {/* Pending restart banner */}
          {needsRestart && (
            <div className="flex items-center justify-between gap-4 p-4 bg-amber-50 border border-amber-200 rounded-xl">
              <div className="flex items-start gap-3">
                <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-amber-800">Restart required to apply changes</p>
                  <p className="text-xs text-amber-700 mt-0.5">
                    Module changes are queued. Restart the server to activate or deactivate them.
                  </p>
                </div>
              </div>
              <button
                onClick={handleRestartNow}
                className="flex-shrink-0 flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-amber-600 hover:bg-amber-700 rounded-lg transition-colors"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                Restart Now
              </button>
            </div>
          )}

          {loadingMarket ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {Array.from({ length: 6 }).map((_, i) => <CardSkeleton key={i} />)}
            </div>
          ) : entries.length === 0 ? (
            <MarketplaceEmpty onManual={() => setInstallTarget("")} />
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {entries.map((entry) => (
                <MarketplaceCard
                  key={entry.id}
                  entry={entry}
                  builtinStatus={getBuiltinStatus(entry)}
                  pipStatus={getPipStatus(entry)}
                  onInstall={(e) => setInstallTarget(e.manifest_url)}
                  onEnable={handleEnableBuiltin}
                  onPipInstall={handlePipInstall}
                  onRestartNow={handleRestartNow}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Installed tab ── */}
      {activeTab === "installed" && (
        <div className="space-y-3">
          {/* Restart notice if any need it */}
          {needsRestart && (
            <div className="flex items-center justify-between gap-4 p-4 bg-amber-50 border border-amber-200 rounded-xl">
              <div className="flex items-start gap-3">
                <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-amber-800">Restart required to apply changes</p>
                  <p className="text-xs text-amber-700 mt-0.5">
                    Module changes are queued. Restart the server to activate or deactivate them.
                  </p>
                </div>
              </div>
              <button
                onClick={handleRestartNow}
                className="flex-shrink-0 flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-amber-600 hover:bg-amber-700 rounded-lg transition-colors"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                Restart Now
              </button>
            </div>
          )}

          {loadingInstalled ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="h-16 bg-white border border-slate-200 rounded-xl animate-pulse" />
              ))}
            </div>
          ) : installed.length === 0 && pipModules.length === 0 ? (
            <InstalledEmpty />
          ) : (
            <>
              {installed.map((plugin) => (
                <InstalledRow
                  key={plugin.plugin_id}
                  plugin={plugin}
                  onUninstall={setUninstallTarget}
                />
              ))}
              {pipModules.length > 0 && (
                <div className="space-y-3 pt-2">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-400 px-1">Pip Modules</p>
                  {pipModules.map((m) => (
                    <PipModuleRow key={m.package} module={m} onUninstall={setPipUninstallTarget} />
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ── Modals ── */}
      {installTarget !== null && (
        <InstallModal
          initial={installTarget}
          onClose={() => setInstallTarget(null)}
          onSuccess={handleInstallSuccess}
          onToast={onToast}
        />
      )}

      {uninstallTarget && (
        <UninstallModal
          plugin={uninstallTarget}
          onClose={() => setUninstallTarget(null)}
          onConfirm={handleUninstall}
          loading={uninstalling}
        />
      )}

      {pipUninstallTarget && (
        <PipUninstallModal
          module={pipUninstallTarget}
          onClose={() => setPipUninstallTarget(null)}
          onConfirm={handlePipUninstall}
          loading={pipUninstalling}
        />
      )}
    </div>
  );
}
