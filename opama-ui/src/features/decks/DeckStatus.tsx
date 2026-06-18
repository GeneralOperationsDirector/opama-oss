/**
 * Deck legality / construction status.
 *
 * Calls GET /decks/{id}/validate and shows a legal/illegal badge, the 60-card
 * count, the Pokémon/Trainer/Energy split, and any construction issues (60-card
 * rule, 4-copy limit, ≥1 Basic Pokémon, ACE SPEC/Radiant limits, format
 * legality). Re-validates whenever the deck's contents change (`signature`),
 * debounced so it reads committed state after a card edit settles.
 */
import { useEffect, useState } from "react";
import { CheckCircle2, AlertTriangle, XCircle, Loader2 } from "lucide-react";
import { api } from "../../lib/api";

type Issue = { code: string; severity: "error" | "warning"; message: string; card_name?: string | null };
type Validation = {
  format: string;
  legal: boolean;
  total: number;
  counts: { pokemon: number; trainer: number; energy: number };
  issues: Issue[];
};

export default function DeckStatus({ deckId, signature }: { deckId: number; signature: string }) {
  const [v, setV] = useState<Validation | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    const t = setTimeout(() => {
      api<Validation>(`/decks/${deckId}/validate`)
        .then((r) => { if (alive) { setV(r); setLoading(false); } })
        .catch(() => { if (alive) { setV(null); setLoading(false); } });
    }, 350);
    return () => { alive = false; clearTimeout(t); };
  }, [deckId, signature]);

  if (loading && !v) {
    return (
      <span className="mt-2 inline-flex items-center gap-1.5 text-xs text-slate-400">
        <Loader2 className="w-3.5 h-3.5 animate-spin" /> Checking…
      </span>
    );
  }
  if (!v) return null;

  const errors = v.issues.filter((i) => i.severity === "error");
  const warnings = v.issues.filter((i) => i.severity === "warning");

  return (
    <div className="mt-2 space-y-1.5">
      <div className="flex items-center gap-2 flex-wrap">
        {v.legal ? (
          <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full">
            <CheckCircle2 className="w-3.5 h-3.5" /> Legal · {v.format}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-xs font-semibold text-rose-700 bg-rose-50 px-2 py-0.5 rounded-full">
            <XCircle className="w-3.5 h-3.5" /> Illegal · {v.format}
          </span>
        )}
        <span className={`text-xs ${v.total === 60 ? "text-slate-500" : "text-rose-600 font-medium"}`}>
          {v.total}/60 cards
        </span>
        <span className="text-xs text-slate-400">
          {v.counts.pokemon} P · {v.counts.trainer} T · {v.counts.energy} E
        </span>
      </div>

      {(errors.length > 0 || warnings.length > 0) && (
        <ul className="text-xs space-y-0.5">
          {errors.map((i, idx) => (
            <li key={`e${idx}`} className="flex items-start gap-1.5 text-rose-600">
              <XCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
              <span>{i.message}</span>
            </li>
          ))}
          {warnings.map((i, idx) => (
            <li key={`w${idx}`} className="flex items-start gap-1.5 text-amber-600">
              <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
              <span>{i.message}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
