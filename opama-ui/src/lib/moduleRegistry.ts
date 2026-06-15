/**
 * Module registry for opama.
 *
 * Defines every known frontend module with its metadata. Controls which
 * modules appear in the top nav and which are gated by VITE_ENABLED_MODULES.
 *
 * VITE_ENABLED_MODULES (build-time env var):
 *   unset or empty → all modules are enabled (default / full install)
 *   "custom_assets,portfolio,system" → only those modules render
 *
 * Modules are either:
 *   navPosition: "topnav"         → button in the header module bar
 *   navPosition: "dashboard-only" → accessible from dashboard cards only
 *   navPosition: "hidden"         → no nav entry (system/profile)
 */

export type ModuleTier = "core" | "free" | "premium" | "enterprise";
export type NavPosition = "topnav" | "dashboard-only" | "hidden";

export interface ModuleDescriptor {
  id: string;
  label: string;
  emoji?: string;
  tier: ModuleTier;
  navPosition: NavPosition;
  description?: string;
}

export const ALL_MODULES: ModuleDescriptor[] = [
  {
    id: "dashboard",
    label: "Home",
    tier: "core",
    navPosition: "topnav",
    description: "Overview of your collections and quick access to modules",
  },
  {
    id: "custom",
    label: "Collections",
    emoji: "📦",
    tier: "core",
    navPosition: "topnav",
    description: "Manage any type of personal asset or collectible",
  },
  {
    id: "portfolio",
    label: "Portfolio",
    emoji: "📈",
    tier: "premium",
    navPosition: "topnav",
    description: "Portfolio valuation, historical tracking, and P&L analysis",
  },
  {
    id: "storefront",
    label: "Storefront",
    emoji: "🛒",
    tier: "premium",
    navPosition: "topnav",
    description: "Publish your collection for sale online",
  },
  {
    id: "pokemon",
    label: "Pokémon TCG",
    emoji: "⚡",
    tier: "premium",
    navPosition: "dashboard-only",
    description: "Catalog, inventory, deck building, trading, and portfolio valuation",
  },
  {
    id: "grading",
    label: "Card Grader",
    emoji: "🔬",
    tier: "premium",
    navPosition: "dashboard-only",
    description: "AI-powered card grading using computer vision and OCR",
  },
  {
    id: "system",
    label: "System",
    tier: "core",
    navPosition: "hidden",
    description: "System diagnostics and health information",
  },
  {
    id: "plugin_store",
    label: "Modules",
    emoji: "🧩",
    tier: "core",
    navPosition: "topnav",
    description: "Enable built-in modules and install community extensions",
  },
  {
    id: "insurance",
    label: "Insurance",
    emoji: "🛡️",
    tier: "free",
    navPosition: "dashboard-only",
    description: "Track insurance policies, scheduled coverage, and appraisal records",
  },
  {
    id: "vehicles",
    label: "Vehicles",
    emoji: "🚗",
    tier: "free",
    navPosition: "dashboard-only",
    description: "Track service history, mileage, and registration documents",
  },
  {
    id: "real_estate",
    label: "Property",
    emoji: "🏠",
    tier: "free",
    navPosition: "dashboard-only",
    description: "Track mortgage details, valuations, and property tax records",
  },
];

// Resolve enabled set from build-time env var.
// Vite replaces import.meta.env.VITE_ENABLED_MODULES at build time.
const _raw = (import.meta.env.VITE_ENABLED_MODULES ?? "").trim();
const _enabledSet: Set<string> | null = _raw
  ? new Set(_raw.split(",").map((s: string) => s.trim()).filter(Boolean))
  : null; // null = all enabled

// Marketplace module ID → frontend module ID mapping.
// active-plugins now returns module-level IDs (e.g. "pokemon_tcg") not service IDs.
const _BACKEND_TO_FRONTEND: Record<string, string> = {
  pokemon_tcg: "pokemon",
  grading: "grading",
  portfolio: "portfolio",
  storefront: "storefront",
  ai: "ai",
  showcase: "showcase",
  insurance: "insurance",
  vehicles: "vehicles",
  real_estate: "real_estate",
};

// All known builtin frontend module IDs (the values of _BACKEND_TO_FRONTEND).
const _ALL_BUILTIN_FRONTEND_IDS = new Set(Object.values(_BACKEND_TO_FRONTEND));

// Module IDs dynamically activated from the backend's active-plugins list.
let _dynamicActiveModuleIds: Set<string> = new Set();

// Builtin modules the backend reported as NOT running. Takes priority over
// _enabledSet so that disabling a module on the main stack (no VITE_ENABLED_MODULES)
// actually hides it from the nav and blocks content rendering.
let _disabledBuiltinIds: Set<string> = new Set();
let _backendDataFetched = false;

/** Translates backend plugin IDs to frontend module IDs; also computes which
 *  known builtins are absent from the active list so they can be blocked. */
export function setActiveBackendPlugins(backendIds: string[]): void {
  const activeSet = new Set(
    backendIds.flatMap((id) => {
      const mapped = _BACKEND_TO_FRONTEND[id];
      return mapped ? [mapped] : [];
    })
  );
  _dynamicActiveModuleIds = activeSet;
  _disabledBuiltinIds = new Set(
    [..._ALL_BUILTIN_FRONTEND_IDS].filter((fid) => !activeSet.has(fid))
  );
  _backendDataFetched = true;
}

/** Returns true if the module with the given ID is enabled. */
export function isModuleEnabled(id: string): boolean {
  // A builtin explicitly absent from the backend's active list is always blocked,
  // even on full installs where _enabledSet is null.
  if (_backendDataFetched && _disabledBuiltinIds.has(id)) return false;
  return _enabledSet === null || _enabledSet.has(id) || _dynamicActiveModuleIds.has(id);
}

/** Returns module descriptors that should appear in the top nav. */
export function getNavModules(): ModuleDescriptor[] {
  return ALL_MODULES.filter(
    (m) => m.navPosition === "topnav" && isModuleEnabled(m.id)
  );
}

/** Look up a module descriptor by ID. */
export function getModule(id: string): ModuleDescriptor | undefined {
  return ALL_MODULES.find((m) => m.id === id);
}
