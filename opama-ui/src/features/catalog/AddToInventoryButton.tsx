import React, { useRef, useState } from "react";
import { ChevronDown, Plus } from "lucide-react";

interface Props {
  onAdd: (quantity: number) => Promise<void>;
}

const QUICK = [1, 2, 4];

export default function AddToInventoryButton({ onAdd }: Props) {
  const [open, setOpen] = useState(false);
  const [custom, setCustom] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handle = async (qty: number) => {
    if (qty < 1) return;
    setBusy(true);
    setOpen(false);
    setCustom("");
    try {
      await onAdd(qty);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative flex">
      {/* Primary +1 button */}
      <button
        disabled={busy}
        onClick={() => handle(1)}
        className="px-2 sm:px-3 py-1.5 rounded-l-xl bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium disabled:opacity-50 transition-colors"
      >
        {busy ? (
          <span className="inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
        ) : (
          <>
            <Plus className="w-3.5 h-3.5 sm:hidden" />
            <span className="hidden sm:inline">Own</span>
          </>
        )}
      </button>

      {/* Dropdown arrow */}
      <button
        disabled={busy}
        onClick={() => { setOpen((o) => !o); setTimeout(() => inputRef.current?.focus(), 50); }}
        className="px-1.5 py-1.5 rounded-r-xl bg-emerald-700 hover:bg-emerald-800 text-white disabled:opacity-50 border-l border-emerald-500 transition-colors"
        aria-label="Choose quantity"
      >
        <ChevronDown className="w-3.5 h-3.5" />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute top-full left-0 mt-1 z-20 bg-white border border-slate-200 rounded-xl shadow-lg p-2 min-w-[120px]">
            <p className="text-xs text-slate-400 px-2 pb-1">Add copies</p>
            {QUICK.map((n) => (
              <button
                key={n}
                onClick={() => handle(n)}
                className="w-full text-left px-3 py-1.5 text-sm rounded-lg hover:bg-emerald-50 hover:text-emerald-700 transition-colors"
              >
                +{n}
              </button>
            ))}
            <div className="flex gap-1 mt-1 px-1">
              <input
                ref={inputRef}
                type="number"
                min={1}
                max={99}
                value={custom}
                onChange={(e) => setCustom(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handle(parseInt(custom) || 1)}
                placeholder="qty"
                className="w-14 border border-slate-200 rounded-lg px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
              />
              <button
                onClick={() => handle(parseInt(custom) || 1)}
                disabled={!custom || parseInt(custom) < 1}
                className="px-2 py-1 rounded-lg bg-emerald-600 text-white text-sm disabled:opacity-40 hover:bg-emerald-700"
              >
                Add
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
