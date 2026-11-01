export type SportGroup = "Running" | "Cycling" | "Hiking" | "Other";

export function sportGroup(sport: string | null): SportGroup {
  const s = (sport ?? "").toLowerCase();
  if (s.includes("run")) return "Running";
  if (s.includes("cycl") || s.includes("bik") || s.includes("ride")) return "Cycling";
  if (s.includes("hik") || s.includes("walk")) return "Hiking";
  return "Other";
}

export const km = (m: number | null | undefined, digits = 2) =>
  m == null ? "–" : (m / 1000).toFixed(digits);

export function duration(s: number | null | undefined): string {
  if (s == null) return "–";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.round(s % 60);
  return `${h ? h + ":" : ""}${String(m).padStart(h ? 2 : 1, "0")}:${String(sec).padStart(2, "0")}`;
}

/** min/km from m/s, e.g. "5:12" */
export function pace(speed: number | null | undefined): string {
  if (!speed || speed < 0.3) return "–";
  const secPerKm = 1000 / speed;
  const m = Math.floor(secPerKm / 60);
  const s = Math.round(secPerKm % 60);
  return s === 60 ? `${m + 1}:00` : `${m}:${String(s).padStart(2, "0")}`;
}

export const kmh = (speed: number | null | undefined) =>
  speed == null ? "–" : (speed * 3.6).toFixed(1);

/** Local calendar day, YYYY-MM-DD, in the browser's timezone. */
export function localDay(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function lastDays(n: number): string[] {
  const out: string[] = [];
  const now = new Date();
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - i);
    out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`);
  }
  return out;
}
