import { LoadDay } from "../api";

function delta7(days: LoadDay[], pick: (d: LoadDay) => number | null | undefined): number | null {
  if (days.length < 8) return null;
  const now = pick(days[days.length - 1]);
  const prev = pick(days[days.length - 8]);
  if (now == null || prev == null) return null;
  return Number((now - prev).toFixed(1));
}

export default function PmcTiles({ days }: { days: LoadDay[] }) {
  const latest = days[days.length - 1];
  const num = (v: number | null | undefined) => v == null ? "—" : v.toFixed(0);
  const d = (v: number | null) => v == null ? "" : `${v >= 0 ? "+" : ""}${v.toFixed(0)}`;

  const rows: {
    label: string; value: string; delta: string; hint: string; band: string
  }[] = latest ? [
    { label: "Fitness", value: num(latest.ctl),
      delta: d(delta7(days, (x) => x.ctl)), hint: "CTL", band: "ctl" },
    { label: "Fatigue", value: num(latest.atl),
      delta: d(delta7(days, (x) => x.atl)), hint: "ATL", band: "atl" },
    { label: "Form", value: num(latest.tsb),
      delta: d(delta7(days, (x) => x.tsb)), hint: "TSB", band: "tsb" },
  ] : [
    { label: "Fitness", value: "—", delta: "", hint: "CTL", band: "ctl" },
    { label: "Fatigue", value: "—", delta: "", hint: "ATL", band: "atl" },
    { label: "Form", value: "—", delta: "", hint: "TSB", band: "tsb" },
  ];

  return (
    <div className="pmc-tiles">
      {rows.map((r) => (
        <div key={r.label} className={`pmc-tile band-${r.band}`}>
          <span className="pmc-label">{r.label}</span>
          <span className="pmc-value">{r.value}</span>
          <span className="pmc-sub">
            <span className="pmc-hint">{r.hint}</span>
            {r.delta && <span className="pmc-delta">{r.delta} / 7 d</span>}
          </span>
        </div>
      ))}
    </div>
  );
}
