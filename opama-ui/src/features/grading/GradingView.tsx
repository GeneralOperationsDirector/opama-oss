/**
 * GradingView — the Card Grader module entry point.
 *
 * Hosts the scan upload → analyze flow (POST /grading/analyze, rate-limited),
 * then renders the result via GradeResultCard. Also surfaces past results
 * (history), aggregate accuracy stats, and per-provider identification stats.
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Upload, ImagePlus, Loader2, History, BarChart2, AlertTriangle, Crosshair } from "lucide-react";
import { api } from "../../lib/api";
import type { GradeResult, FeedbackStats, ProviderStats } from "./types";
import GradeResultCard from "./GradeResultCard";

interface Props {
  userId: number;
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
}

type View = "upload" | "preview" | "annotate" | "analyzing" | "result" | "history" | "stats";

// ---------------------------------------------------------------------------
// Annotation canvas — two rectangle guide tool
// ---------------------------------------------------------------------------

type RectPx = { x: number; y: number; w: number; h: number };
type AnnotateStep = "outer" | "inner" | "done";

interface AnnotationCanvasProps {
  imageSrc: string;
  onComplete: (outer: RectPx, inner: RectPx) => void;
}

function AnnotationCanvas({ imageSrc, onComplete }: AnnotationCanvasProps) {
  const canvasRef  = useRef<HTMLCanvasElement>(null);
  const imgRef     = useRef<HTMLImageElement | null>(null);
  const scaleRef   = useRef({ x: 1, y: 1 });
  const dragRef    = useRef<{ start: [number, number]; end: [number, number] } | null>(null);
  const dragging   = useRef(false);

  const [step, setStep]       = useState<AnnotateStep>("outer");
  const [outerRect, setOuter] = useState<RectPx | null>(null);
  const [innerRect, setInner] = useState<RectPx | null>(null);
  // Use refs too so redraw always has the latest values
  const outerRef = useRef<RectPx | null>(null);
  const innerRef = useRef<RectPx | null>(null);

  const setOuterRect = (r: RectPx | null) => { outerRef.current = r; setOuter(r); };
  const setInnerRect = (r: RectPx | null) => { innerRef.current = r; setInner(r); };

  // Load image once
  useEffect(() => {
    const img = new Image();
    img.src = imageSrc;
    img.onload = () => {
      imgRef.current = img;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const maxW  = canvas.parentElement?.clientWidth ?? 500;
      const scale = Math.min(1, maxW / img.naturalWidth);
      canvas.width  = Math.round(img.naturalWidth  * scale);
      canvas.height = Math.round(img.naturalHeight * scale);
      scaleRef.current = { x: img.naturalWidth / canvas.width, y: img.naturalHeight / canvas.height };
      redraw();
    };
  }, [imageSrc]);

  const drawRect = (
    ctx: CanvasRenderingContext2D,
    r: RectPx,
    stroke: string,
    fill: string,
    dashed = false,
  ) => {
    ctx.save();
    ctx.setLineDash(dashed ? [5, 3] : []);
    ctx.lineWidth   = 2;
    ctx.strokeStyle = stroke;
    ctx.fillStyle   = fill;
    ctx.fillRect(r.x, r.y, r.w, r.h);
    ctx.strokeRect(r.x, r.y, r.w, r.h);
    ctx.restore();
  };

  const redraw = (drag?: { start: [number, number]; end: [number, number] }) => {
    const canvas = canvasRef.current;
    const img    = imgRef.current;
    if (!canvas || !img) return;
    const ctx = canvas.getContext("2d")!;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

    if (outerRef.current) {
      drawRect(ctx, outerRef.current, "#3b82f6", "rgba(59,130,246,0.12)");
      // Label
      ctx.fillStyle = "#3b82f6";
      ctx.font = "bold 11px sans-serif";
      ctx.fillText("OUTER", outerRef.current.x + 4, outerRef.current.y + 14);
    }
    if (innerRef.current) {
      drawRect(ctx, innerRef.current, "#f97316", "rgba(249,115,22,0.12)");
      ctx.fillStyle = "#f97316";
      ctx.font = "bold 11px sans-serif";
      ctx.fillText("INNER", innerRef.current.x + 4, innerRef.current.y + 14);
    }

    if (drag) {
      const r = {
        x: Math.min(drag.start[0], drag.end[0]),
        y: Math.min(drag.start[1], drag.end[1]),
        w: Math.abs(drag.end[0] - drag.start[0]),
        h: Math.abs(drag.end[1] - drag.start[1]),
      };
      const isOuter = step === "outer" || (step === "done" && !outerRef.current);
      drawRect(ctx, r,
        isOuter ? "#3b82f6" : "#f97316",
        isOuter ? "rgba(59,130,246,0.1)" : "rgba(249,115,22,0.1)",
        true,
      );
    }
  };

  const canvasCoords = (e: React.MouseEvent<HTMLCanvasElement>): [number, number] => {
    const r  = canvasRef.current!.getBoundingClientRect();
    const sx = canvasRef.current!.width  / r.width;
    const sy = canvasRef.current!.height / r.height;
    return [Math.floor((e.clientX - r.left) * sx), Math.floor((e.clientY - r.top) * sy)];
  };

  const toOriginal = (r: RectPx): RectPx => ({
    x: Math.round(r.x * scaleRef.current.x),
    y: Math.round(r.y * scaleRef.current.y),
    w: Math.round(r.w * scaleRef.current.x),
    h: Math.round(r.h * scaleRef.current.y),
  });

  const onMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (step === "done") return;
    dragging.current = true;
    const pt = canvasCoords(e);
    dragRef.current  = { start: pt, end: pt };
  };

  const onMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!dragging.current || !dragRef.current) return;
    dragRef.current.end = canvasCoords(e);
    redraw(dragRef.current);
  };

  const onMouseUp = () => {
    if (!dragging.current || !dragRef.current) return;
    dragging.current = false;
    const { start, end } = dragRef.current;
    const r: RectPx = {
      x: Math.min(start[0], end[0]),
      y: Math.min(start[1], end[1]),
      w: Math.abs(end[0] - start[0]),
      h: Math.abs(end[1] - start[1]),
    };
    if (r.w < 15 || r.h < 15) { redraw(); return; }

    if (step === "outer") {
      setOuterRect(r);
      setStep("inner");
      redraw();
    } else if (step === "inner") {
      setInnerRect(r);
      setStep("done");
      redraw();
      // Automatically fire completion
      onComplete(toOriginal(outerRef.current!), toOriginal(r));
    }
  };

  const redo = (which: "outer" | "inner") => {
    if (which === "outer") { setOuterRect(null); setInnerRect(null); setStep("outer"); }
    else                   { setInnerRect(null);                     setStep("inner"); }
    setTimeout(redraw, 0);
  };

  const stepColor = (s: AnnotateStep) =>
    s === "outer" ? "text-blue-600" : s === "inner" ? "text-orange-500" : "text-emerald-600";

  return (
    <div className="space-y-3">
      {/* Step indicators */}
      <div className="space-y-1.5">
        {(["outer", "inner"] as const).map((s) => {
          const done   = s === "outer" ? !!outerRect : !!innerRect;
          const active = step === s;
          const color  = s === "outer" ? "bg-blue-500" : "bg-orange-500";
          const label  = s === "outer"
            ? "Draw around the outer card edge"
            : "Draw around the inner border (where artwork begins)";
          return (
            <div key={s} className={`flex items-center gap-2.5 text-sm transition ${active ? stepColor(s) : done ? "text-slate-400 line-through" : "text-slate-300"}`}>
              <div className={`w-2.5 h-2.5 rounded-sm flex-shrink-0 ${color}`} style={{ opacity: active || done ? 1 : 0.3 }} />
              <span>{label}</span>
              {done && (
                <button onClick={() => redo(s)} className="ml-auto text-xs text-slate-400 hover:text-slate-600 no-underline" style={{ textDecoration: "none" }}>
                  redo
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* Canvas */}
      <canvas
        ref={canvasRef}
        className={`w-full rounded-lg border select-none ${
          step === "done"
            ? "border-emerald-300 cursor-default"
            : step === "outer"
            ? "border-blue-300 cursor-crosshair"
            : "border-orange-300 cursor-crosshair"
        }`}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={() => { if (dragging.current) { dragging.current = false; redraw(); } }}
      />

      {step !== "done" && (
        <p className="text-xs text-slate-400">
          {step === "outer"
            ? "Drag to draw the outer card boundary (blue) — be generous, just outside the card edge"
            : "Drag to draw the inner boundary (orange) — just inside the coloured border, where the artwork starts"}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main grading view
// ---------------------------------------------------------------------------

export default function GradingView({ userId, onToast }: Props) {
  const [view, setView]             = useState<View>("upload");
  const [result, setResult]         = useState<GradeResult | null>(null);
  const [pendingFile, setPending]   = useState<File | null>(null);
  const [preview, setPreview]       = useState<string | null>(null);
  const [guides, setGuides]         = useState<{ outer: RectPx; inner: RectPx } | null>(null);
  const [history, setHistory]           = useState<GradeResult[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyOffset, setHistoryOffset]   = useState(0);
  const [historyHasMore, setHistoryHasMore] = useState(false);
  const HISTORY_PAGE = 20;
  const [stats, setStats]           = useState<FeedbackStats | null>(null);
  const [providerStats, setProviderStats]   = useState<ProviderStats[]>([]);
  const [statsLoading, setStatsLoading]     = useState(false);
  const [dragOver, setDragOver]     = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadStats = useCallback(async () => {
    setStatsLoading(true);
    try {
      const [feedbackData, providerData] = await Promise.all([
        api<FeedbackStats>("/grading/feedback/stats"),
        api<ProviderStats[]>("/grading/provider-stats"),
      ]);
      setStats(feedbackData);
      setProviderStats(providerData);
    } catch { onToast("Failed to load accuracy stats", "error"); }
    finally  { setStatsLoading(false); }
  }, [onToast]);

  const loadHistory = useCallback(async (offset = 0) => {
    setHistoryLoading(true);
    try {
      const data = await api<GradeResult[]>(`/grading/history?limit=${HISTORY_PAGE}&offset=${offset}`);
      setHistory((prev) => offset === 0 ? data : [...prev, ...data]);
      setHistoryOffset(offset);
      setHistoryHasMore(data.length === HISTORY_PAGE);
    } catch { onToast("Failed to load history", "error"); }
    finally  { setHistoryLoading(false); }
  }, [onToast]);

  // Store the file + show preview, but don't analyze yet
  const stagefile = useCallback((file: File) => {
    if (!file.type.startsWith("image/")) {
      onToast("Please upload an image file (JPEG or PNG)", "error");
      return;
    }
    if (preview) URL.revokeObjectURL(preview);
    setPending(file);
    setPreview(URL.createObjectURL(file));
    setGuides(null);
    setView("preview");
  }, [onToast, preview]);

  // Send to the grading API (with or without guides)
  const submitAnalysis = useCallback(async (file: File, g: typeof guides) => {
    setView("analyzing");
    const form = new FormData();
    form.append("image", file);
    let path = "/grading/analyze";
    if (g) {
      const qs = new URLSearchParams({
        guide_outer: `${g.outer.x},${g.outer.y},${g.outer.w},${g.outer.h}`,
        guide_inner: `${g.inner.x},${g.inner.y},${g.inner.w},${g.inner.h}`,
      });
      path = `${path}?${qs.toString()}`;
    }
    try {
      const data = await api<GradeResult>(path, {
        method: "POST", body: form, headers: {},
      });
      setResult(data);
      setView("result");
      const tag = g ? " (guide-assisted)" : "";
      onToast(`Grade ${data.estimated_grade.toFixed(1)} — ${data.grade_label}${tag}`, "success");
    } catch (err: any) {
      setView("preview");
      onToast(err.message || "Analysis failed", "error");
    }
  }, [onToast]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) stagefile(file);
    e.target.value = "";
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) stagefile(file);
  };

  const reset = () => {
    if (preview) URL.revokeObjectURL(preview);
    setPreview(null);
    setPending(null);
    setGuides(null);
    setResult(null);
    setView("upload");
  };

  const handleTransferred = useCallback((destination: string, itemId: number) => {
    setResult((r) => r ? { ...r, transferred_to: destination, transferred_item_id: itemId } : r);
  }, []);

  const handleHistoryTransferred = useCallback((resultId: number) => (destination: string, itemId: number) => {
    setHistory((prev) => prev.map((r) =>
      r.id === resultId ? { ...r, transferred_to: destination, transferred_item_id: itemId } : r
    ));
  }, []);

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Card Grader</h1>
          <p className="text-sm text-slate-500 mt-1">
            Upload a scan to estimate PSA-equivalent centering, corners, surface, and edge grades.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => { if (view !== "stats") { setView("stats"); loadStats(); } else { setView(result ? "result" : "upload"); } }}
            className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 transition"
          >
            <BarChart2 size={16} />
            {view === "stats" ? "Back" : "Accuracy"}
          </button>
          <button
            onClick={() => { if (view !== "history") { setView("history"); loadHistory(0); } else { setView(result ? "result" : "upload"); } }}
            className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 transition"
          >
            <History size={16} />
            {view === "history" ? "Back" : "History"}
          </button>
        </div>
      </div>

      {/* Upload */}
      {view === "upload" && (
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => fileRef.current?.click()}
          className={`border-2 border-dashed rounded-2xl p-16 text-center cursor-pointer transition
            ${dragOver ? "border-indigo-400 bg-indigo-50" : "border-slate-300 bg-slate-50 hover:border-indigo-300 hover:bg-indigo-50/50"}`}
        >
          <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={handleFileChange} />
          <ImagePlus size={48} className="mx-auto mb-4 text-slate-300" />
          <p className="text-slate-600 font-medium">Drop a card scan here, or click to browse</p>
          <p className="text-sm text-slate-400 mt-1">JPEG · PNG · WebP · max 20 MB</p>
        </div>
      )}

      {/* Preview — choose quick or guided */}
      {view === "preview" && pendingFile && preview && (
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          <div className="p-5 flex items-start gap-4">
            <img src={preview} alt="Card scan" className="h-32 object-contain rounded-lg shadow border border-slate-200 flex-shrink-0" />
            <div className="flex-1 space-y-4">
              <div>
                <p className="text-sm font-semibold text-slate-800 mb-1">Ready to analyze</p>
                <p className="text-xs text-slate-500">
                  Quick analyze uses automatic border detection. Guide-assisted lets you draw
                  the card boundary and inner border to guarantee accurate centering.
                </p>
              </div>
              <div className="flex flex-col gap-2">
                <button
                  onClick={() => submitAnalysis(pendingFile, null)}
                  className="w-full py-2.5 rounded-xl bg-slate-900 text-white text-sm font-medium hover:bg-slate-700 transition"
                >
                  Quick analyze
                </button>
                <button
                  onClick={() => setView("annotate")}
                  className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl border border-indigo-200 text-indigo-600 text-sm font-medium hover:bg-indigo-50 transition"
                >
                  <Crosshair size={14} />
                  Guide-assisted — draw border guides
                </button>
              </div>
            </div>
          </div>
          <div className="border-t border-slate-100 px-5 py-3">
            <button onClick={reset} className="text-xs text-slate-400 hover:text-slate-600">
              ← Choose different image
            </button>
          </div>
        </div>
      )}

      {/* Annotate — two-rectangle guide tool */}
      {view === "annotate" && pendingFile && preview && (
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          <div className="px-6 pt-5 pb-2">
            <p className="text-sm font-semibold text-slate-800 mb-1">Border guides</p>
            <p className="text-xs text-slate-500 mb-4">
              Draw two rectangles so the grader knows exactly where the card and its border are.
              You don't need to be pixel-perfect — a rough rectangle is enough.
            </p>
            <AnnotationCanvas
              imageSrc={preview}
              onComplete={(outer, inner) => {
                setGuides({ outer, inner });
              }}
            />
          </div>

          <div className="px-6 pb-5 pt-3 flex items-center gap-3">
            {guides ? (
              <button
                onClick={() => submitAnalysis(pendingFile, guides)}
                className="flex-1 py-2.5 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition"
              >
                Analyze with guides
              </button>
            ) : (
              <button
                disabled
                className="flex-1 py-2.5 rounded-xl bg-slate-100 text-slate-400 text-sm font-medium"
              >
                Draw both rectangles to continue
              </button>
            )}
            <button onClick={() => setView("preview")} className="text-sm text-slate-400 hover:text-slate-600">
              Back
            </button>
          </div>
        </div>
      )}

      {/* Analyzing */}
      {view === "analyzing" && (
        <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-sm">
          {preview && (
            <img src={preview} alt="Card being analyzed" className="h-40 object-contain rounded-lg mx-auto mb-6 shadow" />
          )}
          <Loader2 size={32} className="animate-spin mx-auto text-indigo-500 mb-3" />
          <p className="text-slate-700 font-medium">Analyzing card…</p>
          <div className="mt-2 space-y-0.5 text-xs text-slate-400">
            <p>Measuring centering, corners, surface, and edges</p>
            <p>Reading card name, number, and set</p>
          </div>
        </div>
      )}

      {/* Result */}
      {view === "result" && result && (
        <div className="space-y-4">
          <div className="flex items-center gap-3 mb-2">
            {preview && (
              <img src={preview} alt="Analyzed card" className="h-20 w-14 object-contain rounded-lg shadow border border-slate-200" />
            )}
            <div className="flex-1">
              {result.confidence === "low" && (
                <div className="flex items-start gap-2 rounded-lg bg-amber-50 border border-amber-200 p-3 text-sm text-amber-800">
                  <AlertTriangle size={16} className="mt-0.5 flex-shrink-0" />
                  <span>
                    Card boundary could not be detected — results are based on the full image without perspective correction.
                    For best accuracy, photograph the card against a contrasting background or use border guides.
                  </span>
                </div>
              )}
              {guides && (
                <div className="flex items-center gap-2 rounded-lg bg-indigo-50 border border-indigo-100 px-3 py-2 text-xs text-indigo-700">
                  <Crosshair size={12} />
                  Centering measured from your border guides
                </div>
              )}
            </div>
          </div>

          <GradeResultCard result={result} onToast={onToast} onTransferred={handleTransferred} />

          <button
            onClick={reset}
            className="w-full flex items-center justify-center gap-2 rounded-xl border border-slate-200 py-3 text-sm text-slate-600 hover:bg-slate-50 transition"
          >
            <Upload size={15} />
            Analyze another card
          </button>
        </div>
      )}

      {/* Accuracy stats */}
      {view === "stats" && (
        <div className="space-y-4">
          {statsLoading && <div className="text-center py-12"><Loader2 size={24} className="animate-spin mx-auto text-slate-400" /></div>}
          {!statsLoading && stats && (
            <>
              {stats.total_feedback === 0 ? (
                <div className="text-center py-16 text-slate-400">
                  <BarChart2 size={40} className="mx-auto mb-3 opacity-30" />
                  <p>No feedback submitted yet.</p>
                  <p className="text-sm mt-1">After analyzing a card, use the feedback widget to rate the result.</p>
                </div>
              ) : (
                <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
                  <div className="bg-slate-900 text-white px-6 py-4">
                    <p className="text-sm text-slate-400 uppercase tracking-widest">Algorithm Accuracy</p>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Based on {stats.total_feedback} feedback submission{stats.total_feedback !== 1 ? "s" : ""} across {stats.total_analyses} analyses
                    </p>
                  </div>
                  <div className="p-6 space-y-5">
                    <div>
                      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Overall verdict</p>
                      <div className="flex rounded-lg overflow-hidden h-6 text-xs font-semibold">
                        {stats.accurate_pct > 0 && <div className="bg-emerald-500 text-white flex items-center justify-center" style={{ width: `${stats.accurate_pct}%` }}>{stats.accurate_pct.toFixed(0)}%</div>}
                        {stats.too_high_pct > 0 && <div className="bg-amber-400 text-white flex items-center justify-center" style={{ width: `${stats.too_high_pct}%` }}>{stats.too_high_pct.toFixed(0)}%</div>}
                        {stats.too_low_pct > 0  && <div className="bg-blue-400 text-white flex items-center justify-center"  style={{ width: `${stats.too_low_pct}%`  }}>{stats.too_low_pct.toFixed(0)}%</div>}
                      </div>
                      <div className="flex gap-4 mt-2 text-xs text-slate-500">
                        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" />Accurate</span>
                        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-400 inline-block" />Too high</span>
                        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-400 inline-block" />Too low</span>
                      </div>
                    </div>
                    {stats.graded_count > 0 && (
                      <div>
                        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Grade error ({stats.graded_count} slab{stats.graded_count !== 1 ? "s" : ""})</p>
                        <div className="flex gap-6 text-sm">
                          <div>
                            <p className="text-slate-400 text-xs">Mean error</p>
                            <p className={`font-semibold ${stats.mean_error === null ? "text-slate-400" : Math.abs(stats.mean_error) < 0.5 ? "text-emerald-600" : "text-amber-600"}`}>
                              {stats.mean_error !== null ? `${stats.mean_error > 0 ? "+" : ""}${stats.mean_error.toFixed(2)}` : "—"}
                            </p>
                            <p className="text-xs text-slate-400">positive = over-graded</p>
                          </div>
                          <div>
                            <p className="text-slate-400 text-xs">Mean abs error</p>
                            <p className="font-semibold text-slate-700">{stats.mean_abs_error !== null ? `±${stats.mean_abs_error.toFixed(2)}` : "—"}</p>
                          </div>
                        </div>
                      </div>
                    )}
                    <div>
                      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Dimension accuracy</p>
                      <div className="space-y-2">
                        {stats.dimension_accuracy.map(({ dimension, times_flagged, flag_rate }) => (
                          <div key={dimension}>
                            <div className="flex justify-between text-sm mb-1">
                              <span className="capitalize text-slate-600">{dimension}</span>
                              <span className="text-slate-400 text-xs">{times_flagged > 0 ? `flagged ${times_flagged}× (${(flag_rate * 100).toFixed(0)}%)` : "no issues reported"}</span>
                            </div>
                            <div className="h-1.5 rounded-full bg-slate-100">
                              <div className={`h-1.5 rounded-full ${flag_rate > 0.4 ? "bg-red-400" : flag_rate > 0.2 ? "bg-amber-400" : "bg-emerald-400"}`} style={{ width: `${(1 - flag_rate) * 100}%` }} />
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              )}
              {providerStats.length > 0 && (
                <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
                  <div className="bg-slate-800 text-white px-6 py-4">
                    <p className="text-sm text-slate-300 uppercase tracking-widest">Card Identification — Provider Accuracy</p>
                    <p className="text-xs text-slate-500 mt-0.5">Accuracy computed from transfers where you confirmed or corrected the auto-identified card.</p>
                  </div>
                  <div className="divide-y divide-slate-100">
                    {providerStats.map((ps) => {
                      const shortName  = ps.provider.replace("ollama_full:", "Full image · ").replace("ollama_region:", "Number crop · ").replace("ocr_tesseract", "Tesseract OCR");
                      const nameAcc    = ps.name_accuracy   !== null ? Math.round(ps.name_accuracy   * 100) : null;
                      const numberAcc  = ps.number_accuracy !== null ? Math.round(ps.number_accuracy * 100) : null;
                      const accColor   = (p: number | null) => p === null ? "text-slate-400" : p >= 80 ? "text-emerald-600" : p >= 50 ? "text-amber-600" : "text-red-500";
                      return (
                        <div key={ps.provider} className="px-6 py-4">
                          <div className="flex items-start justify-between gap-4">
                            <div>
                              <p className="text-sm font-semibold text-slate-800">{shortName}</p>
                              <p className="text-xs text-slate-400 mt-0.5">{ps.total_attempts} attempt{ps.total_attempts !== 1 ? "s" : ""}{ps.name_evaluated > 0 && ` · ${ps.name_evaluated} evaluated`}</p>
                            </div>
                            <div className="flex gap-6 text-right flex-shrink-0">
                              <div><p className="text-xs text-slate-400">Name</p><p className={`text-sm font-semibold ${accColor(nameAcc)}`}>{nameAcc !== null ? `${nameAcc}%` : "—"}</p></div>
                              <div><p className="text-xs text-slate-400">Number</p><p className={`text-sm font-semibold ${accColor(numberAcc)}`}>{numberAcc !== null ? `${numberAcc}%` : "—"}</p></div>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  <div className="px-6 py-3 bg-slate-50 border-t border-slate-100">
                    <p className="text-xs text-slate-400">The best-performing provider is automatically preferred during fusion. Transfer more cards to build up accuracy data.</p>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* History */}
      {view === "history" && (
        <div className="space-y-4">
          {historyLoading && <div className="text-center py-12"><Loader2 size={24} className="animate-spin mx-auto text-slate-400" /></div>}
          {!historyLoading && history.length === 0 && (
            <div className="text-center py-16 text-slate-400">
              <History size={40} className="mx-auto mb-3 opacity-30" />
              <p>No analyses yet. Upload a card scan to get started.</p>
            </div>
          )}
          {history.map((r) => (
            <div key={r.id} className="space-y-2">
              <div className="flex items-center justify-between text-xs text-slate-400 px-1">
                <span>{r.analyzed_at ? new Date(r.analyzed_at).toLocaleString() : ""}</span>
                {r.identification?.name && <span className="font-medium text-slate-500">{r.identification.name}</span>}
              </div>
              <GradeResultCard result={r} onToast={onToast} onTransferred={r.id ? handleHistoryTransferred(r.id) : undefined} />
            </div>
          ))}
          {historyHasMore && !historyLoading && (
            <button
              onClick={() => loadHistory(historyOffset + HISTORY_PAGE)}
              className="w-full py-2.5 rounded-xl border border-slate-200 text-sm text-slate-500 hover:bg-slate-50 transition"
            >
              Load more
            </button>
          )}
        </div>
      )}
    </div>
  );
}
