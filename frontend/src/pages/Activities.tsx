import { useEffect, useState } from "react";
import { Activity, ActivityList, api } from "../api";

const km = (m: number | null) => (m == null ? "–" : (m / 1000).toFixed(2));
const dur = (s: number | null) => {
  if (s == null) return "–";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.round(s % 60);
  return `${h ? h + ":" : ""}${String(m).padStart(h ? 2 : 1, "0")}:${String(sec).padStart(2, "0")}`;
};

export default function Activities({ goSettings }: { goSettings: () => void }) {
  const [data, setData] = useState<ActivityList | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<ActivityList>("/activities?limit=100").then(setData).catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Loading…</p>;
  if (data.total === 0)
    return (
      <section className="card wide">
        <h2>No activities yet</h2>
        <p>
          Add your Garmin key in <button className="link" onClick={goSettings}>Settings</button>, then sync.
        </p>
      </section>
    );

  return (
    <section className="card wide">
      <h2>Activities ({data.total})</h2>
      <table>
        <thead>
          <tr>
            <th>Date</th><th>Sport</th><th>Name</th><th className="num">km</th>
            <th className="num">Time</th><th className="num">Avg HR</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((a: Activity) => (
            <tr key={a.id}>
              <td>{new Date(a.start_time).toLocaleDateString()}</td>
              <td>{a.sport ?? "–"}</td>
              <td>{a.name ?? "–"}</td>
              <td className="num">{km(a.distance_m)}</td>
              <td className="num">{dur(a.duration_s)}</td>
              <td className="num">{a.avg_hr ? Math.round(a.avg_hr) : "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
