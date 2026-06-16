import React, { createContext, useContext, useEffect, useState } from "react";
import { API_BASE } from "../lib/api";
import { getModule } from "../lib/moduleRegistry";

export interface LicenseState {
  loading: boolean;
  valid: boolean;
  tier: string;
  modules: string[] | "*";
  customer: string | null;
  expiresAt: string | null;
  message: string;
}

interface LicenseContextType extends LicenseState {
  isModuleLicensed: (moduleId: string) => boolean;
}

const TIER_RANK: Record<string, number> = { core: 0, free: 1, premium: 2, enterprise: 3 };

const LOADING_STATE: LicenseState = {
  loading: true,
  valid: false,
  tier: "dev",
  modules: "*",
  customer: null,
  expiresAt: null,
  message: "",
};

const LicenseContext = createContext<LicenseContextType | undefined>(undefined);

export function useLicense() {
  const ctx = useContext(LicenseContext);
  if (!ctx) throw new Error("useLicense must be used within a LicenseProvider");
  return ctx;
}

function isModuleLicensedFor(state: LicenseState, moduleId: string): boolean {
  // While loading, optimistically show everything (avoids flash of lock icons)
  if (state.loading) return true;

  if (state.modules === "*") return true;

  if (Array.isArray(state.modules)) {
    if (state.modules.includes(moduleId)) return true;
    // Non-empty list → strict: only listed modules are enabled
    if (state.modules.length > 0) {
      // Core modules are always accessible regardless of explicit list
      const moduleDef = getModule(moduleId);
      if (moduleDef?.tier === "core") return true;
      return false;
    }
  }

  // Tier-based check
  const moduleDef = getModule(moduleId);
  if (!moduleDef) return false;
  return (TIER_RANK[moduleDef.tier] ?? 0) <= (TIER_RANK[state.tier] ?? 0);
}

export function LicenseProvider({ children }: { children: React.ReactNode }) {
  const [license, setLicense] = useState<LicenseState>(LOADING_STATE);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/license`)
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        setLicense({
          loading: false,
          valid: data.valid ?? false,
          tier: data.tier ?? "dev",
          modules: data.modules ?? "*",
          customer: data.customer ?? null,
          expiresAt: data.expires_at ?? null,
          message: data.message ?? "",
        });
      })
      .catch(() => {
        if (cancelled) return;
        // On error, default to all-enabled so a broken license endpoint
        // never locks users out of their instance.
        setLicense({ loading: false, valid: false, tier: "dev", modules: "*", customer: null, expiresAt: null, message: "license check failed" });
      });
    return () => { cancelled = true; };
  }, []);

  const value: LicenseContextType = {
    ...license,
    isModuleLicensed: (id) => isModuleLicensedFor(license, id),
  };

  return (
    <LicenseContext.Provider value={value}>
      {children}
    </LicenseContext.Provider>
  );
}
