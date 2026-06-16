import React, { useEffect, useState } from "react";
import { Save, ExternalLink, Info, AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Github, KeyRound, Eye, EyeOff, Wifi, Loader2, XCircle } from "lucide-react";
import { api } from "../../lib/api";
import type { StorefrontSettings, GitHubPublishSettings, GitHubTestResult, ImageUrlTestResult } from "./types";

interface Props {
  settings: StorefrontSettings | null;
  onSaved: (s: StorefrontSettings) => void;
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
}

function Field({
  label, required, hint, warning, children,
}: {
  label: string;
  required?: boolean;
  hint?: React.ReactNode;
  warning?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label className="block text-sm font-medium text-slate-700">
        {label}
        {required && <span className="ml-1 text-red-500">*</span>}
      </label>
      {children}
      {hint && (
        <p className="text-xs text-slate-500 leading-relaxed">{hint}</p>
      )}
      {warning && (
        <div className="flex items-start gap-1.5 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-2.5 py-2">
          <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
          <span>{warning}</span>
        </div>
      )}
    </div>
  );
}

function Section({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
        {description && <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{description}</p>}
      </div>
      {children}
    </div>
  );
}

function Callout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 bg-indigo-50 border border-indigo-200 rounded-lg px-3 py-2.5 text-xs text-indigo-800 leading-relaxed">
      <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0 text-indigo-500" />
      <span>{children}</span>
    </div>
  );
}

function Code({ children }: { children: string }) {
  return (
    <code className="font-mono bg-slate-100 text-slate-700 px-1 py-0.5 rounded text-[11px]">
      {children}
    </code>
  );
}

function CollapsibleExample({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-slate-200 rounded-lg overflow-hidden text-xs">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-1.5 px-3 py-2 bg-slate-50 text-slate-600 hover:bg-slate-100 transition-colors text-left"
      >
        {open ? <ChevronDown className="w-3.5 h-3.5 flex-shrink-0" /> : <ChevronRight className="w-3.5 h-3.5 flex-shrink-0" />}
        {title}
      </button>
      {open && <div className="px-3 py-2.5 space-y-1.5 text-slate-600 leading-relaxed">{children}</div>}
    </div>
  );
}

const INPUT = "w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400";
const INPUT_MONO = `${INPUT} font-mono`;

export default function SettingsTab({ settings, onSaved, onToast }: Props) {
  const [form, setForm] = useState({
    site_name:      settings?.site_name      ?? "",
    site_url:       settings?.site_url       ?? "",
    public_api_url: settings?.public_api_url ?? "",
    catalog_path:   settings?.catalog_path   ?? "",
    webhook_url:    settings?.webhook_url    ?? "",
  });
  const [ghSettings, setGhSettings] = useState<GitHubPublishSettings | null>(null);
  const [ghForm, setGhForm] = useState({
    token:          "",   // always blank on load — existing token is preserved server-side
    repo:           ghSettings?.repo           ?? "",
    file_path:      ghSettings?.file_path      ?? "public/collectibles/catalog.json",
    commit_message: ghSettings?.commit_message ?? "chore: publish catalog ({n} items)",
  });
  const [saving, setSaving] = useState(false);
  const [showToken, setShowToken] = useState(false);
  const [testingGithub, setTestingGithub] = useState(false);
  const [githubTestResult, setGithubTestResult] = useState<GitHubTestResult | null>(null);
  const [testingImageUrl, setTestingImageUrl] = useState(false);
  const [imageUrlTestResult, setImageUrlTestResult] = useState<ImageUrlTestResult | null>(null);

  const set = (k: keyof typeof form, v: string) => setForm(f => ({ ...f, [k]: v }));
  const setGh = (k: keyof typeof ghForm, v: string) => setGhForm(f => ({ ...f, [k]: v }));

  useEffect(() => {
    (async () => {
      try {
        const s = await api<GitHubPublishSettings>("/integrations/github/settings");
        setGhSettings(s);
        setGhForm(f => ({
          ...f,
          repo: s.repo ?? f.repo,
          file_path: s.file_path ?? f.file_path,
          commit_message: s.commit_message ?? f.commit_message,
        }));
      } catch {
        setGhSettings(null);
      }
    })();
  }, []);

  const handleTestGithubPublish = async () => {
    setTestingGithub(true);
    setGithubTestResult(null);
    try {
      const result = await api<GitHubTestResult>("/integrations/github/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token: ghForm.token || null,
          repo: ghForm.repo || null,
        }),
      });
      setGithubTestResult(result);
    } catch {
      setGithubTestResult({ connected: false, error: "Connection test failed" });
    } finally {
      setTestingGithub(false);
    }
  };

  const handleSaveGithub = async () => {
    const saved = await api<GitHubPublishSettings>("/integrations/github/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        repo: ghForm.repo || null,
        file_path: ghForm.file_path || null,
        commit_message: ghForm.commit_message || null,
        token: ghForm.token || null,
      }),
    });
    setGhSettings(saved);
  };

  const handleTestImageUrl = async () => {
    setTestingImageUrl(true);
    setImageUrlTestResult(null);
    try {
      const result = await api<ImageUrlTestResult>("/storefront/settings/test-image-url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ public_api_url: form.public_api_url }),
      });
      setImageUrlTestResult(result);
    } catch {
      setImageUrlTestResult({ reachable: false, tested_url: form.public_api_url, error: "Connection test failed" });
    } finally {
      setTestingImageUrl(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const saved = await api<StorefrontSettings>("/storefront/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...form,
          catalog_path: form.catalog_path || null,
          webhook_url:  form.webhook_url  || null,
        }),
      });
      await handleSaveGithub();
      onSaved(saved);
      onToast("Settings saved", "success");
    } catch {
      onToast("Failed to save settings", "error");
    } finally {
      setSaving(false);
    }
  };

  const hasGitHub = ghSettings?.token_set && ghForm.repo;
  const hasPublishTarget = form.catalog_path || form.webhook_url || hasGitHub;

  return (
    <form onSubmit={handleSubmit} className="max-w-xl space-y-8">

      {/* ── Shop Identity ─────────────────────────────────────────── */}
      <Section
        title="Shop Identity"
        description="How your storefront is labelled inside opama and on the Publish tab."
      >
        <Field
          label="Shop Name"
          required
          hint="Displayed in the Storefront header and publish confirmations. Use your website's name or brand."
        >
          <input
            required
            value={form.site_name}
            onChange={e => set("site_name", e.target.value)}
            placeholder="yourshop.com"
            className={INPUT}
          />
        </Field>

        <Field
          label="Public Shop URL"
          hint="The buyer-facing URL for your shop. Used for the 'Visit shop' link and cross-referencing listings."
        >
          <input
            value={form.site_url}
            onChange={e => set("site_url", e.target.value)}
            placeholder="https://yourshop.com/collectibles"
            className={INPUT}
          />
          {form.site_url && (
            <a href={form.site_url} target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-1 text-xs text-indigo-600 hover:underline mt-0.5">
              <ExternalLink className="w-3 h-3" /> Visit shop
            </a>
          )}
        </Field>
      </Section>

      {/* ── Image URLs ────────────────────────────────────────────── */}
      <Section
        title="Image URLs"
        description="Item images uploaded to opama are stored as relative paths (e.g. /uploads/assets/42.jpg). Your shop needs absolute URLs to load them."
      >
        <Field
          label="API Base URL"
          hint={
            <>
              The publicly reachable root of this opama API. Prepended to every image path when
              the catalog is published — e.g. setting this to{" "}
              <Code>https://api.yourdomain.com</Code> turns{" "}
              <Code>/uploads/assets/42.jpg</Code> into{" "}
              <Code>https://api.yourdomain.com/uploads/assets/42.jpg</Code>.
            </>
          }
          warning={
            !form.public_api_url
              ? "Without this, item images will not load on your website. Images will appear broken in the catalog."
              : undefined
          }
        >
          <input
            value={form.public_api_url}
            onChange={e => { set("public_api_url", e.target.value); setImageUrlTestResult(null); }}
            placeholder="https://api.your-domain.com"
            className={INPUT}
          />
        </Field>

        <div>
          <button
            type="button"
            onClick={handleTestImageUrl}
            disabled={testingImageUrl || !form.public_api_url}
            className="flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            {testingImageUrl ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Wifi className="w-3.5 h-3.5" />}
            {testingImageUrl ? "Testing…" : "Test Image URL"}
          </button>

          {imageUrlTestResult && (
            <div className={`mt-2 flex items-start gap-1.5 text-xs rounded-lg px-2.5 py-2 border ${
              imageUrlTestResult.reachable
                ? "text-emerald-700 bg-emerald-50 border-emerald-200"
                : "text-red-700 bg-red-50 border-red-200"
            }`}>
              {imageUrlTestResult.reachable
                ? <CheckCircle2 className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                : <XCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />}
              <span>
                {imageUrlTestResult.reachable
                  ? <>Reachable — <Code>{imageUrlTestResult.tested_url}</Code> responded {imageUrlTestResult.status_code} ({imageUrlTestResult.content_type}).</>
                  : <>Could not reach <Code>{imageUrlTestResult.tested_url}</Code>{imageUrlTestResult.error ? `: ${imageUrlTestResult.error}` : "."}</>}
              </span>
            </div>
          )}
        </div>

        <CollapsibleExample title="Local development setup (using ngrok or Cloudflare Tunnel)">
          <p>In production set this to your real API domain. For local development the API must be reachable from the internet so your website can load the images. Options:</p>
          <ul className="list-disc list-inside space-y-1 mt-1">
            <li><strong>ngrok:</strong> run <Code>ngrok http 6000</Code> and set the HTTPS URL it gives you.</li>
            <li><strong>Cloudflare Tunnel:</strong> run <Code>cloudflared tunnel --url http://localhost:6000</Code>.</li>
            <li><strong>Same machine:</strong> if your storefront site and opama are on the same server, you can use the local IP (<Code>http://192.168.x.x:6000</Code>).</li>
          </ul>
        </CollapsibleExample>
      </Section>

      {/* ── GitHub Publishing ─────────────────────────────────────── */}
      <Section
        title="GitHub Publishing"
        description="The recommended way to publish for Cloudflare Pages sites. Opama commits catalog.json directly to your GitHub repo — Cloudflare detects the push and deploys the live site automatically within ~60 seconds."
      >
        <Callout>
          This replaces the manual workflow of generating catalog.json and pushing it to your site repo by hand. With this configured, the Publish button does everything in one click.
        </Callout>

        <Field
          label="Personal Access Token"
          hint={
            <>
              A GitHub PAT with <Code>contents: write</Code> permission on the target repository.
              Fine-grained tokens are recommended — scope it to only your storefront site repo.{" "}
              Create one at{" "}
              <a href="https://github.com/settings/tokens?type=beta" target="_blank" rel="noreferrer"
                className="text-indigo-600 hover:underline inline-flex items-center gap-0.5">
                github.com/settings/tokens <ExternalLink className="w-2.5 h-2.5" />
              </a>.
            </>
          }
        >
          <div className="relative">
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">
              <KeyRound className="w-4 h-4" />
            </div>
            <input
              type={showToken ? "text" : "password"}
              value={ghForm.token}
              onChange={e => setGh("token", e.target.value)}
              placeholder={ghSettings?.token_set
                ? `Current token: ${ghSettings.token_hint} — leave blank to keep`
                : "github_pat_…"}
              className={`${INPUT} pl-9 pr-10 font-mono`}
            />
            <button
              type="button"
              onClick={() => setShowToken(v => !v)}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
            >
              {showToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          {ghSettings?.token_set && (
            <div className="flex items-center gap-1.5 text-xs text-emerald-700 mt-1">
              <CheckCircle2 className="w-3.5 h-3.5" />
              Token configured ({ghSettings.token_hint}). Leave blank to keep it.
            </div>
          )}
        </Field>

        <Field
          label="Repository"
          hint={<>The GitHub repository that Cloudflare Pages deploys from. Format: <Code>owner/repo</Code></>}
        >
          <div className="relative">
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">
              <Github className="w-4 h-4" />
            </div>
            <input
              value={ghForm.repo}
              onChange={e => setGh("repo", e.target.value)}
              placeholder="youruser/yourshop-site"
              className={`${INPUT} pl-9 font-mono`}
            />
          </div>
          {ghForm.repo && (
            <a
              href={`https://github.com/${ghForm.repo}`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-xs text-indigo-600 hover:underline mt-0.5"
            >
              <ExternalLink className="w-3 h-3" /> View on GitHub
            </a>
          )}
        </Field>

        <div>
          <button
            type="button"
            onClick={handleTestGithubPublish}
            disabled={testingGithub || !ghForm.repo || (!ghForm.token && !ghSettings?.token_set)}
            className="flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            {testingGithub ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Wifi className="w-3.5 h-3.5" />}
            {testingGithub ? "Testing…" : "Test Connection"}
          </button>

          {githubTestResult && (
            <div className={`mt-2 flex items-start gap-1.5 text-xs rounded-lg px-2.5 py-2 border ${
              githubTestResult.connected
                ? "text-emerald-700 bg-emerald-50 border-emerald-200"
                : "text-red-700 bg-red-50 border-red-200"
            }`}>
              {githubTestResult.connected
                ? <CheckCircle2 className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                : <XCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />}
              <span>
                {githubTestResult.connected
                  ? <>
                      Connected to <strong>{githubTestResult.repo_full_name}</strong> ({githubTestResult.private ? "private" : "public"}).{" "}
                      {githubTestResult.can_push
                        ? "Token has write access."
                        : "Warning: token does not have write (push) access to this repo."}
                    </>
                  : githubTestResult.error}
              </span>
            </div>
          )}
        </div>

        <Field
          label="File Path in Repository"
          hint={<>Path to <Code>catalog.json</Code> relative to the repo root. This is the file that Cloudflare Pages serves as your shop's data source.</>}
        >
          <input
            value={ghForm.file_path}
            onChange={e => setGh("file_path", e.target.value)}
            placeholder="public/collectibles/catalog.json"
            className={INPUT_MONO}
          />
        </Field>

        <Field
          label="Commit Message"
          hint={<><Code>{"{n}"}</Code> is replaced with the number of items in the catalog.</>}
        >
          <input
            value={ghForm.commit_message}
            onChange={e => setGh("commit_message", e.target.value)}
            placeholder="chore: publish catalog ({n} items)"
            className={INPUT}
          />
        </Field>

        <CollapsibleExample title="How to create a Fine-grained Personal Access Token">
          <ol className="list-decimal list-inside space-y-1.5">
            <li>Go to <strong>GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens</strong></li>
            <li>Click <strong>Generate new token</strong></li>
            <li>Set <strong>Repository access</strong> to "Only select repositories" → choose your storefront site repo</li>
            <li>Under <strong>Repository permissions</strong>, set <strong>Contents</strong> to <em>Read and write</em></li>
            <li>Set an expiration (90 days recommended — you'll get an email when it's near expiry)</li>
            <li>Copy the token and paste it above</li>
          </ol>
        </CollapsibleExample>
      </Section>

      {/* ── Publish Target ────────────────────────────────────────── */}
      <Section
        title="Alternative Publish Targets"
        description="Use these if you're not deploying via GitHub, or as additional targets alongside GitHub publishing."
      >
        <Callout>
          Publishing generates a <Code>catalog.json</Code> array of your active listings and pushes it to your website so buyers see up-to-date prices, images, and availability. It does not go live until you click Publish on the Publish tab.
        </Callout>

        <Field
          label="Catalog File Path"
          hint={
            <>
              Absolute filesystem path <em>inside the backend Docker container</em> where{" "}
              <Code>catalog.json</Code> should be written. The backend container only has access
              to paths that are volume-mounted in <Code>docker-compose.yml</Code>. The{" "}
              <Code>./uploads</Code> directory is already mounted at <Code>/app/uploads</Code>.
            </>
          }
          warning={
            form.catalog_path && !form.catalog_path.startsWith("/app/uploads")
              ? "This path may not be accessible inside the Docker container. Only paths under /app/uploads are guaranteed to be available. Consider using the Webhook URL option instead to reach a service running on the host."
              : undefined
          }
        >
          <input
            value={form.catalog_path}
            onChange={e => set("catalog_path", e.target.value)}
            placeholder="/app/uploads/catalog.json"
            className={INPUT_MONO}
          />
        </Field>

        <CollapsibleExample title="File path examples">
          <ul className="space-y-2">
            <li>
              <strong>Write into opama's uploads folder (always accessible):</strong><br />
              <Code>/app/uploads/catalog.json</Code> — accessible at <Code>http://localhost:6000/uploads/catalog.json</Code>
            </li>
            <li>
              <strong>Write directly to your site repo (requires volume mount):</strong><br />
              Add <Code>- ../yourshop-site/public/collectibles:/mnt/storefront</Code> to the backend volumes in <Code>docker-compose.yml</Code>, then use <Code>/mnt/storefront/catalog.json</Code>.
            </li>
          </ul>
        </CollapsibleExample>

        <Field
          label="Webhook URL"
          hint={
            <>
              An HTTP endpoint that accepts a <Code>POST</Code> request with the full catalog JSON
              array as the body. Opama will POST to this URL on every publish. If the server
              returns a non-2xx response the publish will be marked as failed.
            </>
          }
        >
          <input
            value={form.webhook_url}
            onChange={e => set("webhook_url", e.target.value)}
            placeholder="http://host.docker.internal:3333/api/catalog"
            className={INPUT_MONO}
          />
        </Field>

        <CollapsibleExample title="Webhook examples">
          <p>If your storefront site has an admin server with a <Code>POST /api/catalog</Code> endpoint that writes the catalog, you can POST straight to it. From inside Docker, <Code>localhost</Code> refers to the container itself — use the special hostname <Code>host.docker.internal</Code> to reach services running on your host machine instead:</p>
          <div className="mt-2 space-y-1.5">
            <div>
              <strong>Local development (admin server on port 3333):</strong><br />
              <Code>http://host.docker.internal:3333/api/catalog</Code>
            </div>
            <div>
              <strong>Production:</strong><br />
              <Code>https://admin.yourshop.com/api/catalog</Code>
            </div>
          </div>
        </CollapsibleExample>

        {!hasPublishTarget && (
          <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2.5 text-xs text-amber-700">
            <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
            Neither option is configured. You can still preview and download the catalog on the Publish tab, but automatic publishing will not work.
          </div>
        )}

        {hasPublishTarget && (
          <div className="flex items-center gap-2 text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
            <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" />
            Publish target configured — the Publish tab is ready to use.
          </div>
        )}
      </Section>

      <div className="flex gap-3 pt-1 border-t border-slate-100">
        <button
          type="submit"
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium disabled:opacity-50"
        >
          <Save className="w-4 h-4" />
          {saving ? "Saving…" : "Save Settings"}
        </button>
      </div>
    </form>
  );
}
