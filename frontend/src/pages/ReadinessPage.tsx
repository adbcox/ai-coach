import { useEffect, useState } from "react";
import { api, Correlation, CorrelationsList, Readiness, ReadinessHistory } from "../api";

function bandColor(b: string | null): string {
  if (b === "green") return "#1a7f37";
  if (b === "yellow") return "#b35900";
  if (b === "red") return "#c0362c";
  return "#8b949e";
}

export default function ReadinessPage() {
  const [today, setToday] = useState<Readiness | null>(null);
  const [hist, setHist] = useState<ReadinessHistory | null>(null);
  const [corr, setCorr] = useState<Correlation[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Readiness>("/readiness/today").then(setToday).catch(() => undefined);
    api<ReadinessHistory>("/readiness/history?days=90").then(setHist).catch(() => undefined);
    api<CorrelationsList>("/correlations?y=readiness_score&min_abs_rho=0.2&limit=10")
      .then((d) => setCorr(d.rows)).catch((e) => setError((e as Error).message));
  }, []);

  return (
    <div className="dash">
      <section className="card">
        <h2 className="dash-h">Readiness</h2>
        <div className="readi-strip">
          {(hist?.days ?? []).slice(-60).map((d) => (
            <span key={d.day} className="readi-day"
              title={`${d.day}: ${d.score ?? "—"} (${d.band ?? "—"})`}
              style={{
                background: bandColor(d.band),
                height: `${Math.max(4, ((d.score ?? 0) / 100) * 40)}px`,
              }} />
          ))}
        </div>
        {today && today.score != null ? (
          <div className="row">
            <span className={`readi-chip band-${today.band}`}>Today: {today.score} · {today.band}</span>
            {typeof today.hrv_part === "number" && <span className="muted">HRV {Math.round(today.hrv_part * 100)}%</span>}
            {typeof today.sleep_part === "number" && <span className="muted">Sleep {Math.round(today.sleep_part * 100)}%</span>}
            {typeof today.rhr_part === "number" && <span className="muted">RHR {Math.round(today.rhr_part * 100)}%</span>}
            {typeof today.load_part === "number" && <span className="muted">Load {Math.round(today.load_part * 100)}%</span>}
          </div>
        ) : <p className="muted">No readiness score for today yet.</p>}
      </section>

      <section className="card">
        <h2 className="dash-h">What moves your readiness</h2>
        <p className="muted">Correlations over your recent history — association, not cause.</p>
        {corr.length === 0 ? (
          <p className="muted">Not enough data yet.</p>
        ) : (
          <table className="tbl-latest">
            <thead>
              <tr>
                <th>Driver</th>
                <th className="num">ρ</th>
                <th className="num">n</th>
                <th>Direction</th>
              </tr>
            </thead>
            <tbody>
              {corr.map((c, i) => (
                <tr key={i}>
                  <td>{c.x.replace(/_/g, " ")}</td>
                  <td className="num">{c.rho.toFixed(2)}</td>
                  <td className="num">{c.n}</td>
                  <td>{c.rho > 0 ? "higher driver → higher readiness" : "higher driver → lower readiness"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {error && <p className="error">{error}</p>}
      </section>
    </div>
  );
}
