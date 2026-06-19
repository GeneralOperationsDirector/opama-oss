/**
 * Collection completion summary (the motivating headline the Pokédex lacked).
 *
 * One call to GET /cards/sets/progress — server-computed exact owned/total per
 * set for the active org — surfaced as an aggregate ("N cards collected across
 * M sets") plus the sets closest to completion with mini progress bars.
 */
import { useEffect, useState } from "react";
import { Trophy } from "lucide-react";
import { api } from "../../lib/api";

type SetProgress = { set_id: string; name: string; owned: number; total: number; pct: number };
type Progress = {
  summary: { sets_started: number; cards_owned: number; catalog_total: number };
  sets: SetProgress[];
};

export default function CollectionSummary() {
  const [p, setP] = useState<Progress | null>(null);

  useEffect(() => {
    let alive = true;
    api<Progress>("/cards/sets/progress")
      .then((r) => alive && setP(r))
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  if (!p || p.summary.sets_started === 0) return null;
  const top = p.sets.slice(0, 6);

  return (
    <div className="mb-3 rounded-2xl border bg-gradient-to-br from-indigo-50 to-white p-3">
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-800">
        <Trophy className="w-4 h-4 text-amber-500 flex-shrink-0" />
        {p.summary.cards_owned.toLocaleString()} cards collected · {p.summary.sets_started}
        {" "}set{p.summary.sets_started !== 1 ? "s" : ""} started
      </div>

      <div className="mt-2 grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
        {top.map((s) => (
          <div key={s.set_id} className="text-xs">
            <div className="flex items-baseline justify-between gap-2">
              <span className="truncate font-medium text-slate-700">{s.name}</span>
              <span className="text-slate-400 shrink-0">{s.owned}/{s.total} · {s.pct}%</span>
            </div>
            <div className="mt-1 h-1.5 rounded-full bg-slate-100 overflow-hidden">
              <div className="h-full bg-indigo-500" style={{ width: `${Math.min(100, s.pct)}%` }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
