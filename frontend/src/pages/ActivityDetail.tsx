import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityDetail as Detail, api, Climb, CoachReply, Disagreement,
  PowerCurve, RideMetrics, SamplesData,
} from "../api";
import LinkedCharts, { HrZone, ZONE_COLORS } from "../components/LinkedCharts";
import PowerCurveChart from "../components/PowerCurveChart";
import RunMap from "../components/RunMap";
import {
  duration, elevation, km, kmh, pace, sportGroup, unitDist, unitSpeed,
} from "../lib/format";
import { useUnits } from "../lib/units";
import Laps from "../components/Laps";

const num = (v: unknown): number | null => (typeof v === "number" && isFinite(v) ? v : null);

const SECTIONS = [
  { k: "overview", label: "Overview" },
  { k: "analysis", label: "Analysis" },
  { k: "hr", label: "Heart rate" },
  { k: "power", label: "Power curve" },
  { k: "zones", label: "Zones" },
  { k: "laps", label: "Laps" },
  { k: "best", label: "Best efforts" },
  { k: "climbs", label: "Climbs" },
  { k: "map", label: "Map" },
] as const;
type SectionKey = (typeof SECTIONS)[number]["k"];

export default function ActivityDetail({ id, back }: { id: number; back: () => void }) {
  useUnits();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [samples, setSamples] = useState<SamplesData | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [isRace, setIsRace] = useState(false);
  const [zones, setZones] = useState<HrZone[]>([]);
  const [metrics, setMetrics] = useState<RideMetrics | null>(null);
  const [pcurve, setPcurve] = useState<PowerCurve | null>(null);
  const [climbs, setClimbs] = useState<Climb[]>([]);
  const [coach, setCoach] = useState<CoachReply | null>(null);
  const [disagreement, setDisagreement] = useState<Disagreement | null>(null);
  const [section, setSection] = useState<SectionKey>("overview");
  const [error, setError] = useState("");

  useEffect(() => {
    setDetail(null); setSamples(null); setMetrics(null); setPcurve(null);
    setClimbs([]); setCoach(null); setDisagreement(null);
    api<{ hr_zones: HrZone[] }>("/preferences").then((p) => setZones(p.hr_zones)).catch(() => undefined);
    api<Detail>(`/activities/${id}`)
      .then((d) => { setDetail(d); setIsRace(!!(d as unknown as { is_race?: boolean }).is_race); })
      .catch((e) => setError(e.message));
    api<SamplesData>(`/activities/${id}/samples?max_points=1500`).then(setSamples).catch((e) => setError(e.message));
    api<RideMetrics>(`/activities/${id}/metrics`).then(setMetrics).catch(() => undefined);
    api<PowerCurve>(`/activities/${id}/power_curve`).then(setPcurve).catch(() => undefined);
    api<{ climbs: Climb[] }>(`/activities/${id}/climbs`).then((d) => setClimbs(d.climbs)).catch(() => undefined);
    api<CoachReply>(`/coach/ride/${id}`, "POST").then(setCoach).catch(() => undefined);
    api<Disagreement>(`/activities/${id}/disagreement`).then(setDisagreement).catch(() => undefined);
  }, [id]);

  const onHover = useCallback((i: number | null) => setHover(i), []);

  const bestEfforts = useMemo(() => {
    if (!pcurve) return [] as { label: string; watts?: number; speedMps?: number }[];
    const want = [5, 60, 300, 600, 1200, 1800, 3600];
    const pMap = new Map(pcurve.power.map((p) => [p.window_s, p.watts]));
    const sMap = new Map(pcurve.pace.map((p) => [p.window_s, p.metres_per_s]));
    return want.map((w) => ({
      label: w < 60 ? `${w}s` : w < 3600 ? `${Math.round(w / 60)} min` : `${(w / 3600).toFixed(1)} h`,
      watts: pMap.get(w),
      speedMps: sMap.get(w),
    })).filter((r) => r.watts != null || r.speedMps != null);
  }, [pcurve]);

  if (error) return <p className="error">{error} <button onClick={back}>Back</button></p>;
  if (!detail) return <p className="muted">Loading…</p>;

  const running = sportGroup(detail.sport) === "Running";
  const avgSpeed = detail.distance_m && detail.duration_s ? detail.distance_m / detail.duration_s : null;
  const hasGps = !!samples && samples.lat.some((v) => v != null);
  const s = detail.summary ?? {};
  const load = num(s["activityTrainingLoad"]);
  const aero = num(s["aerobicTrainingEffect"]);
  const anaero = num(s["anaerobicTrainingEffect"]);

  const stats: [string, string][] = [
    ["Distance", `${km(detail.distance_m)} ${unitDist()}`],
    ["Time", duration(detail.duration_s)],
    [running ? "Avg pace" : "Avg speed", running ? `${pace(avgSpeed)} /${unitDist()}` : `${kmh(avgSpeed)} ${unitSpeed()}`],
    ["Elevation gain", elevation(detail.elevation_gain_m)],
    ["Avg HR", detail.avg_hr ? `${Math.round(detail.avg_hr)} bpm` : "–"],
    ["Max HR", detail.max_hr ? `${Math.round(detail.max_hr)} bpm` : "–"],
  ];
  const cad = num(s["averageRunningCadenceInStepsPerMinute"]);
  const stride = num(s["avgStrideLength"]);
  const gct = num(s["avgGroundContactTime"]);
  const vo = num(s["avgVerticalOscillation"]);
  const pw = num(s["avgPower"]);
  const npw = num(s["normPower"]);
  const temp = num(s["maxTemperature"]);
  if (cad) stats.push(["Cadence", `${Math.round(cad)} spm`]);
  if (stride && stride > 30) stats.push(["Stride length", `${(stride / 100).toFixed(2)} m`]);
  if (gct && gct > 0) stats.push(["Ground contact", `${Math.round(gct)} ms`]);
  if (vo) stats.push(["Vertical oscillation", `${vo.toFixed(1)} cm`]);
  if (pw) stats.push(["Avg power", `${Math.round(pw)} W`]);
  if (npw) stats.push(["Normalized power", `${Math.round(npw)} W`]);
  if (temp != null) stats.push(["Max temperature", `${Math.round(temp)} °C`]);
  if (load != null) stats.push(["Training load", load.toFixed(0)]);
  if (aero != null) stats.push(["Aerobic effect", aero.toFixed(1)]);
  if (anaero != null) stats.push(["Anaerobic effect", anaero.toFixed(1)]);
  if (metrics) {
    if (metrics.np != null) stats.push(["NP (coach)", `${Math.round(metrics.np as number)} W`]);
    if (metrics.if_ != null) stats.push(["IF", (metrics.if_ as number).toFixed(2)]);
    if (metrics.tss != null) stats.push(["TSS", (metrics.tss as number).toFixed(0)]);
    if (metrics.ef != null) stats.push(["EF", (metrics.ef as number).toFixed(2)]);
    if (metrics.decoupling_pct != null) {
      const dec = metrics.decoupling_pct as number;
      stats.push(["Decoupling", `${dec.toFixed(1)}%${dec > 5 ? " ⚠" : ""}`]);
    }
  }

  const showMap = section === "overview" || section === "map";
  const showTraces = section === "overview" || section === "analysis" || section === "hr";
  return (
    <div className="ride">
      <div className="ride-head">
        <button className="link" onClick={back}>← Back</button>
        <div className="ride-title">
          <h2>{detail.name ?? detail.sport ?? "Activity"}</h2>
          <span className="muted">
            {new Date(detail.start_time).toLocaleString()} · {detail.sport ?? "unknown sport"} · {detail.source}
          </span>
        </div>
        <div className="row">
          <button onClick={async () => { await api(`/activities/${id}/race`, isRace ? "DELETE" : "POST"); setIsRace(!isRace); }}
            title="Races are used to check how well predictions would have done">
            {isRace ? "Unmark as race" : "Mark as a race"}
          </button>
          {hasGps && <a className="button" href={`/api/activities/${id}/gpx`} download>Download GPX</a>}
        </div>
      </div>

      {coach && <section className="card swo-note" style={{ margin: 0 }}>{coach.reply}</section>}
      {disagreement && disagreement.disagreement_score >= 1 && (
        <section className="card disagreement">
          <strong>Power/HR mismatch ({Math.round(disagreement.disagreement_score)}):</strong>{" "}
          <span>{disagreement.cause.replace(/_/g, " ")}</span>
          <span className="muted"> · confidence {Math.round(disagreement.confidence * 100)}%</span>
        </section>
      )}

      <div className="ride-body">
        <nav className="ride-nav" aria-label="Sections">
          {SECTIONS.map((s0) => (
            <button key={s0.k} className={section === s0.k ? "active" : ""}
              onClick={() => setSection(s0.k)}>{s0.label}</button>
          ))}
        </nav>
        <div className="ride-main">
          {section === "overview" && (
            <>
              <div className="tiles">
                {stats.map(([label, value]) => (
                  <div key={label} className="card tile">
                    <span className="muted">{label}</span>
                    <strong>{value}</strong>
                  </div>
                ))}
              </div>
              {samples && samples.t.length > 1 && (
                <section className="card wide">
                  <LinkedCharts data={samples} running={running} onHover={onHover} zones={zones} />
                </section>
              )}
            </>
          )}

          {section === "analysis" && samples && samples.t.length > 1 && (
            <section className="card wide">
              <LinkedCharts data={samples} running={running} onHover={onHover} zones={zones} />
              <span className="muted">
                Stacked synced traces — speed, HR, power, cadence (whichever exist). Hover for exact values.
              </span>
            </section>
          )}

          {section === "hr" && (
            <>
              {samples && samples.t.length > 1 && (
                <section className="card wide">
                  <LinkedCharts data={samples} running={running} onHover={onHover} zones={zones} />
                </section>
              )}
              <ZoneBars summary={s} />
            </>
          )}

          {section === "power" && (
            <section className="card wide">
              <h3 style={{ margin: 0 }}>Mean-maximal power</h3>
              <PowerCurveChart points={pcurve?.power ?? []} />
            </section>
          )}

          {section === "zones" && <ZoneBars summary={s} />}

          {section === "laps" && <Laps activityId={id} running={running} />}

          {section === "best" && (
            <section className="card wide">
              <h3 style={{ margin: 0 }}>Best efforts</h3>
              {bestEfforts.length === 0 ? (
                <p className="muted">No power/pace mean-maximal data for this activity.</p>
              ) : (
                <table className="tbl-latest">
                  <tbody>
                    {bestEfforts.map((b) => (
                      <tr key={b.label}>
                        <td className="nowrap">{b.label}</td>
                        <td className="num">
                          {b.watts != null ? `${Math.round(b.watts)} W` : ""}
                          {b.watts != null && b.speedMps != null ? " · " : ""}
                          {b.speedMps != null ? (running
                              ? `${pace(b.speedMps)} /${unitDist()}`
                              : `${kmh(b.speedMps)} ${unitSpeed()}`) : ""}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          )}

          {section === "climbs" && (
            <section className="card wide">
              <h3 style={{ margin: 0 }}>Climbs</h3>
              {climbs.length === 0 ? (
                <p className="muted">No climbs detected.</p>
              ) : (
                <table className="tbl-latest">
                  <thead>
                    <tr>
                      <th>#</th><th className="num">Length</th>
                      <th className="num">Grade (avg · max)</th>
                      <th className="num">VAM</th>
                    </tr>
                  </thead>
                  <tbody>
                    {climbs.map((c) => (
                      <tr key={c.idx}>
                        <td>{c.idx + 1}</td>
                        <td className="num">{km(c.length_m)} {unitDist()}</td>
                        <td className="num">{(c.avg_gradient * 100).toFixed(1)}% · {(c.max_gradient * 100).toFixed(1)}%</td>
                        <td className="num">{Math.round(c.vam)} m/h</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          )}

          {section === "map" && samples && hasGps && (
            <section className="card wide nopad">
              <RunMap lat={samples.lat} lon={samples.lon} hoverIndex={hover} />
            </section>
          )}
          {section === "map" && !hasGps && <p className="muted">No GPS track stored for this activity.</p>}
        </div>
      </div>

      {showMap && hasGps && samples && section === "overview" && (
        <section className="card wide nopad">
          <RunMap lat={samples.lat} lon={samples.lon} hoverIndex={hover} />
        </section>
      )}
      {showTraces && samples && samples.t.length === 0 && (
        <p className="muted">No per-second data stored for this activity.</p>
      )}
    </div>
  );
}

function ZoneBars({ summary }: { summary: Record<string, unknown> }) {
  const zones = [1, 2, 3, 4, 5].map((z) => num(summary[`hrTimeInZone_${z}`]) ?? 0);
  const total = zones.reduce((a, b) => a + b, 0);
  if (total <= 0) return <p className="muted">No HR zone data for this activity.</p>;
  const colors = ZONE_COLORS;
  return (
    <section className="card wide">
      <h3 style={{ margin: 0 }}>Time in heart-rate zones</h3>
      {zones.map((sec, i) => (
        <div key={i} className="zonerow">
          <span className="muted">Zone {i + 1}</span>
          <div className="zonebar"><i style={{ width: `${(sec / total) * 100}%`, background: colors[i] }} /></div>
          <span>{duration(sec)} <span className="muted">({Math.round((sec / total) * 100)}%)</span></span>
        </div>
      ))}
    </section>
  );
}
