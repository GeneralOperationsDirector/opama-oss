/**
 * GradeResultCard — renders one finished grading result.
 *
 * Shows the overall PSA-style grade plus the four sub-scores (centering,
 * corners, surface, edges) from the backend pipeline, the identified card,
 * the annotated debug crops, the PNG report download, the recenter tool, and
 * the accuracy-feedback controls. Consumed by GradingView. Display-only over
 * the GradeResult shape — grading itself happens server-side (analyzer.py).
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle, ChevronDown, ChevronUp, Crosshair, Download, Loader2, ScanSearch } from "lucide-react";
import { api, API_BASE } from "../../lib/api";
import { getAuthToken } from "../../lib/authToken";
import { orgHeader } from "../../lib/activeOrg";
import type { GradeResult, Verdict, Dimension, FeedbackOut } from "./types";
import TransferPanel from "./TransferPanel";

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ScoreBar({ score, max = 10 }: { score: number; max?: number }) {
  const pct = (score / max) * 100;
  const color =
    score >= 9 ? "bg-emerald-500" :
    score >= 7 ? "bg-lime-500" :
    score >= 5 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 rounded-full bg-slate-200">
        <div className={`h-2 rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-sm font-semibold w-6 text-right">{score}</span>
    </div>
  );
}

function MiniBar({ value, max }: { value: number; max: number }) {
  const pct = Math.min((value / max) * 100, 100);
  const color =
    pct <= 30 ? "bg-emerald-400" :
    pct <= 60 ? "bg-amber-400" : "bg-red-400";
  return (
    <div className="flex-1 h-1.5 rounded-full bg-slate-200">
      <div className={`h-1.5 rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function CornerDot({ value }: { value: number }) {
  const color =
    value >= 70 ? "bg-emerald-400" :
    value >= 45 ? "bg-amber-400" : "bg-red-400";
  return (
    <div className="flex flex-col items-center gap-0.5">
      <div
        title={`${value.toFixed(0)}/100`}
        className={`w-3 h-3 rounded-full ${color} border border-white shadow`}
      />
      <span className="text-[9px] text-slate-400 leading-none">{value.toFixed(0)}</span>
    </div>
  );
}

function gradeColor(grade: number) {
  if (grade >= 9) return "text-emerald-600";
  if (grade >= 7) return "text-lime-600";
  if (grade >= 5) return "text-amber-600";
  return "text-red-600";
}

// ---------------------------------------------------------------------------
// Grade labels map
// ---------------------------------------------------------------------------

const GRADE_LABELS: Record<number, string> = {
  10: "Gem Mint",
  9: "Mint",
  8: "NM-MT",
  7: "Near Mint",
  6: "EX-MT",
  5: "Excellent",
  4: "VG-EX",
  3: "Very Good",
  2: "Good",
  1: "Poor",
};

// ---------------------------------------------------------------------------
// Adjustments panel
// ---------------------------------------------------------------------------

const DEFAULT_WEIGHTS = { centering: 40, corners: 40, surface: 20 };

interface AdjustmentsPanelProps {
  scores: { centering: number; corners: number; surface: number };
  baseGrade: number;
}

function AdjustmentsPanel({ scores, baseGrade }: AdjustmentsPanelProps) {
  const [open, setOpen] = useState(false);
  const [fullArt, setFullArt] = useState(false);
  const [weights, setWeights] = useState(DEFAULT_WEIGHTS);

  const wC  = fullArt ? 0 : weights.centering;
  const wCo = weights.corners;
  const wS  = weights.surface;
  const total = wC + wCo + wS;

  const raw = total > 0
    ? (scores.centering * wC
       + scores.corners * wCo
       + scores.surface * wS) / total
    : baseGrade;

  const adjGrade = Math.max(1, Math.min(10, Math.round(raw * 2) / 2));
  const labelKey = Object.keys(GRADE_LABELS)
    .map(Number)
    .reduce((prev, curr) =>
      Math.abs(curr - adjGrade) < Math.abs(prev - adjGrade) ? curr : prev
    );
  const adjLabel = GRADE_LABELS[labelKey];

  return (
    <div className="border-t border-slate-100">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-6 py-3 text-sm text-slate-500 hover:text-slate-700 hover:bg-slate-50 transition"
      >
        <span>Adjustments</span>
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {open && (
        <div className="px-6 pb-5 space-y-4">
          {/* Full Art toggle */}
          <div>
            <button
              onClick={() => setFullArt((f) => !f)}
              className={`px-4 py-1.5 rounded-full text-xs font-medium border transition
                ${fullArt
                  ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                  : "border-slate-200 text-slate-500 hover:border-slate-300"}`}
            >
              Full Art / No Border
            </button>
            {fullArt && (
              <p className="mt-1.5 text-xs text-slate-400">
                Centering excluded — full art card has no printable border
              </p>
            )}
          </div>

          {/* Weight sliders */}
          <div className="space-y-3">
            {(["centering", "corners", "surface"] as const).map((dim) => {
              const label = dim.charAt(0).toUpperCase() + dim.slice(1);
              const disabled = dim === "centering" && fullArt;
              return (
                <div key={dim} className="flex items-center gap-3">
                  <span className={`text-xs w-20 ${disabled ? "text-slate-300" : "text-slate-500"}`}>
                    {label}
                  </span>
                  <input
                    type="range"
                    min={0}
                    max={60}
                    step={5}
                    value={weights[dim]}
                    disabled={disabled}
                    onChange={(e) =>
                      setWeights((w) => ({ ...w, [dim]: Number(e.target.value) }))
                    }
                    className="flex-1 accent-indigo-500 disabled:opacity-30"
                  />
                  <span className={`text-xs w-8 text-right font-mono ${disabled ? "text-slate-300" : "text-slate-600"}`}>
                    {weights[dim]}%
                  </span>
                </div>
              );
            })}
          </div>

          {/* Reset button */}
          <button
            onClick={() => setWeights(DEFAULT_WEIGHTS)}
            className="text-xs text-slate-400 hover:text-slate-600 transition"
          >
            Reset weights
          </button>

          {/* Adjusted grade */}
          <div className="bg-slate-50 rounded-xl px-4 py-3 text-center">
            <p className="text-xs text-slate-400 uppercase tracking-wide mb-1">Adjusted Grade</p>
            <span className={`text-3xl font-black ${gradeColor(adjGrade)}`}>
              {adjGrade.toFixed(1)}
            </span>
            <span className="ml-2 text-base font-semibold text-slate-500">— {adjLabel}</span>
          </div>

          <p className="text-xs text-slate-400">
            Weights only affect this view — they are not saved.
          </p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Feedback widget
// ---------------------------------------------------------------------------

const DIMENSIONS: { id: Dimension; label: string }[] = [
  { id: "centering", label: "Centering" },
  { id: "corners",   label: "Corners" },
  { id: "surface",   label: "Surface" },
  { id: "edges",     label: "Edges" },
];

const COMPANIES = ["PSA", "CGC", "BGS", "SGC"];

interface FeedbackWidgetProps {
  resultId: number;
  estimatedGrade: number;
  onToast?: (msg: string, type?: "success" | "error" | "info") => void;
}

function FeedbackWidget({ resultId, estimatedGrade, onToast }: FeedbackWidgetProps) {
  const [open, setOpen] = useState(false);
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [actualGrade, setActualGrade] = useState("");
  const [company, setCompany] = useState("");
  const [dims, setDims] = useState<Set<Dimension>>(new Set());
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const toggleDim = (d: Dimension) =>
    setDims((prev) => {
      const next = new Set(prev);
      next.has(d) ? next.delete(d) : next.add(d);
      return next;
    });

  const handleSubmit = async () => {
    if (!verdict) return;
    setSubmitting(true);
    try {
      await api<FeedbackOut>(`/grading/${resultId}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          overall_verdict: verdict,
          actual_grade: actualGrade ? parseFloat(actualGrade) : null,
          grading_company: company || null,
          inaccurate_dimensions: Array.from(dims),
          notes: notes.trim() || null,
        }),
      });
      setSubmitted(true);
    } catch (err: any) {
      onToast?.(`Failed to submit feedback: ${err.message}`, "error");
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div className="flex items-center gap-2 px-6 py-3 bg-emerald-50 border-t border-emerald-100 text-emerald-700 text-sm">
        <CheckCircle size={15} />
        Feedback recorded — thank you.
      </div>
    );
  }

  return (
    <div className="border-t border-slate-100">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-6 py-3 text-sm text-slate-500 hover:text-slate-700 hover:bg-slate-50 transition"
      >
        <span>Was this estimate accurate?</span>
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {open && (
        <div className="px-6 pb-5 space-y-4">

          {/* Verdict */}
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Overall</p>
            <div className="flex gap-2">
              {(["too_low", "accurate", "too_high"] as Verdict[]).map((v) => {
                const label = v === "too_low" ? "Too low" : v === "accurate" ? "Accurate" : "Too high";
                const active = verdict === v;
                const color =
                  v === "accurate" ? "border-emerald-500 bg-emerald-50 text-emerald-700" :
                  v === "too_high"  ? "border-amber-500  bg-amber-50  text-amber-700"  :
                                      "border-blue-500   bg-blue-50   text-blue-700";
                return (
                  <button
                    key={v}
                    onClick={() => setVerdict(v)}
                    className={`flex-1 py-1.5 rounded-lg border text-sm font-medium transition
                      ${active ? color : "border-slate-200 text-slate-500 hover:border-slate-300"}`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Which dimensions were off */}
          {verdict && verdict !== "accurate" && (
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
                Which area(s) were wrong?
              </p>
              <div className="flex flex-wrap gap-2">
                {DIMENSIONS.map(({ id, label }) => (
                  <button
                    key={id}
                    onClick={() => toggleDim(id)}
                    className={`px-3 py-1 rounded-full text-xs border transition
                      ${dims.has(id)
                        ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                        : "border-slate-200 text-slate-500 hover:border-slate-300"}`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Actual grade (optional) */}
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
              Actual grade <span className="font-normal normal-case">(if professionally graded)</span>
            </p>
            <div className="flex gap-2">
              <input
                type="number"
                min={1}
                max={10}
                step={0.5}
                placeholder={`Est. ${estimatedGrade}`}
                value={actualGrade}
                onChange={(e) => setActualGrade(e.target.value)}
                className="w-24 px-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
              <select
                value={company}
                onChange={(e) => setCompany(e.target.value)}
                className="flex-1 px-3 py-1.5 rounded-lg border border-slate-200 text-sm text-slate-600 focus:outline-none focus:ring-2 focus:ring-indigo-300"
              >
                <option value="">Grading company…</option>
                {COMPANIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          </div>

          {/* Notes */}
          <div>
            <textarea
              rows={2}
              placeholder="Optional notes (e.g. 'corners are actually sharp, surface is clean')"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              maxLength={500}
              className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm text-slate-700 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
          </div>

          <button
            onClick={handleSubmit}
            disabled={!verdict || submitting}
            className="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-slate-900 text-white text-sm font-medium disabled:opacity-40 hover:bg-slate-700 transition"
          >
            {submitting && <Loader2 size={14} className="animate-spin" />}
            Submit feedback
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Debug diagnostic images
// ---------------------------------------------------------------------------

const DEBUG_VIEWS = ["boundary", "rectified", "centering", "corners", "surface", "edges", "grade"] as const;
type DebugView = typeof DEBUG_VIEWS[number];

const DEBUG_LABELS: Record<DebugView, string> = {
  boundary:  "1 · Boundary detection — card quad on original image",
  rectified: "2 · Rectification — perspective-corrected to 630×882",
  centering: "3 · Centering — inner border detection + ratio bars",
  corners:   "4 · Corners — patch sharpness (original vs Sobel heatmap)",
  surface:   "5 · Surface — directional top-hat scratch detection",
  edges:     "6 · Edges — strip standard deviation",
  grade:     "7 · Grade summary — scores, weights, formula",
};

interface DebugPanelProps {
  resultId: number;
}

function DebugPanel({ resultId }: DebugPanelProps) {
  const [open, setOpen]       = useState(false);
  const [loading, setLoading] = useState(false);
  const [urls, setUrls]       = useState<Partial<Record<DebugView, string>>>({});
  const [errors, setErrors]   = useState<Partial<Record<DebugView, string>>>({});

  useEffect(() => {
    return () => {
      Object.values(urls).forEach((u) => u && URL.revokeObjectURL(u));
    };
  }, [urls]);

  const load = async () => {
    if (Object.keys(urls).length > 0 || Object.keys(errors).length > 0) return;
    setLoading(true);
    const token = await getAuthToken();
    const headers: HeadersInit = { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...orgHeader() };
    const results = await Promise.allSettled(
      DEBUG_VIEWS.map(async (view) => {
        const res = await fetch(`${API_BASE}/grading/${resultId}/debug/${view}`, { headers });
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
        return [view, URL.createObjectURL(await res.blob())] as [DebugView, string];
      })
    );
    const newUrls: Partial<Record<DebugView, string>> = {};
    const newErrors: Partial<Record<DebugView, string>> = {};
    results.forEach((r, i) => {
      if (r.status === "fulfilled") newUrls[DEBUG_VIEWS[i]]  = r.value[1];
      else                         newErrors[DEBUG_VIEWS[i]] = r.reason?.message ?? "Failed";
    });
    setUrls(newUrls);
    setErrors(newErrors);
    setLoading(false);
  };

  const toggle = () => {
    if (!open) load();
    setOpen((o) => !o);
  };

  return (
    <div className="border-t border-slate-100">
      <button
        onClick={toggle}
        className="w-full flex items-center justify-between px-6 py-3 text-sm text-slate-500 hover:text-slate-700 hover:bg-slate-50 transition"
      >
        <span className="flex items-center gap-2">
          <ScanSearch size={14} />
          Diagnostic views
        </span>
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {open && (
        <div className="px-6 pb-5">
          {loading && (
            <div className="flex justify-center py-8">
              <Loader2 size={22} className="animate-spin text-slate-400" />
            </div>
          )}
          {!loading && (
            <div className="space-y-5">
              {DEBUG_VIEWS.map((view) => (
                <div key={view}>
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
                    {DEBUG_LABELS[view]}
                  </p>
                  {urls[view] ? (
                    <img
                      src={urls[view]}
                      alt={`${view} diagnostic`}
                      className="w-full rounded-lg border border-slate-200 bg-slate-50"
                    />
                  ) : errors[view] ? (
                    <div className="h-10 rounded-lg bg-red-50 border border-red-100 flex items-center px-3 text-xs text-red-500">
                      {errors[view]}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Border colour sampler — rectangle drag tool for centering re-analysis
// ---------------------------------------------------------------------------

interface BorderSamplerProps {
  resultId: number;
  onRecenter: (centering: GradeResult["centering"], grade: number, label: string, method: string) => void;
  onToast?: (msg: string, type?: "success" | "error" | "info") => void;
}

function BorderSampler({ resultId, onRecenter, onToast }: BorderSamplerProps) {
  const [open, setOpen]         = useState(false);
  const [color, setColor]       = useState<[number, number, number] | null>(null);
  const [loading, setLoading]   = useState(false);
  const [method, setMethod]     = useState<string | null>(null);
  const canvasRef   = useRef<HTMLCanvasElement>(null);
  const imgRef      = useRef<HTMLImageElement | null>(null);
  const dragRef     = useRef<{ start: [number,number]; end: [number,number] } | null>(null);
  const dragging    = useRef(false);

  const scanUrl = `${API_BASE}/uploads/grading/${resultId}.jpg`;

  useEffect(() => {
    if (!open) return;
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.src = scanUrl;
    img.onload = () => {
      imgRef.current = img;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const maxW = canvas.parentElement?.clientWidth ?? 480;
      const scale = Math.min(1, maxW / img.naturalWidth);
      canvas.width  = img.naturalWidth  * scale;
      canvas.height = img.naturalHeight * scale;
      canvas.getContext("2d")!.drawImage(img, 0, 0, canvas.width, canvas.height);
    };
  }, [open, scanUrl]);

  const coords = (e: React.MouseEvent<HTMLCanvasElement>): [number, number] => {
    const r = canvasRef.current!.getBoundingClientRect();
    const sx = canvasRef.current!.width  / r.width;
    const sy = canvasRef.current!.height / r.height;
    return [Math.floor((e.clientX - r.left) * sx), Math.floor((e.clientY - r.top) * sy)];
  };

  const redraw = (start?: [number,number], end?: [number,number]) => {
    const canvas = canvasRef.current;
    const img    = imgRef.current;
    if (!canvas || !img) return;
    const ctx = canvas.getContext("2d")!;
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    if (start && end) {
      const x = Math.min(start[0], end[0]), y = Math.min(start[1], end[1]);
      const w = Math.abs(end[0] - start[0]),  h = Math.abs(end[1] - start[1]);
      ctx.fillStyle   = "rgba(99,102,241,0.15)";
      ctx.fillRect(x, y, w, h);
      ctx.strokeStyle = "#6366f1";
      ctx.lineWidth   = 2;
      ctx.setLineDash([4, 2]);
      ctx.strokeRect(x, y, w, h);
    }
  };

  const onMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    dragging.current = true;
    const pt = coords(e);
    dragRef.current  = { start: pt, end: pt };
    setColor(null);
    setMethod(null);
  };

  const onMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!dragging.current || !dragRef.current) return;
    dragRef.current.end = coords(e);
    redraw(dragRef.current.start, dragRef.current.end);
  };

  const onMouseUp = () => {
    if (!dragging.current || !dragRef.current) return;
    dragging.current = false;
    const { start, end } = dragRef.current;
    const canvas = canvasRef.current!;
    const x = Math.min(start[0], end[0]), y = Math.min(start[1], end[1]);
    const w = Math.max(1, Math.abs(end[0] - start[0]));
    const h = Math.max(1, Math.abs(end[1] - start[1]));
    const data = canvas.getContext("2d")!.getImageData(x, y, w, h).data;
    const rs: number[] = [], gs: number[] = [], bs: number[] = [];
    for (let i = 0; i < data.length; i += 4) { rs.push(data[i]); gs.push(data[i+1]); bs.push(data[i+2]); }
    const med = (a: number[]) => { const s = [...a].sort((x,y)=>x-y); return s[Math.floor(s.length/2)]; };
    setColor([med(rs), med(gs), med(bs)]);
  };

  const handleRecenter = useCallback(async () => {
    if (!color) return;
    setLoading(true);
    try {
      const token = await getAuthToken();
      const res = await fetch(`${API_BASE}/grading/${resultId}/recenter`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...({ ...(token ? { Authorization: `Bearer ${token}` } : {}), ...orgHeader() }),
        },
        body: JSON.stringify({ border_r: color[0], border_g: color[1], border_b: color[2] }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();
      setMethod(data.method);
      onRecenter(data.centering, data.estimated_grade, data.grade_label, data.method);
      if (data.method === "color_hint") {
        onToast?.("Centering updated using sampled border colour", "success");
      } else {
        onToast?.("Border colour not clearly detected — gradient method used", "info");
      }
    } catch {
      onToast?.("Re-centering failed", "error");
    } finally {
      setLoading(false);
    }
  }, [color, resultId, onRecenter, onToast]);

  return (
    <div className="mt-3">
      {!open ? (
        <button
          onClick={() => { setOpen(true); setColor(null); setMethod(null); }}
          className="flex items-center gap-1.5 text-xs text-indigo-500 hover:text-indigo-700 transition"
        >
          <Crosshair size={12} />
          Fix centering — sample border colour
        </button>
      ) : (
        <div className="space-y-3 mt-1">
          <div className="flex items-center justify-between">
            <p className="text-xs text-slate-500">
              Drag a rectangle over the card's coloured border band
            </p>
            <button onClick={() => setOpen(false)} className="text-xs text-slate-400 hover:text-slate-600">
              Cancel
            </button>
          </div>
          <canvas
            ref={canvasRef}
            className="w-full rounded-lg border border-slate-200 cursor-crosshair select-none"
            onMouseDown={onMouseDown}
            onMouseMove={onMouseMove}
            onMouseUp={onMouseUp}
            onMouseLeave={onMouseUp}
          />
          {color && (
            <div className="flex items-center gap-3">
              <div
                className="w-8 h-8 rounded-lg border border-slate-200 flex-shrink-0 shadow-sm"
                style={{ backgroundColor: `rgb(${color.join(",")})` }}
              />
              <div className="flex-1 min-w-0">
                <p className="text-xs text-slate-500">rgb({color.join(", ")})</p>
              </div>
              <button
                onClick={handleRecenter}
                disabled={loading}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs font-medium disabled:opacity-40 hover:bg-indigo-700 transition flex-shrink-0"
              >
                {loading && <Loader2 size={12} className="animate-spin" />}
                Re-analyze
              </button>
            </div>
          )}
          {method === "gradient_fallback" && (
            <p className="text-xs text-amber-600 bg-amber-50 rounded px-2 py-1.5">
              Border colour not clearly detected — gradient method used. Try selecting a region with a more saturated colour.
            </p>
          )}
          {method === "color_hint" && (
            <p className="text-xs text-emerald-600 bg-emerald-50 rounded px-2 py-1.5">
              Centering updated using the sampled border colour.
            </p>
          )}
        </div>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface Props {
  result: GradeResult;
  onToast?: (msg: string, type?: "success" | "error" | "info") => void;
  onTransferred?: (destination: string, itemId: number) => void;
}

export default function GradeResultCard({ result, onToast, onTransferred }: Props) {
  const [downloading, setDownloading]     = useState(false);
  // Local overrides applied after a colour-hint re-centering
  const [localCentering, setLocalCentering] = useState<GradeResult["centering"] | null>(null);
  const [localGrade, setLocalGrade]         = useState<{ estimated_grade: number; grade_label: string } | null>(null);

  const centering = localCentering ?? result.centering;
  const { corners, surface, edges } = result;
  const displayGrade = localGrade?.estimated_grade ?? result.estimated_grade;
  const displayLabel = localGrade?.grade_label     ?? result.grade_label;

  const handleRecenter = useCallback(
    (c: GradeResult["centering"], grade: number, label: string) => {
      setLocalCentering(c);
      setLocalGrade({ estimated_grade: grade, grade_label: label });
    },
    []
  );

  const handleDownloadReport = async () => {
    if (!result.id) return;
    setDownloading(true);
    try {
      const token = await getAuthToken();
      const res = await fetch(`${API_BASE}/grading/${result.id}/report.png`, {
        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...orgHeader() },
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href     = url;
      const name = result.identification?.name ?? "card";
      a.download = `grade-report-${name.toLowerCase().replace(/\s+/g, "-")}-${result.id}.png`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      onToast?.("Failed to download report", "error");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
      {/* Header */}
      <div className="bg-slate-900 text-white px-6 py-5 flex items-center justify-between">
        <div>
          <p className="text-sm text-slate-400 uppercase tracking-widest mb-0.5">Estimated Grade</p>
          <div className="flex items-baseline gap-3">
            <span className={`text-5xl font-black ${gradeColor(displayGrade)}`}>
              {displayGrade.toFixed(1)}
            </span>
            <span className="text-xl font-semibold text-slate-200">{displayLabel}</span>
          </div>
        </div>
        <div className="flex items-center gap-4">
          {result.id && (
            <button
              onClick={handleDownloadReport}
              disabled={downloading}
              title="Download grading report"
              className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition disabled:opacity-40"
            >
              {downloading
                ? <Loader2 size={14} className="animate-spin" />
                : <Download size={14} />}
              <span>Report</span>
            </button>
          )}
          <div className="text-right">
            <p className="text-xs text-slate-500 uppercase tracking-wide">Confidence</p>
            <span className={`text-sm font-semibold capitalize ${
              result.confidence === "high" ? "text-emerald-400" :
              result.confidence === "medium" ? "text-amber-400" : "text-slate-400"
            }`}>
              {result.confidence}
            </span>
          </div>
        </div>
      </div>

      {/* Dimension breakdown */}
      <div className="p-6 grid grid-cols-1 sm:grid-cols-2 gap-6">
        {/* Centering */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Centering</p>
            {localCentering && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-indigo-50 text-indigo-600 font-medium">
                colour-corrected
              </span>
            )}
          </div>
          <div className="space-y-2 mb-3">
            <div className="flex justify-between text-sm text-slate-600">
              <span>Left / Right</span>
              <span className="font-mono font-semibold">{centering.lr_ratio}</span>
            </div>
            <div className="flex justify-between text-sm text-slate-600">
              <span>Top / Bottom</span>
              <span className="font-mono font-semibold">{centering.tb_ratio}</span>
            </div>
          </div>
          <ScoreBar score={centering.score} />
          {result.id && (
            <BorderSampler
              resultId={result.id}
              onRecenter={handleRecenter}
              onToast={onToast}
            />
          )}
        </div>

        {/* Corners */}
        <div>
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Corners</p>
          <div className="grid grid-cols-2 gap-1 w-24 mb-3">
            <div className="flex justify-start"><CornerDot value={corners.top_left} /></div>
            <div className="flex justify-end"><CornerDot value={corners.top_right} /></div>
            <div className="flex justify-start"><CornerDot value={corners.bottom_left} /></div>
            <div className="flex justify-end"><CornerDot value={corners.bottom_right} /></div>
          </div>
          <ScoreBar score={corners.score} />
        </div>

        {/* Surface */}
        <div>
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Surface</p>
          <div className="flex items-center justify-between text-sm text-slate-600 mb-2">
            <span>Scratch risk</span>
            <span className="font-mono font-semibold">{(surface.scratch_risk * 100).toFixed(0)}%</span>
          </div>
          <ScoreBar score={surface.score} />
          {surface.flags.length > 0 && (
            <ul className="mt-2 space-y-1">
              {surface.flags.map((f, i) => (
                <li key={i} className="text-xs text-amber-700 bg-amber-50 rounded px-2 py-0.5">{f}</li>
              ))}
            </ul>
          )}
          {surface.th_h_mean > 0 && (
            <div className="mt-3 space-y-1.5">
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400 w-14">H: {surface.th_h_mean.toFixed(2)}</span>
                <MiniBar value={surface.th_h_mean} max={15} />
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400 w-14">V: {surface.th_v_mean.toFixed(2)}</span>
                <MiniBar value={surface.th_v_mean} max={15} />
              </div>
              <p className="text-xs text-slate-400">
                Symmetry: {surface.symmetry.toFixed(2)}
                {" "}
                <span className="text-slate-300">
                  {surface.symmetry > 0.7 ? "(holo-like)" : "(directional)"}
                </span>
              </p>
            </div>
          )}
        </div>

        {/* Edges */}
        <div>
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Edges</p>
          <ScoreBar score={edges.score} />
          {edges.top_std > 0 && (
            <div className="mt-3 space-y-1.5">
              {(["Top", "Bottom", "Left", "Right"] as const).map((side) => {
                const key = `${side.toLowerCase()}_std` as "top_std" | "bottom_std" | "left_std" | "right_std";
                const val = edges[key];
                return (
                  <div key={side} className="flex items-center gap-2">
                    <span className="text-xs text-slate-400 w-14">{side}: σ{val.toFixed(1)}</span>
                    <MiniBar value={val} max={60} />
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Adjustments panel */}
      <AdjustmentsPanel
        scores={{
          centering: centering.score,
          corners: corners.score,
          surface: surface.score,
        }}
        baseGrade={displayGrade}
      />

      {/* Observations */}
      {result.notes.length > 0 && (
        <div className="px-6 pb-5 border-t border-slate-100 pt-4">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Observations</p>
          <ul className="space-y-1">
            {result.notes.map((n, i) => (
              <li key={i} className="text-sm text-slate-600 flex gap-2">
                <span className="text-slate-300">•</span>
                {n}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Transfer to collection */}
      {result.id && onToast && onTransferred && (
        <TransferPanel
          result={result}
          onToast={onToast}
          onTransferred={onTransferred}
        />
      )}

      {/* Debug diagnostic images */}
      {result.id && <DebugPanel resultId={result.id} />}

      {/* Feedback */}
      {result.id && (
        <FeedbackWidget resultId={result.id} estimatedGrade={result.estimated_grade} onToast={onToast} />
      )}
    </div>
  );
}
