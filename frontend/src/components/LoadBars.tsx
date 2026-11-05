import { useMemo } from "react";
import { LoadDay } from "../api";

const PALETTE: Record<string, string> = {
  run_road: "#1f6feb",
  run_trail: "#1a7f37",
  bike_road: "#e8590c",
  bike_gravel: "#b35900",
  bike_mtb: "#8b949e",
  swim: "#4c8dff",
  hike: "#2da44e",
  other: "#98a2b3",
};

export interface FamDay { day: string; family: string; tss: number }

export default function LoadBars({ days, familyDays, height = 110 }:
  { days: LoadDay[]; familyDays: FamDay[]; height?: number }) {
  const byDay = useMemo(() => {
    const out: Record<string, FamDay[]> = {};
    for (const r of familyDays) { (out[r.day] ??= []).push(r); }
    return out;
  }, [familyDays]);

  const xs = days.map((d) => d.day);
  const totals = days.map((d) => d.tss ?? 0);
  const peak = Math.max(1, ...totals);

  return (
    <div className="loadbars" style={{ height }}>
      {xs.map((day, i) => {
        const stack = byDay[day] ?? [];
        if (stack.length === 0 && totals[i] > 0) {
          const h = (totals[i] / peak) * 100;
          return <div key={day} className="lb-col" title={`${day}: ${Math.round(totals[i])} TSS`}>
            <div className="lb-fill" style={{ height: `${h}%`, background: PALETTE.other }} />
          </div>;
        }
        return (
          <div key={day} className="lb-col"
               title={`${day}: ${Math.round(totals[i])} TSS\n${stack.map(s => `${s.family} ${Math.round(s.tss)}`).join("\n")}`}>
            {stack.map((s) => (
              <div key={s.family} className="lb-fill"
                   style={{ height: `${((s.tss || 0) / peak) * 100}%`,
                            background: PALETTE[s.family] ?? PALETTE.other }} />
            ))}
          </div>
        );
      })}
    </div>
  );
}
