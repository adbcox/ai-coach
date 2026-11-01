import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, ActivityList, api } from "../api";
import { duration, km, sportGroup, SportGroup } from "../lib/format";

const PAGE = 100;
const FILTERS: ("All" | SportGroup)[] = ["All", "Running", "Cycling", "Hiking", "Other"];

export default function Activities({ goSettings, open }: { goSettings: () => void; open: (id: number) => void }) {
  const [items, setItems] = useState<Activity[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("All");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadMore = useCallback(() => {
    setLoading(true);
    api<ActivityList>(`/activities?limit=${PAGE}&offset=${items.length}`)
      .then((d) => { setItems((prev) => [...prev, ...d.items]); setTotal(d.total); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [items.length]);
  useEffect(() => { loadMore(); /* first page */ }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const shown = useMemo(() => items.filter((a) => filter === "All" || sportGroup(a.sport) === filter), [items, filter]);

  if (error) return <p className="error">{error}</p>;
  if (total === null) return <p className="muted">Loading…</p>;
  if (total === 0)
    return (
      <section className="card wide">
        <h2>No activities yet</h2>
        <p>Add your Garmin key in <button className="link" onClick={goSettings}>Settings</button>, then sync.</p>
      </section>
    );

  return (
    <section className="card wide">
      <div className="row between">
        <h2 style={{ margin: 0 }}>Activities ({total})</h2>
        <div className="chips">
          {FILTERS.map((f) => (
            <button key={f} className={f === filter ? "active" : ""} onClick={() => setFilter(f)}>{f}</button>
          ))}
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th>Date</th><th>Sport</th><th>Name</th><th className="num">km</th>
            <th className="num">Time</th><th className="num">Avg HR</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((a) => (
            <tr key={a.id} className="click" onClick={() => open(a.id)}>
              <td>{new Date(a.start_time).toLocaleDateString()}</td>
              <td>{(a.sport ?? "–").replace(/_/g, " ")}</td>
              <td>{a.name ?? "–"}</td>
              <td className="num">{a.distance_m ? km(a.distance_m) : "–"}</td>
              <td className="num">{duration(a.duration_s)}</td>
              <td className="num">{a.avg_hr ? Math.round(a.avg_hr) : "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {shown.length === 0 && <p className="muted">No {filter.toLowerCase()} activities in the {items.length} loaded so far.</p>}
      {items.length < total && (
        <div className="row">
          <button onClick={loadMore} disabled={loading}>{loading ? "Loading…" : `Show more (${items.length} of ${total})`}</button>
        </div>
      )}
    </section>
  );
}
