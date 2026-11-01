import { Activity } from "../api";
import { km, lastDays, localDay, sportGroup, SportGroup } from "../lib/format";

const GROUPS: SportGroup[] = ["Running", "Cycling", "Other"];
const COLORS: Record<SportGroup, string> = {
  Running: "var(--run)",
  Cycling: "var(--ride)",
  Other: "var(--other)",
};

export default function MileageChart({ activities, days = 14 }: { activities: Activity[]; days?: number }) {
  const labels = lastDays(days);
  const byDay = new Map<string, Record<SportGroup, number>>();
  for (const day of labels) byDay.set(day, { Running: 0, Cycling: 0, Other: 0 });
  for (const a of activities) {
    const bucket = byDay.get(localDay(a.start_time));
    if (bucket && a.distance_m) bucket[sportGroup(a.sport)] += a.distance_m / 1000;
  }
  const totals = labels.map((d) => GROUPS.reduce((n, g) => n + byDay.get(d)![g], 0));
  const rawMax = Math.max(5, ...totals);
  const step = rawMax <= 10 ? 5 : rawMax <= 40 ? 10 : rawMax <= 100 ? 20 : 50;
  const max = Math.ceil(rawMax / step) * step;
  const W = 960, H = 250, padL = 44, padB = 28, padT = 18;
  const bw = (W - padL) / days;

  return (
    <div>
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
                <title>{`${day} ${g}: ${byDay.get(day)![g].toFixed(1)} km`}</title>
              </rect>
            ) : null;
          });
          const d = new Date(day + "T00:00");
          return (
            <g key={day}>
              {parts}
              {(i % 2 === 1 || days <= 8) && (
                <text x={padL + i * bw + bw / 2} y={H - 8} textAnchor="middle" className="tick">
                  {d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                </text>
              )}
            </g>
          );
        })}
        <text x={padL - 6} y={10} textAnchor="end" className="tick">km</text>
      </svg>
      <div className="legend">
        {GROUPS.map((g) => (
          <span key={g}>
            <i style={{ background: COLORS[g] }} /> {g}
          </span>
        ))}
        <span className="muted">Total {km(totals.reduce((a, b) => a + b, 0) * 1000, 1)} km</span>
      </div>
    </div>
  );
}
