import { useEffect, useState } from "react";
import { api } from "../api";
import { duration, km, paceFromSecPerKm, unitDist, unitSpeed } from "../lib/format";
import { elevFactor, elevUnit, useUnits } from "../lib/units";

interface Lap {
  n: number; start_offset_s: number | null; distance_m: number | null; time_s: number | null; avg_speed: number | null;
  pace_s_per_km: number | null; avg_hr: number | null; max_hr: number | null; ascent_m: number | null; descent_m: number | null;
  cadence_spm: number | null; avg_power: number | null; trigger: string | null; intensity: string | null;
}
interface LapData {
  scanned: boolean; count: number; kind: "auto_distance" | "manual" | "workout" | "none"; auto_distance_m: number | null;
  fastest_lap: number | null; slowest_lap: number | null; running: boolean; laps: Lap[];
}

const INTENSITY_COLOR: Record<string, string> = { warmup: "#8b949e", cooldown: "#8b949e", rest: "#8b949e", recovery: "#8b949e", interval: "#cf222e", active: "#1f6feb" };

/** Garmin's "splits": automatic laps (usually every 1 km), manual laps, or the steps of a structured workout. */
export default function Laps({ activityId, running }: { activityId: number; running: boolean }) {
  useUnits();
  const [data, setData] = useState<LapData | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { setData(null); api<LapData>(`/activities/${activityId}/laps`).then(setData).catch((e) => setError(e.message)); }, [activityId]);
  if (error) return <p className="error">{error}</p>;
  if (!data || data.count === 0) return null;

  const showPace = running;
  const ef = elevFactor();
  const speeds = data.laps.map((l) => l.avg_speed ?? 0).filter((v) => v > 0);
  const maxSpeed = Math.max(...speeds, 0.1);
  const minSpeed = Math.min(...speeds, maxSpeed);
  const barWidth = (s: number | null) => (s && s > 0 ? 35 + 65 * ((s - minSpeed * 0.8) / (maxSpeed - minSpeed * 0.8 || 1)) : 0);
  const anyPower = data.laps.some((l) => l.avg_power);
  const anyCad = data.laps.some((l) => l.cadence_spm);
  const anyElev = data.laps.some((l) => l.ascent_m != null || l.descent_m != null);
  const kindText = data.kind === "auto_distance" && data.auto_distance_m
    ? `Automatic laps every ${km(data.auto_distance_m, 2)} ${unitDist()}`
    : data.kind === "workout" ? "Workout steps" : "Laps you or the workout set";
  const rate = (l: Lap) => (showPace ? (l.pace_s_per_km ? paceFromSecPerKm(l.pace_s_per_km) : "–") : (l.avg_speed ? (l.avg_speed * 3.6 * (unitDist() === "mi" ? 1 / 1.609344 : 1)).toFixed(1) : "–"));
  const rateUnit = showPace ? `/${unitDist()}` : unitSpeed();

  return (
    <section className="card wide">
      <div className="row between" style={{ alignItems: "baseline" }}>
        <h3 style={{ margin: 0 }}>Laps</h3>
        <span className="muted">{data.count} · {kindText} (as recorded by your watch)</span>
      </div>

      <div className="lapbars" role="img" aria-label="Pace of each lap">
        {data.laps.map((l) => {
          const color = data.kind === "workout" ? INTENSITY_COLOR[l.intensity ?? "active"] ?? "#1f6feb" : "#1f6feb";
          const best = l.n === data.fastest_lap;
          return (
            <div key={l.n} className="lapbar">
              <span className="muted lapn">{l.n}</span>
              <span className="lapfill" style={{ width: `${barWidth(l.avg_speed)}%`, background: color, outline: best ? "2px solid #2da44e" : undefined }} />
              <span className="lapval">{rate(l)}{best && <span className="ok-text"> fastest</span>}</span>
            </div>
          );
        })}
      </div>

      <div style={{ overflowX: "auto" }}>
        <table className="fixed-ok">
          <thead>
            <tr>
              <th>Lap</th><th className="num">{unitDist()}</th><th className="num">Time</th><th className="num">{showPace ? `Pace (${rateUnit})` : `Speed (${rateUnit})`}</th>
              <th className="num">Avg HR</th><th className="num hide-sm">Max HR</th>
              {anyElev && <th className="num hide-sm">Elev ({elevUnit()})</th>}
              {anyCad && <th className="num hide-sm">Cadence</th>}
              {anyPower && <th className="num hide-sm">Power</th>}
            </tr>
          </thead>
          <tbody>
            {data.laps.map((l) => (
              <tr key={l.n}>
                <td>{l.n}{data.kind === "workout" && l.intensity && l.intensity !== "active" && <span className="badge muted" style={{ marginLeft: 6 }}>{l.intensity}</span>}</td>
                <td className="num">{km(l.distance_m, 2)}</td>
                <td className="num">{duration(l.time_s)}</td>
                <td className="num"><strong>{rate(l)}</strong></td>
                <td className="num">{l.avg_hr ? Math.round(l.avg_hr) : "–"}</td>
                <td className="num hide-sm">{l.max_hr ? Math.round(l.max_hr) : "–"}</td>
                {anyElev && <td className="num hide-sm">{l.ascent_m != null ? `+${Math.round(l.ascent_m * ef)}` : "–"} / {l.descent_m != null ? `−${Math.round(l.descent_m * ef)}` : "–"}</td>}
                {anyCad && <td className="num hide-sm">{l.cadence_spm ? Math.round(l.cadence_spm) : "–"}</td>}
                {anyPower && <td className="num hide-sm">{l.avg_power ? Math.round(l.avg_power) : "–"}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <span className="muted">Taken from the activity file Garmin sent, so they match Garmin Connect. A short last lap is the distance left over. Cadence is steps per minute.</span>
    </section>
  );
}
