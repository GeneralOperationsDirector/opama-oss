export type CardRow = {
  id: string;
  name: string;
  set_id: string;
  number?: string | null;
  image_small?: string | null;
  image_large?: string | null;
  rarity?: string | null;
  stage?: string | null;     // optional, from API if present
  subtypes?: string | null;  // e.g., "Basic", "Stage 1", "ex"
};

export type SetMeta = { total: number | null; items: CardRow[]; loading: boolean; lastLoadedOffset: number };

export type CanonRarity =
  | "Common" | "Uncommon" | "Rare" | "Holo Rare" | "Ultra Rare"
  | "Illustration Rare" | "Special Illustration Rare"
  | "Hyper Rare" | "Secret Rare" | "ACE SPEC" | "Amazing Rare" | "Promo" | "Other";

export const CANON_RARITIES: CanonRarity[] = [
  "Common","Uncommon","Rare","Holo Rare","Ultra Rare","Illustration Rare","Special Illustration Rare",
  "Hyper Rare","Secret Rare","ACE SPEC","Amazing Rare","Promo","Other",
];

export function canonRarity(r?: string | null): CanonRarity {
  const t = (r || "").toLowerCase().trim();
  if (!t) return "Other";
  if (t.includes("common")) return "Common";
  if (t.includes("uncommon")) return "Uncommon";
  if (t.includes("special") && t.includes("illustration")) return "Special Illustration Rare";
  if (t.includes("illustration")) return "Illustration Rare";
  if (t.includes("holo")) return "Holo Rare";
  if (t.includes("ultra")) return "Ultra Rare";
  if (t.includes("hyper")) return "Hyper Rare";
  if (t.includes("secret")) return "Secret Rare";
  if (t.includes("ace spec")) return "ACE SPEC";
  if (t.includes("amazing")) return "Amazing Rare";
  if (t.includes("promo")) return "Promo";
  if (/\brare\b/.test(t)) return "Rare";
  return "Other";
}

// ---- Stage + evolution helpers ----
export type StageBucket = "Basic" | "Stage 1" | "Stage 2" | "ex" | "Other";

export function canonStage(c: { stage?: string | null; subtypes?: string | null; name?: string | null }): StageBucket {
  const raw = `${c.stage ?? ""} ${c.subtypes ?? ""}`.toLowerCase();
  if (raw.includes("basic")) return "Basic";
  if (raw.includes("stage 1")) return "Stage 1";
  if (raw.includes("stage 2")) return "Stage 2";
  if (/\bex\b/i.test(c.name ?? "") || /\bex\b/.test(raw)) return "ex";
  return "Other";
}

export const STAGE_RANK_ASC: Record<StageBucket, number> = { Basic: 0, "Stage 1": 1, "Stage 2": 2, ex: 3, Other: 9 };
export const STAGE_RANK_DESC: Record<StageBucket, number> = { ex: 0, "Stage 2": 1, "Stage 1": 2, Basic: 3, Other: 9 };

/** Normalize a card name into a species family key (e.g., "M Charizard-EX" → "charizard"). */
export function speciesKey(name?: string | null): string {
  if (!name) return "";
  let s = name.toLowerCase();

  s = s.replace(/^(m\s+|dark\s+|light\s+|team\s+rocket\s+|ancient\s+|alolan\s+|galarian\s+|hisui[a-z]*\s+)/, "");
  s = s
    .replace(/\bmega\b/g, "")
    .replace(/\bex\b/g, "")
    .replace(/\bgx\b/g, "")
    .replace(/\bvmax\b/g, "")
    .replace(/\bv[-\s]?star\b/g, "")
    .replace(/\bv\b/g, "")
    .replace(/\blv\.?x\b/g, "")
    .replace(/\bbreak\b/g, "")
    .replace(/[▢◇☆★]/g, "")
    .replace(/\b(prism\s+star|delta|δ|prime|legend)\b/g, "");
  s = s.split(" - ")[0];
  s = s.replace(/\s*\([^)]*\)\s*$/, "");
  s = s.replace(/\s+/g, " ").trim();

  const firstTwo = s.split(" ").slice(0, 2).join(" ");
  const keepTwo = /^(mr\.|tapu|type:|ho-oh|porygon-z|mime jr\.)/.test(firstTwo);
  return (keepTwo ? firstTwo : s.split(" ")[0]).trim();
}

export function getCardImageUrls(card: { image_small?: string | null; image_large?: string | null; set_id?: string | null; number?: string | null; id: string }) {
  let setId = card.set_id?.trim() || null;
  let num = card.number?.trim() || null;
  if ((!setId || !num) && card.id.includes("-")) {
    const [sid, n] = card.id.split("-", 2);
    if (!setId) setId = sid || null;
    if (!num) num = n || null;
  }
  // Priority 1: Local images
  if (setId && num) {
    const localUrl = `/img/${setId}_clean/${setId}-${num}.png`;
    return { small: localUrl, large: localUrl };
  }
  // Priority 2: Database URLs
  const dbSmall = card.image_small?.trim() || null;
  const dbLarge = card.image_large?.trim() || null;
  if (dbSmall || dbLarge) return { small: dbSmall ?? dbLarge, large: dbLarge ?? dbSmall };
  // Priority 3: Remote API fallback
  if (setId && num) {
    const base = `https://images.pokemontcg.io/${setId}/${num}`;
    return { small: `${base}.png`, large: `${base}/large.png` };
  }
  return { small: null as string | null, large: null as string | null };
}

/** Heuristic series ordering if `release_date` missing. */
export const SERIES_PREFIX_YEAR: Record<string, number> = {
  base: 1999, gym: 2000, neo: 2000, ecard: 2002, ex: 2003, pop: 2004,
  dp: 2007, pl: 2009, hgss: 2010, bw: 2011, xy: 2014, sm: 2016, swsh: 2020, sv: 2023,
};
