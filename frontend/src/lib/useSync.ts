import { useCallback, useEffect, useState } from "react";
import { api, GarminStatus } from "../api";

/** Garmin status + sync trigger, polling while a sync is running. */
export function useSync(onFinished?: () => void) {
  const [status, setStatus] = useState<GarminStatus | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    return api<GarminStatus>("/providers/garmin").then(setStatus).catch((e) => setError(e.message));
  }, []);
  useEffect(() => { load(); }, [load]);

  const running = !!status && (status.syncing || status.last_sync?.status === "running");
  useEffect(() => {
    if (!running) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [running, load]);

  // tell the page when a running sync completes
  const [wasRunning, setWasRunning] = useState(false);
  useEffect(() => {
    if (wasRunning && !running) onFinished?.();
    setWasRunning(running);
  }, [running]); // eslint-disable-line react-hooks/exhaustive-deps

  const start = useCallback(async (mode: "quick" | "background" | "full") => {
    setError("");
    try {
      await api("/sync?mode=" + mode, "POST");
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }, [load]);

  return { status, setStatus, error, setError, running, start, load };
}

export function ago(iso: string | null | undefined): string {
  if (!iso) return "never";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 90) return "just now";
  if (s < 5400) return `${Math.round(s / 60)} min ago`;
  if (s < 129600) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}

export function intervalLabel(m: number): string {
  if (m === 0) return "Off";
  if (m < 1440) return `Every ${m / 60} hour${m === 60 ? "" : "s"}`;
  return m === 1440 ? "Every day" : `Every ${m / 1440} days`;
}
