import { useMemo, useState } from "react";
import { Activity } from "../api";
import { lastDays, localDay } from "../lib/format";
import { useWidth } from "../lib/useWidth";

const SPAN = 28; // days shown
const WINDOW = 7; // rolling window

interface Pt { day: string; value: number }

function niceMax(v: number): number {
  if (v <= 0) return 5;
  const step = v <= 10 ? 2 : v <= 30 ? 5 : v <= 100 ? 10 : v <= 250 ? 25 : 50;
  return Math.max(step, Math.ceil(v / step) * step);
}

function LineChart({ title, unit, points, color, sub }: {
  title: string; unit: string; points: Pt[]; color: string; sub: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const [box, W] = useWidth(640);
  const H = 230, padL = 44, padR = 14, padT = 22, padB = 28;
  const max = niceMax(Math.max(...points.map((p) => p.value)) * 1.05);
  const x = (i: number) => padL + ((W - padL - padR) * i) / (points.length - 1);
  const y = (v: number) => padT + (H - padT - padB) * (1 - v / max);
  const line = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ");
  const area = `${line} L${x(points.length - 1)},${y(0)} L${x(0)},${y(0)} Z`;
  const shown = hover ?? points.length - 1;
  const cur = points[shown];
  const weekAgo = points[shown - 7];
  const delta = weekAgo ? cur.value - weekAgo.value : null;
  const fmt = (v: number) => v.toFixed(1);

  return (
    <section className="card wide">
      <div className="row between" style={{ alignItems: "baseline" }}>
        <h3 style={{ margin: 0 }}>{title}</h3>
        <span>
          <strong>{fmt(cur.value)} {unit}</strong>{" "}
          <span className="muted">
            {new Date(cur.day + "T00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" })}
            {delta != null && ` · ${delta >= 0 ? "+" : ""}${fmt(delta)} vs 7 days earlier`}
          </span>
        </span>
      </div>
      <div ref={box}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="chart"
        style={{ touchAction: "pan-y" }}
        role="img"
        aria-label={title}
        onPointerMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          const px = ((e.clientX - r.left) / r.width) * W;
          setHover(Math.min(points.length - 1, Math.max(0, Math.round(((px - padL) / (W - padL - padR)) * (points.length - 1)))));
        }}
        onPointerDown={(e) => e.currentTarget.dispatchEvent(new PointerEvent("pointermove", { clientX: e.clientX, clientY: e.clientY, bubbles: true }))}
        onPointerLeave={(e) => e.pointerType === "mouse" && setHover(null)}
      >
        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <g key={f}>
            <line x1={padL} x2={W - padR} y1={y(max * f)} y2={y(max * f)} className="grid" />
            <text x={padL - 6} y={y(max * f) + 4} textAnchor="end" className="tick big">{Math.round(max * f * 10) / 10}</text>
          </g>
        ))}
        {points.map((p, i) =>
          i % 7 === 0 || i === points.length - 1 ? (
            <text key={p.day} x={x(i)} y={H - 8} textAnchor={i === points.length - 1 ? "end" : "middle"} className="tick big">
              {new Date(p.day + "T00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" })}
            </text>
          ) : null,
        )}
        <path d={area} fill={color} opacity={0.12} />
        <path d={line} fill="none" stroke={color} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
        <text x={2} y={11} className="tick big">{unit}</text>
        <line x1={x(shown)} x2={x(shown)} y1={padT} y2={H - padB} stroke={color} strokeDasharray="3 3" opacity={hover == null ? 0 : 0.6} />
        <circle cx={x(shown)} cy={y(cur.value)} r={4.5} fill={color} stroke="var(--card)" strokeWidth={2} />
      </svg>
      </div>
      <span className="muted">{sub}</span>
    </section>
  );
}

export default function RollingCharts({ activities, noun }: { activities: Activity[]; noun: string }) {
  const { avg, longest } = useMemo(() => {
    const days = lastDays(SPAN + WINDOW - 1);
    const total = new Map(days.map((d) => [d, 0]));
    const best = new Map(days.map((d) => [d, 0]));
    for (const a of activities) {
      const d = localDay(a.start_time);
      if (!total.has(d) || !a.distance_m) continue;
      total.set(d, total.get(d)! + a.distance_m / 1000);
      best.set(d, Math.max(best.get(d)!, a.distance_m / 1000));
    }
    const avg: Pt[] = [], longest: Pt[] = [];
    for (let i = WINDOW - 1; i < days.length; i++) {
      const win = days.slice(i - WINDOW + 1, i + 1);
      avg.push({ day: days[i], value: win.reduce((n, d) => n + total.get(d)!, 0) });
      // Today is unfinished: until there is an activity today, look back 8 days (today plus the
      // 7 before it) so a long run exactly a week ago does not drop out of the line mid-week.
      const isToday = i === days.length - 1;
      const reach = isToday && best.get(days[i])! === 0 ? WINDOW : WINDOW - 1;
      const wide = days.slice(Math.max(0, i - reach), i + 1);
      longest.push({ day: days[i], value: Math.max(...wide.map((d) => best.get(d)!)) });
    }
    return { avg, longest };
  }, [activities]);

  return (
    <div className="grid2">
      <LineChart
        title="Weekly mileage (rolling 7 days)"
        unit="km/week"
        points={avg}
        color="var(--run)"
        sub="Each point is the total distance of the 7 days ending that day (km per week), so you can see how mileage builds."
      />
      <LineChart
        title={`Rolling 7-day longest ${noun}`}
        unit="km"
        points={longest}
        color="var(--ride)"
        sub={`Each point is the longest single ${noun} in the 7 days ending that day. Until you have a ${noun} today, today looks back 8 days so last week\u2019s long ${noun} does not vanish early.`}
      />
    </div>
  );
}
