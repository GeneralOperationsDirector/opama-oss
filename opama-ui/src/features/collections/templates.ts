export interface CollectionTemplate {
  id: string;
  emoji: string;
  name: string;
  category: string;
  fields: string[];        // pre-populated custom field keys (values left blank for user)
  conditions?: string[];   // override the default condition list if category-specific
}

export const TEMPLATES: CollectionTemplate[] = [
  // ── Watches & Jewelry ────────────────────────────────────────
  {
    id: "watch",
    emoji: "⌚",
    name: "Watch",
    category: "Watch",
    fields: ["Brand", "Model", "Reference #", "Movement", "Case Size (mm)", "Dial Color", "Serial #", "Box & Papers"],
    conditions: ["Unworn", "Mint", "Excellent", "Very Good", "Good", "Fair", "Poor"],
  },
  {
    id: "jewelry",
    emoji: "💍",
    name: "Jewelry",
    category: "Jewelry",
    fields: ["Type", "Metal", "Primary Stone", "Stone Carat", "Total Weight (g)", "Hallmarks", "Designer", "Certificate #"],
  },
  {
    id: "handbag",
    emoji: "👜",
    name: "Handbag",
    category: "Handbag",
    fields: ["Brand", "Model", "Material", "Color", "Hardware", "Season/Year", "Serial #"],
    conditions: ["Brand New", "Pristine", "Excellent", "Very Good", "Good", "Fair"],
  },

  // ── Musical Instruments ───────────────────────────────────────
  {
    id: "guitar",
    emoji: "🎸",
    name: "Guitar",
    category: "Guitar",
    fields: ["Brand", "Model", "Year", "Serial #", "Color/Finish", "Body Style", "Pickups", "Neck Profile", "Case"],
  },
  {
    id: "vinyl",
    emoji: "🎵",
    name: "Vinyl Record",
    category: "Vinyl Record",
    fields: ["Artist", "Album", "Label", "Catalogue #", "Pressing Country", "Pressing Year", "Speed (RPM)", "Matrix #"],
    conditions: ["Sealed", "Mint", "Near Mint", "Very Good+", "Very Good", "Good", "Fair", "Poor"],
  },

  // ── Collectibles ─────────────────────────────────────────────
  {
    id: "sports-card",
    emoji: "🏆",
    name: "Sports Card",
    category: "Sports Card",
    fields: ["Player", "Year", "Brand/Set", "Card #", "Parallel/Variant", "Grade", "Grading Company", "Cert #", "Population"],
    conditions: ["PSA 10", "PSA 9", "PSA 8", "PSA 7", "BGS 9.5", "BGS 9", "CGC 9", "Raw"],
  },
  {
    id: "comic",
    emoji: "💥",
    name: "Comic Book",
    category: "Comic Book",
    fields: ["Publisher", "Title", "Issue #", "Cover Date", "Key Issue Notes", "Grade", "Grading Company", "Cert #", "Variant"],
    conditions: ["CGC 9.8", "CGC 9.6", "CGC 9.4", "CGC 9.2", "CGC 9.0", "CGC 8.5", "Raw VF/NM", "Raw VF", "Raw FN"],
  },
  {
    id: "action-figure",
    emoji: "🤖",
    name: "Action Figure",
    category: "Action Figure",
    fields: ["Character", "Line/Series", "Manufacturer", "Year", "Scale", "Accessories"],
    conditions: ["Sealed/MOC", "Mint Complete", "Complete", "Loose Good", "Loose Fair"],
  },
  {
    id: "lego",
    emoji: "🧱",
    name: "LEGO Set",
    category: "LEGO Set",
    fields: ["Set #", "Theme", "Name", "Year", "Piece Count"],
    conditions: ["Sealed", "Complete w/ Box & Instructions", "Complete", "Partial"],
  },

  // ── Art ──────────────────────────────────────────────────────
  {
    id: "art",
    emoji: "🎨",
    name: "Art",
    category: "Art",
    fields: ["Artist", "Title", "Medium", "Dimensions", "Year Created", "Edition (if print)", "Provenance", "Certificate of Authenticity"],
  },
  {
    id: "photograph",
    emoji: "📷",
    name: "Photography",
    category: "Photograph",
    fields: ["Photographer", "Title", "Process", "Dimensions", "Edition #", "Year", "Signed"],
  },

  // ── Spirits & Wine ───────────────────────────────────────────
  {
    id: "wine",
    emoji: "🍷",
    name: "Wine",
    category: "Wine",
    fields: ["Producer", "Appellation/Region", "Vintage", "Varietal(s)", "Bottle Size", "Cellar Location", "Bin #"],
    conditions: ["Pristine", "Very Good", "Good", "Average", "Poor"],
  },
  {
    id: "whisky",
    emoji: "🥃",
    name: "Whisky / Spirits",
    category: "Whisky",
    fields: ["Distillery", "Expression", "Age Statement", "ABV (%)", "Cask Type", "Bottle #", "Release Year", "Region"],
    conditions: ["Sealed", "Opened (>90%)", "Opened (75–90%)", "Opened (<75%)"],
  },

  // ── Numismatic & Philatelic ───────────────────────────────────
  {
    id: "coin",
    emoji: "🪙",
    name: "Coin",
    category: "Coin",
    fields: ["Country", "Denomination", "Year", "Mint Mark", "Grade", "Grading Company", "Cert #", "Composition"],
    conditions: ["MS-70", "MS-69", "MS-65", "MS-63", "MS-60", "AU-58", "VF-20", "Fine", "Good"],
  },
  {
    id: "stamp",
    emoji: "📮",
    name: "Stamp",
    category: "Stamp",
    fields: ["Country", "Year", "Scott #", "Denomination", "Colour", "Condition Notes", "Certificate"],
  },

  // ── Cameras & Electronics ─────────────────────────────────────
  {
    id: "camera",
    emoji: "📸",
    name: "Camera",
    category: "Camera",
    fields: ["Brand", "Model", "Type", "Serial #", "Sensor/Format", "Shutter Count", "Accessories Included"],
  },
  {
    id: "lens",
    emoji: "🔭",
    name: "Camera Lens",
    category: "Lens",
    fields: ["Brand", "Focal Length", "Max Aperture", "Mount", "Serial #", "Filter Size (mm)", "Elements/Groups"],
  },
  {
    id: "console",
    emoji: "🎮",
    name: "Video Game / Console",
    category: "Video Game",
    fields: ["Platform", "Title/Model", "Region", "Publisher", "Year", "Complete in Box"],
    conditions: ["Sealed", "CIB Mint", "CIB Good", "Loose Mint", "Loose Good", "For Parts"],
  },

  // ── Fashion ──────────────────────────────────────────────────
  {
    id: "sneakers",
    emoji: "👟",
    name: "Sneakers",
    category: "Sneakers",
    fields: ["Brand", "Model", "Colorway", "Style Code (SKU)", "Size (US)", "Size (EU)", "Release Year"],
    conditions: ["DS/Deadstock", "Near Deadstock", "Very Good", "Good", "Worn"],
  },

  // ── Precious Metals ──────────────────────────────────────────
  {
    id: "precious-metal",
    emoji: "✨",
    name: "Precious Metal",
    category: "Precious Metal",
    fields: ["Metal", "Form (Bar/Coin/Round)", "Weight (oz)", "Purity", "Mint/Brand", "Serial #"],
  },

  // ── Memorabilia ──────────────────────────────────────────────
  {
    id: "memorabilia",
    emoji: "🏅",
    name: "Signed Memorabilia",
    category: "Signed Memorabilia",
    fields: ["Item Type", "Signed By", "Inscribed Text", "Event/Date", "Authentication Company", "Cert #", "Sport/Category"],
  },

  // ── Vehicles ─────────────────────────────────────────────────
  {
    id: "car",
    emoji: "🚗",
    name: "Vehicle",
    category: "Vehicle",
    fields: ["Make", "Model", "Year", "VIN", "Mileage", "Color", "Engine", "Transmission", "Title Status"],
  },

  // ── Financial Assets ─────────────────────────────────────────
  {
    id: "stock",
    emoji: "📈",
    name: "Stock",
    category: "Stock",
    fields: ["Ticker Symbol", "Company Name", "Exchange", "Shares Held", "Avg. Cost Per Share", "Broker / Account", "Sector", "ISIN"],
  },
  {
    id: "bond",
    emoji: "🏦",
    name: "Bond",
    category: "Bond",
    fields: ["Issuer", "Bond Type", "Face Value", "Coupon Rate (%)", "Maturity Date", "CUSIP / ISIN", "Credit Rating", "Broker / Account", "Purchase Price"],
  },
  {
    id: "crypto",
    emoji: "₿",
    name: "Cryptocurrency",
    category: "Cryptocurrency",
    fields: ["Asset / Ticker", "Network", "Wallet / Exchange", "Quantity", "Avg. Cost Per Unit", "Wallet Address", "Staking / Yield (%)"],
  },

  // ── Catch-all ────────────────────────────────────────────────
  {
    id: "custom",
    emoji: "📦",
    name: "Custom",
    category: "",
    fields: [],
  },
];

export const TEMPLATE_MAP = Object.fromEntries(TEMPLATES.map((t) => [t.id, t]));

/** category string → first matching template (case-insensitive) */
export const CATEGORY_TO_TEMPLATE = Object.fromEntries(
  TEMPLATES.map((t) => [t.category.toLowerCase(), t])
) as Record<string, CollectionTemplate>;
