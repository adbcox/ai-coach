import { FormEvent, useEffect, useState } from "react";
import { api, GarminStatus } from "../api";
import Backups from "../components/Backups";
import { intervalLabel, useSync } from "../lib/useSync";

const KEY_PAGE = "https://connect.garmin.com/app/settings/personalApiToken";
const DOCS = "https://developer.garmin.com/gc-developer-program/personal/personal-api/";

function Preferences() {
  const [sport, setSport] = useState("");
  const [options, setOptions] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const [maxHr, setMaxHr] = useState("");
  const [auto, setAuto] = useState<number | null>(null);
  const [zones, setZones] = useState<{ zone: number; low: number; high: number }[]>([]);
  const [hrError, setHrError] = useState("");
  type PrefData = { default_sport: string; sport_options: string[]; max_hr: number | null; max_hr_source: string | null; max_hr_auto: number | null; hr_zones: { zone: number; low: number; high: number }[] };
  const apply = (p: PrefData) => {
    setSport(p.default_sport); setOptions(p.sport_options); setAuto(p.max_hr_auto);
    setMaxHr(p.max_hr_source === "custom" && p.max_hr ? String(p.max_hr) : ""); setZones(p.hr_zones);
  };
  useEffect(() => { api<PrefData>("/preferences").then(apply).catch(() => undefined); }, []);
  async function saveMaxHr() {
    setHrError("");
    try { apply(await api<PrefData>("/preferences", "PUT", { max_hr: maxHr.trim() ? Number(maxHr) : null })); }
    catch (e) { setHrError((e as Error).message === "Please check the form fields." ? "Enter a value between 100 and 230, or leave blank for automatic." : (e as Error).message); }
  }
  async function change(value: string) {
    setSport(value);
    setSaved(false);
    try {
      await api("/preferences", "PUT", { default_sport: value });
      setSaved(true);
    } catch { /* leave unsaved */ }
  }
  if (!options.length) return null;
  return (
    <section className="card wide">
      <h2>Preferences</h2>
      <label>
        Dashboard starts on
        <select value={sport} onChange={(e) => change(e.target.value)}>
          {options.map((o) => <option key={o} value={o}>{o === "All" ? "All sports" : o}</option>)}
        </select>
      </label>
      <span className="muted">
        Sets which sport the dashboard shows when you open it (mileage, rolling charts, latest activities).
        You can still switch sport on the dashboard itself. {saved && <strong>Saved.</strong>}
      </span>
      <label>
        Max heart rate (bpm)
        <input type="number" min={100} max={230} value={maxHr} onChange={(e) => setMaxHr(e.target.value)}
               onBlur={saveMaxHr} placeholder={auto ? `automatic (${auto})` : "automatic"} style={{ maxWidth: 200 }} />
      </label>
      <span className="muted">
        Used to draw heart-rate zones behind the heart-rate chart (Strava colours: grey, blue, green, orange, red).
        Blank = the highest heart rate recorded in your activities{auto ? ` (${auto} bpm)` : ""}.
        {zones.length > 0 && ` Zones: ${zones.map((z) => `Z${z.zone} ${z.low}\u2013${z.high}`).join(", ")}.`} These are
        estimates at 50/60/70/80/90% of max heart rate; your Garmin watch may use different zone boundaries.
      </span>
      {hrError && <span className="error">{hrError}</span>}
    </section>
  );
}

function Version() {
  const [v, setV] = useState("");
  useEffect(() => {
    api<{ version: string; build: string }>("/health").then((h) => setV(`v${h.version} (build ${h.build})`)).catch(() => undefined);
  }, []);
  return <p className="muted" style={{ textAlign: "center" }}>Endurance Coach {v}</p>;
}

export default function Settings({ onRestored }: { onRestored: () => void }) {
  const { status, setStatus, running, start, load } = useSync();
  const [key, setKey] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      setStatus(await api<GarminStatus>("/providers/garmin", "PUT", { api_key: key }));
      setKey("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function run<T>(fn: () => Promise<T>) {
    setError("");
    try {
      await fn();
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const last = status?.last_sync;
  return (
    <div className="stack">
    <section className="card wide">
      <h2>Garmin</h2>
      <p className="muted">
        Create a personal API key on <a href={KEY_PAGE} target="_blank" rel="noreferrer">Garmin Connect</a>{" "}
        (it is shown only once), then paste it here. It is encrypted on the server and never shown again.{" "}
        <a href={DOCS} target="_blank" rel="noreferrer">Garmin's documentation</a>.
      </p>

      <p>
        Status:{" "}
        {status?.configured ? (
          <strong>key saved{status.validated_at ? `, verified ${new Date(status.validated_at).toLocaleString()}` : ""}</strong>
        ) : (
          <strong>no key yet</strong>
        )}
      </p>

      <form onSubmit={save} className="row">
        <input
          type="password"
          placeholder={status?.configured ? "Paste a new key to replace the saved one" : "Paste your Garmin API key"}
          value={key}
          onChange={(e) => setKey(e.target.value)}
          autoComplete="off"
          spellCheck={false}
        />
        <button className="primary" disabled={busy || key.length < 8}>
          {busy ? "Checking…" : "Save and test"}
        </button>
      </form>
      {error && <p className="error">{error}</p>}

      {status?.configured && (
        <div className="row">
          <button onClick={() => start("background")} disabled={running}
            title="Looks back 30 days from your newest data to close any gaps">
            {running ? "Syncing…" : "Sync now (30-day check)"}
          </button>
          <button
            onClick={() => start("full")}
            disabled={running}
            title="Re-scan all history and fill any gaps"
          >
            Re-sync all history
          </button>
          <button onClick={() => confirm("Remove the saved Garmin key?") && run(() => api("/providers/garmin", "DELETE"))}>
            Remove key
          </button>
        </div>
      )}

      {status?.configured && (
        <div className="stack" style={{ gap: 6 }}>
          <label>
            Automatic sync
            <select
              value={status.schedule.interval_minutes}
              onChange={(e) =>
                run(async () =>
                  setStatus(await api<GarminStatus>("/providers/garmin/schedule", "PUT", { interval_minutes: Number(e.target.value) })),
                )
              }
            >
              {status.schedule.options.map((m) => (
                <option key={m} value={m}>{intervalLabel(m)}</option>
              ))}
            </select>
          </label>
          <span className="muted">
            {status.schedule.next_run_at
              ? `Next automatic sync: ${
                  new Date(status.schedule.next_run_at).getTime() <= Date.now()
                    ? "due now (within a minute)"
                    : new Date(status.schedule.next_run_at).toLocaleString()
                }. Each one looks back 30 days from your newest data so nothing is missed.`
              : "Automatic sync is off. Use Sync here or on the home page."}
          </span>
        </div>
      )}

      {status?.stored && status.stored.activities > 0 && (
        <p className="muted">
          Stored: {status.stored.activities} activities
          {status.stored.first_activity
            ? ` (${new Date(status.stored.first_activity).toLocaleDateString()} to ${new Date(status.stored.last_activity ?? status.stored.first_activity).toLocaleDateString()})`
            : ""}
          {Object.keys(status.stored.health_records).length > 0 &&
            `; health data: ${Object.entries(status.stored.health_records)
              .map(([k, n]) => `${k.replace(/_/g, " ")} ${n}`)
              .join(", ")}`}
        </p>
      )}

      {status?.stored && status.stored.activities > 0 && (
        <p className="muted">
          Having problems or want help improving the app? Download a{" "}
          <a href="/api/diagnostics/shapes" download>data-shapes file</a>: field names, types and
          numeric ranges. It leaves out names, places, GPS coordinates, ids, timestamps and body
          measurements, but still look it over before sharing.
        </p>
      )}

      {last && (
        <p className="muted">
          {last.status === "running" ? "Sync in progress" : "Last sync"}: {last.status === "running" ? "" : last.status}
          {last.finished_at ? ` at ${new Date(last.finished_at).toLocaleString()}` : ""} — {last.message ?? ""}
        </p>
      )}
    </section>
    <Preferences />
    <Backups onRestored={onRestored} />
    <Version />
    </div>
  );
}
