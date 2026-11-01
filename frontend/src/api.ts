export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: {
      "X-Requested-With": "aec",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
  });
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") msg = data.detail;
      else if (Array.isArray(data.detail)) msg = "Please check the form fields.";
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, msg);
  }
  return (await res.json()) as T;
}

export interface SessionInfo {
  setup_required: boolean;
  authenticated: boolean;
  username: string | null;
}

export interface SyncRun {
  started_at: string;
  finished_at: string | null;
  status: "running" | "ok" | "error";
  new_activities: number;
  message: string | null;
}

export interface StoredSummary {
  activities: number;
  first_activity: string | null;
  last_activity: string | null;
  health_records: Record<string, number>;
}

export interface GarminStatus {
  stored: StoredSummary;
  configured: boolean;
  validated_at: string | null;
  syncing: boolean;
  last_sync: SyncRun | null;
}

export interface Activity {
  id: number;
  source: string;
  source_id: string;
  start_time: string;
  sport: string | null;
  name: string | null;
  distance_m: number | null;
  duration_s: number | null;
  elevation_gain_m: number | null;
  avg_hr: number | null;
  max_hr: number | null;
  has_samples: number;
}

export interface ActivityList {
  total: number;
  items: Activity[];
}
