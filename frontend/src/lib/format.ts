export type SportGroup = "Running" | "Cycling" | "Hiking" | "Other";

export function sportGroup(sport: string | null): SportGroup {
  const s = (sport ?? "").toLowerCase();
  if (s.includes("run")) return "Running";
  if (s.includes("cycl") || s.includes("bik") || s.includes("ride")) return "Cycling";
  if (s.includes("hik") || s.includes("walk")) return "Hiking";
  return "Other";
}

import { distFactor, distUnit, elevFactor, elevUnit } from "./units";

/** Distance in the user's unit (km or mi) as text; the name is historical. */
export const km = (m: number | null | undefined, digits = 2) =>
  m == null ? "–" : ((m / 1000) * distFactor()).toFixed(digits);
/** Same but a number, for charts. */
export const distNum = (km_: number) => km_ * distFactor();
export const unitDist = () => distUnit();
export const elevation = (m: number | null | undefined) =>
  m == null ? "–" : `${Math.round(m * elevFactor())} ${elevUnit()}`;
export const unitElev = () => elevUnit();

export function duration(s: number | null | undefined): string {
  if (s == null) return "–";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.round(s % 60);
  return `${h ? h + ":" : ""}${String(m).padStart(h ? 2 : 1, "0")}:${String(sec).padStart(2, "0")}`;
}

/** Pace per km or per mile (by the user's unit) from m/s, e.g. "5:12" */
export function pace(speed: number | null | undefined): string {
  if (!speed || speed < 0.3) return "–";
  const secPer = 1000 / speed / distFactor();
  const m = Math.floor(secPer / 60);
  const s = Math.round(secPer % 60);
  return s === 60 ? `${m + 1}:00` : `${m}:${String(s).padStart(2, "0")}`;
}
/** Pace from seconds per km. */
export function paceFromSecPerKm(secPerKm: number): string {
  const secPer = secPerKm / distFactor();
  const m = Math.floor(secPer / 60);
  const s = Math.round(secPer % 60);
  return s === 60 ? `${m + 1}:00` : `${m}:${String(s).padStart(2, "0")}`;
}

/** Speed in km/h or mph. */
export const kmh = (speed: number | null | undefined) =>
  speed == null ? "–" : (speed * 3.6 * distFactor()).toFixed(1);
export const unitSpeed = () => (distUnit() === "mi" ? "mph" : "km/h");

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
