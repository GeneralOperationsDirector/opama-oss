/** ******************************************************************
 * Organization switcher (pool tenancy).
 *
 * Reads GET /auth/orgs (every org the caller can act in, role included) and lets
 * the user pick the active one. Switching persists the choice (lib/activeOrg) —
 * which the API client sends as `X-Org-Id` on every request — then reloads so all
 * data refetches under the new org. Hidden for solo collectors (a single org).
 ******************************************************************* */

import { useEffect, useRef, useState } from "react";
import { Building2, ChevronDown, Check } from "lucide-react";
import { api } from "../lib/api";
import { getActiveOrgId, setActiveOrgId } from "../lib/activeOrg";

type OrgSummary = {
  id: number;
  name: string;
  slug: string;
  role: string;
  is_personal: boolean;
  plan_tier: string;
  plan_status: string;
};

export default function OrgSwitcher() {
  const [orgs, setOrgs] = useState<OrgSummary[]>([]);
  const [open, setOpen] = useState(false);
  const activeId = getActiveOrgId();
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    api<OrgSummary[]>("/auth/orgs")
      .then((list) => alive && setOrgs(list))
      .catch(() => {/* non-fatal — switcher just stays hidden */});
    return () => { alive = false; };
  }, []);

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [open]);

  // Nothing to switch between — don't clutter the header for solo collectors.
  if (orgs.length <= 1) return null;

  // Active = stored choice, else the first (personal sorts first server-side).
  const active = orgs.find((o) => o.id === activeId) ?? orgs[0];

  const choose = (id: number) => {
    setOpen(false);
    if (id === active.id) return;
    setActiveOrgId(id);
    // Reload so every view refetches under the new org scope.
    window.location.reload();
  };

  return (
    <div ref={wrapRef} className="relative flex-shrink-0">
      <button
        onClick={() => setOpen((v) => !v)}
        title="Switch organization"
        className="h-8 flex items-center gap-1.5 px-2.5 rounded-lg text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-colors max-w-[180px]"
      >
        <Building2 className="w-4 h-4 flex-shrink-0" />
        <span className="hidden md:inline truncate">{active.name}</span>
        <ChevronDown className="w-3.5 h-3.5 flex-shrink-0 text-slate-400" />
      </button>

      {open && (
        <div className="absolute right-0 mt-1 w-60 rounded-lg border border-slate-200 bg-white shadow-lg py-1 z-20">
          <div className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Organizations
          </div>
          {orgs.map((o) => (
            <button
              key={o.id}
              onClick={() => choose(o.id)}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-slate-50 transition-colors"
            >
              <span className="flex-1 min-w-0">
                <span className="block truncate text-slate-800">{o.name}</span>
                <span className="block text-xs text-slate-400 capitalize">
                  {o.role}{o.is_personal ? " · personal" : ""}
                </span>
              </span>
              {o.id === active.id && <Check className="w-4 h-4 text-indigo-600 flex-shrink-0" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
