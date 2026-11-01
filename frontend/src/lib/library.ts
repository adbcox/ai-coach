import { ApiError } from "../api";

export interface LibItem {
  id: string; title: string; authors: string[]; year: number | null; venue: string | null; doi: string | null; url: string | null;
  ref_id: string | null; status: "converted" | "citation_only" | "needs_ocr" | "failed"; reviewed: boolean; evidence_type: string | null;
  tags: string[]; words: number | null; pages: number | null; added: string | null; message: string | null; notes_status: string | null;
  snippet?: string | null; duplicate?: boolean;
}
export interface LibList {
  items: LibItem[]; tags: string[]; counts: Record<string, number>; total: number; inbox_waiting: number;
  statuses: string[]; evidence_types: string[]; template: string; folder: string;
}
export interface LibDetail extends LibItem {
  fulltext: string; has_source: boolean; source_ext: string | null; converter?: string; notes?: string;
  actionable: { exists: boolean; status: string | null; body: string; reviewed_on: string | null };
}

export const STATUS_LABEL: Record<string, string> = {
  converted: "converted", citation_only: "citation only", needs_ocr: "needs OCR", failed: "failed",
};
export const STATUS_CLASS: Record<string, string> = { converted: "ok", citation_only: "muted", needs_ocr: "warn", failed: "bad" };

/** Send one file as the raw request body (no multipart), so there is no size limit beyond the server's. */
export async function sendFile<T>(path: string, file: File, params: Record<string, string> = {}, method = "PUT"): Promise<T> {
  const qs = new URLSearchParams({ filename: file.name, ...params }).toString();
  const res = await fetch(`/api${path}?${qs}`, { method, headers: { "X-Requested-With": "aec" }, body: file, credentials: "same-origin" });
  if (!res.ok) {
    let msg = `Upload failed (${res.status})`;
    try { const d = await res.json(); if (typeof d.detail === "string") msg = d.detail; } catch { /* ignore */ }
    throw new ApiError(res.status, msg);
  }
  return (await res.json()) as T;
}

export function authorsShort(a: string[]): string {
  if (!a.length) return "";
  const last = (n: string) => (n.includes(",") ? n.split(",")[0] : n.trim().split(/\s+/).slice(-1)[0]);
  return a.length === 1 ? last(a[0]) : a.length === 2 ? `${last(a[0])} & ${last(a[1])}` : `${last(a[0])} et al.`;
}

/** Turn "[[match]]" markers from the search snippet into highlighted pieces without ever treating text as HTML. */
export function snippetParts(s: string): { text: string; hit: boolean }[] {
  return s.split(/(\[\[.*?\]\])/g).filter(Boolean).map((p) => (p.startsWith("[[") && p.endsWith("]]") ? { text: p.slice(2, -2), hit: true } : { text: p, hit: false }));
}
