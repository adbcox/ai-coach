import { useEffect, useState } from "react";
import { api } from "../api";
import Cite from "./Cite";

interface Method { id: string; name: string; value: number | null; low?: number; high?: number; unit?: string; status: string; steps: string[]; warnings: string[]; citation: string }
interface Data {
  methods: Method[]; note: string; trend: { date: string; vdot: number; effort: { distance_m: number; time_s: number } }[];
  watch: { value: number; entered: string | null; differences: { method: string; diff: number }[] } | null;
  max_hr: { value: number | null; estimate: number | null };
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
  return (
    <section className="card wide">
      <h3 style={{ margin: 0 }}>VO2max estimates</h3>
      <span className="muted">{d.note}</span>
      {d.methods.map((m) => (
        <details key={m.id} className="method">
          <summary>
            <span className="mname">{m.name}</span>
            <span className="mtime">{m.value != null ? `${m.value.toFixed(1)} ${m.unit ?? ""}` : "–"}</span>
            {m.low != null && m.high != null && <span className="muted">{m.low.toFixed(1)}–{m.high.toFixed(1)}</span>}
            <span className={`badge ${m.status === "ok" ? "ok" : "muted"}`}>{m.status === "ok" ? "estimate" : "not enough data"}</span>
          </summary>
          <pre className="math">{m.steps.join("\n")}</pre>
          {m.warnings.map((w) => <p key={w} className="warnline">{w}</p>)}
          <p className="muted">Source: <Cite id={m.citation} /></p>
        </details>
      ))}
      <label>Your watch's VO2max (optional, to compare)
        <div className="row"><input type="number" min={15} max={90} step="0.1" value={watch} onChange={(e) => setWatch(e.target.value)} onBlur={saveWatch} placeholder="e.g. 52" style={{ maxWidth: 140 }} /></div>
      </label>
      {d.watch && <p className="muted" style={{ margin: 0 }}>Garmin does not share its VO2max through the Personal API, so enter what your watch shows. Differences: {d.watch.differences.map((x) => `${x.method} ${x.diff > 0 ? "+" : ""}${x.diff.toFixed(1)}`).join("; ")}.</p>}
      {d.trend.length > 0 && (
        <div className="tablewrap"><table>
          <thead><tr><th>As of</th><th className="num">Best VDOT in the 90 days before</th></tr></thead>
          <tbody>{d.trend.map((t) => <tr key={t.date}><td>{t.date}</td><td className="num">{t.vdot.toFixed(1)}</td></tr>)}</tbody>
        </table></div>
      )}
      <span className="muted">Sources: <Cite id="daniels1979" /> <Cite id="uth2004" /> <Cite id="molina2022" /></span>
    </section>
  );
}
