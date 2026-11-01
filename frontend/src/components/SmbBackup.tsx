import { FormEvent, useState } from "react";
import { api, SmbStatus } from "../api";
import { ago } from "../lib/useSync";

const label = (m: number) =>
  m === 0 ? "Manual only (no schedule)" : m < 1440 ? `Every ${m / 60} hours` : m === 1440 ? "Every day" : "Every week";

export default function SmbBackup({ status, onChange }: { status: SmbStatus; onChange: () => void }) {
  const [editing, setEditing] = useState(!status.configured);
  const [f, setF] = useState({
    host: status.host ?? "", port: status.port ?? 445, share: status.share ?? "", folder: status.folder ?? "",
    username: status.username ?? "", domain: status.domain ?? "", password: "",
    interval_minutes: status.interval_minutes ?? 1440, keep: status.keep ?? 14,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (k: string, v: string | number) => setF((p) => ({ ...p, [k]: v }));

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/backups/smb", "PUT", { ...f, domain: f.domain || null, password: f.password || null });
      setEditing(false);
      set("password", "");
      onChange();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack" style={{ gap: 8 }}>
      <h3 style={{ margin: "8px 0 0" }}>Automatic backups to a network share (SMB)</h3>
      {status.configured && !editing ? (
        <>
          <p style={{ margin: 0 }}>
            <strong>\\{status.host}\{status.share}{status.folder ? `\${status.folder}` : ""}</strong>{" "}
            <span className="muted">as {status.username} · {label(status.interval_minutes ?? 0)} · keep {status.keep}</span>
          </p>
          <p className="muted" style={{ margin: 0 }}>
            {status.last_run_at
              ? `Last upload ${ago(status.last_run_at)}: ${status.last_status === "ok" ? "" : "FAILED, "}${status.last_message ?? ""}`
              : "No upload yet."}
            {status.next_run_at && ` Next automatic backup: ${new Date(status.next_run_at).getTime() <= Date.now() ? "due now (within a minute)" : new Date(status.next_run_at).toLocaleString()}.`}
          </p>
          <div className="row">
            <button onClick={() => setEditing(true)}>Edit</button>
            <button onClick={() => confirm("Remove the share? Existing files on the share are not deleted.") && api("/backups/smb", "DELETE").then(onChange)}>
              Remove
            </button>
          </div>
        </>
      ) : (
        <form onSubmit={save} className="stack" style={{ gap: 8 }}>
          <p className="muted" style={{ margin: 0 }}>
            Scheduled backups never include your Garmin key. The password is encrypted on the server and never shown again.
            The connection is tested before saving.
          </p>
          <div className="row">
            <label style={{ flex: 2, minWidth: 180 }}>Server<input value={f.host} onChange={(e) => set("host", e.target.value)} placeholder="nas.local or 192.168.1.10" required /></label>
            <label style={{ flex: 1, minWidth: 120 }}>Share<input value={f.share} onChange={(e) => set("share", e.target.value)} placeholder="backups" required /></label>
            <label style={{ flex: 1, minWidth: 140 }}>Folder (optional)<input value={f.folder} onChange={(e) => set("folder", e.target.value)} placeholder="endurance-coach" /></label>
          </div>
          <div className="row">
            <label style={{ flex: 1, minWidth: 140 }}>Username<input value={f.username} onChange={(e) => set("username", e.target.value)} autoComplete="off" required /></label>
            <label style={{ flex: 1, minWidth: 140 }}>Password{status.configured && <span className="muted"> (blank = keep)</span>}
              <input type="password" value={f.password} onChange={(e) => set("password", e.target.value)} autoComplete="new-password" required={!status.configured} />
            </label>
            <label style={{ flex: 1, minWidth: 120 }}>Domain (optional)<input value={f.domain} onChange={(e) => set("domain", e.target.value)} /></label>
            <label style={{ width: 90 }}>Port<input type="number" value={f.port} onChange={(e) => set("port", Number(e.target.value))} /></label>
          </div>
          <div className="row">
            <label>How often
              <select value={f.interval_minutes} onChange={(e) => set("interval_minutes", Number(e.target.value))}>
                {status.interval_options.map((m) => <option key={m} value={m}>{label(m)}</option>)}
              </select>
            </label>
            <label style={{ width: 150 }}>Keep newest<input type="number" min={1} max={365} value={f.keep} onChange={(e) => set("keep", Number(e.target.value))} /></label>
          </div>
          {error && <p className="error">{error}</p>}
          <div className="row">
            <button className="primary" disabled={busy}>{busy ? "Testing connection…" : "Test and save"}</button>
            {status.configured && <button type="button" onClick={() => setEditing(false)}>Cancel</button>}
          </div>
        </form>
      )}
    </div>
  );
}
