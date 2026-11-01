import { useEffect, useRef } from "react";
import { distFactor, elevFactor, elevUnit, useUnits } from "../lib/units";
import { unitSpeed } from "../lib/format";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { SamplesData } from "../api";

export interface HrZone { zone: number; low: number; high: number }

// Strava-style zone colours: 1 grey, 2 blue, 3 green, 4 orange, 5 red
export const ZONE_COLORS = ["#8b949e", "#1f6feb", "#2da44e", "#e8590c", "#cf222e"];

interface Props {
  data: SamplesData;
  running: boolean;
  onHover: (index: number | null) => void;
  zones?: HrZone[];
}

function smooth(values: (number | null)[], window: number): (number | null)[] {
  const half = Math.floor(window / 2);
  return values.map((_, i) => {
    let sum = 0, n = 0;
    for (let j = Math.max(0, i - half); j <= Math.min(values.length - 1, i + half); j++) {
      const v = values[j];
      if (v != null) { sum += v; n++; }
    }
    return n ? sum / n : null;
  });
}

const has = (a: (number | null)[]) => a.some((v) => v != null && v !== 0);

export default function LinkedCharts({ data, running, onHover, zones = [] }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const units = useUnits();

  useEffect(() => {
    const root = host.current;
    if (!root) return;
    root.innerHTML = "";
    const useDist = data.dist.some((d) => d != null && d > 0);
    const x = useDist ? data.dist.map((d) => ((d ?? 0) / 1000) * distFactor()) : data.t.map((t) => t / 60);
    const xLabel = useDist ? units.distance : "min";
    const speed = smooth(data.speed, 7);

    interface Spec { title: string; values: (number | null)[]; stroke: string; invert?: boolean; bands?: boolean; fmt?: (v: number) => string }
    const specs: Spec[] = [];
    if (has(data.speed)) {
      if (running) {
        const paceMin = speed.map((s) => (s && s > 0.8 ? 1000 / s / 60 / distFactor() : null));
        specs.push({
          title: `Pace (min/${units.distance})`, values: paceMin, stroke: "#1f6feb", invert: true,
          fmt: (v) => `${Math.floor(v)}:${String(Math.round((v % 1) * 60)).padStart(2, "0")}`,
        });
      } else {
        specs.push({ title: `Speed (${unitSpeed()})`, values: speed.map((s) => (s == null ? null : s * 3.6 * distFactor())), stroke: "#1f6feb" });
      }
    }
    if (has(data.hr)) specs.push({ title: "Heart rate (bpm)", values: smooth(data.hr, 5), stroke: "#cf222e", bands: zones.length > 0 });
    if (has(data.alt)) specs.push({ title: `Elevation (${elevUnit()})`, values: data.alt.map((v) => (v == null ? null : v * elevFactor())), stroke: "#6e7781" });
    if (has(data.power)) specs.push({ title: "Power (W)", values: smooth(data.power, 7), stroke: "#8250df" });
    if (has(data.cadence)) specs.push({ title: "Cadence", values: smooth(data.cadence, 7), stroke: "#2da44e" });

    const plots: uPlot[] = [];
    const sync = uPlot.sync("run");
    const width = Math.max(300, root.clientWidth);
    specs.forEach((spec, idx) => {
      const wrap = document.createElement("div");
      wrap.className = "plot";
      const label = document.createElement("div");
      label.className = "plot-title";
      label.textContent = spec.title;
      root.appendChild(wrap);
      wrap.appendChild(label);
      const target = document.createElement("div");
      wrap.appendChild(target);
      if (spec.bands) {
        const legend = document.createElement("div");
        legend.className = "zlegend";
        zones.forEach((z, i) => {
          const chip = document.createElement("span");
          chip.className = "zchip";
          chip.style.background = ZONE_COLORS[i];
          chip.textContent = `Z${z.zone} ${z.low}\u2013${z.high}`;
          legend.appendChild(chip);
        });
        wrap.appendChild(legend);
      }
      const opts: uPlot.Options = {
        width,
        height: 140,
        legend: { show: false },
        cursor: { sync: { key: sync.key }, points: { show: false } },
        scales: { x: { time: false }, y: spec.invert ? { dir: -1 } : {} },
        axes: [
          { show: idx === specs.length - 1, label: xLabel, stroke: "#8b949e", grid: { stroke: "rgba(128,128,128,.15)" } },
          {
            stroke: "#8b949e", size: 54, grid: { stroke: "rgba(128,128,128,.15)" },
            values: spec.fmt ? (_u, ticks) => ticks.map((t) => spec.fmt!(t)) : undefined,
          },
        ],
        series: [{}, { stroke: spec.stroke, width: 2, spanGaps: true, points: { show: false } }],
        hooks: {
          drawClear: spec.bands
            ? [
                (u) => {
                  const { ctx, bbox } = u;
                  const yMin = u.scales.y.min ?? 0, yMax = u.scales.y.max ?? 0;
                  ctx.save();
                  zones.forEach((z, i) => {
                    const lo = Math.max(z.low, yMin), hi = Math.min(z.high, yMax);
                    if (hi <= lo) return;
                    const top = u.valToPos(hi, "y", true), bottom = u.valToPos(lo, "y", true);
                    ctx.fillStyle = ZONE_COLORS[i] + "30";
                    ctx.fillRect(bbox.left, top, bbox.width, bottom - top);
                  });
                  ctx.restore();
                },
              ]
            : [],
          setCursor: [
            (u) => {
              // linked charts also report "no point"; only a real index moves the map marker
              // (the marker is cleared on mouseleave below)
              if (u.cursor.idx != null && u.cursor.left != null && u.cursor.left >= 0) onHover(u.cursor.idx);
            },
          ],
        },
      };
      const u = new uPlot(opts, [x, spec.values as number[]], target);
      plots.push(u);
      // uPlot only listens to the mouse; let a finger scrub the charts and the map marker too.
      const over = u.over;
      over.style.touchAction = "pan-y";
      const touch = (e: TouchEvent) => {
        const t = e.touches[0];
        if (!t) return;
        const r = over.getBoundingClientRect();
        u.setCursor({ left: Math.min(Math.max(t.clientX - r.left, 0), r.width), top: t.clientY - r.top });
      };
      over.addEventListener("touchstart", touch, { passive: true });
      over.addEventListener("touchmove", touch, { passive: true });
    });

    const ro = new ResizeObserver(() => {
      const w = Math.max(300, root.clientWidth);
      plots.forEach((p) => p.setSize({ width: w, height: 140 }));
    });
    ro.observe(root);
    const leave = () => onHover(null);
    root.addEventListener("mouseleave", leave);
    return () => {
      ro.disconnect();
      root.removeEventListener("mouseleave", leave);
      plots.forEach((p) => p.destroy());
    };
  }, [data, running, onHover, zones, units]);

  return <div ref={host} className="plots" />;
}
