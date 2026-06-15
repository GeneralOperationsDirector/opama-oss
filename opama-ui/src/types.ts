// Shared types used across tabs/components

export type AppModule = "dashboard" | "pokemon" | "custom" | "portfolio" | "grading" | "storefront" | "system" | "plugin_store" | "insurance" | "vehicles" | "real_estate";

export type PokemonTab = "catalog" | "inventory" | "decks" | "showcase" | "wishlist" | "trade" | "suggest" | "ebay" | "pokedex" | "portfolio";

export type Tab = PokemonTab | "profile" | "dashboard";
export interface SetRow {
  id: string;
  name: string;
  series: string;
}

export interface CardRow {
  id: string;
  name: string;
  set_id: string;
  rules_text?: string | null;
  retreat_cost?: number | null;
}

export interface Deck {
  id: number;
  user_id: number;
  name: string;
  format?: string | null;
  strategy_notes?: string | null;
}

export interface DeckCard {
  id: number;
  deck_id: number;
  card_id: string;
  quantity: number;
  role?: string | null;
}

export interface InvCardLite {
  id: string;
  name: string;
  set_id: string;
  number?: string | null;
  rarity?: string | null;
  image_small?: string | null;
  image_large?: string | null;
  types?: string | null;
  subtypes?: string | null;
  hp?: string | null;
  ability_name?: string | null;
  ability_text?: string | null;
  attack1_damage?: string | null;
  attack2_damage?: string | null;
  attack3_damage?: string | null;
  weaknesses?: string | null;
  resistances?: string | null;
  retreat_cost?: number | null;
  stage?: string | null;
}

export interface InvRow {
  inventory: {
    id: number;
    user_id: number;
    card_id: string;
    quantity: number;
    condition?: string | null;
    is_reverse_holo?: boolean | null;
  };
  card: InvCardLite | null;
}

export interface DeckCardHydrated extends DeckCard {
  card?: {
    id: string;
    name: string;
    set_id: string;
    number?: string | null;
    rarity?: string | null;
    image_small?: string | null;
  } | null;
}

export interface DeckWithCards {
  deck: Deck;
  cards: DeckCardHydrated[];
}

// PATCH shapes
export type PatchDeckCardPayload = { quantity_delta?: number; role?: string; };
export type PatchInventoryQuantityResponse = { deleted: boolean; item?: { id: number; quantity: number }; id?: number; };
export type DeleteInventoryResponse = { ok: boolean; id: number; };

// Portfolio types
export interface CardValuation {
  card_id: string;
  card_name: string;
  set_id: string;
  set_name: string;
  quantity: number;
  condition: string;
  unit_price: number;
  total_value: number;
  purchase_price?: number | null;
  unrealized_gain?: number | null;
  unrealized_gain_pct?: number | null;
  price_source: string;
  confidence_score?: number | null;
  price_change_7d?: number | null;
  price_change_30d?: number | null;
}

export interface ConditionBreakdown {
  count: number;
  value: number;
  percentage: number;
}

export interface PortfolioValue {
  user_id: number;
  total_value: number;
  total_cost: number;
  unrealized_gain: number;
  unrealized_gain_pct?: number | null;
  currency: string;
  calculated_at: string;
  total_items: number;
  unique_cards: number;
  breakdown: Record<string, ConditionBreakdown>;
  top_holdings: CardValuation[];
  graded_value: number;
  graded_count: number;
}

export interface SnapshotSummary {
  date: string;
  total_value: number;
  total_items: number;
  unrealized_gain?: number | null;
}

export interface PortfolioHistory {
  user_id: number;
  period: {
    start_date: string;
    end_date: string;
    days: number;
  };
  snapshots: SnapshotSummary[];
  summary: {
    start_value: number;
    end_value: number;
    absolute_change: number;
    percentage_change: number;
    peak_value: number;
    trough_value: number;
  };
}

export interface SaleTransaction {
  id: number;
  user_id: number;
  card_id: string;
  card_name: string;
  quantity_sold: number;
  condition: string;
  sale_price: number;
  unit_price: number;
  fees: number;
  net_proceeds: number;
  original_cost: number;
  realized_gain: number;
  realized_gain_pct?: number | null;
  sale_date: string;
  platform?: string | null;
  currency: string;
}

export interface RealizedGainsSummary {
  user_id: number;
  period?: { days?: number } | null;
  total_sales: number;
  total_proceeds: number;
  total_fees: number;
  net_proceeds: number;
  total_cost_basis: number;
  total_realized_gain: number;
  total_realized_gain_pct: number;
  profitable_sales: number;
  losing_sales: number;
  breakeven_sales: number;
  best_sale?: SaleTransaction | null;
  worst_sale?: SaleTransaction | null;
}

// Showcase types
export interface Showcase {
  id: number;
  user_id: number;
  title: string;
  description?: string | null;
  is_public: boolean;
  created_at: string;
  updated_at: string;
}

export interface ShowcaseCardItem {
  id: number;
  showcase_id: number;
  card_id: string;
  quantity: number;
  notes?: string | null;
  added_at: string;
  card?: {
    id: string;
    name: string;
    set_id?: string | null;
    number?: string | null;
    rarity?: string | null;
    image_small?: string | null;
    image_large?: string | null;
    category?: string | null;
    source?: "asset" | "catalog";
  } | null;
}

export interface ShowcaseWithCards {
  showcase: Showcase;
  cards: ShowcaseCardItem[];
}
