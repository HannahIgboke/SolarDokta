"use client";
// Load something from the backend, with loading and error states. Optionally refresh it
// every `refreshMs` milliseconds (e.g. the live picture every minute).
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api";

export function useApi<T>(path: string | null, refreshMs?: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(path));
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    if (!path) return;
    let alive = true;
    setLoading((was) => was || data === null);
    api<T>(path)
      .then((d) => alive && (setData(d), setError(null)))
      .catch((e) => alive && setError(e instanceof ApiError ? e.message : String(e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, tick]);

  useEffect(() => {
    if (!path || !refreshMs) return;
    const id = setInterval(reload, refreshMs);
    return () => clearInterval(id);
  }, [path, refreshMs, reload]);

  return { data, error, loading, reload };
}

export const naira = (n: number) => `₦${Math.round(n).toLocaleString("en-NG")}`;
export const kw = (w: number) => (Math.abs(w) >= 1000 ? `${(w / 1000).toFixed(1)} kW` : `${Math.round(w)} W`);
