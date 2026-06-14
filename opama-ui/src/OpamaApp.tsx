/**
 * OpamaApp — the app shell and module router.
 *
 * This is the top-level component. It owns two pieces of navigation state:
 *   - `activeModule` (AppModule): which top-level feature is showing —
 *     dashboard, custom (collections), portfolio, storefront, grading,
 *     pokemon, plugin_store, system.
 *   - `tab` (Tab): the sub-tab *within* the Pokémon module only
 *     (catalog / inventory / decks / showcase / wishlist / trade / …).
 *
 * Rendering is a flat list of guarded blocks (see the big return below): each
 * module renders only when `isModuleEnabled(id)` (the plugin/module registry
 * allows it) AND `activeModule === id`. Disabled or unlicensed modules fall
 * back to the dashboard. `onSelectModule(module, tab?, arg?)` is the single
 * entry point children use to navigate — `arg` carries a collection category
 * or template id for the custom-assets module (see CLAUDE.md).
 */
import React, { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import HeaderBar from "./shared/HeaderBar";
import CatalogTab from "./features/catalog/CatalogTab";
import InventoryTab from "./features/inventory/InventoryTab";
import DecksTab from "./features/decks/DecksTab";
import WishListTab from "./features/trading/WishListTab";
import TradeTab from "./features/trading/TradeTab";
import Section from "./shared/atoms/Section";
import PokedexTab from "./features/pokedex/PokedexTab";
import PortfolioTab from "./features/portfolio/PortfolioTab";
import ProfileTab from "./features/profile/ProfileTab";
import ShowcaseTab from "./features/showcase/ShowcaseTab";
import DashboardView from "./features/dashboard/DashboardView";
import MainPortfolioView from "./features/portfolio/MainPortfolioView";
import CustomAssetsModule from "./features/custom-assets/CustomAssetsModule";
import StorefrontModule from "./features/storefront/StorefrontModule";
import GradingView from "./features/grading/GradingView";
import SystemPanel from "./features/system/SystemPanel";
import PluginStoreModule from "./features/plugin-store/PluginStoreModule";
import Toaster from "./shared/Toaster";
import AuthModal from "./components/auth/AuthModal";
import AuthGuardrail from "./components/auth/AuthGuardrail";
import InputModal from "./shared/atoms/InputModal";
import { useAuth } from "./contexts/AuthContext";
import { useLicense } from "./contexts/LicenseContext";

import { API_BASE, api, fetchDecksForUser, addToWishlist, upsertTradeItem } from "./lib/api";
import { isModuleEnabled, setActiveBackendPlugins } from "./lib/moduleRegistry";
import type { AppModule, Deck, DeckWithCards, Tab } from "./types";

// ── Guest prompt — shown in place of any data-bound module when not signed in ─

function GuestPrompt({ onSignUp, onSignIn }: { onSignUp: () => void; onSignIn: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-6 text-center">
      <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-indigo-400 to-violet-500 flex items-center justify-center text-4xl select-none">
        📦
      </div>
      <div className="space-y-2">
        <h2 className="text-2xl font-bold text-slate-800">Create a free account to get started</h2>
        <p className="text-slate-500 max-w-sm leading-relaxed">
          Sign up in seconds to save your collections, track values, and manage everything in one place.
        </p>
      </div>
      <div className="flex items-center gap-3">
        <button
          onClick={onSignUp}
          className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-xl transition-colors shadow-sm"
        >
          Create account
        </button>
        <button
          onClick={onSignIn}
          className="px-6 py-2.5 border border-slate-300 hover:border-slate-400 text-slate-700 font-medium rounded-xl transition-colors"
        >
          Sign in
        </button>
      </div>
    </div>
  );
}

// Lazies
const SuggestionPanel = lazy(() => import("./features/decks/SuggestionPanel"));
const CardDetailsPanel = lazy(() => import("./shared/CardDetailsPanel"));
const EbayTab = lazy(() => import("./features/marketplace/EbayTab")); // ✅ new tab

/**
 * Root application shell
 * ----------------------
 * Holds global UI state (selected tab, user, active deck, overlays) and
 * routes between feature tabs. Side-effects (fetching decks, refreshing a
 * selection) live here; the tabs remain presentational/small.
 *
 * Design choices:
 * - Keep props/handlers stable via useCallback to help child memoization.
 * - Make network helpers resilient (alert on failure, no crashes).
 * - Lazy-load heavy panels (Suggestions, CardDetails, Ebay) behind Suspense.
 */
export default function OpamaApp() {
  // ---------------------------------------------------------------------------
  // Authentication
  // ---------------------------------------------------------------------------
  const { currentUser, logout } = useAuth();
  const { isModuleLicensed } = useLicense();
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [authModalMode, setAuthModalMode] = useState<'login' | 'signup'>('login');

  const openAuth = useCallback((mode: 'login' | 'signup' = 'login') => {
    setAuthModalMode(mode);
    setShowAuthModal(true);
  }, []);
  const [userProfile, setUserProfile] = useState<{ id: number } | null>(null);
  // Bumped after fetching active-plugins so isModuleEnabled() re-evaluates in all children.
  const [moduleRegistryVersion, setModuleRegistryVersion] = useState(0);

  const userId = userProfile?.id || 1;

  // ---------------------------------------------------------------------------
  // Global state
  // ---------------------------------------------------------------------------
  const [activeModule, setActiveModule] = useState<AppModule>("dashboard");
  const [showNewDeckModal, setShowNewDeckModal] = useState(false);
  const [tab, setTab] = useState<Tab>("catalog");
  const [showProfile, setShowProfile] = useState(false);
  const [pendingCollectionTemplate, setPendingCollectionTemplate] = useState<string | null>(null);

  const handleSelectModule = useCallback((module: AppModule, tab?: string, templateId?: string) => {
    setActiveModule(module);
    setShowProfile(false);  // always close the profile overlay when navigating to a module
    if (module === "pokemon") setTab((tab as any) ?? "catalog");
    if (templateId) setPendingCollectionTemplate(templateId);
  }, []);

  // Decks for the current user
  const [decks, setDecks] = useState<Deck[]>([]);
  const [activeDeckId, setActiveDeckId] = useState<number | undefined>(undefined);
  const [activeDeck, setActiveDeck] = useState<DeckWithCards | null>(null);

  // Details overlay
  const [detailsCardId, setDetailsCardId] = useState<string | null>(null);

  // Ebay tab prefill (optional): when "Find on eBay" actions are added, set this then switch to ebay tab
  const [ebayQuery, setEbayQuery] = useState<string>("");

  // Toast notifications
  const [toasts, setToasts] = useState<Array<{ id: number; message: string; type: "success" | "error" | "info" }>>([]);
  const toastIdRef = useRef(1);

  const addToast = useCallback((message: string, type: "success" | "error" | "info" = "info") => {
    const id = toastIdRef.current++;
    setToasts((prev) => [...prev, { id, message, type }]);
    // Auto-remove after 5 seconds
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  }, []);

  // ---------------------------------------------------------------------------
  // Effects
  // ---------------------------------------------------------------------------

  // Fetch active backend plugins on startup so dynamically-enabled modules
  // (enabled via the Plugin Store) appear in the nav/dashboard without needing
  // a VITE_ENABLED_MODULES rebuild. Bumps moduleRegistryVersion to trigger
  // a re-render of all children that call isModuleEnabled().
  useEffect(() => {
    fetch(`${API_BASE}/plugin-store/active-plugins`)
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (data?.active) {
          setActiveBackendPlugins(data.active as string[]);
          setModuleRegistryVersion((v) => v + 1);
        }
      })
      .catch(() => {/* non-fatal */});
  }, []);

  // If the active module becomes disabled after the backend registry is fetched
  // (e.g. user disabled a module and restarted), redirect to dashboard.
  useEffect(() => {
    if (moduleRegistryVersion > 0 && !isModuleEnabled(activeModule)) {
      setActiveModule("dashboard");
      setShowProfile(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [moduleRegistryVersion]);

  // Listen for tab-switch events dispatched by child components (e.g. ShowcaseTab)
  useEffect(() => {
    const handler = (e: Event) => {
      const tab = (e as CustomEvent).detail as Tab;
      if (tab) {
        setActiveModule("pokemon");
        setTab(tab);
      }
    };
    window.addEventListener("switchTab", handler);
    return () => window.removeEventListener("switchTab", handler);
  }, []);

  // Fetch user profile when authenticated
  useEffect(() => {
    if (!currentUser) {
      setUserProfile(null);
      return;
    }

    (async () => {
      try {
        const profile = await api<{ id: number; firebase_uid: string; email: string }>('/auth/me');
        setUserProfile(profile);
      } catch (err) {
        console.error('Failed to fetch user profile:', err);
        addToast('Failed to load user profile', 'error');
      }
    })();
  }, [currentUser, addToast]);

  // Load decks when the user changes. Decks belong to the Pokémon TCG module
  // (external_plugins/opama_pokemon_tcg) — wait for the active-plugins fetch
  // (moduleRegistryVersion > 0) before checking isModuleEnabled, otherwise
  // core-only installs (no VITE_ENABLED_MODULES set) read the "not yet known"
  // default of true and 404 against a /decks route that doesn't exist there.
  useEffect(() => {
    if (moduleRegistryVersion === 0 || !isModuleEnabled("pokemon")) return;
    (async () => {
      try {
        const list = await fetchDecksForUser(userId);
        setDecks(list);

        // If the active deck no longer belongs to this user (or was deleted), clear it.
        if (activeDeckId && !list.some((d) => d.id === activeDeckId)) {
          setActiveDeckId(undefined);
          setActiveDeck(null);
        }
      } catch {
        /* keep the UI usable if this fails */
      }
    })();
    // We intentionally do NOT depend on activeDeckId; this effect is scoped to user changes only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, moduleRegistryVersion]);

  // ---------------------------------------------------------------------------
  // Network helpers (stable callbacks)
  // ---------------------------------------------------------------------------

  /**
   * Fetch deck details and set it as the active deck.
   */
  const refreshDeck = useCallback(async (id: number) => {
    try {
      const data = await api<DeckWithCards>(`/decks/${id}`);
      setActiveDeckId(id);
      setActiveDeck(data);

      // Keep the decks list in sync with any server-side changes to this deck.
      setDecks((prev) =>
        prev.some((d) => d.id === data.deck.id)
          ? prev.map((d) => (d.id === data.deck.id ? data.deck : d))
          : [...prev, data.deck],
      );
    } catch {
      /* no-op; UX surfaces this elsewhere */
    }
  }, []);

  /**
   * Create a new (empty) deck for the current user and jump to Decks tab.
   */
  const createDeck = useCallback(() => {
    setShowNewDeckModal(true);
  }, []);

  const handleCreateDeckConfirm = useCallback(async (name: string) => {
    setShowNewDeckModal(false);
    try {
      const res = await api<{ id: number }>(`/decks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, name, format: "Standard" }),
      });
      setActiveDeckId(res.id);
      await refreshDeck(res.id);
      setTab("decks");
    } catch (e) {
      addToast(e instanceof Error ? e.message : String(e), "error");
    }
  }, [refreshDeck, userId, addToast]);

  /**
   * Add a single copy of a card to the current user's inventory.
   */
  const addToInventory = useCallback(
    async (card_id: string, quantity = 1) => {
      try {
        await api(`/inventory`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: userId, card_id, quantity }),
        });
        addToast(quantity > 1 ? `Added ${quantity}× to inventory` : "Added to inventory", "success");
      } catch (e) {
        addToast(e instanceof Error ? e.message : String(e), "error");
      }
    },
    [userId, addToast],
  );

  /**
   * Add a single copy of a card to the active deck (if any).
   */
  const addCardToDeck = useCallback(
    async (card_id: string) => {
      if (!activeDeckId) {
        addToast("Create or select a deck first.", "info");
        return;
      }
      try {
        await api(`/decks/${activeDeckId}/cards`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ card_id, quantity: 1 }),
        });
        await refreshDeck(activeDeckId);
      } catch (e) {
        addToast(e instanceof Error ? e.message : String(e), "error");
      }
    },
    [activeDeckId, refreshDeck, addToast],
  );

  /**
   * Add a card to the wishlist for the current user.
   */
  const addWish = useCallback(
    async (cardId: string) => {
      try {
        await addToWishlist(userId, cardId);
        addToast("Added to Wish List", "success");
      } catch (e) {
        addToast(e instanceof Error ? e.message : String(e), "error");
      }
    },
    [userId, addToast],
  );

  /**
   * Mark a card for trade for the current user.
   */
  const markTrade = useCallback(
    async (cardId: string) => {
      try {
        await upsertTradeItem(userId, cardId, 1);
        addToast("Marked for trade", "success");
      } catch (e) {
        addToast(e instanceof Error ? e.message : String(e), "error");
      }
    },
    [userId, addToast],
  );

  /**
   * Fetch quick heuristic suggestions for the active deck and show a simple alert.
   * (The richer SuggestionPanel lives under the "suggest" tab.)
   */
  const getSuggestions = useCallback(async () => {
    if (!activeDeckId) {
      addToast("Select a deck first", "info");
      return;
    }
    try {
      const res = await api<{
        recommendations: { reason: string; card_id: string; name: string; set: string }[];
      }>(`/suggest/${activeDeckId}?limit=10`);
      const lines = res.recommendations.map((r) => `• ${r.name} (${r.set}) — ${r.reason}`).join("\n");
      addToast(lines || "No suggestions yet", "info");
    } catch (e) {
      addToast(e instanceof Error ? e.message : String(e), "error");
    }
  }, [activeDeckId, addToast]);

  // (Optional) Example: route a card to eBay by pre-filling the query then switching tabs.
  // const findOnEbay = useCallback((query: string) => {
  //   setEbayQuery(query);
  //   setTab("ebay" as Tab); // ensure 'ebay' exists in Tab union in ./types
  // }, []);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-sky-50 to-emerald-50 text-slate-800">
      <HeaderBar
        activeModule={activeModule}
        tab={tab}
        setTab={(t) => { setShowProfile(false); setTab(t); }}
        onSelectModule={handleSelectModule}
        currentUser={currentUser}
        onLogin={() => openAuth('login')}
        onLogout={logout}
        activeDeckName={activeDeck?.deck?.name ?? null}
        showProfile={showProfile}
        onOpenProfile={() => setShowProfile((p) => !p)}
      />

      <AuthGuardrail onOpenProfile={() => setShowProfile(true)} />

      <main className="max-w-6xl mx-auto px-4 py-6 grid gap-6">

        {/* Profile overlay — shown when user explicitly opens it via the Profile button */}
        {showProfile && (
          <ProfileTab onToast={addToast} />
        )}

        {/* Module content — hidden while profile is open */}
        {!showProfile && <>

        {/* Locked module notice */}
        {!isModuleLicensed(activeModule) && (
          <div className="flex flex-col items-center justify-center py-24 gap-4 text-center">
            <div className="w-16 h-16 rounded-2xl bg-amber-100 flex items-center justify-center">
              <span className="text-3xl">🔒</span>
            </div>
            <h2 className="text-xl font-semibold text-slate-800">Premium Module</h2>
            <p className="text-slate-500 max-w-sm">
              This module requires a premium license. Contact your administrator or upgrade your plan to unlock it.
            </p>
            <button
              onClick={() => handleSelectModule("dashboard")}
              className="mt-2 px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors"
            >
              Back to Dashboard
            </button>
          </div>
        )}

        {/* Dashboard */}
        {isModuleEnabled("dashboard") && activeModule === "dashboard" && (
          <DashboardView
            onSelectModule={handleSelectModule}
            userId={currentUser ? userId : undefined}
            onSignUp={currentUser ? undefined : () => openAuth('signup')}
          />
        )}

        {/* Pokémon TCG module tabs */}
        {isModuleEnabled("pokemon") && activeModule === "pokemon" && tab === "catalog" && (
          <CatalogTab
            userId={userId}
            onAddToInventory={addToInventory}
            onAddCardToDeck={addCardToDeck}
            onOpenDetails={setDetailsCardId}
            onAddToWishlist={addWish}
            // onFindOnEbay={findOnEbay} // ← wire when the component supports it
          />
        )}

        {/* ── Pokémon TCG module ── */}
        {isModuleEnabled("pokemon") && activeModule === "pokemon" && tab === "inventory" && (
          <InventoryTab
            userId={userId}
            decks={decks}
            activeDeckId={activeDeckId}
            refreshDeck={refreshDeck}
            createDeck={createDeck}
            addCardToDeck={addCardToDeck}
            onOpenDetails={setDetailsCardId}
            onAddToWishlist={addWish}
            onMarkForTrade={markTrade}
          />
        )}

        {isModuleEnabled("pokemon") && activeModule === "pokemon" && tab === "decks" && (
          <DecksTab
            userId={userId}
            decks={decks}
            setDecks={setDecks}
            activeDeck={activeDeck}
            setActiveDeck={setActiveDeck}
            activeDeckId={activeDeckId}
            setActiveDeckId={setActiveDeckId}
            getSuggestions={getSuggestions}
            refreshDeck={refreshDeck}
            createDeck={createDeck}
          />
        )}

        {isModuleEnabled("pokemon") && activeModule === "pokemon" && tab === "showcase" && (
          <ShowcaseTab
            userId={userId}
            onOpenDetails={setDetailsCardId}
            onToast={addToast}
          />
        )}

        {isModuleEnabled("pokemon") && activeModule === "pokemon" && tab === "wishlist" && (
          <WishListTab
            userId={userId}
            onOpenDetails={setDetailsCardId}
            onAddToDeck={addCardToDeck}
            activeDeckName={activeDeck?.deck?.name ?? null}
          />
        )}

        {isModuleEnabled("pokemon") && activeModule === "pokemon" && tab === "trade" && (
          <TradeTab userId={userId} onOpenDetails={setDetailsCardId} />
        )}

        {isModuleEnabled("pokemon") && isModuleEnabled("marketplace") && activeModule === "pokemon" && tab === "ebay" && (
          <Section title="eBay">
            <Suspense fallback={<div className="text-sm text-slate-600">Loading eBay…</div>}>
              <EbayTab initialQuery={ebayQuery} />
            </Suspense>
          </Section>
        )}

        {isModuleEnabled("pokemon") && activeModule === "pokemon" && tab === "pokedex" && (
          <Section title="Pokédex">
            <PokedexTab
              userId={userId}
              onOpenDetails={setDetailsCardId}
              onAddToInventory={addToInventory}
              onAddToDeck={addCardToDeck}
              onAddToWishlist={addWish}
            />
          </Section>
        )}

        {isModuleEnabled("pokemon") && isModuleEnabled("portfolio") && activeModule === "pokemon" && tab === "portfolio" && (
          <PortfolioTab
            userId={userId}
            onOpenDetails={setDetailsCardId}
            onToast={addToast}
          />
        )}

        {/* ── Portfolio module ── */}
        {isModuleEnabled("portfolio") && activeModule === "portfolio" && (
          currentUser ? (
            <MainPortfolioView userId={userId} onNavigate={handleSelectModule} />
          ) : (
            <GuestPrompt onSignUp={() => openAuth('signup')} onSignIn={() => openAuth('login')} />
          )
        )}

        {/* ── Storefront module ── */}
        {isModuleEnabled("storefront") && activeModule === "storefront" && (
          currentUser ? (
            <StorefrontModule userId={userId} onToast={addToast} />
          ) : (
            <GuestPrompt onSignUp={() => openAuth('signup')} onSignIn={() => openAuth('login')} />
          )
        )}

        {/* ── Grading module ── */}
        {isModuleEnabled("grading") && activeModule === "grading" && (
          currentUser ? (
            <GradingView userId={userId} onToast={addToast} />
          ) : (
            <GuestPrompt onSignUp={() => openAuth('signup')} onSignIn={() => openAuth('login')} />
          )
        )}

        {/* ── Custom Assets module ── */}
        {isModuleEnabled("custom") && activeModule === "custom" && (
          currentUser ? (
            <CustomAssetsModule
              userId={userId}
              onToast={addToast}
              pendingTemplateId={pendingCollectionTemplate}
              onPendingTemplateConsumed={() => setPendingCollectionTemplate(null)}
            />
          ) : (
            <GuestPrompt onSignUp={() => openAuth('signup')} onSignIn={() => openAuth('login')} />
          )
        )}

        {/* ── Plugin Store module ── */}
        {isModuleEnabled("plugin_store") && activeModule === "plugin_store" && (
          currentUser ? (
            <PluginStoreModule userId={userId} onToast={addToast} />
          ) : (
            <GuestPrompt onSignUp={() => openAuth('signup')} onSignIn={() => openAuth('login')} />
          )
        )}

        {/* ── System module ── */}
        {activeModule === "system" && <SystemPanel />}

        </>}

      </main>

      <footer className="py-10 text-center text-xs text-slate-400">
        opama • API: {API_BASE}
      </footer>

      {/* Details overlay (lazy) */}
      <Suspense fallback={null}>
        {detailsCardId && (
          <CardDetailsPanel
            apiBase={API_BASE}
            cardId={detailsCardId}
            onClose={() => setDetailsCardId(null)}
            onAddToInventory={addToInventory}
            onAddToDeck={addCardToDeck}
            onAddToWishlist={addWish}
            onMarkForTrade={markTrade}
            // onFindOnEbay={findOnEbay}
          />
        )}
      </Suspense>

      {/* Toast Notifications */}
      <Toaster toasts={toasts} onDismiss={(id) => setToasts((prev) => prev.filter((t) => t.id !== id))} />

      {/* Auth Modal */}
      {showAuthModal && (
        <AuthModal
          initialMode={authModalMode}
          onClose={() => setShowAuthModal(false)}
          onSuccess={() => {
            setShowAuthModal(false);
            addToast(authModalMode === 'signup' ? 'Account created — welcome!' : 'Welcome back!', 'success');
          }}
        />
      )}

      {/* New Deck Modal */}
      {showNewDeckModal && (
        <InputModal
          title="New Deck"
          placeholder="e.g. Charizard ex Control"
          confirmLabel="Create"
          onConfirm={handleCreateDeckConfirm}
          onCancel={() => setShowNewDeckModal(false)}
        />
      )}
    </div>
  );
}
