import React, { useState } from "react";
import { Search, X } from "lucide-react";
import { TEMPLATES, type CollectionTemplate } from "./templates";

interface Props {
  recentCategories?: string[];
  onSelect: (template: CollectionTemplate) => void;
  onClose: () => void;
}

export default function TemplatePicker({ recentCategories = [], onSelect, onClose }: Props) {
  const [query, setQuery] = useState("");

  const filtered = query.trim()
    ? TEMPLATES.filter(
        (t) =>
          t.name.toLowerCase().includes(query.toLowerCase()) ||
          t.category.toLowerCase().includes(query.toLowerCase())
      )
    : TEMPLATES;

  // Pin recently-used categories to the top (excluding custom)
  const recent = recentCategories
    .map((cat) => TEMPLATES.find((t) => t.category.toLowerCase() === cat.toLowerCase()))
    .filter((t): t is CollectionTemplate => !!t && t.id !== "custom");

  const showRecent = recent.length > 0 && !query.trim();

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-end sm:items-center justify-center p-0 sm:p-4">
      <div className="bg-white w-full sm:max-w-2xl sm:rounded-2xl shadow-2xl flex flex-col max-h-[90vh]">

        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-5 pb-3 border-b border-slate-100">
          <div>
            <h2 className="text-lg font-bold text-slate-800">What are you tracking?</h2>
            <p className="text-sm text-slate-500 mt-0.5">Pick a template to pre-fill common fields, or start custom.</p>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Search */}
        <div className="px-5 py-3 border-b border-slate-100">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              autoFocus
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search templates…"
              className="w-full pl-9 pr-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
          </div>
        </div>

        {/* Template grid */}
        <div className="overflow-y-auto px-5 py-4 space-y-5">

          {/* Recent */}
          {showRecent && (
            <section>
              <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Recent</h3>
              <div className="flex flex-wrap gap-2">
                {recent.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => onSelect(t)}
                    className="flex items-center gap-2 px-3 py-2 rounded-xl border border-slate-200 bg-white hover:border-indigo-400 hover:bg-indigo-50 transition-colors text-sm font-medium text-slate-700"
                  >
                    <span className="text-base">{t.emoji}</span>
                    {t.name}
                  </button>
                ))}
              </div>
            </section>
          )}

          {/* All templates */}
          <section>
            {showRecent && (
              <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">All Templates</h3>
            )}
            <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
              {filtered.map((t) => (
                <button
                  key={t.id}
                  onClick={() => onSelect(t)}
                  className={`flex flex-col items-center gap-1.5 p-3 rounded-xl border transition-colors text-center group ${
                    t.id === "custom"
                      ? "border-dashed border-slate-300 hover:border-indigo-400 hover:bg-indigo-50"
                      : "border-slate-200 hover:border-indigo-400 hover:bg-indigo-50"
                  }`}
                >
                  <span className="text-2xl leading-none">{t.emoji}</span>
                  <span className="text-xs font-medium text-slate-700 group-hover:text-indigo-700 leading-tight">
                    {t.name}
                  </span>
                </button>
              ))}
            </div>

            {filtered.length === 0 && (
              <div className="py-8 text-center text-slate-400 text-sm">
                No templates match "{query}" —{" "}
                <button
                  className="text-indigo-600 hover:underline"
                  onClick={() => onSelect({ ...TEMPLATES.at(-1)!, category: query, name: query })}
                >
                  create custom
                </button>
              </div>
            )}
          </section>

        </div>
      </div>
    </div>
  );
}
