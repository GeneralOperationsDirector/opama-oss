import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

type ToastType = "info" | "success" | "error";

export type ToastOptions = {
  type?: ToastType;
  duration?: number; // ms
  title?: string;
};

type Toast = {
  id: number;
  message: string;
  type: ToastType;
  title?: string;
  expiresAt: number;
};

type ToastContextValue = {
  toast: (message: string, opts?: ToastOptions) => void;
  success: (message: string, opts?: Omit<ToastOptions, "type">) => void;
  error: (message: string, opts?: Omit<ToastOptions, "type">) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

/** Provider that renders the toast viewport and exposes the toast() API via context. */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const idRef = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((t) => t.filter((x) => x.id !== id));
  }, []);

  const add = useCallback((message: string, opts?: ToastOptions) => {
    const id = idRef.current++;
    const type: ToastType = opts?.type ?? "info";
    const duration = Math.max(800, opts?.duration ?? (type === "error" ? 5000 : 2500));
    const title = opts?.title;
    const expiresAt = Date.now() + duration;

    setToasts((t) => [...t, { id, message, type, title, expiresAt }]);

    // simple auto-dismiss
    const timer = setTimeout(() => dismiss(id), duration);
    // best-effort cleanup if unmounted early
    return () => clearTimeout(timer);
  }, [dismiss]);

  const api = useMemo<ToastContextValue>(
    () => ({
      toast: (m, o) => void add(m, o),
      success: (m, o) => void add(m, { ...o, type: "success" }),
      error: (m, o) => void add(m, { ...o, type: "error" }),
    }),
    [add]
  );

  // Sweep (optional: prevents zombie toasts if tab slept)
  React.useEffect(() => {
    const t = setInterval(() => {
      const now = Date.now();
      setToasts((list) => list.filter((x) => x.expiresAt > now));
    }, 2000);
    return () => clearInterval(t);
  }, []);

  return (
    <ToastContext.Provider value={api}>
      {children}
      {/* Viewport (bottom-right) */}
      <div className="fixed bottom-4 right-4 z-[9999] flex flex-col gap-2 w-[min(92vw,360px)] pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={[
              "pointer-events-auto shadow-lg rounded-xl border p-3 text-sm animate-in fade-in slide-in-from-bottom-3",
              t.type === "success" ? "bg-emerald-50 border-emerald-200 text-emerald-900" :
              t.type === "error" ? "bg-rose-50 border-rose-200 text-rose-900" :
                                   "bg-slate-50 border-slate-200 text-slate-900",
            ].join(" ")}
          >
            <div className="flex items-start gap-2">
              <span
                className={[
                  "mt-0.5 inline-block size-2 rounded-full",
                  t.type === "success" ? "bg-emerald-500" :
                  t.type === "error" ? "bg-rose-500" :
                                       "bg-slate-500",
                ].join(" ")}
              />
              <div className="flex-1">
                {t.title && <div className="font-medium mb-0.5">{t.title}</div>}
                <div className="whitespace-pre-line">{t.message}</div>
              </div>
              <button
                className="ml-2 -mr-1 px-2 py-1 text-slate-500 hover:text-slate-700"
                onClick={() => dismiss(t.id)}
                aria-label="Dismiss"
              >
                ✕
              </button>
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

/** Hook to use inside components */
export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    // Friendly hint if provider is missing
    throw new Error("useToast() must be used within <ToastProvider>");
  }
  return ctx;
}

/** Legacy Toaster component for backward compatibility */
type LegacyToast = {
  id: number;
  message: string;
  type: "success" | "error" | "info";
};

export default function Toaster({
  toasts,
  onDismiss,
}: {
  toasts: LegacyToast[];
  onDismiss: (id: number) => void;
}) {
  return (
    <div className="fixed bottom-4 right-4 z-[9999] flex flex-col gap-2 w-[min(92vw,360px)] pointer-events-none">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={[
            "pointer-events-auto shadow-lg rounded-xl border p-3 text-sm animate-in fade-in slide-in-from-bottom-3",
            t.type === "success" ? "bg-emerald-50 border-emerald-200 text-emerald-900" :
            t.type === "error" ? "bg-rose-50 border-rose-200 text-rose-900" :
                                 "bg-slate-50 border-slate-200 text-slate-900",
          ].join(" ")}
        >
          <div className="flex items-start gap-2">
            <span
              className={[
                "mt-0.5 inline-block size-2 rounded-full",
                t.type === "success" ? "bg-emerald-500" :
                t.type === "error" ? "bg-rose-500" :
                                     "bg-slate-500",
              ].join(" ")}
            />
            <div className="flex-1 whitespace-pre-line">{t.message}</div>
            <button
              className="ml-2 -mr-1 px-2 py-1 text-slate-500 hover:text-slate-700"
              onClick={() => onDismiss(t.id)}
              aria-label="Dismiss"
            >
              ✕
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
