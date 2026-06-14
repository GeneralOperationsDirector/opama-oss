/**
 * Tests for the module registry.
 *
 * Run with:  npm test  (inside opama-ui)
 *
 * These run in a Node environment (no DOM, no import.meta.env injection).
 * The registry defaults to "all modules enabled" when VITE_ENABLED_MODULES
 * is not set, which is the case here.
 */

import { describe, it, expect } from "vitest";
import {
  ALL_MODULES,
  getNavModules,
  isModuleEnabled,
  getModule,
  type ModuleDescriptor,
  type ModuleTier,
  type NavPosition,
} from "./moduleRegistry";

// ---------------------------------------------------------------------------
// ALL_MODULES structure
// ---------------------------------------------------------------------------

describe("ALL_MODULES", () => {
  it("contains the expected set of module IDs", () => {
    const ids = ALL_MODULES.map((m) => m.id);
    const expected = [
      "dashboard", "custom", "portfolio", "storefront",
      "pokemon", "grading", "system",
    ];
    expect(ids.sort()).toEqual(expected.sort());
  });

  it("has exactly 7 modules", () => {
    expect(ALL_MODULES).toHaveLength(7);
  });

  it("has no duplicate IDs", () => {
    const ids = ALL_MODULES.map((m) => m.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("every module has a non-empty id", () => {
    for (const m of ALL_MODULES) {
      expect(m.id).toBeTruthy();
      expect(typeof m.id).toBe("string");
    }
  });

  it("every module has a non-empty label", () => {
    for (const m of ALL_MODULES) {
      expect(m.label).toBeTruthy();
      expect(typeof m.label).toBe("string");
    }
  });

  it("every module has a valid tier", () => {
    const validTiers: ModuleTier[] = ["core", "free", "premium", "enterprise"];
    for (const m of ALL_MODULES) {
      expect(validTiers).toContain(m.tier);
    }
  });

  it("every module has a valid navPosition", () => {
    const validPositions: NavPosition[] = ["topnav", "dashboard-only", "hidden"];
    for (const m of ALL_MODULES) {
      expect(validPositions).toContain(m.navPosition);
    }
  });
});

// ---------------------------------------------------------------------------
// Tier expectations
// ---------------------------------------------------------------------------

describe("Module tiers", () => {
  it("dashboard is core", () => {
    expect(getModule("dashboard")?.tier).toBe("core");
  });

  it("custom (Collections) is core", () => {
    expect(getModule("custom")?.tier).toBe("core");
  });

  it("system is core", () => {
    expect(getModule("system")?.tier).toBe("core");
  });

  it("portfolio is premium", () => {
    expect(getModule("portfolio")?.tier).toBe("premium");
  });

  it("storefront is premium", () => {
    expect(getModule("storefront")?.tier).toBe("premium");
  });

  it("pokemon is premium", () => {
    expect(getModule("pokemon")?.tier).toBe("premium");
  });

  it("grading is premium", () => {
    expect(getModule("grading")?.tier).toBe("premium");
  });

  it("has exactly 3 core modules", () => {
    const core = ALL_MODULES.filter((m) => m.tier === "core");
    expect(core).toHaveLength(3);
  });

  it("has exactly 4 premium modules", () => {
    const premium = ALL_MODULES.filter((m) => m.tier === "premium");
    expect(premium).toHaveLength(4);
  });
});

// ---------------------------------------------------------------------------
// Nav position expectations
// ---------------------------------------------------------------------------

describe("Module navPositions", () => {
  it("dashboard is in topnav", () => {
    expect(getModule("dashboard")?.navPosition).toBe("topnav");
  });

  it("custom is in topnav", () => {
    expect(getModule("custom")?.navPosition).toBe("topnav");
  });

  it("portfolio is in topnav", () => {
    expect(getModule("portfolio")?.navPosition).toBe("topnav");
  });

  it("storefront is in topnav", () => {
    expect(getModule("storefront")?.navPosition).toBe("topnav");
  });

  it("pokemon is dashboard-only (not in top nav)", () => {
    expect(getModule("pokemon")?.navPosition).toBe("dashboard-only");
  });

  it("grading is dashboard-only (not in top nav)", () => {
    expect(getModule("grading")?.navPosition).toBe("dashboard-only");
  });

  it("system is hidden", () => {
    expect(getModule("system")?.navPosition).toBe("hidden");
  });
});

// ---------------------------------------------------------------------------
// getNavModules
// ---------------------------------------------------------------------------

describe("getNavModules()", () => {
  it("returns only topnav modules", () => {
    const nav = getNavModules();
    for (const m of nav) {
      expect(m.navPosition).toBe("topnav");
    }
  });

  it("returns exactly 4 nav modules (all enabled, default)", () => {
    expect(getNavModules()).toHaveLength(4);
  });

  it("includes dashboard, custom, portfolio, storefront in nav", () => {
    const ids = getNavModules().map((m) => m.id);
    expect(ids).toContain("dashboard");
    expect(ids).toContain("custom");
    expect(ids).toContain("portfolio");
    expect(ids).toContain("storefront");
  });

  it("excludes pokemon from nav (dashboard-only)", () => {
    const ids = getNavModules().map((m) => m.id);
    expect(ids).not.toContain("pokemon");
  });

  it("excludes grading from nav (dashboard-only)", () => {
    const ids = getNavModules().map((m) => m.id);
    expect(ids).not.toContain("grading");
  });

  it("excludes system from nav (hidden)", () => {
    const ids = getNavModules().map((m) => m.id);
    expect(ids).not.toContain("system");
  });
});

// ---------------------------------------------------------------------------
// isModuleEnabled (default: all enabled when VITE_ENABLED_MODULES not set)
// ---------------------------------------------------------------------------

describe("isModuleEnabled()", () => {
  it("returns true for dashboard in default state", () => {
    expect(isModuleEnabled("dashboard")).toBe(true);
  });

  it("returns true for custom in default state", () => {
    expect(isModuleEnabled("custom")).toBe(true);
  });

  it("returns true for portfolio in default state", () => {
    expect(isModuleEnabled("portfolio")).toBe(true);
  });

  it("returns true for storefront in default state", () => {
    expect(isModuleEnabled("storefront")).toBe(true);
  });

  it("returns true for pokemon in default state", () => {
    expect(isModuleEnabled("pokemon")).toBe(true);
  });

  it("returns true for grading in default state", () => {
    expect(isModuleEnabled("grading")).toBe(true);
  });

  it("returns true for system in default state", () => {
    expect(isModuleEnabled("system")).toBe(true);
  });

  it("returns true for unknown IDs in default state (all enabled)", () => {
    // When no env var is set, ALL ids are considered enabled
    expect(isModuleEnabled("some_future_plugin")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// getModule
// ---------------------------------------------------------------------------

describe("getModule()", () => {
  it("finds dashboard by ID", () => {
    const m = getModule("dashboard");
    expect(m).toBeDefined();
    expect(m?.label).toBe("Home");
  });

  it("finds custom by ID", () => {
    const m = getModule("custom");
    expect(m).toBeDefined();
    expect(m?.label).toBe("Collections");
  });

  it("finds grading by ID", () => {
    const m = getModule("grading");
    expect(m).toBeDefined();
    expect(m?.tier).toBe("premium");
  });

  it("returns undefined for unknown IDs", () => {
    expect(getModule("no_such_module")).toBeUndefined();
  });

  it("returns undefined for empty string", () => {
    expect(getModule("")).toBeUndefined();
  });

  it("returns a ModuleDescriptor with all required fields", () => {
    const m = getModule("portfolio") as ModuleDescriptor;
    expect(m).toHaveProperty("id");
    expect(m).toHaveProperty("label");
    expect(m).toHaveProperty("tier");
    expect(m).toHaveProperty("navPosition");
  });
});
