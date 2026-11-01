import { useEffect, useState } from "react";
import { api } from "../api";

export interface Reference {
  id: string; short: string; kind: string; authors: string; year: number | null; title: string; venue: string;
  doi: string | null; url: string | null; verified: "full_text" | "abstract" | "secondary" | "documentation";
  verified_label: string; verified_note: string; your_copy?: { id: string; status: string } | null; used_for: string[]; how_used: string; limits: string;
}
export const VERIFIED_CLASS: Record<string, string> = { full_text: "ok", abstract: "warn", secondary: "warn", documentation: "warn" };

let cache: Record<string, Reference> | null = null;
let pending: Promise<Record<string, Reference>> | null = null;
function loadRefs(): Promise<Record<string, Reference>> {
  if (cache) return Promise.resolve(cache);
  pending ??= api<{ references: Reference[] }>("/references").then((r) => {
    cache = Object.fromEntries(r.references.map((x) => [x.id, x]));
    return cache;
  });
  return pending;
}

/** A credit that names the source, shows how well it was checked, and links to the references page. */
export default function Cite({ id }: { id: string }) {
  const [ref, setRef] = useState<Reference | null>(cache?.[id] ?? null);
  useEffect(() => { if (!ref) loadRefs().then((m) => setRef(m[id] ?? null)).catch(() => undefined); }, [id, ref]);
  return (
    <a className="cite" href={`#/references/${id}`} title={ref ? `${ref.title} — ${ref.verified_label}` : id}>
      {ref ? ref.short : id}
      {ref && <span className={`dot ${VERIFIED_CLASS[ref.verified]}`} aria-label={ref.verified_label} />}
    </a>
  );
}
