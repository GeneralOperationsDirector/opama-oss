/**
 * Import a deck from PTCG Live decklist text.
 *
 * Paste a decklist (the "4 Charizard ex OBF 125 / …" format players export from
 * PTCG Live), POST it to /decks/import, and the server resolves each line to a
 * catalog card and creates a new deck. Lines that can't be matched are surfaced
 * back so nothing fails silently.
 */
import { useState } from "react";
import { Upload, X, Loader2 } from "lucide-react";
import { postJSON } from "../../lib/api";
import { useToast } from "../../shared/Toaster";

type ImportResult = {
  deck_id: number;
  name: string;
  added: number;
  unique_cards: number;
  unresolved: { qty: number; name: string; set_code: string | null; number: string | null }[];
};

export default function ImportDeckModal({
  onClose,
  onImported,
}: {
  onClose: () => void;
  onImported: (deckId: number) => Promise<void> | void;
}) {
  const { success, error: toastError, toast } = useToast();
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!text.trim()) {
      toastError("Paste a decklist first");
      return;
    }
    setBusy(true);
    try {
      const r = await postJSON<ImportResult>("/decks/import", {
        text,
        name: name.trim() || undefined,
      });
      success(`Imported ${r.added} cards into "${r.name}"`);
      if (r.unresolved.length) {
        toast(`${r.unresolved.length} line(s) couldn't be matched: ${r.unresolved.map((u) => u.name).slice(0, 3).join(", ")}${r.unresolved.length > 3 ? "…" : ""}`, { type: "info" });
      }
      await onImported(r.deck_id);
      onClose();
    } catch (e) {
      toastError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b">
          <div className="font-semibold flex items-center gap-2">
            <Upload className="w-4 h-4 text-indigo-600" /> Import decklist
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700"><X className="w-4 h-4" /></button>
        </div>

        <div className="p-4 space-y-3">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Deck name (optional)"
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
          />
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={12}
            placeholder={"Pokémon: 6\n4 Charizard ex OBF 125\n2 Charmander MEW 4\n\nTrainer: …\nEnergy: …"}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm font-mono"
          />
          <p className="text-xs text-slate-400">
            Paste the PTCG Live export format. Cards are matched by set code + number, falling back to name.
          </p>
        </div>

        <div className="flex justify-end gap-2 px-4 py-3 border-t">
          <button onClick={onClose} className="px-3 h-9 rounded-lg text-sm text-slate-600 hover:bg-slate-100">Cancel</button>
          <button
            onClick={submit}
            disabled={busy}
            className="px-3 h-9 rounded-lg text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 inline-flex items-center gap-1.5"
          >
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
            Import
          </button>
        </div>
      </div>
    </div>
  );
}
