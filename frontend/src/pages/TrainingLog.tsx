import { useCallback, useEffect, useMemo, useState } from "react";
import { api, Activity, ActivityList, LoadHistory } from "../api";
import { duration, km, unitDist } from "../lib/format";

const FAMILIES = [
  { k: "run_road", label: "Run", c: "#1f6feb" },
  { k: "bike_road", label: "Ride", c: "#e8590c" },
  { k: "hike", label: "Hike", c: "#2da44e" },
  { k: "other", label: "Other", c: "#98a2b3" },
] as const;
const WEEKS = 12;

type FamDay = { day: string; family: string; tss: number };
type WeekRow = {
  weekStart: string;         // Monday iso
  label: string;              // "Oct 20 — Oct 26"
  activities: Activity[];
  familyTss: Record<string, number>;
  totalTss: number;
  longestMin: number;
  ctlEnd: number | null;
  ctlRamp: number | null;     // ctl change across the week
};

function isoMonday(d: Date): string {
  const copy = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const day = copy.getUTCDay();                  // 0..6, 0=Sun
  const diff = (day === 0 ? -6 : 1) - day;
  copy.setUTCDate(copy.getUTCDate() + diff);
  return copy.toISOString().slice(0, 10);
}
function addDays(iso: string, n: number): string {
  const d = new Date(iso + "T12:00:00Z");
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
function pretty(iso: string): string {
  const d = new Date(iso + "T12:00:00Z");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function TrainingLog({ open }: { open: (id: number) => void }) {
  const [load, setLoad] = useState<LoadHistory | null>(null);
  const [famDays, setFamDays] = useState<FamDay[]>([]);
  const [acts, setActs] = useState<Activity[]>([]);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const days = WEEKS * 7 + 7;
      const L = await api<LoadHistory>(`/load/history?days=${days}`);
      setLoad(L);
      const famRows: FamDay[] = [];
      await Promise.all(FAMILIES.map(async (f) => {
        try {
          const h = await api<LoadHistory>(`/load/history?days=${days}&family=${f.k}`);
          for (const d of h.days) {
            if ((d.tss ?? 0) > 0) famRows.push({ day: d.day, family: f.k, tss: d.tss as number });
          }
        } catch { /* missing family is fine */ }
      }));
      setFamDays(famRows);
      const a = await api<ActivityList>(`/activities?limit=200`);
      setActs(a.items);
    } catch (e) { setError((e as Error).message); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const weeks = useMemo<WeekRow[]>(() => {
    if (!load) return [];
    const now = new Date();
    const thisMonday = isoMonday(now);
    const rows: WeekRow[] = [];
    const famByDay: Record<string, FamDay[]> = {};
    for (const r of famDays) (famByDay[r.day] ??= []).push(r);
    const ctlByDay: Record<string, number | null> = {};
    for (const d of load.days) ctlByDay[d.day] = d.ctl ?? null;

    for (let w = 0; w < WEEKS; w++) {
      const weekStart = addDays(thisMonday, -7 * w);
      const weekEnd = addDays(weekStart, 6);
      const familyTss: Record<string, number> = {};
      let totalTss = 0;
      const dayActs = acts.filter((a) => {
        const day = a.start_time.slice(0, 10);
        return day >= weekStart && day <= weekEnd;
      });
      for (let i = 0; i < 7; i++) {
        const day = addDays(weekStart, i);
        for (const r of famByDay[day] ?? []) {
          familyTss[r.family] = (familyTss[r.family] ?? 0) + r.tss;
          totalTss += r.tss;
        }
      }
      const longestMin = Math.max(0, ...dayActs.map((a) => (a.duration_s ?? 0) / 60));
      const ctlEnd = ctlByDay[weekEnd] ?? ctlByDay[addDays(weekEnd, -1)] ?? null;
      const ctlPrev = ctlByDay[addDays(weekStart, -1)] ?? null;
      const ctlRamp = ctlEnd != null && ctlPrev != null ? Number((ctlEnd - ctlPrev).toFixed(1)) : null;
      rows.push({
        weekStart,
        label: `${pretty(weekStart)} — ${pretty(weekEnd)}`,
        activities: dayActs.sort((a, b) => a.start_time.localeCompare(b.start_time)),
        familyTss,
        totalTss,
        longestMin,
        ctlEnd,
        ctlRamp,
      });
    }
    return rows;
  }, [load, famDays, acts]);

  const peakBubble = useMemo(() => {
    let p = 1;
    for (const w of weeks) for (const a of w.activities) {
      const key = a.id;
      // use the activity's duration as a proxy; scaled by TSS proportion if available via family share
      const mins = (a.duration_s ?? 0) / 60;
      if (mins > p) p = mins;
      void key;
    }
    return Math.max(60, p);
  }, [weeks]);

  if (error) return <p className="error">{error}</p>;
  if (!load) return <p className="muted">Loading training log…</p>;

  return (
    <div className="log">
      <section className="card">
        <div className="row between">
          <h2 className="dash-h">Training log · last {WEEKS} weeks</h2>
          <div className="family-legend">
            {FAMILIES.map((f) => (
              <span key={f.k} className="fl-item"><i style={{ background: f.c }} />{f.label}</span>
            ))}
          </div>
        </div>
        <div className="log-weeks">
          {weeks.map((w) => (
            <div key={w.weekStart} className="log-week">
              <div className="log-wlabel">
                <strong>{w.label}</strong>
                <span className="muted">{w.activities.length} activities</span>
              </div>
              <div className="log-days">
                {Array.from({ length: 7 }, (_, i) => {
                  const day = addDays(w.weekStart, i);
                  const dayActs = w.activities.filter((a) => a.start_time.slice(0, 10) === day);
                  return (
                    <div key={i} className="log-day">
                      <span className="log-ddate">{pretty(day).split(" ")[1]}</span>
                      <div className="log-bubbles">
                        {dayActs.map((a) => {
                          const fam = familyOf(a.sport);
                          const col = FAMILIES.find((f) => f.k === fam)?.c ?? "#98a2b3";
                          const mins = (a.duration_s ?? 0) / 60;
                          const size = 14 + Math.round((mins / peakBubble) * 34);
                          return (
                            <button key={a.id} className="log-bubble"
                              onClick={() => open(a.id)}
                              style={{ width: size, height: size, background: col }}
                              title={`${a.name ?? a.sport ?? "activity"} · ${km(a.distance_m)} ${unitDist()} · ${duration(a.duration_s)}`}
                            />
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="log-stats">
                <Stat k="Weekly TSS" v={Math.round(w.totalTss).toString()} />
                <Stat k="Ramp (CTL)" v={w.ctlRamp == null ? "—" : `${w.ctlRamp >= 0 ? "+" : ""}${w.ctlRamp}`} />
                <Stat k="Longest" v={w.longestMin > 0 ? `${Math.round(w.longestMin)} min` : "—"} />
                <Stat k="CTL" v={w.ctlEnd == null ? "—" : Math.round(w.ctlEnd).toString()} />
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function Stat({ k, v }: { k: string; v: string }) {
  return <div className="log-stat"><span className="muted">{k}</span><strong>{v}</strong></div>;
}

function familyOf(sport: string | null): string {
  if (!sport) return "other";
  const s = sport.toLowerCase();
  if (s.includes("run")) return "run_road";
  if (s.includes("cycl") || s.includes("bike") || s.includes("ride")) return "bike_road";
  if (s.includes("hik") || s.includes("walk")) return "hike";
  return "other";
}
