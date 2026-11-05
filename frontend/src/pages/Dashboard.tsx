import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity, ActivityList, CoachReply, LoadDay, LoadHistory,
  Readiness, SuggestedWorkout, api,
} from "../api";
import LoadBars, { FamDay } from "../components/LoadBars";
import PmcChart from "../components/PmcChart";
import PmcTiles from "../components/PmcTiles";
import ReadinessChip from "../components/ReadinessChip";
import SuggestedWorkoutCard from "../components/SuggestedWorkoutCard";
import { duration, km, unitDist } from "../lib/format";
import { ago, useSync } from "../lib/useSync";

const FAMILY_FILTERS: { key: string; label: string }[] = [
  { key: "all", label: "All" },
  { key: "run_road", label: "Run" },
  { key: "bike_road", label: "Ride" },
  { key: "hike", label: "Hike" },
  { key: "other", label: "Other" },
];
const RANGE_OPTS: { key: "90d" | "180d" | "1y" | "2y" | "5y"; label: string; days: number }[] = [
  { key: "90d", label: "90d", days: 90 },
  { key: "180d", label: "180d", days: 180 },
  { key: "1y", label: "1y", days: 365 },
  { key: "2y", label: "2y", days: 730 },
  { key: "5y", label: "5y", days: 1825 },
];

export default function Dashboard({ open, goSettings }: {
  open: (id: number) => void; goSettings: () => void;
}) {
  const [range, setRange] = useState<(typeof RANGE_OPTS)[number]["key"]>("180d");
  const rangeDays = RANGE_OPTS.find((r) => r.key === range)!.days;
  const [load, setLoad] = useState<LoadHistory | null>(null);
  const [famDays, setFamDays] = useState<FamDay[]>([]);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [suggest, setSuggest] = useState<SuggestedWorkout | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [recent, setRecent] = useState<Activity[]>([]);
  const [filter, setFilter] = useState<string>("all");
  const [error, setError] = useState("");

  const loadAll = useCallback(async () => {
    try {
      const L = await api<LoadHistory>(`/load/history?days=${rangeDays}`);
      setLoad(L);
      // Family bars: pull once per known family in parallel; stack on the date axis.
      const families = ["run_road", "bike_road", "hike", "other"];
      const famRows: FamDay[] = [];
      await Promise.all(families.map(async (fam) => {
        try {
          const famHist = await api<LoadHistory>(`/load/history?days=30&family=${fam}`);
          for (const d of famHist.days) {
            if ((d.tss ?? 0) > 0) famRows.push({ day: d.day, family: fam, tss: d.tss as number });
          }
        } catch { /* missing family is fine */ }
      }));
      setFamDays(famRows);

      api<Readiness>("/readiness/today").then(setReadiness).catch(() => undefined);
      api<SuggestedWorkout>("/suggest/today").then(setSuggest).catch(() => undefined);
      api<ActivityList>("/activities?limit=6").then((d) => setRecent(d.items)).catch(() => undefined);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [rangeDays]);

  useEffect(() => { loadAll(); }, [loadAll]);
  const sync = useSync(loadAll);

  const askCoach = useCallback(async () => {
    try {
      const r = await api<CoachReply>("/coach/daily", "POST");
      setNote(r.reply);
    } catch (e) {
      setNote(null);  // non-fatal; dashboard still works
    }
  }, []);

  // Fire once after load lands so the first-paint has real tiles before the LLM note comes in.
  useEffect(() => {
    if (load?.days.length && !note) askCoach();
  }, [load]); // eslint-disable-line react-hooks/exhaustive-deps

  const daysFiltered = useMemo(() => {
    if (!load) return [] as LoadDay[];
    if (filter === "all") return load.days;
    const famRows = famDays.filter((f) => f.family === filter);
    const famByDay: Record<string, number> = {};
    for (const r of famRows) famByDay[r.day] = (famByDay[r.day] ?? 0) + (r.tss || 0);
    return load.days.map((d) => ({ ...d, tss: famByDay[d.day] ?? 0 }));
  }, [load, famDays, filter]);

  const famDaysFiltered = useMemo(() => {
    if (filter === "all") return famDays;
    return famDays.filter((f) => f.family === filter);
  }, [famDays, filter]);

  const firstBuild = !load || load.days.length === 0;

  return (
    <div className="dash">
      <SyncBar sync={sync} goSettings={goSettings} />

      <div className="dash-top">
        <SuggestedWorkoutCard suggest={suggest} note={note} onFeedback={loadAll} />
        <ReadinessChip readiness={readiness} />
      </div>

      <section className="card dash-pmc">
        <div className="row between dash-pmc-head">
          <div>
            <h2 className="dash-h">Fitness &amp; Freshness</h2>
            <span className="muted">CTL · ATL · TSB · ACWR 0.8–1.3 band greyed</span>
          </div>
          <div className="chips">
            {RANGE_OPTS.map((o) => (
              <button key={o.key} className={range === o.key ? "active" : ""}
                onClick={() => setRange(o.key)}>{o.label}</button>
            ))}
          </div>
        </div>
        <PmcTiles days={load?.days ?? []} />
        {firstBuild ? (
          <HistoryBuilding sync={sync} />
        ) : (
          <>
            <PmcChart days={daysFiltered} height={320} />
            <LoadBars days={daysFiltered.slice(-30)} familyDays={famDaysFiltered} />
            <FamilyLegend />
          </>
        )}
      </section>

      <section className="card dash-recent">
        <div className="row between">
          <h2 className="dash-h">Recent activities</h2>
          <div className="chips">
            {FAMILY_FILTERS.map((f) => (
              <button key={f.key} className={f.key === filter ? "active" : ""}
                onClick={() => setFilter(f.key)}>{f.label}</button>
            ))}
          </div>
        </div>
        {recent.length === 0 ? (
          <p className="muted">No activities in view yet.</p>
        ) : (
          <table className="tbl-latest">
            <tbody>
              {recent.map((a) => (
                <tr key={a.id} className="click" onClick={() => open(a.id)}>
                  <td className="nowrap">{new Date(a.start_time).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</td>
                  <td className="ellip">{a.name ?? a.sport ?? "Activity"}</td>
                  <td className="num nowrap">{km(a.distance_m)} {unitDist()}</td>
                  <td className="num">{duration(a.duration_s)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {error && <p className="error">{error}</p>}
    </div>
  );
}

function SyncBar({ sync, goSettings }: { sync: ReturnType<typeof useSync>; goSettings: () => void }) {
  if (!sync.status) return <div className="syncbar" />;
  const s = sync.status;
  if (!s.configured) {
    return (
      <div className="syncbar">
        <span className="muted">
          No data source connected.{" "}
          <button className="link" onClick={goSettings}>Add your Garmin key</button>
        </span>
      </div>
    );
  }
  return (
    <div className="syncbar">
      <button className="primary small" onClick={() => sync.start("quick")} disabled={sync.running}>
        {sync.running ? "Syncing…" : "Sync now"}
      </button>
      <span className="muted">
        {sync.running
          ? (s.last_sync?.message ?? "Working on it…")
          : `Last synced ${ago(s.last_sync?.finished_at)}${s.last_sync?.status === "error" ? ` (${s.last_sync.message})` : ""}`}
      </span>
      {sync.error && <span className="error">{sync.error}</span>}
    </div>
  );
}

function HistoryBuilding({ sync }: { sync: ReturnType<typeof useSync> }) {
  return (
    <div className="dash-building">
      <div className="spinner" />
      <div>
        <strong>Building your history</strong>
        <p className="muted">
          The nightly import is still bringing older rides in. Numbers here fill out as the first
          long sync finishes; refresh when a sync lands.
        </p>
        {sync.status?.last_sync && (
          <p className="muted">
            Last sync: {sync.status.last_sync.status}
            {sync.status.last_sync.new_activities != null && ` · ${sync.status.last_sync.new_activities} new`}
          </p>
        )}
      </div>
    </div>
  );
}

function FamilyLegend() {
  const items = [
    { k: "run_road", l: "Run", c: "#1f6feb" },
    { k: "bike_road", l: "Ride", c: "#e8590c" },
    { k: "hike", l: "Hike", c: "#2da44e" },
    { k: "other", l: "Other", c: "#98a2b3" },
  ];
  return (
    <div className="family-legend">
      {items.map((x) => (
        <span key={x.k} className="fl-item">
          <i style={{ background: x.c }} />{x.l}
        </span>
      ))}
    </div>
  );
}
