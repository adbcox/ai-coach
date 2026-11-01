import { useSyncExternalStore } from "react";

export type Units = { distance: "km" | "mi"; elevation: "m" | "ft"; weight: "kg" | "lb"; height: "cm" | "ftin" };

export const KM_PER_MI = 1.609344;
export const FT_PER_M = 3.280839895;
export const LB_PER_KG = 2.2046226218;

let units: Units = { distance: "km", elevation: "m", weight: "kg", height: "cm" };
const listeners = new Set<() => void>();

export function setUnits(u: Partial<Units> | null | undefined) {
  if (!u) return;
  units = { ...units, ...u };
  listeners.forEach((f) => f());
}
export const getUnits = () => units;
export function useUnits(): Units {
  return useSyncExternalStore((f) => { listeners.add(f); return () => { listeners.delete(f); }; }, getUnits);
}

/** Distance factor: kilometres -> current unit. */
export const distFactor = () => (units.distance === "mi" ? 1 / KM_PER_MI : 1);
export const distUnit = () => units.distance;
export const elevFactor = () => (units.elevation === "ft" ? FT_PER_M : 1);
export const elevUnit = () => units.elevation;

export const kgToDisplay = (kg: number) => (units.weight === "lb" ? kg * LB_PER_KG : kg);
export const displayToKg = (v: number) => (units.weight === "lb" ? v / LB_PER_KG : v);

/** cm -> {ft, in} rounded to the nearest inch. */
export function cmToFtIn(cm: number): { ft: number; inch: number } {
  const total = Math.round(cm / 2.54);
  return { ft: Math.floor(total / 12), inch: total % 12 };
}
export const ftInToCm = (ft: number, inch: number) => Math.round((ft * 12 + inch) * 2.54 * 10) / 10;
