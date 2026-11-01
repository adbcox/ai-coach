import { useEffect, useState } from "react";
import { api } from "../api";
import Cite from "./Cite";

interface Method { id: string; name: string; value: number | null; low?: number; high?: number; unit?: string; status: string; steps: string[]; warnings: string[]; citation: string; source_year?: number }
interface Data {
  methods: Method[]; note: string; trend: { date: string; vdot: number }[];
  watch: { value: number; entered: string | null; differences: { method: string; diff: number }[] } | null;
}

export default function Vo2max() {
  const [d, setD] = useState<Data | null>(null);
  const [watch, setWatch] = useState("");
  const load = () => api<Data>("/vo2max").then((x) => { setD(x); setWatch(x.watch ? String(x.watch.value) : ""); }).catch(() => undefined);
  useEffect(() => { load(); }, []);
  async function saveWatch() {
    await api("/preferences", "PUT", { watch_vo2max: watch.trim() ? Number(watch) : null });
    load();
  }
  if (!d) return null;
  const have = d.methods.filter((m) => m.value != null);
  return (
    <section className="card wide">
      <h3 style={{ margin: 0 }}>VO2max estimate</h3>
      {have.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>Not enough data yet. Open "Show the math" to see what each method needs.</p>
      ) : (
        <div className="tiles">
          {have.map((m) => (
            <div key={m.id} className="card tile">
              <span className="muted">{m.id === "vdot" ? "From your race times" : "From your heart rate"}</span>
              <strong>{m.value!.toFixed(0)}{m.unit === "VDOT" ? " VDOT" : ""}</strong>
              {m.low != null && m.high != null && <span className="muted">{m.low.toFixed(0)}–{m.high.toFixed(0)}</span>}
            </div>
          ))}
        </div>
      )}
      <span className="muted">An estimate for tracking trends, not a measurement. {d.watch && `Your watch says ${d.watch.value}.`}</span>
      <details>
        <summary>Show the math</summary>
        <div className="stack" style={{ marginTop: 10 }}>
          <p className="muted" style={{ margin: 0 }}>{d.note}</p>
          {d.methods.map((m) => (
            <details key={m.id} className="method">
              <summary>
                <span className="mname">{m.name}</span>
                <span className="mtime">{m.value != null ? `${m.value.toFixed(1)} ${m.unit ?? ""}` : "–"}</span>
                {m.source_year && <span className="badge warn">based on {m.source_year} research</span>}
                {m.status !== "ok" && <span className="badge muted">not enough data</span>}
              </summary>
              <pre className="math">{m.steps.join("\n")}</pre>
              {m.warnings.map((w) => <p key={w} className="warnline">{w}</p>)}
              <p className="muted">Source: <Cite id={m.citation} /></p>
            </details>
          ))}
          <label>Your watch's VO2max (to compare; Garmin does not share it through its API)
            <div className="row"><input type="number" min={15} max={90} step="0.1" value={watch} onChange={(e) => setWatch(e.target.value)} onBlur={saveWatch} placeholder="e.g. 52" style={{ maxWidth: 140 }} /></div>
          </label>
          {d.watch && <p className="muted" style={{ margin: 0 }}>Differences from your watch: {d.watch.differences.map((x) => `${x.method} ${x.diff > 0 ? "+" : ""}${x.diff.toFixed(1)}`).join("; ")}.</p>}
          {d.trend.length > 0 && (
            <div className="tablewrap"><table>
              <thead><tr><th>As of</th><th className="num">Best VDOT in the 90 days before</th></tr></thead>
              <tbody>{d.trend.map((t) => <tr key={t.date}><td>{t.date}</td><td className="num">{t.vdot.toFixed(1)}</td></tr>)}</tbody>
            </table></div>
          )}
          <span className="muted">Sources: <Cite id="daniels1979" /> <Cite id="uth2004" /> <Cite id="molina2022" /> · not used yet: <Cite id="firstbeat2017" /> <Cite id="frontiers2024_acsm" /> <Cite id="elife2023" /></span>
        </div>
      </details>
    </section>
  );
}
