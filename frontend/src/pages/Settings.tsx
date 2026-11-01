import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, GarminStatus } from "../api";

const KEY_PAGE = "https://connect.garmin.com/app/settings/personalApiToken";
const DOCS = "https://developer.garmin.com/gc-developer-program/personal/personal-api/";

export default function Settings() {
  const [status, setStatus] = useState<GarminStatus | null>(null);
  const [key, setKey] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api<GarminStatus>("/providers/garmin").then(setStatus).catch((e) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  // poll while a sync is running
  useEffect(() => {
    if (!status?.syncing && status?.last_sync?.status !== "running") return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [status, load]);

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
          <button onClick={() => run(() => api("/sync", "POST"))} disabled={status.syncing}>
            {status.syncing ? "Syncing…" : "Sync now"}
          </button>
          <button
            onClick={() => run(() => api("/sync?full=true", "POST"))}
            disabled={status.syncing}
            title="Re-scan all history and fill any gaps"
          >
            Re-sync all history
          </button>
          <button onClick={() => confirm("Remove the saved Garmin key?") && run(() => api("/providers/garmin", "DELETE"))}>
            Remove key
          </button>
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

      {last && (
        <p className="muted">
          {last.status === "running" ? "Sync in progress" : "Last sync"}: {last.status === "running" ? "" : last.status}
          {last.finished_at ? ` at ${new Date(last.finished_at).toLocaleString()}` : ""} — {last.message ?? ""}
        </p>
      )}
    </section>
  );
}
