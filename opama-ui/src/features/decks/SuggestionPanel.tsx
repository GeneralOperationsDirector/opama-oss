/**
 * Suggestion Panel
 * ----------------
 * Tools to improve a deck:
 *  - Heuristic recommendations (Owned / Acquire)
 *  - Strategy (LLM one-shot)
 *  - Build from inventory (suggests a starter list + what to acquire)
 *  - Chat (LLM) with thread persisted per user+deck
 *
 * Improvements vs original:
 * - Uses shared atoms (Button, Select, TextInput) for consistency
 * - Non-blocking toasts for errors/feedback (useToast)
 * - API helpers from lib/api with clear types; chat has a 404 fallback
 * - Commented throughout; defensive guards (no active deck, etc.)
 */

import React, { useEffect, useMemo, useRef, useState } from "react";
import { Sparkles, Wand2, Package, PlusCircle, MessageSquare, Send, Trash2 } from "lucide-react";
import Button from "../../shared/atoms/Button";
import Select from "../../shared/atoms/Select";
import TextInput from "../../shared/atoms/TextInput";
import { useToast } from "../../shared/Toaster";
import {
  getHeuristicSuggestions,
  postAiSuggest,
  postJSON,
  API_BASE,
} from "../../lib/api"; // chat uses manual fetch fallback below

/** Props from host app */
export interface SuggestionPanelProps {
  userId: number;
  activeDeckId?: number | null;
}

/** Shared shapes (kept local for UI) */
export interface Rec {
  card_id: string;
  name: string;
  set?: string | null;
  reason: string;
  confidence?: number | null;
}
interface HeuristicResponse { recommendations: Rec[]; note?: string | null; }
interface AiSuggestOut { recommendations: Rec[]; note?: string | null; }

interface BuildFromInvIn {
  user_id: number;
  primary_types?: string[] | null;
  deck_size?: number;
}
interface DeckLine { card_id: string; name: string; qty: number; role?: string | null; }
interface BuildFromInvOut {
  deck: DeckLine[];
  summary: {
    counts?: { total?: number; by_supertype?: Record<string, number>; by_type?: Record<string, number> };
    primary_types?: string[];
    used_unique?: number;
    owned_used?: Record<string, number>;
    owned_leftover?: Record<string, number>;
  };
  acquire_suggestions: Rec[];
  notes?: string | null;
}

/** Chat types */
type ChatRole = "system" | "user" | "assistant";
interface ChatMessage { role: ChatRole; content: string; }

export default function SuggestionPanel({ userId, activeDeckId }: SuggestionPanelProps) {
  type TabKey = "owned" | "acquire" | "strategy" | "build" | "chat";
  const [tab, setTab] = useState<TabKey>("owned");

  // Shared UI state
  const [limit, setLimit] = useState<number>(10);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const { toast, error: toastError } = useToast();

  // Heuristic results
  const [ownedOnlyRecs, setOwnedOnlyRecs] = useState<Rec[]>([]);
  const [ownedNote, setOwnedNote] = useState<string | null>(null);
  const [acquireOnlyRecs, setAcquireOnlyRecs] = useState<Rec[]>([]);
  const [acquireNote, setAcquireNote] = useState<string | null>(null);

  // AI (one-shot strategy)
  const [aiTemperature, setAiTemperature] = useState<number>(0.3);
  const [aiRecs, setAiRecs] = useState<Rec[]>([]);
  const [aiNote, setAiNote] = useState<string | null>(null);

  // Build-from-inventory
  const [buildTypes, setBuildTypes] = useState<string[]>([]);
  const [buildDeckSize, setBuildDeckSize] = useState<number>(60);
  const [buildDeck, setBuildDeck] = useState<DeckLine[]>([]);
  const [buildSummary, setBuildSummary] = useState<BuildFromInvOut["summary"] | null>(null);
  const [buildAcquire, setBuildAcquire] = useState<Rec[]>([]);
  const [buildNotes, setBuildNotes] = useState<string | null>(null);

  // Chat
  const [chatModel, setChatModel] = useState<string>("gpt-4o-mini");
  const [chatTemperature, setChatTemperature] = useState<number>(0.3);
  const [chat, setChat] = useState<ChatMessage[]>([]);
  const [userInput, setUserInput] = useState<string>("");
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  const storageKey = useMemo(
    () => `ptcg-chat:${userId}:${activeDeckId ?? "none"}`,
    [userId, activeDeckId]
  );
  const defaultSystem = useMemo<ChatMessage>(
    () => ({
      role: "system",
      content:
        `You are a helpful Pokémon TCG deck-building assistant. ` +
        `Keep answers concise and actionable. If a deck_id is provided, focus on that deck's game plan.`,
    }),
    []
  );

  // Persist chat thread per (user, deck)
  useEffect(() => {
    try {
      const saved = localStorage.getItem(storageKey);
      setChat(saved ? (JSON.parse(saved) as ChatMessage[]) : [defaultSystem]);
    } catch {
      setChat([defaultSystem]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  useEffect(() => {
    try { localStorage.setItem(storageKey, JSON.stringify(chat)); } catch {}
  }, [chat, storageKey]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat]);

  const availableEnergyTypes = useMemo(
    () => ["Grass","Fire","Water","Lightning","Psychic","Fighting","Darkness","Metal","Fairy","Dragon","Colorless"],
    []
  );

  const deckDisabled = !activeDeckId || activeDeckId <= 0;

  // ---------------------------------------------------------------------------
  // Actions – Heuristics
  // ---------------------------------------------------------------------------
  async function runHeuristic(ownedOnly: boolean, acquireOnly: boolean) {
    if (!activeDeckId) { setError("Select a deck first."); return; }
    setLoading(true); setError(null);
    try {
      const data = await getHeuristicSuggestions({
        deck_id: activeDeckId,
        user_id: userId,
        limit,
        owned_only: ownedOnly || undefined,
        acquire_only: acquireOnly || undefined,
      });
      if (ownedOnly) { setOwnedOnlyRecs(data.recommendations); setOwnedNote(data.note ?? null); }
      else if (acquireOnly) { setAcquireOnlyRecs(data.recommendations); setAcquireNote(data.note ?? null); }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg); toastError(msg);
    } finally { setLoading(false); }
  }

  // ---------------------------------------------------------------------------
  // Actions – AI Strategy (one-shot)
  // ---------------------------------------------------------------------------
  async function runAI() {
    if (!activeDeckId) { setError("Select a deck first."); return; }
    setLoading(true); setError(null);
    try {
      const data = await postAiSuggest({
        deck_id: activeDeckId,
        user_id: userId,
        n: limit,
        temperature: aiTemperature,
        owned_only: false,
        acquire_only: false,
      });
      setAiRecs(data.recommendations);
      setAiNote(data.note ?? null);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg); toastError(msg);
    } finally { setLoading(false); }
  }

  // ---------------------------------------------------------------------------
  // Actions – Build from Inventory
  // ---------------------------------------------------------------------------
  async function runBuildFromInventory() {
    setLoading(true); setError(null);
    try {
      const payload: BuildFromInvIn = {
        user_id: userId,
        primary_types: buildTypes.length ? buildTypes : undefined,
        deck_size: buildDeckSize,
      };
      const res = await postJSON<BuildFromInvOut>(`/suggest/build_from_inventory`, payload);
      setBuildDeck(res.deck);
      setBuildSummary(res.summary ?? null);
      setBuildAcquire(res.acquire_suggestions);
      setBuildNotes(res.notes ?? null);
      toast("Built a starter list from inventory", { title: "Deck Builder" });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg); toastError(msg);
    } finally { setLoading(false); }
  }

  // ---------------------------------------------------------------------------
  // Actions – Chat (with graceful endpoint fallback)
  // ---------------------------------------------------------------------------
  async function sendChat() {
    const text = userInput.trim();
    if (!text) return;

    const next = [...chat, { role: "user" as const, content: text }];
    setChat(next);
    setUserInput("");
    setLoading(true);
    setError(null);

    try {
      // Prefer /suggest/chat (matches our api helper), but fall back to /ai/chat if 404
      const r1 = await fetch(`${API_BASE}/suggest/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          deck_id: activeDeckId ?? null,
          model: chatModel,
          temperature: chatTemperature,
          messages: next,
        }),
      });

      let replyText = "";
      if (r1.status === 404) {
        // Back-compat fallback
        const r2 = await fetch(`${API_BASE}/ai/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_id: userId,
            deck_id: activeDeckId ?? null,
            model: chatModel,
            temperature: chatTemperature,
            messages: next,
          }),
        });
        if (!r2.ok) throw new Error(await r2.text());
        const data2 = (await r2.json()) as { reply: string };
        replyText = data2.reply ?? "";
      } else if (!r1.ok) {
        throw new Error(await r1.text());
      } else {
        const data1 = (await r1.json()) as { reply: string };
        replyText = data1.reply ?? "";
      }

      const assistantMsg: ChatMessage = { role: "assistant", content: replyText };
      setChat((cur) => [...cur, assistantMsg]);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg); toastError(msg);
    } finally {
      setLoading(false);
    }
  }

  function resetThread() {
    setChat([defaultSystem]);
    setError(null);
  }

  // ---- Render helpers
  function RecList({ recs }: { recs: Rec[] }) {
    if (!recs.length) return <div className="text-sm text-slate-500">No results yet.</div>;
    return (
      <ul className="space-y-2">
        {recs.map((r) => (
          <li key={`${r.card_id}`} className="p-3 border rounded-xl bg-white">
            <div className="font-medium">{r.name}</div>
            <div className="text-xs text-slate-500">
              {r.card_id}{r.set ? ` • ${r.set}` : ""}{typeof r.confidence === "number" ? ` • conf ${r.confidence.toFixed(2)}` : ""}
            </div>
            <div className="text-sm mt-1">{r.reason}</div>
          </li>
        ))}
      </ul>
    );
  }

  function DeckList({ lines }: { lines: DeckLine[] }) {
    if (!lines.length) return <div className="text-sm text-slate-500">No deck built yet.</div>;
    return (
      <ul className="space-y-1">
        {lines.map((l) => (
          <li key={l.card_id} className="flex items-center justify-between p-2 border rounded-lg bg-white">
            <div className="min-w-0">
              <div className="font-medium truncate">{l.name}</div>
              <div className="text-xs text-slate-500 truncate">
                {l.card_id} {l.role ? `• ${l.role}` : ""}
              </div>
            </div>
            <div className="text-sm">x{l.qty}</div>
          </li>
        ))}
      </ul>
    );
  }

  // ---- UI
  return (
    <div className="grid gap-4">
      {/* Tabs */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setTab("owned")}
          className={`px-3 py-2 rounded-xl border ${tab === "owned" ? "bg-indigo-600 text-white border-indigo-600" : "bg-white hover:bg-slate-50"}`}
          title="Recommend from cards you already own"
        >
          <Package className="inline-block w-4 h-4 mr-2" />
          Owned
        </button>
        <button
          onClick={() => setTab("acquire")}
          className={`px-3 py-2 rounded-xl border ${tab === "acquire" ? "bg-indigo-600 text-white border-indigo-600" : "bg-white hover:bg-slate-50"}`}
          title="Recommend cards to acquire"
        >
          <PlusCircle className="inline-block w-4 h-4 mr-2" />
          Acquire
        </button>
        <button
          onClick={() => setTab("strategy")}
          className={`px-3 py-2 rounded-xl border ${tab === "strategy" ? "bg-indigo-600 text-white border-indigo-600" : "bg-white hover:bg-slate-50"}`}
          title="Model-generated strategy suggestions"
        >
          <Wand2 className="inline-block w-4 h-4 mr-2" />
          Strategy (AI)
        </button>
        <button
          onClick={() => setTab("build")}
          className={`px-3 py-2 rounded-xl border ${tab === "build" ? "bg-indigo-600 text-white border-indigo-600" : "bg-white hover:bg-slate-50"}`}
          title="Build a starter deck from inventory"
        >
          <Sparkles className="inline-block w-4 h-4 mr-2" />
          Build from Inventory
        </button>
        <button
          onClick={() => setTab("chat")}
          className={`px-3 py-2 rounded-xl border ${tab === "chat" ? "bg-indigo-600 text-white border-indigo-600" : "bg-white hover:bg-slate-50"}`}
          title="Chat with the AI"
        >
          <MessageSquare className="inline-block w-4 h-4 mr-2" />
          Chat (AI)
        </button>
      </div>

      {/* Shared controls (hide on chat/build when not relevant) */}
      {(tab !== "build" && tab !== "chat") && (
        <div className="flex items-center gap-3">
          <label className="text-xs text-slate-600">Limit</label>
          <TextInput
            type="number"
            min={1}
            max={100}
            value={limit}
            onChange={(e) => setLimit(Math.max(1, Math.min(100, Number(e.target.value))))}
            style={{ maxWidth: 90 }}
          />
          <span className="text-xs text-slate-500">Active Deck: {activeDeckId ?? "—"}</span>
        </div>
      )}

      {error && <div className="text-sm text-rose-600">{error}</div>}
      {loading && <div className="text-sm text-slate-600">Working…</div>}

      {/* Owned */}
      {tab === "owned" && (
        <div className="grid gap-3">
          <div className="flex items-center gap-2">
            <Button
              onClick={() => runHeuristic(true, false)}
              disabled={deckDisabled}
              title={deckDisabled ? "Select a deck first" : "Suggest from owned cards"}
            >
              <Package className="w-4 h-4" />
              Suggest from Owned
            </Button>
            <span className="text-xs text-slate-500">GET /suggest/:deck_id?owned_only&user_id</span>
          </div>
          {ownedNote && <div className="text-xs text-slate-500">{ownedNote}</div>}
          <RecList recs={ownedOnlyRecs} />
        </div>
      )}

      {/* Acquire */}
      {tab === "acquire" && (
        <div className="grid gap-3">
          <div className="flex items-center gap-2">
            <Button
              onClick={() => runHeuristic(false, true)}
              disabled={deckDisabled}
              title={deckDisabled ? "Select a deck first" : "Suggest cards to acquire"}
            >
              <PlusCircle className="w-4 h-4" />
              Suggest to Acquire
            </Button>
            <span className="text-xs text-slate-500">GET /suggest/:deck_id?acquire_only&user_id</span>
          </div>
          {acquireNote && <div className="text-xs text-slate-500">{acquireNote}</div>}
          <RecList recs={acquireOnlyRecs} />
        </div>
      )}

      {/* Strategy (AI) */}
      {tab === "strategy" && (
        <div className="grid gap-3">
          <div className="flex items-center gap-3">
            <label className="text-xs text-slate-600">Temperature</label>
            <TextInput
              type="number"
              step="0.1"
              min={0}
              max={2}
              value={aiTemperature}
              onChange={(e) => setAiTemperature(Number(e.target.value))}
              style={{ maxWidth: 100 }}
            />
            <Button onClick={runAI} disabled={deckDisabled} title={deckDisabled ? "Select a deck first" : "Ask AI"}>
              <Wand2 className="w-4 h-4" />
              Ask AI
            </Button>
            <span className="text-xs text-slate-500">POST /suggest/ai</span>
          </div>
          {aiNote && <div className="text-xs text-slate-500">{aiNote}</div>}
          <RecList recs={aiRecs} />
        </div>
      )}

      {/* Build from Inventory */}
      {tab === "build" && (
        <div className="grid gap-4">
          <div className="grid sm:grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-600 mb-1 block">Primary Types (optional)</label>
              <select
                multiple
                className="px-3 py-2 rounded-xl border w-full"
                value={buildTypes}
                onChange={(e) =>
                  setBuildTypes(Array.from(e.target.selectedOptions).map((o) => o.value))
                }
                size={Math.min(8, Math.max(2, availableEnergyTypes.length))}
              >
                {availableEnergyTypes.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
              <div className="text-[11px] text-slate-500 mt-1">Leave empty to consider all owned types.</div>
            </div>

            <div>
              <label className="text-xs text-slate-600 mb-1 block">Deck Size</label>
              <TextInput
                type="number"
                min={20}
                max={60}
                value={buildDeckSize}
                onChange={(e) => setBuildDeckSize(Math.max(20, Math.min(60, Number(e.target.value))))}
              />
              <div className="text-[11px] text-slate-500 mt-1">Standard is 60; you can preview cores with smaller sizes.</div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button onClick={runBuildFromInventory} title="Build using your inventory">
              <Sparkles className="w-4 h-4" />
              Build from Inventory
            </Button>
            <span className="text-xs text-slate-500">POST /suggest/build_from_inventory</span>
          </div>

          {buildNotes && <div className="text-sm text-slate-600">{buildNotes}</div>}

          {/* Results */}
          <div className="grid md:grid-cols-2 gap-4">
            <div className="p-3 border rounded-xl bg-white">
              <div className="font-semibold mb-2">Deck List</div>
              <DeckList lines={buildDeck} />
            </div>

            <div className="p-3 border rounded-xl bg-white">
              <div className="font-semibold mb-2">Summary</div>
              {!buildSummary ? (
                <div className="text-sm text-slate-500">No build yet.</div>
              ) : (
                <div className="text-sm grid gap-2">
                  <div>
                    <div className="text-xs text-slate-500">Total Cards</div>
                    <div className="font-medium">
                      {buildSummary.counts?.total ?? buildDeck.reduce((a, b) => a + b.qty, 0)}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">By Supertype</div>
                    <ul className="text-sm list-disc pl-5">
                      {Object.entries(buildSummary.counts?.by_supertype ?? {}).map(([k, v]) => (
                        <li key={k}>{k}: {v}</li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">By Type</div>
                    <ul className="text-sm list-disc pl-5">
                      {Object.entries(buildSummary.counts?.by_type ?? {}).map(([k, v]) => (
                        <li key={k}>{k}: {v}</li>
                      ))}
                    </ul>
                  </div>
                  {!!(buildSummary.primary_types?.length ?? 0) && (
                    <div>
                      <div className="text-xs text-slate-500">Primary Types</div>
                      <div className="font-medium">{buildSummary.primary_types?.join(", ")}</div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          <div className="p-3 border rounded-xl bg-white">
            <div className="font-semibold mb-2">Acquire to Complete</div>
            <RecList recs={buildAcquire} />
          </div>
        </div>
      )}

      {/* Chat (AI) */}
      {tab === "chat" && (
        <div className="grid gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-xs text-slate-500">
              Thread scope: User {userId}{activeDeckId ? ` • Deck ${activeDeckId}` : ""}
            </span>

            <label className="text-xs text-slate-600">Model</label>
            <Select
              value={chatModel}
              onChange={(e) => setChatModel(e.target.value)}
              style={{ maxWidth: 180 }}
            >
              <option value="gpt-4o-mini">gpt-4o-mini</option>
              <option value="gpt-4o">gpt-4o</option>
              <option value="o3-mini">o3-mini</option>
            </Select>

            <label className="text-xs text-slate-600">Temperature</label>
            <TextInput
              type="number"
              step="0.1"
              min={0}
              max={2}
              value={chatTemperature}
              onChange={(e) => setChatTemperature(Number(e.target.value))}
              style={{ maxWidth: 90 }}
            />

            <button
              className="px-3 py-2 rounded-xl border text-sm hover:bg-rose-50 inline-flex items-center gap-2"
              onClick={resetThread}
              title="Clear this conversation"
            >
              <Trash2 className="w-4 h-4" /> Reset Thread
            </button>
          </div>

          <div className="h-[380px] overflow-auto rounded-xl border bg-white/70 p-3">
            {chat.map((m, i) => (
              <div key={i} className={`mb-3 ${m.role === "user" ? "text-right" : "text-left"}`}>
                <div
                  className={`inline-block max-w-[85%] px-3 py-2 rounded-2xl ${
                    m.role === "user"
                      ? "bg-indigo-600 text-white"
                      : m.role === "assistant"
                      ? "bg-white border"
                      : "bg-slate-100 text-slate-700"
                  }`}
                >
                  <div className="text-[11px] opacity-70 mb-1">
                    {m.role === "user" ? "You" : m.role === "assistant" ? "Assistant" : "System"}
                  </div>
                  <div className="whitespace-pre-wrap text-sm">{m.content}</div>
                </div>
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>

          <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); sendChat(); }}>
            <textarea
              placeholder="Ask about your deck strategy, combos, card swaps… (Shift+Enter for newline)"
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); } }}
              className="w-full min-h-[70px] max-h-[200px] px-3 py-2 rounded-xl border outline-none focus:ring-2 focus:ring-indigo-400"
            />
            <Button type="submit" title="Send">
              <Send className="w-4 h-4" />
              Send
            </Button>
          </form>

          <div className="text-[11px] text-slate-500">
            Tries <code>POST /suggest/chat</code> first, falls back to <code>POST /ai/chat</code>.
          </div>
        </div>
      )}
    </div>
  );
}
