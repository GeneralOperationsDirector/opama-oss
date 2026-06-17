import React from "react";
import { motion } from "motion/react";
import {
  Database, Package, Layers, Repeat, Heart,
  ShoppingCart, BookOpen, TrendingUp, LogIn, LogOut,
  User as UserIcon, LayoutDashboard, Swords, Settings, Bot,
} from "lucide-react";
import type { AppModule, Tab } from "../types";
import type { AppUser } from "../contexts/AuthContext";
import { useHealthCheck } from "../lib/useHealthCheck";
import { getNavModules, type ModuleDescriptor } from "../lib/moduleRegistry";
import OrgSwitcher from "./OrgSwitcher";

function StatusDot() {
  const health = useHealthCheck();
  const label =
    health === "ok"   ? "API connected" :
    health === "down" ? "API unreachable" : "Connecting…";
  const colour =
    health === "ok"   ? "bg-emerald-400" :
    health === "down" ? "bg-red-400 animate-pulse" :
                        "bg-amber-400 animate-pulse";
  return (
    <div title={label} className="flex items-center gap-1.5 flex-shrink-0">
      <span className={`w-2 h-2 rounded-full ${colour}`} />
      {health === "down" && (
        <span className="hidden sm:inline text-xs text-red-500 font-medium">Offline</span>
      )}
    </div>
  );
}

// Showcase, Portfolio, and eBay are intentionally not in this nav — their
// tab components (ShowcaseTab, PortfolioTab, EbayTab) and OpamaApp.tsx render
// blocks are kept as-is for the planned Themed Portfolios / skins integration
// with the core Opama Portfolio module (see opama_pokemon_tcg module work).
const POKEMON_TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: "catalog",   label: "Catalog",   icon: <Database     className="w-3.5 h-3.5" /> },
  { id: "inventory", label: "Inventory", icon: <Package      className="w-3.5 h-3.5" /> },
  { id: "decks",     label: "Decks",     icon: <Layers       className="w-3.5 h-3.5" /> },
  { id: "trade",     label: "Trade",     icon: <Repeat       className="w-3.5 h-3.5" /> },
  { id: "wishlist",  label: "Wish List", icon: <Heart        className="w-3.5 h-3.5" /> },
  { id: "pokedex",   label: "Pokédex",   icon: <BookOpen     className="w-3.5 h-3.5" /> },
];

// Lucide icons for nav module pills. Preferred over emoji for reliability.
const MODULE_ICONS: Record<string, React.ReactNode> = {
  dashboard:    <LayoutDashboard className="w-4 h-4" />,
  custom:       <Package         className="w-4 h-4" />,
  portfolio:    <TrendingUp      className="w-4 h-4" />,
  storefront:   <ShoppingCart    className="w-4 h-4" />,
  plugin_store: <Layers          className="w-4 h-4" />,
  ai_assistant: <Bot             className="w-4 h-4" />,
};

function moduleIcon(m: ModuleDescriptor): React.ReactNode | null {
  return MODULE_ICONS[m.id] ?? null;
}

export default function HeaderBar({
  activeModule, tab, setTab, onSelectModule,
  currentUser, onLogin, onLogout,
  activeDeckName, showProfile, onOpenProfile,
}: {
  activeModule: AppModule;
  tab: Tab;
  setTab: (t: Tab) => void;
  onSelectModule: (m: AppModule) => void;
  currentUser: AppUser | null;
  onLogin: () => void;
  onLogout: () => void;
  activeDeckName?: string | null;
  showProfile?: boolean;
  onOpenProfile?: () => void;
}) {
  return (
    <header className="sticky top-0 z-10 bg-white/95 backdrop-blur border-b border-slate-200 shadow-sm">
      <div className="max-w-6xl mx-auto px-3 sm:px-4 h-12 flex items-center gap-1.5">

        {/* Brand */}
        <motion.div
          initial={{ rotate: -8, scale: 0.9 }}
          animate={{ rotate: 0, scale: 1 }}
          transition={{ type: "spring", stiffness: 160 }}
          className="flex items-center gap-1.5 flex-shrink-0 mr-1"
        >
          <span className="w-7 h-7 rounded-lg bg-indigo-600 text-white flex items-center justify-center flex-shrink-0">
            <LayoutDashboard className="w-3.5 h-3.5" />
          </span>
          <span className="hidden sm:block text-base font-bold text-slate-800 leading-none">opama</span>
        </motion.div>

        <div className="w-px h-4 bg-slate-200 flex-shrink-0" />

        {/* Module pills — driven by the module registry */}
        <nav className="flex items-center gap-0.5 overflow-x-auto scrollbar-none flex-shrink-0">
          {getNavModules().map((m) => {
            const active = activeModule === m.id;
            const icon = moduleIcon(m);
            const lead = icon
              ? <span className="flex-shrink-0 flex items-center">{icon}</span>
              : m.emoji
              ? <span className="text-base leading-none">{m.emoji}</span>
              : null;
            return (
              <button
                key={m.id}
                title={m.label}
                onClick={() => onSelectModule(m.id as AppModule)}
                aria-current={active ? "page" : undefined}
                className={
                  active
                    ? "h-8 flex items-center gap-1.5 px-2.5 rounded-lg text-sm font-medium whitespace-nowrap transition-colors bg-indigo-50 text-indigo-700 border border-indigo-200"
                    : "h-8 flex items-center gap-1.5 px-2.5 rounded-lg text-sm font-medium whitespace-nowrap transition-colors text-slate-500 hover:text-slate-800 hover:bg-slate-100"
                }
              >
                {lead}
                <span className="hidden lg:inline text-sm">{m.label}</span>
              </button>
            );
          })}
        </nav>

        {/* Active deck chip */}
        {activeModule === "pokemon" && activeDeckName && (
          <button
            onClick={() => setTab("decks")}
            className="hidden lg:flex items-center gap-1 px-2 py-1 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-700 text-xs font-medium hover:bg-indigo-100 transition-colors flex-shrink-0"
            title="Go to active deck"
          >
            <Swords className="w-3 h-3" />
            <span className="truncate max-w-[100px]">{activeDeckName}</span>
          </button>
        )}

        <div className="flex-1" />

        <StatusDot />

        {/* Auth */}
        <div className="flex items-center gap-1 flex-shrink-0 ml-1">
          {currentUser ? (
            <>
              <OrgSwitcher />
              <span className="hidden lg:block text-xs text-slate-400 max-w-[140px] truncate mr-0.5">
                {currentUser.email}
              </span>
              <button
                onClick={onOpenProfile}
                title="Profile & Settings"
                className={
                  showProfile
                    ? "h-8 flex items-center gap-1.5 px-2.5 rounded-lg transition-colors bg-indigo-600 text-white text-sm font-medium"
                    : "h-8 flex items-center gap-1.5 px-2.5 rounded-lg transition-colors text-slate-500 hover:text-slate-900 hover:bg-slate-100 text-sm font-medium"
                }
              >
                <UserIcon className="w-4 h-4" />
                <span className="hidden sm:inline">Profile</span>
              </button>
              <button
                onClick={() => onSelectModule("system")}
                title="System"
                className={
                  activeModule === "system"
                    ? "h-8 flex items-center gap-1.5 px-2.5 rounded-lg transition-colors bg-indigo-600 text-white text-sm font-medium"
                    : "h-8 flex items-center gap-1.5 px-2.5 rounded-lg transition-colors text-slate-500 hover:text-slate-900 hover:bg-slate-100 text-sm font-medium"
                }
              >
                <Settings className="w-4 h-4" />
                <span className="hidden sm:inline">System</span>
              </button>
              <button
                onClick={onLogout}
                title="Logout"
                className="h-8 flex items-center gap-1.5 px-2.5 rounded-lg transition-colors text-slate-500 hover:text-red-500 hover:bg-red-50 text-sm font-medium"
              >
                <LogOut className="w-4 h-4" />
                <span className="hidden sm:inline">Logout</span>
              </button>
            </>
          ) : (
            <button
              onClick={onLogin}
              className="h-8 px-3 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white flex items-center gap-1.5 text-sm font-medium transition-colors"
            >
              <LogIn className="w-4 h-4" />
              <span className="hidden sm:inline">Login</span>
            </button>
          )}
        </div>
      </div>

      {/* Pokémon tab strip */}
      {activeModule === "pokemon" && (
        <div className="border-t border-slate-100">
          <nav
            className="max-w-6xl mx-auto px-3 sm:px-4 flex gap-0.5 overflow-x-auto scrollbar-none"
            aria-label="Pokémon TCG tabs"
          >
            {POKEMON_TABS.map(({ id, label, icon }) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                aria-current={tab === id ? "page" : undefined}
                className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium whitespace-nowrap border-b-2 transition-colors flex-shrink-0 ${
                  tab === id
                    ? "border-indigo-600 text-indigo-600"
                    : "border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300"
                }`}
              >
                {icon}
                {label}
              </button>
            ))}
          </nav>
        </div>
      )}
    </header>
  );
}
