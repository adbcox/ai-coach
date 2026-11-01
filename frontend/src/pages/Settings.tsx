import { cmToFtIn, displayToKg, ftInToCm, kgToDisplay, setUnits, Units } from "../lib/units";
import { FormEvent, useEffect, useState } from "react";
import { api, GarminStatus } from "../api";
import Backups from "../components/Backups";
import Cite from "../components/Cite";
import MaxHr from "../components/MaxHr";
import { intervalLabel, useSync } from "../lib/useSync";

const KEY_PAGE = "https://connect.garmin.com/app/settings/personalApiToken";
const DOCS = "https://developer.garmin.com/gc-developer-program/personal/personal-api/";

type PrefData = { default_sport: string; sport_options: string[]; max_hr: number | null; max_hr_source: string | null; max_hr_auto: number | null; birth_year: number | null; birthday: string | null; height_cm: number | null; units: Units; unit_options: Record<string, string[]>; age: number | null; sex: string | null; weight_kg: number | null; weight_source: string | null; weight_garmin_kg: number | null; weight_garmin_date: string | null; hr_zones: { zone: number; low: number; high: number }[] };

function Preferences() {
  const [sport, setSport] = useState("");
  const [options, setOptions] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const [maxHr, setMaxHr] = useState("");
  const [auto, setAuto] = useState<number | null>(null);
  const [zones, setZones] = useState<{ zone: number; low: number; high: number }[]>([]);
  const [hrError, setHrError] = useState("");
  const [birthday, setBirthday] = useState("");
  const [heightCm, setHeightCm] = useState("");
  const [heightFt, setHeightFt] = useState("");
  const [heightIn, setHeightIn] = useState("");
  const [sex, setSex] = useState("");
  const [weight, setWeight] = useState("");
  const [prof, setProf] = useState<PrefData | null>(null);
  const apply = (p: PrefData) => {
    setSport(p.default_sport); setOptions(p.sport_options); setAuto(p.max_hr_auto);
    setMaxHr(p.max_hr_source === "custom" && p.max_hr ? String(p.max_hr) : ""); setZones(p.hr_zones);
    setBirthday(p.birthday ?? "");
    setUnits(p.units);
    if (p.height_cm) { const fi = cmToFtIn(p.height_cm); setHeightCm(String(p.height_cm)); setHeightFt(String(fi.ft)); setHeightIn(String(fi.inch)); }
    else { setHeightCm(""); setHeightFt(""); setHeightIn(""); }
    setSex(p.sex ?? ""); setProf(p);
    setWeight(p.weight_source === "custom" && p.weight_kg ? String(Math.round(kgToDisplay(p.weight_kg) * 10) / 10) : "");
  };
  useEffect(() => { api<PrefData>("/preferences").then(apply).catch(() => undefined); }, []);
  async function saveHeightFtIn() {
    if (!heightFt.trim() && !heightIn.trim()) { apply(await api<PrefData>("/preferences", "PUT", { height_cm: null })); return; }
    apply(await api<PrefData>("/preferences", "PUT", { height_cm: ftInToCm(Number(heightFt || 0), Number(heightIn || 0)) }));
  }
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
        Draws the heart-rate zones on run charts. Blank = estimated from your own recorded peaks{auto ? ` (${auto} bpm)` : ""}.
        {zones.length > 0 && ` Zones: ${zones.map((z) => `Z${z.zone} ${z.low}\u2013${z.high}`).join(", ")}.`}
      </span>
      {hrError && <span className="error">{hrError}</span>}
      <MaxHr onApplied={() => api<PrefData>("/preferences").then(apply)} />
      <h3 style={{ marginBottom: 0 }}>About you</h3>
      <span className="muted">Used only for the formulas that need them (shown with their working). Sex means the physiological value those formulas use.</span>
      <label>Sex
        <select value={sex} onChange={async (e) => { setSex(e.target.value); apply(await api<PrefData>("/preferences", "PUT", { sex: e.target.value || null })); }} style={{ maxWidth: 200 }}>
          <option value="">Not set</option><option value="female">Female</option><option value="male">Male</option>
        </select>
      </label>
      <label>Birthday{prof?.age != null ? ` (age ${prof.age})` : ""}
        <input type="date" min="1920-01-01" value={birthday} onChange={(e) => setBirthday(e.target.value)}
               onBlur={async () => apply(await api<PrefData>("/preferences", "PUT", { birthday: birthday || null }))}
               style={{ maxWidth: 200 }} />
      </label>
      <label>Weight ({prof?.units.weight ?? "kg"})
        <input type="number" min={prof?.units.weight === "lb" ? 55 : 25} max={prof?.units.weight === "lb" ? 660 : 300} step="0.1" value={weight} onChange={(e) => setWeight(e.target.value)}
               onBlur={async () => apply(await api<PrefData>("/preferences", "PUT", { weight_kg: weight.trim() ? Math.round(displayToKg(Number(weight)) * 100) / 100 : null }))}
               placeholder={prof?.weight_garmin_kg ? `from Garmin (${Math.round(kgToDisplay(prof.weight_garmin_kg) * 10) / 10})` : "no weight from Garmin yet"} style={{ maxWidth: 200 }} />
      </label>
      <span className="muted">
        {prof?.weight_source === "custom" && `Using your typed value. `}
        {prof?.weight_garmin_kg ? `Garmin's latest weight: ${Math.round(kgToDisplay(prof.weight_garmin_kg) * 10) / 10} ${prof.units.weight} (${prof.weight_garmin_date}). ` : "No weight found in your synced Garmin data (record one on a Garmin scale or in Garmin Connect and sync). "}
        {prof?.weight_source === "custom" ? "Clear the box to go back to Garmin's value." : "Type a value to override Garmin's."}
      </span>
      <label>Height{prof?.units.height === "ftin" ? " (ft, in)" : " (cm)"}
        {prof?.units.height === "ftin" ? (
          <span className="row" style={{ gap: 8 }}
                onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) saveHeightFtIn(); }}>
            <input type="number" min={3} max={8} value={heightFt} onChange={(e) => setHeightFt(e.target.value)} placeholder="ft" style={{ maxWidth: 80 }} />
            <input type="number" min={0} max={11} value={heightIn} onChange={(e) => setHeightIn(e.target.value)} placeholder="in" style={{ maxWidth: 80 }} />
          </span>
        ) : (
          <input type="number" min={100} max={250} step="0.1" value={heightCm} onChange={(e) => setHeightCm(e.target.value)} style={{ maxWidth: 200 }}
                 onBlur={async () => apply(await api<PrefData>("/preferences", "PUT", { height_cm: heightCm.trim() ? Number(heightCm) : null }))} />
        )}
      </label>
      <h3 style={{ marginBottom: 0 }}>Units</h3>
      <span className="muted">Display only. The working in "Show the math" stays metric so it matches the papers.</span>
      {([["distance", "Distance, pace and speed", { km: "Kilometres", mi: "Miles" }], ["elevation", "Elevation", { m: "Metres", ft: "Feet" }],
         ["weight", "Weight", { kg: "Kilograms", lb: "Pounds" }], ["height", "Height", { cm: "Centimetres", ftin: "Feet and inches" }]] as [string, string, Record<string, string>][]).map(([key, label, opts]) => (
        <label key={key}>{label}
          <select value={prof?.units[key as keyof Units] ?? Object.keys(opts)[0]} style={{ maxWidth: 200 }}
                  onChange={async (e) => apply(await api<PrefData>("/preferences", "PUT", { [`units_${key}`]: e.target.value }))}>
            {Object.entries(opts).map(([v, name]) => <option key={v} value={v}>{name}</option>)}
          </select>
        </label>
      ))}
      <details><summary className="muted">About the zones</summary><p className="muted">A common five-zone split of max heart rate (50/60/70/80/90%), which may differ from your Garmin's own boundaries. <Cite id="garmin_zones" /></p></details>
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
    <p className="muted" style={{ textAlign: "center" }}><a href="#/references">Sources and credits</a></p>
    <Version />
    </div>
  );
}
