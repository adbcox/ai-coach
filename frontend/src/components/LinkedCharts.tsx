import { useEffect, useRef } from "react";
import { distFactor, elevFactor, elevUnit, useUnits } from "../lib/units";
import { duration, unitSpeed } from "../lib/format";
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
    const x = useDist ? data.dist.map((d) => ((d ?? 0) / 1000) * distFactor()) : data.t.map((t) => t);
    const xLabel = useDist ? units.distance : "time";
    const speed = smooth(data.speed, 7);

    interface Spec { title: string; values: (number | null)[]; stroke: string; invert?: boolean; bands?: boolean; fmt?: (v: number) => string; unit: string; dec: number }
    const specs: Spec[] = [];
    if (has(data.speed)) {
      if (running) {
        const paceMin = speed.map((s) => (s && s > 0.8 ? 1000 / s / 60 / distFactor() : null));
        specs.push({
          title: `Pace (min/${units.distance})`, values: paceMin, stroke: "#1f6feb", invert: true, unit: `/${units.distance}`, dec: 0,
          fmt: (v) => {
            const m = Math.floor(v), s = Math.round((v - m) * 60);
            return s === 60 ? `${m + 1}:00` : `${m}:${String(s).padStart(2, "0")}`;
          },
        });
      } else {
        specs.push({ title: `Speed (${unitSpeed()})`, values: speed.map((s) => (s == null ? null : s * 3.6 * distFactor())), stroke: "#1f6feb", unit: unitSpeed(), dec: 1 });
      }
    }
    if (has(data.hr)) specs.push({ title: "Heart rate (bpm)", values: smooth(data.hr, 5), stroke: "#cf222e", bands: zones.length > 0, unit: "bpm", dec: 0 });
    if (has(data.alt)) specs.push({ title: `Elevation (${elevUnit()})`, values: data.alt.map((v) => (v == null ? null : v * elevFactor())), stroke: "#6e7781", unit: elevUnit(), dec: 1 });
    if (has(data.power)) specs.push({ title: "Power (W)", values: smooth(data.power, 7), stroke: "#8250df", unit: "W", dec: 0 });
    if (has(data.cadence)) {
      // FIT files store running cadence as strides per minute (one foot); Garmin Connect shows steps per minute (both feet).
      const mult = running ? 2 : 1;
      specs.push({ title: running ? "Cadence (spm)" : "Cadence (rpm)", values: smooth(data.cadence, 7).map((v) => (v == null ? null : v * mult)), stroke: "#2da44e", unit: running ? "spm" : "rpm", dec: 0 });
    }

    const plots: uPlot[] = [];
    const sync = uPlot.sync("run");
    const width = Math.max(300, root.clientWidth);
    specs.forEach((spec, idx) => {
      const wrap = document.createElement("div");
      wrap.className = "plot";
      const label = document.createElement("div");
      label.className = "plot-title";
      const titleText = document.createElement("span");
      titleText.textContent = spec.title;
      const readout = document.createElement("span");
      readout.className = "plot-readout";
      readout.style.color = spec.stroke;
      label.append(titleText, readout);
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
        padding: [null, 28, null, null],   // same right padding on every chart so their plot areas (and cursor lines) line up
        cursor: { sync: { key: sync.key }, points: { show: true, size: 8, width: 2, stroke: spec.stroke, fill: "#ffffff" } },
        scales: { x: { time: false }, y: spec.invert ? { dir: -1 } : {} },
        axes: [
          { show: idx === specs.length - 1, label: xLabel, stroke: "#8b949e", grid: { stroke: "rgba(128,128,128,.15)" },
            values: useDist ? undefined : (_u, ticks) => ticks.map((t) => duration(t)) },
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
              // exact value at the cursor: shown in every chart's title row, and as a pop-up on the chart being pointed at
              const i = u.cursor.idx;
              const v = i != null && i >= 0 ? spec.values[i] : null;
              if (v == null || i == null) {
                readout.textContent = "";
                tip.style.display = "none";
              } else {
                const text = `${spec.fmt ? spec.fmt(v) : v.toFixed(spec.dec)} ${spec.unit}`;
                readout.textContent = text;
                const at = useDist ? `${x[i].toFixed(2)} ${units.distance}` : duration(x[i]);
                if (hovering && u.cursor.left != null && u.cursor.left >= 0) {
                  tip.innerHTML = "";
                  const big = document.createElement("strong");
                  big.textContent = text;
                  const small = document.createElement("span");
                  small.textContent = ` at ${at}`;
                  tip.append(big, small);
                  tip.style.display = "block";
                  const w = tip.offsetWidth;
                  tip.style.left = `${u.cursor.left + 14 + w > u.over.clientWidth ? u.cursor.left - 14 - w : u.cursor.left + 14}px`;
                } else tip.style.display = "none";
              }
              // linked charts also report "no point"; only a real index moves the map marker
              // (the marker is cleared on mouseleave below)
              if (u.cursor.idx != null && u.cursor.left != null && u.cursor.left >= 0) onHover(u.cursor.idx);
            },
          ],
        },
      };
      let hovering = false;
      const tip = document.createElement("div");
      tip.className = "plot-tip";
      tip.style.display = "none";
      const u = new uPlot(opts, [x, spec.values as number[]], target);
      plots.push(u);
      u.over.appendChild(tip);
      u.over.addEventListener("mouseenter", () => { hovering = true; });
      u.over.addEventListener("mouseleave", () => { hovering = false; tip.style.display = "none"; });
      u.over.addEventListener("touchstart", () => { hovering = true; }, { passive: true });
      u.over.addEventListener("touchend", () => { hovering = false; tip.style.display = "none"; }, { passive: true });
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
