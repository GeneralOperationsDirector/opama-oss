import React from "react";
import Select from "../../../shared/atoms/Select";
import Button from "../../../shared/atoms/Button";
import { ArrowUpDown, Search as SearchIcon } from "lucide-react";
import type { CanonRarity } from "./utils";

export type FilterMode = "all" | "missing" | "owned";
export type SeriesOrder = "asc" | "desc";
export type SortMode = "set" | "stageAsc" | "stageDesc" | "evoAsc" | "evoDesc";

export default function PokedexControls({
  setQuery, onSetQuery,
  seriesOptions, seriesFilter, onSeriesFilter,
  seriesOrder, onToggleSeriesOrder,
  filterMode, onFilterMode,
  rarityFilter, onRarityFilter, rarityOptions,
  sortMode, onSortMode,
}: {
  setQuery: string;
  onSetQuery: (v: string) => void;

  seriesOptions: string[];
  seriesFilter: string;
  onSeriesFilter: (v: string) => void;

  seriesOrder: SeriesOrder;
  onToggleSeriesOrder: () => void;

  filterMode: FilterMode;
  onFilterMode: (v: FilterMode) => void;

  rarityFilter: CanonRarity | "";
  onRarityFilter: (v: CanonRarity | "") => void;
  rarityOptions: CanonRarity[];

  sortMode: SortMode;
  onSortMode: (v: SortMode) => void;
}) {
  return (
    <div className="grid gap-3 lg:grid-cols-[1fr,220px,auto,auto,220px,260px] mb-3">
      {/* Search sets */}
      <div className="flex items-center gap-2 rounded-2xl border px-3 py-2 shadow-sm bg-white/80">
        <SearchIcon className="h-4 w-4 opacity-60" />
        <input
          type="text"
          placeholder="Search sets… name, series, or id"
          value={setQuery}
          onChange={(e) => onSetQuery(e.target.value)}
          className="w-full bg-transparent outline-none text-sm"
        />
        {setQuery && (
          <button className="text-xs opacity-70 hover:opacity-100" onClick={() => onSetQuery("")}>
            Clear
          </button>
        )}
      </div>

      {/* Series (chronological) */}
      <Select value={seriesFilter} onChange={(e) => onSeriesFilter(e.target.value)}>
        <option value="">All series</option>
        {seriesOptions.map((s) => (
          <option key={s} value={s}>{s}</option>
        ))}
      </Select>

      {/* Series order toggle */}
      <Button
        variant="secondary"
        onClick={onToggleSeriesOrder}
        title={seriesOrder === "asc" ? "Oldest → Newest (click to flip)" : "Newest → Oldest (click to flip)"}
      >
        <ArrowUpDown className="w-4 h-4" />
        {seriesOrder === "asc" ? "Oldest → Newest" : "Newest → Oldest"}
      </Button>

      {/* Owned/Missing tri-state */}
      <div className="flex items-center gap-3 rounded-xl border px-3 py-2 bg-white/70">
        <label className="inline-flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            className="accent-indigo-600"
            checked={filterMode === "owned"}
            onChange={(e) => onFilterMode(e.target.checked ? "owned" : "all")}
          />
          Show only owned
        </label>
        <label className="inline-flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            className="accent-indigo-600"
            checked={filterMode === "missing"}
            onChange={(e) => onFilterMode(e.target.checked ? "missing" : (filterMode === "missing" ? "all" : filterMode))}
          />
          Show only missing
        </label>
      </div>

      {/* Rarity */}
      <Select
        value={rarityFilter}
        onChange={(e) => onRarityFilter((e.target.value || "") as CanonRarity | "")}
        title="Filter cards in the expanded set by rarity"
      >
        <option value="">All rarities</option>
        {rarityOptions.map((r) => (
          <option key={r} value={r}>{r}</option>
        ))}
      </Select>

      {/* Sort */}
      <Select
        value={sortMode}
        onChange={(e) => onSortMode(e.target.value as SortMode)}
        title="Sort cards within the expanded set"
      >
        <option value="set">Sort: Set order</option>
        <option value="stageAsc">Sort: Stage (Basic → Stage 1 → Stage 2 → ex)</option>
        <option value="stageDesc">Sort: Stage (ex → Stage 2 → Stage 1 → Basic)</option>
        <option value="evoAsc">Sort: Evolution (Charmander → Charmeleon → Charizard → Charizard ex)</option>
        <option value="evoDesc">Sort: Evolution (reverse)</option>
      </Select>
    </div>
  );
}
