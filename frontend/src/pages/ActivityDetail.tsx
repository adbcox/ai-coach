import { useCallback, useEffect, useState } from "react";
import { ActivityDetail as Detail, api, SamplesData } from "../api";
import LinkedCharts from "../components/LinkedCharts";
import RunMap from "../components/RunMap";
import { duration, km, kmh, pace, sportGroup } from "../lib/format";

const num = (v: unknown): number | null => (typeof v === "number" && isFinite(v) ? v : null);

export default function ActivityDetail({ id, back }: { id: number; back: () => void }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [samples, setSamples] = useState<SamplesData | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setDetail(null);
    setSamples(null);
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
          <LinkedCharts data={samples} running={running} onHover={onHover} />
          <span className="muted">
            Showing {samples.t.length} of {samples.total_samples} samples. Hover a chart to see that point on the map.
          </span>
        </section>
      )}
    </div>
  );
}
