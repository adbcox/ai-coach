import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import TrendChart from "../components/TrendChart";
import { hm, lastDays } from "../lib/format";

interface Day {
  date: string;
  sleep_score?: number; sleep_h?: number; deep_h?: number; rem_h?: number; light_h?: number; awake_h?: number;
  hrv?: number; hrv_weekly?: number; hrv_status?: string; hrv_low?: number; hrv_high?: number;
  resting_hr?: number; bb_max?: number; bb_min?: number; bb_charged?: number; bb_drained?: number;
  stress_avg?: number; steps?: number; intensity_min?: number; respiration?: number; spo2?: number;
}

const RANGES = [30, 90, 180, 365];

export default function Recovery({ goSettings }: { goSettings: () => void }) {
  const [range, setRange] = useState(90);
  const [data, setData] = useState<Day[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setData(null);
    api<{ days: Day[] }>(`/recovery?days=${range}`).then((d) => setData(d.days)).catch((e) => setError(e.message));
  }, [range]);

  const days = useMemo(() => lastDays(range), [range]);
  const col = (key: keyof Day) => {
    const by = new Map((data ?? []).map((d) => [d.date, d]));
    return days.map((dt) => { const v = by.get(dt)?.[key]; return typeof v === "number" ? v : null; });
  };
  const latest = useMemo(() => [...(data ?? [])].reverse(), [data]);
  const newest = (key: keyof Day) => latest.find((d) => typeof d[key] === "number")?.[key] as number | undefined;

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Loading…</p>;
  if (data.length === 0)
    return (
      <section className="card wide">
        <h2>No recovery data yet</h2>
        <p>
          Sleep, HRV, resting heart rate and Body Battery arrive with the health-data sync. Start it in{" "}
          <button className="link" onClick={goSettings}>Settings</button> (Re-sync all history) and give it time.
        </p>
      </section>
    );

  return (
    <div className="stack">
      <div className="row between">
        <h2 style={{ margin: 0 }}>Recovery</h2>
        <div className="chips">
          {RANGES.map((r) => (
            <button key={r} className={r === range ? "active" : ""} onClick={() => setRange(r)}>
              {r < 365 ? `${r} days` : "1 year"}
            </button>
          ))}
        </div>
      </div>

      <div className="tiles">
        <Tile label="Sleep score" value={newest("sleep_score")} unit="" />
        <Tile label="Sleep (h:mm)" value={newest("sleep_h")} unit="" asHours />
        <Tile label="HRV (last night)" value={newest("hrv")} unit=" ms" />
        <Tile label="Resting HR" value={newest("resting_hr")} unit=" bpm" />
        <Tile label="Body Battery (max)" value={newest("bb_max")} unit="" />
      </div>

      <div className="grid2">
        <TrendChart title="Sleep score" unit="score" days={days} decimals={0}
          series={[{ name: "Sleep score", color: "#8250df", values: col("sleep_score") }]} />
        <TrendChart title="Sleep duration" unit="h:mm" days={days} hours
          series={[{ name: "Total", color: "#1f6feb", values: col("sleep_h") },
                   { name: "Deep", color: "#0b3d91", values: col("deep_h"), dashed: true },
                   { name: "REM", color: "#e8590c", values: col("rem_h"), dashed: true }]} />
        <TrendChart title="Heart-rate variability" unit="ms" days={days}
          series={[{ name: "Last night", color: "#1f6feb", values: col("hrv") },
                   { name: "7-day avg", color: "#cf222e", values: col("hrv_weekly"), dashed: true }]}
          band={{ low: col("hrv_low"), high: col("hrv_high"), label: "Your balanced range" }}
          note="The green band is Garmin's personal balanced range for your HRV." />
        <TrendChart title="Resting heart rate" unit="bpm" days={days}
          series={[{ name: "Resting HR", color: "#cf222e", values: col("resting_hr") }]} />
        <TrendChart title="Body Battery" unit="0–100" days={days}
          series={[{ name: "Highest", color: "#2da44e", values: col("bb_max") },
                   { name: "Lowest", color: "#8b949e", values: col("bb_min"), dashed: true }]} />
        <TrendChart title="Average stress" unit="0–100" days={days}
          series={[{ name: "Stress", color: "#e8590c", values: col("stress_avg") }]}
          note="Garmin's daily average stress level (lower is calmer)." />
      </div>
    </div>
  );
}

function Tile({ label, value, unit, digits = 0, asHours = false }: { label: string; value?: number; unit: string; digits?: number; asHours?: boolean }) {
  return (
    <div className="card tile">
      <span className="muted">{label}</span>
      <strong>{value == null ? "–" : asHours ? hm(value) : `${value.toFixed(digits)}${unit}`}</strong>
    </div>
  );
}
