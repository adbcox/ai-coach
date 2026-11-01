import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, BackupList } from "../api";
import Restore from "./Restore";
import SmbBackup from "./SmbBackup";

const size = (b: number) => (b > 1e9 ? (b / 1e9).toFixed(2) + " GB" : (b / 1e6).toFixed(1) + " MB");

export default function Backups({ onRestored }: { onRestored: () => void }) {
  const [data, setData] = useState<BackupList | null>(null);
  const [passphrase, setPassphrase] = useState("");
  const [include, setInclude] = useState(false);
  const [error, setError] = useState("");
  const [showRestore, setShowRestore] = useState(false);

  const load = useCallback(() => {
    api<BackupList>("/backups").then(setData).catch((e) => setError(e.message));
  }, []);
  useEffect(load, [load]);
  useEffect(() => {
    if (!data?.running) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [data?.running, load]);

  async function create(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api("/backups", "POST", { passphrase: include && passphrase ? passphrase : null });
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <section className="card wide">
      <h2>Backups</h2>
      <p className="muted">
        A backup holds your database (activities, per-second data, health data, account) and the original Garmin
        files. It does <strong>not</strong> include the server's master key. Optionally seal your Garmin key into it
        with a passphrase, so a restore on a new machine works without re-entering it. Keep backup files private:
        they contain your health data.
      </p>

      <form onSubmit={create} className="stack" style={{ gap: 8 }}>
        <label className="check">
          <input type="checkbox" checked={include} onChange={(e) => setInclude(e.target.checked)} style={{ minWidth: 0 }} />
          Include my Garmin key, sealed with a passphrase
        </label>
        {include && (
          <input type="password" placeholder="Passphrase (you will need it to restore the key)" value={passphrase}
                 onChange={(e) => setPassphrase(e.target.value)} autoComplete="off" />
        )}
        <div className="row">
          <button className="primary" disabled={data?.running || (include && passphrase.length < 8)}>
            {data?.running ? "Backing up…" : "Create backup now"}
          </button>
        </div>
      </form>
      {include && passphrase.length > 0 && passphrase.length < 8 && <p className="muted">Use at least 8 characters.</p>}
      {(error || data?.error) && <p className="error">{error || data?.error}</p>}

      {data && data.items.length > 0 && (
        <table>
          <thead><tr><th>Backup</th><th className="num">Size</th><th></th></tr></thead>
          <tbody>
            {data.items.map((b) => (
              <tr key={b.name}>
                <td>{new Date(b.created_at).toLocaleString()}</td>
                <td className="num">{size(b.size)}</td>
                <td className="num">
                  <a href={`/api/backups/${b.name}`} download>Download</a>{" "}
                  <button className="link" onClick={() => confirm("Delete this backup?") && api(`/backups/${b.name}`, "DELETE").then(load)}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data && <p className="muted">The newest {data.keep} backups are kept on the server; older ones are removed automatically. With a network share set up, each backup is also uploaded there.</p>}

      {data && <SmbBackup key={data.smb.configured ? data.smb.host : "new"} status={data.smb} onChange={load} />}

      <details open={showRestore} onToggle={(e) => setShowRestore((e.target as HTMLDetailsElement).open)}>
        <summary>Restore from a backup file</summary>
        <div style={{ marginTop: 12 }}>
          <Restore replacing onDone={onRestored} />
        </div>
      </details>
    </section>
  );
}
