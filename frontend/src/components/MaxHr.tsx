import { useEffect, useState } from "react";
import { api } from "../api";
import Cite from "./Cite";

interface Data {
  estimate: number | null; confidence: string | null; steps: string[]; garmin_summary_max: number | null;
  top_peaks: { activity_id: number; date: string; sport: string | null; peak_hr: number }[]; age_formula_tanaka: number | null; scan_pending: number;
}

export default function MaxHr({ onApplied }: { onApplied: () => void }) {
  const [d, setD] = useState<Data | null>(null);
  const load = () => api<Data>("/maxhr").then(setD).catch(() => undefined);
  useEffect(() => { load(); }, []);
  if (!d) return null;
  return (
    <details className="method">
      <summary>
        <span className="mname">Max heart rate estimated from your own data</span>
        <span className="mtime">{d.estimate ? `${d.estimate} bpm` : "–"}</span>
        {d.confidence && <span className={`badge ${d.confidence === "ok" ? "ok" : "warn"}`}>{d.confidence === "ok" ? "3+ hard efforts" : "low confidence"}</span>}
      </summary>
      {d.scan_pending > 0 && <p className="notice">Still analysing {d.scan_pending} activities.</p>}
      <pre className="math">{d.steps.join("\n")}</pre>
      {d.top_peaks.length > 0 && (
        <div className="tablewrap"><table>
          <thead><tr><th>Date</th><th>Sport</th><th className="num">Peak (15 s average)</th></tr></thead>
          <tbody>{d.top_peaks.map((p) => (
            <tr key={p.activity_id}><td><a href={`#/activity/${p.activity_id}`}>{new Date(p.date).toLocaleDateString()}</a></td><td>{(p.sport ?? "").replace(/_/g, " ")}</td><td className="num">{p.peak_hr.toFixed(0)} bpm</td></tr>
          ))}</tbody>
        </table></div>
      )}
      {d.garmin_summary_max && <p className="muted">Garmin's own summary maximum over this period: {d.garmin_summary_max} bpm (unfiltered, so a sensor glitch can inflate it).</p>}
      <div className="row">
        {d.estimate && <button className="primary" onClick={async () => { await api("/maxhr/apply", "POST"); onApplied(); load(); }}>Use {d.estimate} bpm as my max heart rate</button>}
      </div>
      <p className="muted">Sources: <Cite id="tanaka2001" /> <Cite id="kasiak2023" /></p>
    </details>
  );
}
