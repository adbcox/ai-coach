import { Activity } from "../api";
import { useWidth } from "../lib/useWidth";
import { lastDays, localDay, sportGroup, SportGroup, unitDist } from "../lib/format";
import { distFactor, useUnits } from "../lib/units";

const GROUPS: SportGroup[] = ["Running", "Cycling", "Hiking", "Other"];
const COLORS: Record<SportGroup, string> = {
  Running: "var(--run)",
  Cycling: "var(--ride)",
  Hiking: "var(--hike)",
  Other: "var(--other)",
};

export default function MileageChart({ activities, days = 14 }: { activities: Activity[]; days?: number }) {
  const [box, W] = useWidth(640);
  useUnits();
  const unit = unitDist();
  const labels = lastDays(days);
  const byDay = new Map<string, Record<SportGroup, number>>();
  for (const day of labels) byDay.set(day, { Running: 0, Cycling: 0, Hiking: 0, Other: 0 });
  for (const a of activities) {
    const bucket = byDay.get(localDay(a.start_time));
    if (bucket && a.distance_m) bucket[sportGroup(a.sport)] += (a.distance_m / 1000) * distFactor();
  }
  const totals = labels.map((d) => GROUPS.reduce((n, g) => n + byDay.get(d)![g], 0));
  const rawMax = Math.max(5, ...totals);
  const step = rawMax <= 10 ? 5 : rawMax <= 40 ? 10 : rawMax <= 100 ? 20 : 50;
  const max = Math.ceil(rawMax / step) * step;
  const H = 240, padL = 44, padB = 28, padT = 18;
  const labelEvery = W < 480 ? 3 : 2;
  const bw = (W - padL) / days;

  return (
    <div>
      <div ref={box}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Daily distance, last ${days} days`} className="chart">
        {Array.from({ length: max / step + 1 }, (_, i) => (i * step) / max).map((f) => {
          const y = padT + (H - padT - padB) * (1 - f);
          return (
            <g key={f}>
              <line x1={padL} x2={W} y1={y} y2={y} className="grid" />
              <text x={padL - 6} y={y + 4} textAnchor="end" className="tick">
                {Math.round(max * f)}
              </text>
            </g>
          );
        })}
        {labels.map((day, i) => {
          let yBase = H - padB;
          const parts = GROUPS.map((g) => {
            const h = ((H - padT - padB) * byDay.get(day)![g]) / max;
            yBase -= h;
            return h > 0 ? (
              <rect key={g} x={padL + i * bw + 3} y={yBase} width={bw - 6} height={h} rx={2} fill={COLORS[g]}>
                <title>{`${day} ${g}: ${byDay.get(day)![g].toFixed(1)} ${unit}`}</title>
              </rect>
            ) : null;
          });
          const d = new Date(day + "T00:00");
          return (
            <g key={day}>
              {parts}
              {((days - 1 - i) % labelEvery === 0 || days <= 8) && (
                <text x={padL + i * bw + bw / 2} y={H - 8} textAnchor="middle" className="tick">
                  {d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                </text>
              )}
            </g>
          );
        })}
        <text x={padL - 6} y={10} textAnchor="end" className="tick">{unit}</text>
      </svg>
      </div>
      <div className="legend">
        {GROUPS.map((g) => (
          <span key={g}>
            <i style={{ background: COLORS[g] }} /> {g}
          </span>
        ))}
        <span className="muted">Total {totals.reduce((a, b) => a + b, 0).toFixed(1)} {unit}</span>
      </div>
    </div>
  );
}
