import { useEffect, useMemo, useState } from "react";
import { Activity, ActivityList, api } from "../api";
import MileageChart from "../components/MileageChart";
import { duration, km, lastDays, localDay, sportGroup, SportGroup } from "../lib/format";

const FILTERS: ("All" | SportGroup)[] = ["All", "Running", "Cycling", "Other"];

export default function Dashboard({ open, goSettings }: { open: (id: number) => void; goSettings: () => void }) {
  const [items, setItems] = useState<Activity[] | null>(null);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("All");
  const [error, setError] = useState("");

  useEffect(() => {
    const since = new Date(Date.now() - 16 * 86400000).toISOString();
    api<ActivityList>(`/activities?since=${encodeURIComponent(since)}&limit=500`)
      .then((d) => setItems(d.items))
      .catch((e) => setError(e.message));
  }, []);

  const view = useMemo(
    () => (items ?? []).filter((a) => filter === "All" || sportGroup(a.sport) === filter),
    [items, filter],
  );

  const stats = useMemo(() => {
    const days = lastDays(14);
    const recent = new Set(days.slice(7));
    const prior = new Set(days.slice(0, 7));
    const sum = (set: Set<string>) => {
      const rows = view.filter((a) => set.has(localDay(a.start_time)));
      return {
        dist: rows.reduce((n, a) => n + (a.distance_m ?? 0), 0),
        time: rows.reduce((n, a) => n + (a.duration_s ?? 0), 0),
        count: rows.length,
      };
    };
    return { recent: sum(recent), prior: sum(prior) };
  }, [view]);

  if (error) return <p className="error">{error}</p>;
  if (!items) return <p className="muted">Loading…</p>;

  const delta = stats.recent.dist - stats.prior.dist;
  const latest = view.slice(0, 5);

  return (
    <div className="stack">
      <div className="row between">
        <h2 style={{ margin: 0 }}>Last 14 days</h2>
        <div className="chips">
          {FILTERS.map((f) => (
            <button key={f} className={f === filter ? "active" : ""} onClick={() => setFilter(f)}>
              {f}
            </button>
          ))}
        </div>
      </div>

      <div className="tiles">
        <Tile label="Last 7 days" value={`${km(stats.recent.dist, 1)} km`} sub={`${stats.recent.count} activities · ${duration(stats.recent.time)}`} />
        <Tile label="Previous 7 days" value={`${km(stats.prior.dist, 1)} km`} sub={`${stats.prior.count} activities · ${duration(stats.prior.time)}`} />
        <Tile
          label="Change"
          value={`${delta >= 0 ? "+" : ""}${(delta / 1000).toFixed(1)} km`}
          sub={stats.prior.dist > 0 ? `${Math.round((delta / stats.prior.dist) * 100)}% vs previous week` : "no previous week"}
        />
      </div>

      <section className="card wide">
        <h3 style={{ margin: 0 }}>Daily distance</h3>
        <MileageChart activities={view} />
      </section>

      <section className="card wide">
        <h3 style={{ margin: 0 }}>Latest activities</h3>
        {latest.length === 0 ? (
          <p className="muted">
            Nothing in the last 16 days{filter !== "All" ? ` for ${filter}` : ""}. Older activities are in the Activities tab; check{" "}
            <button className="link" onClick={goSettings}>Settings</button> if a sync is still running.
          </p>
        ) : (
          <table>
            <tbody>
              {latest.map((a) => (
                <tr key={a.id} className="click" onClick={() => open(a.id)}>
                  <td>{new Date(a.start_time).toLocaleDateString()}</td>
                  <td>{a.name ?? a.sport ?? "Activity"}</td>
                  <td className="num">{km(a.distance_m)} km</td>
                  <td className="num">{duration(a.duration_s)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

function Tile({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="card tile">
      <span className="muted">{label}</span>
      <strong>{value}</strong>
      <span className="muted">{sub}</span>
    </div>
  );
}
