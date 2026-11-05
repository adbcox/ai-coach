import { useEffect, useRef } from "react";
import uPlot, { AlignedData, Options } from "uplot";
import "uplot/dist/uPlot.min.css";

const COL = "#fc4c02";

export default function PowerCurveChart({ points, height = 260 }:
  { points: { window_s: number; watts: number }[]; height?: number }) {
  const wrap = useRef<HTMLDivElement>(null);
  const plot = useRef<uPlot | null>(null);

  useEffect(() => {
    if (!wrap.current || points.length === 0) return;
    const el = wrap.current;
    const xs = points.map((p) => p.window_s);
    const ys = points.map((p) => p.watts);
    const data: AlignedData = [xs, ys];

    const opts: Options = {
      width: el.clientWidth || 600,
      height,
      padding: [12, 16, 8, 8],
      cursor: { drag: { x: false, y: false } },
      legend: { show: true, live: true },
      scales: {
        x: {
          distr: 3, // log-10
          time: false,
        },
        y: { auto: true },
      },
      axes: [
        {
          values: (_u, splits) => splits.map((s) => {
            if (s < 60) return `${s}s`;
            if (s < 3600) return `${Math.round(s / 60)}m`;
            return `${(s / 3600).toFixed(1)}h`;
          }),
          stroke: "#667085",
          grid: { stroke: "#e4e7ec", width: 1 },
          ticks: { show: false },
        },
        {
          stroke: "#667085",
          grid: { stroke: "#e4e7ec", width: 1 },
          ticks: { show: false },
          values: (_u, splits) => splits.map((s) => `${Math.round(s)} W`),
        },
      ],
      series: [
        { label: "Duration" },
        {
          label: "Best average power (W)",
          stroke: COL,
          width: 2,
          points: { show: true, size: 4, fill: COL },
        },
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
  }, [points, height]);

  if (points.length === 0) return <p className="muted">No power data for this activity.</p>;
  return <div ref={wrap} className="pcchart" />;
}
