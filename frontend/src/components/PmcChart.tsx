import { useEffect, useRef } from "react";
import uPlot, { AlignedData, Options } from "uplot";
import "uplot/dist/uPlot.min.css";
import { LoadDay } from "../api";

const COLORS = {
  ctl: "#1a7f37",     // Fitness
  atl: "#b35900",     // Fatigue
  tsb: "#1f6feb",     // Form
  band: "rgba(31, 111, 235, 0.08)",
  grid: "#e4e7ec",
  gridDark: "#2a313b",
};

function prefersDark(): boolean {
  return typeof window !== "undefined"
    && window.matchMedia?.("(prefers-color-scheme: dark)").matches;
}

export default function PmcChart({ days, height = 320 }: { days: LoadDay[]; height?: number }) {
  const wrap = useRef<HTMLDivElement>(null);
  const plot = useRef<uPlot | null>(null);

  useEffect(() => {
    if (!wrap.current || days.length === 0) return;
    const el = wrap.current;
    const dark = prefersDark();
    const x = days.map((d) => Math.floor(new Date(d.day + "T12:00:00Z").getTime() / 1000));
    const ctl = days.map((d) => (d.ctl == null ? null : Number(d.ctl.toFixed(1))));
    const atl = days.map((d) => (d.atl == null ? null : Number(d.atl.toFixed(1))));
    const tsb = days.map((d) => (d.tsb == null ? null : Number(d.tsb.toFixed(1))));
    const data: AlignedData = [x, ctl, atl, tsb];

    const opts: Options = {
      width: el.clientWidth || 600,
      height,
      padding: [12, 16, 8, 8],
      cursor: { drag: { x: true, y: false, uni: 50 }, focus: { prox: 20 } },
      legend: { show: true, live: true },
      series: [
        { label: "Date" },
        { label: "Fitness (CTL)", stroke: COLORS.ctl, width: 2, points: { show: false } },
        { label: "Fatigue (ATL)", stroke: COLORS.atl, width: 2, points: { show: false } },
        { label: "Form (TSB)", stroke: COLORS.tsb, width: 1.5, points: { show: false }, dash: [5, 3] },
      ],
      scales: { x: { time: true }, y: { auto: true } },
      axes: [
        { stroke: dark ? "#98a2b3" : "#667085",
          grid: { stroke: dark ? COLORS.gridDark : COLORS.grid, width: 1 },
          ticks: { show: false } },
        { stroke: dark ? "#98a2b3" : "#667085",
          grid: { stroke: dark ? COLORS.gridDark : COLORS.grid, width: 1 },
          ticks: { show: false } },
      ],
    };

    plot.current = new uPlot(opts, data, el);
    const ro = new ResizeObserver(() => {
      if (plot.current && wrap.current) {
        plot.current.setSize({ width: wrap.current.clientWidth, height });
      }
    });
    ro.observe(el);
    return () => { ro.disconnect(); plot.current?.destroy(); plot.current = null; };
  }, [days, height]);

  if (days.length === 0) return <p className="muted">No load history yet. A sync brings this to life.</p>;
  return <div ref={wrap} className="pmcchart" />;
}
