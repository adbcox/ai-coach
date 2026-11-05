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

export interface ScheduleInfo {
  interval_minutes: number;
  options: number[];
  next_run_at: string | null;
}

export interface SyncRun {
  mode: "quick" | "background" | "full" | null;
  scheduled: number;
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
  schedule: ScheduleInfo;
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

export interface ActivityDetail extends Activity {
  summary: Record<string, unknown> | null;
}

export interface SamplesData {
  t: number[];
  start_unix: number;
  total_samples: number;
  lat: (number | null)[];
  lon: (number | null)[];
  alt: (number | null)[];
  hr: (number | null)[];
  cadence: (number | null)[];
  power: (number | null)[];
  speed: (number | null)[];
  dist: (number | null)[];
}

export interface BackupItem { name: string; size: number; created_at: string }
export interface SmbStatus {
  configured: boolean;
  interval_options: number[];
  host?: string; port?: number; share?: string; folder?: string; username?: string; domain?: string | null;
  interval_minutes?: number; keep?: number;
  last_run_at?: string | null; last_status?: "ok" | "error" | null; last_message?: string | null;
  next_run_at?: string | null;
}
export interface BackupList { items: BackupItem[]; running: boolean; error: string | null; keep: number; smb: SmbStatus }
export interface RestoreSummary {
  ok: boolean; rows: Record<string, number>; files: number; created_at: string | null;
  secrets_restored: boolean; secrets_in_backup: boolean; previous_database_kept_as: string | null;
}

// ---- P2/P2b/P3 coach-maths + explain-layer types -------------------------

export interface LoadDay {
  day: string;
  trimp: number | null;
  tss: number | null;
  ctl: number | null;
  atl: number | null;
  tsb: number | null;
  acwr?: number | null;
}
export interface LoadHistory { days: LoadDay[]; family: string | null }
export interface LoadDayFamily {
  family: string; trimp: number; tss: number;
  ctl: number | null; atl: number | null; tsb: number | null;
}
export interface LoadDayDetail extends LoadDay {
  families: LoadDayFamily[];
}
export interface Readiness {
  day: string;
  score: number | null;
  band: "green" | "yellow" | "red" | null;
  hrv_part?: number | null;
  sleep_part?: number | null;
  rhr_part?: number | null;
  load_part?: number | null;
  checkin_part?: number | null;
  inputs?: Record<string, unknown>;
}
export interface SuggestedCandidate {
  family: string;
  cluster: string;
  duration_min: number;
  tss: number;
  decoupling_pct: number;
  has_intervals: boolean;
  score: number;
  components: {
    w1_weekday: number; w2_season: number; w3_prelude: number; w4_rhythm: number;
  };
  n_history: number;
  notes: string[];
}
export interface SuggestedWorkout {
  day: string;
  generated_at: string;
  primary: SuggestedCandidate | null;
  alternative: SuggestedCandidate | null;
  candidates?: SuggestedCandidate[];
  low_confidence: boolean;
  reason?: string;
  context?: {
    readiness: number | null;
    band: string | null;
    ill: boolean;
    tsb_prev: number | null;
    last_day_tss: number | null;
    p95_tss_30d: number | null;
    readiness_delta: number | null;
  };
}
export interface CoachReply {
  reply: string;
  tools_used: { tool: string; arguments: Record<string, unknown> }[];
  model: string;
  duration_ms: number;
  rounds: number;
  finish_reason: string | null;
}
export interface RideMetrics {
  activity_id: number;
  family: string | null;
  np: number | null;
  if_: number | null;
  tss: number | null;
  ef: number | null;
  decoupling_pct: number | null;
  computed_at?: string | null;
  [k: string]: unknown;
}
export interface PowerCurvePoint { window_s: number; watts?: number | null; metres_per_s?: number | null }
export interface PowerCurve {
  activity_id: number;
  power: { window_s: number; watts: number }[];
  pace: { window_s: number; metres_per_s: number }[];
}
export interface Climb {
  idx: number; start_offset_s: number; end_offset_s: number;
  length_m: number; avg_gradient: number; max_gradient: number; vam: number;
}
export interface Interval {
  idx: number; start_offset_s: number; end_offset_s: number;
  work_or_rest: "work" | "rest";
  avg_hr: number | null; avg_power: number | null; avg_pace: number | null;
}
export interface Correlation {
  x: string; y: string; rho: number; n: number; p?: number | null;
  lag_days?: number; note?: string;
}
export interface CorrelationsList { rows: Correlation[]; note: string }
export interface Disagreement {
  activity_id: number;
  disagreement_score: number;
  cause: string;
  confidence: number;
  evidence: Record<string, unknown>;
  computed_at: string;
}
export interface ReadinessHistory {
  days: { day: string; score: number | null; band: "green"|"yellow"|"red"|null }[];
}

export async function restoreBackup(file: File, passphrase: string): Promise<RestoreSummary> {
  const res = await fetch("/api/restore", {
    method: "PUT",
    headers: { "X-Requested-With": "aec", ...(passphrase ? { "X-Passphrase": passphrase } : {}) },
    body: file,
    credentials: "same-origin",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, typeof data.detail === "string" ? data.detail : `Restore failed (${res.status})`);
  return data as RestoreSummary;
}
