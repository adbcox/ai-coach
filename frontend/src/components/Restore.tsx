import { FormEvent, useState } from "react";
import { restoreBackup, RestoreSummary } from "../api";

/** Upload a backup archive. Used on the first-run screen and in Settings. */
export default function Restore({ replacing, onDone }: { replacing: boolean; onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [passphrase, setPassphrase] = useState("");
  const [confirm, setConfirm] = useState(!replacing);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<RestoreSummary | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      setResult(await restoreBackup(file, passphrase));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    return (
      <div className="stack" style={{ gap: 8 }}>
        <strong>Backup restored.</strong>
        <span>
          {result.rows.activities} activities, {result.rows.samples} samples, {result.files} files.
          {result.secrets_restored
            ? " Garmin key restored."
            : result.secrets_in_backup
              ? " The backup holds a sealed Garmin key but no passphrase was given, so re-enter the key in Settings."
              : " Re-enter your Garmin key in Settings."}
          {result.previous_database_kept_as && ` Your previous database was kept as ${result.previous_database_kept_as}.`}
        </span>
        <button className="primary" onClick={onDone}>Continue to sign in</button>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="stack" style={{ gap: 10 }}>
      <label>
        Backup file (.tar)
        <input type="file" accept=".tar" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
      </label>
      <label>
        Passphrase <span className="muted">(only if the backup includes a sealed Garmin key)</span>
        <input type="password" value={passphrase} onChange={(e) => setPassphrase(e.target.value)} autoComplete="off" />
      </label>
      {replacing && (
        <label className="check">
          <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} style={{ minWidth: 0 }} />
          This replaces the current database and signs everyone out. A copy of the current database is kept.
        </label>
      )}
      {error && <p className="error">{error}</p>}
      <button className="primary" disabled={busy || !file || !confirm}>
        {busy ? "Restoring…" : "Restore backup"}
      </button>
    </form>
  );
}
