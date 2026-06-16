/**
 * TransferPanel
 *
 * Shown below the grade result when identification data is available
 * (or always, so users can still manually add to collection).
 *
 * Flow:
 *   1. Shows identified card info — name, number, set — all editable.
 *   2. Shows catalog match preview if found.
 *   3. User picks destination: Pokémon inventory or custom collection item.
 *   4. Fills in condition, quantity, price, grade company, then submits.
 */

import React, { useEffect, useState } from "react";
import { CheckCircle, ChevronDown, ChevronUp, ExternalLink, Loader2, Search } from "lucide-react";
import { api } from "../../lib/api";
import type { CardIdentification, GradeResult, TransferIn, TransferOut } from "./types";

const CONDITIONS = ["NM", "LP", "MP", "HP", "DMG"];
const COMPANIES  = ["PSA", "CGC", "BGS", "SGC"];

interface CatalogCard {
  id: string;
  name: string;
  set_id: string;
  number: string | null;
  image_small: string | null;
  rarity: string | null;
}

interface Props {
  result: GradeResult;
  onTransferred: (destination: string, itemId: number) => void;
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
}

export default function TransferPanel({ result, onTransferred, onToast }: Props) {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<"identity" | "form">("identity");
  const [destination, setDestination] = useState<"inventory" | "asset" | null>(null);

  // Identity fields (editable — user can correct what Claude read)
  const id = result.identification;
  const [cardName, setCardName]     = useState(id?.name ?? "");
  const [cardNumber, setCardNumber] = useState(id?.number ?? "");
  const [setName, setSetName]       = useState(id?.set_name ?? "");

  // Catalog match state
  const [matchedCard, setMatchedCard] = useState<CatalogCard | null>(null);
  const [searching, setSearching]     = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<CatalogCard[]>([]);

  // Transfer form fields
  const [condition, setCondition]       = useState("NM");
  const [quantity, setQuantity]         = useState(1);
  const [purchasePrice, setPurchasePrice] = useState("");
  const [estimatedValue, setEstimatedValue] = useState("");
  const [gradingCompany, setGradingCompany] = useState("");
  const [actualGrade, setActualGrade]   = useState("");
  const [notes, setNotes]               = useState("");

  const [submitting, setSubmitting]     = useState(false);
  const [transferred, setTransferred]   = useState(result.transferred_to !== null);

  // Auto-load catalog match if identification found one.
  // When the card loads, prefer the catalog's own number over whatever the
  // vision model extracted (e.g. it may have read the Pokédex number instead).
  useEffect(() => {
    if (id?.catalog_card_id) {
      api<CatalogCard>(`/cards/${encodeURIComponent(id.catalog_card_id)}`)
        .then((card) => {
          setMatchedCard(card);
          if (card.number) setCardNumber(card.number);
          if (card.name)   setCardName(card.name);
        })
        .catch(() => {});
    }
  }, [id?.catalog_card_id]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const res = await api<{ items: CatalogCard[] }>(
        `/cards/search?q=${encodeURIComponent(searchQuery)}&limit=8`
      );
      setSearchResults(res.items ?? []);
    } catch {
      onToast("Search failed", "error");
    } finally {
      setSearching(false);
    }
  };

  const handleSubmit = async () => {
    if (!destination) return;
    if (destination === "inventory" && !matchedCard) {
      onToast("Select a card from the catalog to add to Pokémon inventory", "error");
      return;
    }

    setSubmitting(true);
    try {
      const payload: TransferIn = {
        destination,
        card_id: destination === "inventory" ? matchedCard!.id : null,
        card_name: cardName || null,
        card_number: cardNumber || null,
        condition: condition || null,
        quantity,
        purchase_price: purchasePrice ? parseFloat(purchasePrice) : null,
        grading_company: gradingCompany || null,
        actual_grade: actualGrade ? parseFloat(actualGrade) : null,
        estimated_value: estimatedValue ? parseFloat(estimatedValue) : null,
        notes: notes.trim() || null,
      };

      const out = await api<TransferOut>(`/grading/${result.id}/transfer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      setTransferred(true);
      onTransferred(out.destination, out.item_id);
      onToast(out.message, "success");
    } catch (err: any) {
      onToast(err.message || "Transfer failed", "error");
    } finally {
      setSubmitting(false);
    }
  };

  if (transferred) {
    return (
      <div className="flex items-center gap-2 px-6 py-3 bg-emerald-50 border-t border-emerald-100 text-emerald-700 text-sm">
        <CheckCircle size={15} />
        Added to collection
        {result.transferred_to && (
          <span className="ml-1 text-emerald-600">
            ({result.transferred_to === "inventory" ? "Pokémon inventory" : "custom collection"})
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="border-t border-slate-100">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-6 py-3 text-sm text-slate-500 hover:text-slate-700 hover:bg-slate-50 transition"
      >
        <span className="font-medium">
          {id ? (
            id.catalog_match
              ? `Identified: ${id.name ?? "Unknown"} — add to collection`
              : `Partially identified — add to collection`
          ) : (
            "Add to collection"
          )}
        </span>
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {open && (
        <div className="px-6 pb-6 space-y-5">

          {/* ── Step 1: Confirm identity ── */}
          {step === "identity" && (
            <>
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
                  Card identity
                  {id && (
                    <span className={`ml-2 normal-case font-normal ${
                      id.confidence === "high" ? "text-emerald-500" :
                      id.confidence === "medium" ? "text-amber-500" : "text-slate-400"
                    }`}>
                      ({id.confidence} confidence)
                    </span>
                  )}
                </p>
                <div className="space-y-2">
                  <div>
                    <label className="text-xs text-slate-400 mb-0.5 block">Name</label>
                    <input
                      type="text"
                      value={cardName}
                      onChange={(e) => setCardName(e.target.value)}
                      placeholder="e.g. Charizard ex"
                      className="w-full px-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                    />
                  </div>
                  <div className="flex gap-2">
                    <div className="flex-1">
                      <label className="text-xs text-slate-400 mb-0.5 block">
                        Card number
                        {/* Show extracted value if it differs from what's now in the field */}
                        {id?.number && id.number !== cardNumber && (
                          <span className="ml-1 text-slate-300" title={`Vision model read: ${id.number}`}>
                            (extracted: {id.number})
                          </span>
                        )}
                      </label>
                      <input
                        type="text"
                        value={cardNumber}
                        onChange={(e) => setCardNumber(e.target.value)}
                        placeholder="e.g. 4"
                        className="w-full px-3 py-1.5 rounded-lg border border-slate-200 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-300"
                      />
                    </div>
                    <div className="flex-1">
                      <label className="text-xs text-slate-400 mb-0.5 block">Set</label>
                      <input
                        type="text"
                        value={setName}
                        onChange={(e) => setSetName(e.target.value)}
                        placeholder="e.g. Destined Rivals"
                        className="w-full px-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* Catalog match */}
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Catalog match</p>

                {matchedCard ? (
                  <div className="flex items-center gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-3">
                    {matchedCard.image_small && (
                      <img src={matchedCard.image_small} alt={matchedCard.name}
                        className="h-14 w-10 object-contain rounded shadow" />
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-slate-800 truncate">{matchedCard.name}</p>
                      <p className="text-xs text-slate-500">{matchedCard.set_id} · #{matchedCard.number}</p>
                      {matchedCard.rarity && (
                        <p className="text-xs text-emerald-600">{matchedCard.rarity}</p>
                      )}
                    </div>
                    <button
                      onClick={() => { setMatchedCard(null); setSearchResults([]); }}
                      className="text-xs text-slate-400 hover:text-slate-600"
                    >
                      Change
                    </button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <p className="text-xs text-slate-400">
                      {id?.catalog_match === false
                        ? "No automatic match found — search the catalog or skip to add as a custom item."
                        : "Search the catalog to link this card."}
                    </p>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                        placeholder={cardName || "Search card name…"}
                        className="flex-1 px-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                      />
                      <button
                        onClick={handleSearch}
                        disabled={searching}
                        className="px-3 py-1.5 rounded-lg bg-slate-800 text-white text-sm hover:bg-slate-700 transition disabled:opacity-50"
                      >
                        {searching ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
                      </button>
                    </div>
                    {searchResults.length > 0 && (
                      <div className="rounded-xl border border-slate-200 divide-y divide-slate-100 max-h-48 overflow-y-auto">
                        {searchResults.map((c) => (
                          <button
                            key={c.id}
                            onClick={() => { setMatchedCard(c); setSearchResults([]); }}
                            className="w-full flex items-center gap-3 px-3 py-2 hover:bg-slate-50 text-left transition"
                          >
                            {c.image_small && (
                              <img src={c.image_small} alt={c.name} className="h-10 w-7 object-contain rounded" />
                            )}
                            <div className="min-w-0">
                              <p className="text-sm font-medium text-slate-800 truncate">{c.name}</p>
                              <p className="text-xs text-slate-400">{c.set_id} · #{c.number}</p>
                            </div>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Destination choice */}
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Add to</p>
                <div className="flex gap-2">
                  <button
                    onClick={() => { setDestination("inventory"); setStep("form"); }}
                    disabled={!matchedCard}
                    className={`flex-1 py-2 rounded-xl border text-sm font-medium transition
                      ${matchedCard
                        ? "border-indigo-400 bg-indigo-50 text-indigo-700 hover:bg-indigo-100"
                        : "border-slate-200 text-slate-300 cursor-not-allowed"}`}
                  >
                    Pokémon inventory
                    {!matchedCard && <span className="block text-xs font-normal">match a catalog card first</span>}
                  </button>
                  <button
                    onClick={() => { setDestination("asset"); setStep("form"); }}
                    className="flex-1 py-2 rounded-xl border border-slate-300 text-sm font-medium text-slate-600 hover:bg-slate-50 transition"
                  >
                    Custom collection item
                  </button>
                </div>
              </div>
            </>
          )}

          {/* ── Step 2: Fill in details ── */}
          {step === "form" && destination && (
            <>
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                  {destination === "inventory" ? "Add to Pokémon inventory" : "Add as custom collection item"}
                </p>
                <button onClick={() => setStep("identity")} className="text-xs text-slate-400 hover:text-slate-600">
                  ← Back
                </button>
              </div>

              {/* Selected card summary */}
              {destination === "inventory" && matchedCard && (
                <div className="flex items-center gap-3 rounded-xl bg-slate-50 border border-slate-200 p-3">
                  {matchedCard.image_small && (
                    <img src={matchedCard.image_small} alt={matchedCard.name}
                      className="h-12 w-9 object-contain rounded shadow" />
                  )}
                  <div>
                    <p className="text-sm font-semibold text-slate-800">{matchedCard.name}</p>
                    <p className="text-xs text-slate-400">{matchedCard.set_id} · #{matchedCard.number}</p>
                  </div>
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-slate-400 mb-0.5 block">Condition</label>
                  <select
                    value={condition}
                    onChange={(e) => setCondition(e.target.value)}
                    className="w-full px-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  >
                    {CONDITIONS.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-slate-400 mb-0.5 block">Quantity</label>
                  <input
                    type="number" min={1} value={quantity}
                    onChange={(e) => setQuantity(Math.max(1, parseInt(e.target.value) || 1))}
                    className="w-full px-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  />
                </div>
              </div>

              {/* Grade override */}
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
                  Professional grade <span className="font-normal normal-case">(optional — overrides estimate)</span>
                </p>
                <div className="flex gap-2">
                  <input
                    type="number" min={1} max={10} step={0.5}
                    placeholder={`Est. ${result.estimated_grade}`}
                    value={actualGrade}
                    onChange={(e) => setActualGrade(e.target.value)}
                    className="w-24 px-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  />
                  <select
                    value={gradingCompany}
                    onChange={(e) => setGradingCompany(e.target.value)}
                    className="flex-1 px-3 py-1.5 rounded-lg border border-slate-200 text-sm text-slate-600 focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  >
                    <option value="">Grading company (optional)</option>
                    {COMPANIES.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-slate-400 mb-0.5 block">Purchase price</label>
                  <input
                    type="number" min={0} step={0.01} placeholder="0.00"
                    value={purchasePrice}
                    onChange={(e) => setPurchasePrice(e.target.value)}
                    className="w-full px-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  />
                </div>
                {destination === "asset" && (
                  <div>
                    <label className="text-xs text-slate-400 mb-0.5 block">Estimated value</label>
                    <input
                      type="number" min={0} step={0.01} placeholder="0.00"
                      value={estimatedValue}
                      onChange={(e) => setEstimatedValue(e.target.value)}
                      className="w-full px-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                    />
                  </div>
                )}
              </div>

              {destination === "asset" && (
                <div>
                  <label className="text-xs text-slate-400 mb-0.5 block">Notes</label>
                  <input
                    type="text" value={notes} onChange={(e) => setNotes(e.target.value)}
                    placeholder="Optional notes"
                    className="w-full px-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  />
                </div>
              )}

              <button
                onClick={handleSubmit}
                disabled={submitting}
                className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-slate-900 text-white text-sm font-semibold hover:bg-slate-700 disabled:opacity-40 transition"
              >
                {submitting && <Loader2 size={14} className="animate-spin" />}
                {destination === "inventory" ? "Add to Pokémon inventory" : "Add to collection"}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
