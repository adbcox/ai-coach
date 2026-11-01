import { useEffect, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { SamplesData } from "../api";

interface Props {
  data: SamplesData;
  running: boolean;
  onHover: (index: number | null) => void;
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

export default function LinkedCharts({ data, running, onHover }: Props) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = host.current;
    if (!root) return;
    root.innerHTML = "";
    const useDist = data.dist.some((d) => d != null && d > 0);
    const x = useDist ? data.dist.map((d) => (d ?? 0) / 1000) : data.t.map((t) => t / 60);
    const xLabel = useDist ? "km" : "min";
    const speed = smooth(data.speed, 7);

    interface Spec { title: string; values: (number | null)[]; stroke: string; invert?: boolean; fmt?: (v: number) => string }
    const specs: Spec[] = [];
    if (has(data.speed)) {
      if (running) {
        const paceMin = speed.map((s) => (s && s > 0.8 ? 1000 / s / 60 : null));
        specs.push({
          title: "Pace (min/km)", values: paceMin, stroke: "#1f6feb", invert: true,
          fmt: (v) => `${Math.floor(v)}:${String(Math.round((v % 1) * 60)).padStart(2, "0")}`,
        });
      } else {
        specs.push({ title: "Speed (km/h)", values: speed.map((s) => (s == null ? null : s * 3.6)), stroke: "#1f6feb" });
      }
    }
    if (has(data.hr)) specs.push({ title: "Heart rate (bpm)", values: smooth(data.hr, 5), stroke: "#cf222e" });
    if (has(data.alt)) specs.push({ title: "Elevation (m)", values: data.alt, stroke: "#6e7781" });
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
          setCursor: [
            (u) => {
              // linked charts also report "no point"; only a real index moves the map marker
              // (the marker is cleared on mouseleave below)
              if (u.cursor.idx != null && u.cursor.left != null && u.cursor.left >= 0) onHover(u.cursor.idx);
            },
          ],
        },
      };
      plots.push(new uPlot(opts, [x, spec.values as number[]], target));
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
  }, [data, running, onHover]);

  return <div ref={host} className="plots" />;
}
