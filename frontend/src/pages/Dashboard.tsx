import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, ActivityList, api } from "../api";
import MileageChart from "../components/MileageChart";
import RollingCharts from "../components/RollingCharts";
import { duration, km, lastDays, localDay, sportGroup, SportGroup, unitDist } from "../lib/format";
import { distFactor } from "../lib/units";
import { ago, useSync } from "../lib/useSync";

const FILTERS: ("All" | SportGroup)[] = ["All", "Running", "Cycling", "Hiking", "Other"];

export default function Dashboard({ open, goSettings }: { open: (id: number) => void; goSettings: () => void }) {
  const [items, setItems] = useState<Activity[] | null>(null);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("Running");
  const [error, setError] = useState("");

  const loadActivities = useCallback(() => {
    const since = new Date(Date.now() - 36 * 86400000).toISOString();
    api<ActivityList>(`/activities?since=${encodeURIComponent(since)}&limit=500`)
      .then((d) => setItems(d.items))
      .catch((e) => setError(e.message));
  }, []);
  useEffect(loadActivities, [loadActivities]);
  // start on the sport chosen in Settings (clicking a chip only changes the view for now)
  useEffect(() => {
    api<{ default_sport: string }>("/preferences")
      .then((p) => (FILTERS as string[]).includes(p.default_sport) && setFilter(p.default_sport as (typeof FILTERS)[number]))
      .catch(() => undefined);
  }, []);
  const sync = useSync(loadActivities);

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
      <div className="row between syncbar">
        <div>
          {sync.status?.configured ? (
            <>
              <button className="primary" onClick={() => sync.start("quick")} disabled={sync.running}>
                {sync.running ? "Syncing…" : "Sync"}
              </button>{" "}
              <span className="muted">
                {sync.running
                  ? sync.status.last_sync?.message ?? ""
                  : `Last synced ${ago(sync.status.last_sync?.finished_at)}${
                      sync.status.last_sync?.status === "error" ? " (failed: " + sync.status.last_sync.message + ")" : ""
                    }`}
              </span>
              {sync.error && <span className="error"> {sync.error}</span>}
            </>
          ) : (
            sync.status && (
              <span className="muted">
                No data source connected. <button className="link" onClick={goSettings}>Add your Garmin key</button>
              </span>
            )
          )}
        </div>
      </div>

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
        <Tile label="Last 7 days" value={`${km(stats.recent.dist, 1)} ${unitDist()}`} sub={`${stats.recent.count} activities · ${duration(stats.recent.time)}`} />
        <Tile label="Previous 7 days" value={`${km(stats.prior.dist, 1)} ${unitDist()}`} sub={`${stats.prior.count} activities · ${duration(stats.prior.time)}`} />
        <Tile
          label="Change"
          value={`${delta >= 0 ? "+" : ""}${((delta / 1000) * distFactor()).toFixed(1)} ${unitDist()}`}
          sub={stats.prior.dist > 0 ? `${Math.round((delta / stats.prior.dist) * 100)}% vs previous week` : "no previous week"}
        />
      </div>

      <section className="card wide">
        <h3 style={{ margin: 0 }}>Daily distance</h3>
        <MileageChart activities={view} />
      </section>

      <div className="row between">
        <h2 style={{ margin: 0 }}>Last 4 weeks</h2>
      </div>
      <RollingCharts activities={view} noun={filter === "Running" ? "run" : filter === "Cycling" ? "ride" : "activity"} />

      <section className="card wide">
        <h3 style={{ margin: 0 }}>Latest activities</h3>
        {latest.length === 0 ? (
          <p className="muted">
            Nothing in the last 5 weeks{filter !== "All" ? ` for ${filter}` : ""}. Older activities are in the Activities tab; check{" "}
            <button className="link" onClick={goSettings}>Settings</button> if a sync is still running.
          </p>
        ) : (
          <table className="tbl-latest">
            <tbody>
              {latest.map((a) => (
                <tr key={a.id} className="click" onClick={() => open(a.id)}>
                  <td className="nowrap">{new Date(a.start_time).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</td>
                  <td className="ellip">{a.name ?? a.sport ?? "Activity"}</td>
                  <td className="num">{km(a.distance_m)} {unitDist()}</td>
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
