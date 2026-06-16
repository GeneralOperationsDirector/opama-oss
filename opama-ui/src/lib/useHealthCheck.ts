import { useEffect, useState } from "react";
import { API_BASE } from "./api";

export type ApiHealth = "checking" | "ok" | "down";

const INTERVAL_MS = 30_000;
const TIMEOUT_MS  = 4_000;

export function useHealthCheck(): ApiHealth {
  const [health, setHealth] = useState<ApiHealth>("checking");

  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
        const res = await fetch(`${API_BASE}/healthz`, { signal: controller.signal });
        clearTimeout(timer);
        if (!cancelled) setHealth(res.ok ? "ok" : "down");
      } catch {
        if (!cancelled) setHealth("down");
      }
    };

    check();
    const id = setInterval(check, INTERVAL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  return health;
}
