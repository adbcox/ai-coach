import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import Cite from "../components/Cite";
import Vo2max from "../components/Vo2max";

interface Brief { activity_id: number; date: string; name: string | null; distance_m: number; time_s: number }
interface Effort extends Brief {
  pace_s_per_km: number; avg_hr: number | null; kind: string; flags: string[]; used: boolean; not_used_because: string[];
  adjustment: string; covered_m: number; is_race: boolean;
}
interface Method {
  id: string; name: string; time_s: number | null; status: "ok" | "extrapolated" | "reference_only" | "not_enough_data";
  steps: string[]; warnings: string[]; citation: string; scenario: boolean; note?: string;
  source_effort?: Brief; by_source?: { from: Brief; time_s: number }[]; interval_s?: [number, number];
}
interface BtSummary { n: number; median_error_pct: number; p25: number; p75: number; within_3pct: number; within_5pct: number }
interface Target {
  key: string; label: string; distance_m: number; actual_best: Brief | null; methods: Method[]; notes: string[];
  headline: { middle_s: number; low_s: number; high_s: number; pace_s_per_km: number; n_methods: number; how: string } | null;
  support: { level: "good" | "extrapolated" | "weak"; text: string; rule: string } | null;
  backtest: { summary: Record<string, BtSummary>; n_anchors: number; how: string; basis: string; races: RaceRow[] };
}
interface Citation { id: string; short: string; how_used: string; verified_label: string }
interface GapModel { name: string; steps: string[]; table: { grade_pct: number; cost_j_per_kg_m: number; ratio: number }[]; limits: string; citation: string }
interface RaceRow { on: string; activity_id: number; name: string | null; actual_s: number; predictions: Record<string, { time_s: number; error_pct: number }> }
interface Result {
  mission: string; efforts: Effort[]; targets: Target[]; citations: Citation[]; caveats: string[]; gap_model: GapModel;
  context: { weeks: number; runs: number; weekly_km: number; longest_run_km: number; text: string };
  scan: { running: boolean; done: number; total: number; pending: number };
}

const t = (s: number) => {
  const r = Math.round(s), h = Math.floor(r / 3600), m = Math.floor((r % 3600) / 60), sec = r % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
};
const pace = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}/km`;
const dist = (m: number) => (Math.abs(m - 21097.5) < 1 ? "21.0975 km" : Math.abs(m - 1609.344) < 1 ? "1 mile" : `${m / 1000} km`);
const STATUS: Record<string, [string, string]> = {
  ok: ["counted", "ok"], extrapolated: ["counted, extrapolated", "warn"],
  reference_only: ["reference only, not counted", "muted"], not_enough_data: ["not enough data", "muted"],
};
const METHOD_LABEL: Record<string, string> = { riegel_106: "Riegel k = 1.06", riegel_fit: "Your fitted exponent", vdot: "VDOT" };

export default function Predict(_props: { goSettings: () => void }) {
  const [windowDays, setWindowDays] = useState(365);
  const [indoor, setIndoor] = useState(true);
  const [trail, setTrail] = useState(true);
  const [gap, setGap] = useState(true);
  const [sel, setSel] = useState("10k");
  const [data, setData] = useState<Result | null>(null);
  const [error, setError] = useState("");
  const [showAll, setShowAll] = useState(false);

  const load = useCallback(() => {
    api<Result>(`/predictions?window_days=${windowDays}&include_indoor=${indoor}&include_trail=${trail}&use_gap=${gap}`)
      .then(setData).catch((e) => setError(e.message));
  }, [windowDays, indoor, trail, gap]);
  useEffect(load, [load]);
  useEffect(() => {
    if (!data?.scan.running && !data?.scan.pending) return;
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, [data?.scan.running, data?.scan.pending, load]);

  const target = data?.targets.find((x) => x.key === sel);
  const efforts = useMemo(() => {
    if (!data || !target) return [];
    const byDist = new Map<number, Effort[]>();
    data.efforts.forEach((e) => byDist.set(e.distance_m, [...(byDist.get(e.distance_m) ?? []), e]));
    const rows: Effort[] = [];
    [...byDist.keys()].sort((a, b) => a - b).forEach((d) => {
      const list = byDist.get(d)!.sort((a, b) => a.time_s - b.time_s);
      rows.push(...(showAll ? list : list.slice(0, 4)));
    });
    return rows;
  }, [data, target, showAll]);

  async function toggle(e: Effort) {
    await api(`/efforts/${e.activity_id}/exclude`, e.not_used_because.includes("excluded by you") ? "DELETE" : "POST");
    load();
  }
  function download() {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "race-prediction-calculation.json";
    a.click();
  }

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Loading…</p>;

  const summary = `${windowDays >= 730 ? "2 years" : windowDays >= 365 ? "12 months" : windowDays >= 180 ? "6 months" : "3 months"} of runs · ${gap ? "hills adjusted" : "hills not adjusted"}${indoor ? " · treadmill included" : ""}${trail && gap ? " · trail included" : ""}`;
  return (
    <div className="stack">
      <div>
        <h2 style={{ margin: 0 }}>Race predictions</h2>
        <p className="muted" style={{ margin: "4px 0 0" }}>Worked out from your own runs. Tap a distance, then "Show the math" to see exactly how.</p>
      </div>

      {data.scan.pending > 0 && (
        <p className="notice">Analysing your runs for best efforts ({data.scan.done} of {data.scan.total || data.scan.pending} done). Predictions fill in as this finishes.</p>
      )}

      <div className="tiles">
        {data.targets.map((x) => (
          <button key={x.key} className={`card tile pick ${x.key === sel ? "active" : ""}`} onClick={() => setSel(x.key)}>
            <span className="muted">{x.label}</span>
            {x.headline ? (
              <>
                <strong>{t(x.headline.middle_s)}</strong>
                <span className="muted">{t(x.headline.low_s)} – {t(x.headline.high_s)} · {pace(x.headline.pace_s_per_km)}</span>
              </>
            ) : (
              <><strong>–</strong><span className="muted">not enough data</span></>
            )}
            {x.support && <span className={`badge ${x.support.level === "good" ? "ok" : x.support.level === "weak" ? "bad" : "warn"}`}>{x.support.level === "good" ? "well supported" : x.support.level}</span>}
            {x.actual_best && <span className="muted">your best: {t(x.actual_best.time_s)}</span>}
          </button>
        ))}
      </div>

      <details className="settingsbar">
        <summary><span className="muted">Based on: {summary}</span> <span className="link">change</span></summary>
        <div className="row" style={{ marginTop: 8 }}>
          <label>Use efforts from the last
            <select value={windowDays} onChange={(e) => setWindowDays(Number(e.target.value))}>
              <option value={90}>3 months</option><option value={180}>6 months</option>
              <option value={365}>12 months</option><option value={730}>2 years</option>
            </select>
          </label>
          <label className="check"><input type="checkbox" checked={gap} onChange={(e) => setGap(e.target.checked)} /> Grade-adjusted pace (hills)</label>
          <label className="check"><input type="checkbox" checked={indoor} onChange={(e) => setIndoor(e.target.checked)} /> Include treadmill runs</label>
          <label className="check"><input type="checkbox" checked={trail && gap} disabled={!gap} onChange={(e) => setTrail(e.target.checked)} /> Include trail runs (needs grade adjustment)</label>
        </div>
      </details>

      {target && (
        <section className="card wide">
          <div className="row between" style={{ alignItems: "baseline" }}>
            <h3 style={{ margin: 0 }}>{target.label}</h3>
            {target.headline && <span>{t(target.headline.middle_s)} <span className="muted">likely range {t(target.headline.low_s)} – {t(target.headline.high_s)}</span></span>}
          </div>
          <p style={{ margin: 0 }}>
            {target.headline
              ? `The middle of ${target.headline.n_methods} methods. ${target.support ? (target.support.level === "good" ? "Your recent efforts are close to this distance, so it is well supported." : target.support.level === "extrapolated" ? "This distance is well beyond your recent efforts, so treat it as a stretch." : "This distance is far beyond your recent efforts, so treat it as a rough guide.") : ""}`
              : target.notes[0] ?? "Not enough data yet. Open the math to see what each method needs."}
          </p>

          <details>
            <summary>Show the math</summary>
            <div className="stack" style={{ marginTop: 10 }}>
              {target.headline && <p className="muted" style={{ margin: 0 }}>{target.headline.how}</p>}
              {target.support && <p className="muted" style={{ margin: 0 }}>{target.support.text} <em>{target.support.rule}</em></p>}

              <details className="method">
                <summary><span className="mname">1. The efforts it starts from</span><span className="muted">{efforts.filter((e) => e.used).length} used</span></summary>
                <p className="muted">For each run, the app finds your fastest stretch of each distance, even inside a longer run, and uses the fastest in your chosen period. Leave any effort out to see the prediction change.</p>
                <details className="method">
                  <summary><span className="mname">How grade adjustment works</span><Cite id={data.gap_model.citation} /></summary>
                  <pre className="math">{data.gap_model.steps.join("\n")}</pre>
                  <div className="tablewrap"><table>
                    <thead><tr><th>Slope</th><th className="num">Cost (J/kg/m)</th><th className="num">Ratio to flat</th></tr></thead>
                    <tbody>{data.gap_model.table.map((r) => <tr key={r.grade_pct}><td>{r.grade_pct > 0 ? "+" : ""}{r.grade_pct.toFixed(0)}%</td><td className="num">{r.cost_j_per_kg_m.toFixed(2)}</td><td className="num">{r.ratio.toFixed(2)}x</td></tr>)}</tbody>
                  </table></div>
                  <p className="warnline">{data.gap_model.limits}</p>
                </details>
                {data.efforts.length === 0 && <p className="muted">No best efforts yet. They appear after a sync once your runs have been analysed.</p>}
                <div className="tablewrap">
                  <table>
                    <thead><tr><th>Distance</th><th>Time</th><th className="num">Pace</th><th>Date</th><th className="hide-sm">Run</th><th></th></tr></thead>
                    <tbody>
                      {efforts.map((e) => (
                        <tr key={`${e.activity_id}-${e.distance_m}`} className={e.used ? "" : "dim"}>
                          <td className="nowrap">{dist(e.distance_m)}</td>
                          <td className="nowrap"><a href={`#/activity/${e.activity_id}`}>{t(e.time_s)}</a></td>
                          <td className="num nowrap">{pace(e.pace_s_per_km)}</td>
                          <td className="nowrap">{new Date(e.date).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "2-digit" })}</td>
                          <td className="hide-sm" title={e.adjustment}>{[...e.flags, ...e.not_used_because].join("; ") || "used"}{e.adjustment ? " – " + e.adjustment : ""}</td>
                          <td><button className="link" onClick={() => toggle(e)}>{e.not_used_because.includes("excluded by you") ? "include" : e.used ? "leave out" : ""}</button></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="row"><button onClick={() => setShowAll(!showAll)}>{showAll ? "Show only the 4 fastest per distance" : "Show all efforts"}</button></div>
              </details>

              <details className="method">
                <summary><span className="mname">2. The methods</span><span className="muted">{target.methods.filter((m) => m.status === "ok" || m.status === "extrapolated").length} counted</span></summary>
                {target.methods.map((m) => (
                  <details key={m.id} className="method">
                    <summary>
                      <span className="mname">{m.name}</span>
                      <span className="mtime">{m.time_s ? t(m.time_s) : "–"}</span>
                      <span className={`badge ${STATUS[m.status][1]}`}>{STATUS[m.status][0]}</span>
                    </summary>
                    {m.note && <p className="muted">{m.note}</p>}
                    <pre className="math">{m.steps.join("\n")}</pre>
                    {m.warnings.map((w) => <p key={w} className="warnline">{w}</p>)}
                    {m.by_source && m.by_source.length > 1 && (
                      <p className="muted">From each of your efforts separately: {m.by_source.map((b) => `${dist(b.from.distance_m)} ${t(b.from.time_s)} → ${t(b.time_s)}`).join("; ")}.</p>
                    )}
                    <p className="muted">Source: <Cite id={m.citation} /></p>
                  </details>
                ))}
              </details>

              <details className="method">
                <summary><span className="mname">3. How much to trust it</span>
                  <span className="muted">{Object.keys(target.backtest.summary).length ? "checked against your history" : "not enough history to check yet"}</span></summary>
                <p style={{ margin: 0 }}>{target.backtest.how}</p>
                {Object.keys(target.backtest.summary).length === 0 ? (
                  <p className="muted">It needs earlier efforts at other distances before each of your fastest {target.label}s ({target.backtest.n_anchors} such efforts found).</p>
                ) : (
                  <div className="tablewrap">
                    <table>
                      <thead><tr><th>Method</th><th className="num">Checks</th><th className="num">Typical error</th><th className="num hide-sm">Middle half of errors</th><th className="num">Within 5%</th></tr></thead>
                      <tbody>
                        {Object.entries(target.backtest.summary).map(([id, s]) => (
                          <tr key={id}>
                            <td>{METHOD_LABEL[id] ?? id}</td><td className="num">{s.n}</td>
                            <td className="num">{s.median_error_pct > 0 ? "+" : ""}{s.median_error_pct.toFixed(1)}%</td>
                            <td className="num hide-sm">{s.p25.toFixed(1)}% to {s.p75.toFixed(1)}%</td>
                            <td className="num">{Math.round(s.within_5pct * 100)}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {target.backtest.races.length > 0 && (
                  <>
                    <h4 style={{ margin: "8px 0 0" }}>Your marked races at this distance</h4>
                    <div className="tablewrap"><table>
                      <thead><tr><th>Race</th><th className="num">Actual</th><th className="num">Riegel 1.06</th><th className="num hide-sm">Your fit</th><th className="num">VDOT</th></tr></thead>
                      <tbody>{target.backtest.races.map((r) => (
                        <tr key={r.activity_id}>
                          <td className="nowrap"><a href={`#/activity/${r.activity_id}`}>{r.on}</a></td><td className="num">{t(r.actual_s)}</td>
                          {["riegel_106", "riegel_fit", "vdot"].map((id) => (
                            <td key={id} className={`num ${id === "riegel_fit" ? "hide-sm" : ""}`}>{r.predictions[id] ? `${t(r.predictions[id].time_s)} (${r.predictions[id].error_pct > 0 ? "+" : ""}${r.predictions[id].error_pct.toFixed(1)}%)` : "–"}</td>
                          ))}
                        </tr>
                      ))}</tbody>
                    </table></div>
                  </>
                )}
                {target.methods.find((m) => m.interval_s) && (() => {
                  const m = target.methods.find((x) => x.interval_s)!;
                  return <p className="muted" style={{ margin: 0 }}>The fitted-exponent method also gives a 95% prediction interval of {t(m.interval_s![0])} to {t(m.interval_s![1])}; with few efforts it is wide, and that is the honest size of the uncertainty.</p>;
                })()}
                {(target.key === "half" || target.key === "marathon") && (
                  <p style={{ margin: 0 }}>Your recent training: <strong>{data.context.weekly_km.toFixed(0)} km a week</strong> on average over {data.context.weeks} weeks across {data.context.runs} runs, longest run <strong>{data.context.longest_run_km.toFixed(1)} km</strong>. {data.context.text}</p>
                )}
              </details>
            </div>
          </details>
        </section>
      )}

      <Vo2max />

      <details className="card wide">
        <summary>Sources and limits</summary>
        <ul className="sources" style={{ marginTop: 10 }}>
          {data.citations.map((c) => (
            <li key={c.id}><Cite id={c.id} /> {c.how_used} <em className="muted">({c.verified_label})</em></li>
          ))}
        </ul>
        {data.caveats.map((c) => <p key={c} className="muted" style={{ margin: "6px 0 0" }}>{c}</p>)}
        <div className="row" style={{ marginTop: 8 }}>
          <button onClick={download}>Download the full calculation (JSON)</button>
          <a href="#/references">All sources and how well each was checked</a>
        </div>
      </details>
    </div>
  );
}
