import { useState } from "react";

export interface Series { name: string; color: string; values: (number | null)[]; dashed?: boolean }

interface Props {
  title: string;
  unit: string;
  days: string[]; // YYYY-MM-DD, oldest first
  series: Series[];
  band?: { low: (number | null)[]; high: (number | null)[]; label: string };
  decimals?: number;
  note?: string;
}

function nice(min: number, max: number): [number, number] {
  const span = Math.max(max - min, 1);
  const step = span <= 10 ? 2 : span <= 30 ? 5 : span <= 100 ? 10 : 25;
  return [Math.floor(min / step) * step, Math.ceil(max / step) * step];
}

/** Line chart with gaps for missing days, optional shaded band, hover readout. */
export default function TrendChart({ title, unit, days, series, band, decimals = 0, note }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 640, H = 220, padL = 44, padR = 14, padT = 22, padB = 28;
  const all = series.flatMap((s) => s.values).concat(band ? band.low.concat(band.high) : []).filter((v): v is number => v != null);
  if (all.length === 0) {
    return (
      <section className="card wide">
        <h3 style={{ margin: 0 }}>{title}</h3>
        <p className="muted">No data for this period yet.</p>
      </section>
    );
  }
  const [lo, hi] = nice(Math.min(...all), Math.max(...all));
  const n = days.length;
  const x = (i: number) => padL + ((W - padL - padR) * i) / Math.max(1, n - 1);
  const y = (v: number) => padT + (H - padT - padB) * (1 - (v - lo) / (hi - lo));
  const path = (vals: (number | null)[]) => {
    let d = "", pen = false;
    vals.forEach((v, i) => {
      if (v == null) { pen = false; return; }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)} `;
      pen = true;
    });
    return d;
  };
  const bandPath = () => {
    if (!band) return "";
    const idx = days.map((_, i) => i).filter((i) => band.low[i] != null && band.high[i] != null);
    if (idx.length < 2) return "";
    return idx.map((i, k) => `${k ? "L" : "M"}${x(i)},${y(band.high[i]!)}`).join(" ")
      + " " + [...idx].reverse().map((i) => `L${x(i)},${y(band.low[i]!)}`).join(" ") + " Z";
  };
  const last = (s: Series) => { for (let i = s.values.length - 1; i >= 0; i--) if (s.values[i] != null) return i; return -1; };
  const at = hover ?? Math.max(...series.map(last));
  const fmt = (v: number | null) => (v == null ? "–" : v.toFixed(decimals));
  const label = (i: number) => new Date(days[i] + "T00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" });
  const ticks = Array.from({ length: 5 }, (_, k) => lo + ((hi - lo) * k) / 4);

  return (
    <section className="card wide">
      <div className="row between" style={{ alignItems: "baseline" }}>
        <h3 style={{ margin: 0 }}>{title}</h3>
        <span className="muted">
          {at >= 0 && label(at)}{" "}
          {series.map((s) => (
            <span key={s.name} style={{ color: s.color, marginLeft: 8 }}>
              <strong>{fmt(s.values[at] ?? null)}</strong> {series.length > 1 ? s.name : unit}
            </span>
          ))}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label={title}
        onMouseMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          const px = ((e.clientX - r.left) / r.width) * W;
          setHover(Math.min(n - 1, Math.max(0, Math.round(((px - padL) / (W - padL - padR)) * (n - 1)))));
        }}
        onMouseLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} className="grid" />
            <text x={padL - 6} y={y(t) + 5} textAnchor="end" className="tick big">{Math.round(t * 10) / 10}</text>
          </g>
        ))}
        <text x={2} y={11} className="tick big">{unit}</text>
        {days.map((d, i) => (i % Math.ceil(n / 5) === 0 || i === n - 1) && (
          <text key={d} x={x(i)} y={H - 8} textAnchor={i === n - 1 ? "end" : "middle"} className="tick big">{label(i)}</text>
        ))}
        {band && <path d={bandPath()} fill="#2da44e" opacity={0.16}><title>{band.label}</title></path>}
        {series.map((s) => (
          <g key={s.name}>
            <path d={path(s.values)} fill="none" stroke={s.color} strokeWidth={2.2} strokeLinejoin="round"
              strokeLinecap="round" strokeDasharray={s.dashed ? "5 4" : undefined} />
            {n <= 45 && s.values.map((v, i) => v != null && <circle key={i} cx={x(i)} cy={y(v)} r={2.4} fill={s.color} />)}
          </g>
        ))}
        {hover != null && <line x1={x(hover)} x2={x(hover)} y1={padT} y2={H - padB} stroke="currentColor" opacity={0.3} strokeDasharray="3 3" />}
      </svg>
      {(series.length > 1 || band) && (
        <div className="legend">
          {series.map((s) => <span key={s.name}><i style={{ background: s.color }} /> {s.name}</span>)}
          {band && <span><i style={{ background: "#2da44e", opacity: 0.4 }} /> {band.label}</span>}
        </div>
      )}
      {note && <span className="muted">{note}</span>}
    </section>
  );
}
