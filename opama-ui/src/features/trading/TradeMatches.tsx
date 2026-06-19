/**
 * Cross-user trade matching (pool tenancy — the flagship social feature).
 *
 * Calls GET /user/matches: discoverable orgs whose trade list holds cards on
 * your wishlist (and, where mutual, whose wishlist holds cards you offer). Also
 * exposes the discoverability opt-in (GET/PUT /user/discovery) — you only appear
 * in others' matches once you opt in.
 */
import { useEffect, useState } from "react";
import { Users, ArrowLeftRight, Loader2, Eye, EyeOff } from "lucide-react";
import { api } from "../../lib/api";
import { useToast } from "../../shared/Toaster";

type CardBrief = { card_id: string; name: string; set_id: string | null; image_small: string | null };
type Match = {
  org_id: number; org_name: string; org_slug: string | null; mutual: boolean;
  they_have: CardBrief[]; they_want: CardBrief[];
};
type MatchResp = {
  matches: Match[]; my_wishlist_count: number; my_tradelist_count: number; discoverable_orgs: number;
};

function CardChips({ cards, onOpen }: { cards: CardBrief[]; onOpen?: (id: string) => void }) {
  if (!cards.length) return <span className="text-xs text-slate-400">—</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {cards.map((c) => (
        <button
          key={c.card_id}
          onClick={() => onOpen?.(c.card_id)}
          title={c.name}
          className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white pl-1 pr-2 py-0.5 text-xs hover:bg-slate-50"
        >
          {c.image_small && <img src={c.image_small} alt="" className="w-4 h-5 object-cover rounded-sm" />}
          <span className="truncate max-w-[120px]">{c.name}</span>
        </button>
      ))}
    </div>
  );
}

export default function TradeMatches({ onOpenDetails }: { onOpenDetails?: (cardId: string) => void }) {
  const { success, error: toastError } = useToast();
  const [data, setData] = useState<MatchResp | null>(null);
  const [loading, setLoading] = useState(true);
  const [discoverable, setDiscoverable] = useState<boolean | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let alive = true;
    api<MatchResp>("/user/matches").then((r) => alive && setData(r)).catch(() => alive && setData(null)).finally(() => alive && setLoading(false));
    api<{ discoverable: boolean }>("/user/discovery").then((r) => alive && setDiscoverable(r.discoverable)).catch(() => {});
    return () => { alive = false; };
  }, []);

  const toggle = async () => {
    if (discoverable === null) return;
    setSaving(true);
    try {
      const r = await api<{ discoverable: boolean }>("/user/discovery", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ discoverable: !discoverable }),
      });
      setDiscoverable(r.discoverable);
      success(r.discoverable ? "You're now discoverable for trades" : "Hidden from trade matching");
    } catch (e) {
      toastError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mb-3 rounded-2xl border bg-white p-3">
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="font-semibold flex items-center gap-2 text-slate-800">
          <Users className="w-4 h-4 text-indigo-600" /> Trade matches
        </div>
        {discoverable !== null && (
          <button
            onClick={toggle}
            disabled={saving}
            title={discoverable ? "You appear in others' matches" : "You're hidden from matching"}
            className={`inline-flex items-center gap-1.5 px-2.5 h-8 rounded-lg text-xs font-medium disabled:opacity-60 ${
              discoverable ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"
            }`}
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : discoverable ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
            {discoverable ? "Discoverable" : "Hidden"}
          </button>
        )}
      </div>

      {loading ? (
        <div className="text-xs text-slate-400 flex items-center gap-1.5"><Loader2 className="w-3.5 h-3.5 animate-spin" /> Finding matches…</div>
      ) : !data || data.matches.length === 0 ? (
        <p className="text-xs text-slate-500">
          No matches yet. Add cards to your wishlist and trade list — matches appear against other collectors who opt into discovery.
        </p>
      ) : (
        <ul className="space-y-2">
          {data.matches.map((m) => (
            <li key={m.org_id} className="rounded-xl border border-slate-100 p-2.5">
              <div className="flex items-center gap-2 mb-1.5">
                <span className="font-medium text-sm text-slate-800">{m.org_name}</span>
                {m.mutual && (
                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-700 bg-indigo-50 px-1.5 py-0.5 rounded-full">
                    <ArrowLeftRight className="w-3 h-3" /> Mutual
                  </span>
                )}
              </div>
              <div className="grid sm:grid-cols-2 gap-2">
                <div>
                  <div className="text-[11px] uppercase tracking-wide text-slate-400 mb-1">They have (you want)</div>
                  <CardChips cards={m.they_have} onOpen={onOpenDetails} />
                </div>
                <div>
                  <div className="text-[11px] uppercase tracking-wide text-slate-400 mb-1">They want (you have)</div>
                  <CardChips cards={m.they_want} onOpen={onOpenDetails} />
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
