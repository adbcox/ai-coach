import { useCallback, useEffect, useState } from "react";
import { ActivityDetail as Detail, api, SamplesData } from "../api";
import LinkedCharts, { HrZone, ZONE_COLORS } from "../components/LinkedCharts";
import RunMap from "../components/RunMap";
import { duration, km, kmh, pace, sportGroup } from "../lib/format";

function ZoneBars({ summary }: { summary: Record<string, unknown> }) {
  const zones = [1, 2, 3, 4, 5].map((z) => num(summary[`hrTimeInZone_${z}`]) ?? 0);
  const total = zones.reduce((a, b) => a + b, 0);
  if (total <= 0) return null;
  // Strava-style zone colours: 1 grey, 2 blue, 3 green, 4 orange, 5 red
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

const num = (v: unknown): number | null => (typeof v === "number" && isFinite(v) ? v : null);

export default function ActivityDetail({ id, back }: { id: number; back: () => void }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [samples, setSamples] = useState<SamplesData | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [zones, setZones] = useState<HrZone[]>([]);
  const [zoneNote, setZoneNote] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setDetail(null);
    setSamples(null);
    api<{ hr_zones: HrZone[]; hr_zone_note: string }>("/preferences")
      .then((p) => { setZones(p.hr_zones); setZoneNote(p.hr_zone_note); })
      .catch(() => undefined);
    api<Detail>(`/activities/${id}`).then(setDetail).catch((e) => setError(e.message));
    api<SamplesData>(`/activities/${id}/samples?max_points=1500`).then(setSamples).catch((e) => setError(e.message));
  }, [id]);

  const onHover = useCallback((i: number | null) => setHover(i), []);

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
    ["Distance", `${km(detail.distance_m)} km`],
    ["Time", duration(detail.duration_s)],
    [running ? "Avg pace" : "Avg speed", running ? `${pace(avgSpeed)} /km` : `${kmh(avgSpeed)} km/h`],
    ["Elevation gain", detail.elevation_gain_m != null ? `${Math.round(detail.elevation_gain_m)} m` : "–"],
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

  return (
    <div className="stack">
      <div className="row between">
        <div>
          <button className="link" onClick={back}>← Back</button>
          <h2 style={{ margin: "4px 0 0" }}>{detail.name ?? detail.sport ?? "Activity"}</h2>
          <span className="muted">
            {new Date(detail.start_time).toLocaleString()} · {detail.sport ?? "unknown sport"} · {detail.source}
          </span>
        </div>
        {hasGps && <a className="button" href={`/api/activities/${id}/gpx`} download>Download GPX</a>}
      </div>

      <div className="tiles">
        {stats.map(([label, value]) => (
          <div key={label} className="card tile">
            <span className="muted">{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>

      <ZoneBars summary={s} />

      {!samples && <p className="muted">Loading track…</p>}
      {samples && samples.t.length === 0 && (
        <p className="muted">No per-second data stored for this activity.</p>
      )}
      {samples && hasGps && (
        <section className="card wide nopad">
          <RunMap lat={samples.lat} lon={samples.lon} hoverIndex={hover} />
        </section>
      )}
      {samples && samples.t.length > 1 && (
        <section className="card wide">
          <LinkedCharts data={samples} running={running} onHover={onHover} zones={zones} />
          <span className="muted">
            Showing {samples.t.length} of {samples.total_samples} samples. Hover (or touch and drag) a chart to see that point on the map.{zones.length > 0 && ` Heart-rate bands: ${zoneNote} Change max heart rate in Settings.`}
          </span>
        </section>
      )}
    </div>
  );
}
