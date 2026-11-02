import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { Reference } from "../components/Cite";
import Markdown from "../components/Markdown";
import { authorsShort, LibDetail, LibList, sendFile, STATUS_CLASS, STATUS_LABEL } from "../lib/library";

type Tab = "notes" | "text" | "details";

export default function LibraryItem({ id }: { id: string }) {
  const [item, setItem] = useState<LibDetail | null>(null);
  const [meta, setMeta] = useState<LibList | null>(null);
  const [refs, setRefs] = useState<Reference[]>([]);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("text");
  const [raw, setRaw] = useState(false);
  const [notes, setNotes] = useState("");
  const [notesStatus, setNotesStatus] = useState("draft");
  const [notesMsg, setNotesMsg] = useState("");
  const [form, setForm] = useState({ title: "", authors: "", year: "", venue: "", doi: "", url: "", evidence_type: "", tags: "", notes: "", ref_id: "", reviewed: false });
  const [formMsg, setFormMsg] = useState("");
  const [busy, setBusy] = useState("");

  const apply = useCallback((d: LibDetail) => {
    setItem(d);
    setNotes(d.actionable.exists ? d.actionable.body : "");
    setNotesStatus(d.actionable.status ?? "draft");
    setForm({ title: d.title, authors: d.authors.join("; "), year: d.year ? String(d.year) : "", venue: d.venue ?? "", doi: d.doi ?? "", url: d.url ?? "",
      evidence_type: d.evidence_type ?? "", tags: d.tags.join(", "), notes: d.notes ?? "", ref_id: d.ref_id ?? "", reviewed: d.reviewed });
  }, []);
  const load = useCallback(() => { api<LibDetail>(`/library/${id}`).then(apply).catch((e) => setError(e.message)); }, [id, apply]);
  useEffect(() => { setItem(null); setError(""); load(); }, [load]);
  useEffect(() => {   // a scan being read: keep checking until it is done
    if (item?.status !== "ocr_pending") return;
    const t = window.setInterval(load, 3000);
    return () => window.clearInterval(t);
  }, [item?.status, load]);
  useEffect(() => {
    api<LibList>("/library").then(setMeta).catch(() => undefined);
    api<{ references: Reference[] }>("/references").then((r) => setRefs(r.references)).catch(() => undefined);
  }, []);
  useEffect(() => { if (item && item.status !== "converted") setTab("details"); }, [item?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (error) return <div className="stack"><a href="#/library">← Library</a><p className="error">{error}</p></div>;
  if (!item) return <p className="muted">Loading…</p>;

  async function saveDetails() {
    setFormMsg("");
    try {
      const d = await api<LibDetail>(`/library/${id}`, "PATCH", { title: form.title, authors: form.authors, year: form.year ? Number(form.year) : null, venue: form.venue,
        doi: form.doi, url: form.url, evidence_type: form.evidence_type || null, tags: form.tags, notes: form.notes, ref_id: form.ref_id || null, reviewed: form.reviewed });
      apply({ ...item!, ...d, fulltext: item!.fulltext, actionable: item!.actionable, has_source: item!.has_source, source_ext: item!.source_ext });
      setFormMsg("Saved.");
    } catch (e) { setFormMsg((e as Error).message); }
  }
  async function saveNotes(status = notesStatus) {
    setNotesMsg("");
    try {
      const a = await api<LibDetail["actionable"]>(`/library/${id}/actionable`, "PUT", { body: notes, status });
      setItem({ ...item!, actionable: a }); setNotesStatus(a.status ?? "draft"); setNotesMsg("Saved.");
    } catch (e) { setNotesMsg((e as Error).message); }
  }
  async function attach(file: File) {
    setBusy("Converting…"); setError("");
    try { const d = await sendFile<LibDetail>(`/library/${id}/attach`, file, {}, "POST"); apply({ ...item!, ...d }); load(); }
    catch (e) { setFormMsg((e as Error).message); }
    setBusy("");
  }
  async function reconvert() {
    setBusy("Converting again…");
    try { await api(`/library/${id}/reconvert`, "POST"); load(); } catch (e) { setFormMsg((e as Error).message); }
    setBusy("");
  }
  async function readScan() {
    setBusy("Starting OCR\u2026");
    try { await api(`/library/${id}/ocr`, "POST"); load(); } catch (e) { setFormMsg((e as Error).message); setTab("details"); }
    setBusy("");
  }
  async function remove() {
    if (!window.confirm("Delete this source, your notes on it and the original file from the server? This cannot be undone.")) return;
    try { await api(`/library/${id}`, "DELETE"); window.location.hash = "#/library"; } catch (e) { setFormMsg((e as Error).message); }
  }

  const doiLink = item.doi ? `https://doi.org/${item.doi}` : item.url;
  return (
    <div className="stack">
      <a href="#/library">← Library</a>
      <section className="card wide">
        <h2 style={{ margin: 0 }}>{item.title}</h2>
        <span className="muted">{[item.authors.join(", "), item.year, item.venue].filter(Boolean).join(" · ") || authorsShort(item.authors)}</span>
        <span className="row" style={{ alignItems: "center", gap: 6 }}>
          <span className={`badge ${STATUS_CLASS[item.status]}`}>{STATUS_LABEL[item.status]}</span>
          {item.reviewed && <span className="badge ok">reviewed by you</span>}
          {item.evidence_type && <span className="badge muted">{item.evidence_type}</span>}
          {item.ref_id && <a href={`#/references/${item.ref_id}`}>cited by the app</a>}
          {doiLink && <a href={doiLink} target="_blank" rel="noreferrer noopener">{item.doi ? `doi:${item.doi}` : "link"}</a>}
        </span>
        {item.status === "ocr_pending" && <span role="status">Reading the scanned pages{item.progress && item.progress.total > 0 ? `: page ${item.progress.done} of ${item.progress.total}` : ""}. This can take a few seconds per page and the page updates by itself.</span>}
        {item.message && item.status !== "ocr_pending" && <span className={item.ocr ? "warn-text" : item.status === "converted" ? "muted" : "error"}>{item.message}</span>}
        <span className="muted">
          {item.status === "converted" && !item.ocr ? `Converted with ${item.converter ?? "a text extractor"}${item.pages ? ` from ${item.pages} ${item.pages === 1 ? "page" : "pages"}` : ""} (${(item.words ?? 0).toLocaleString()} words). Automatic conversion can garble tables, figures, symbols and numbers: check the original before relying on a number.` : ""}
        </span>
        <div className="row">
          {item.has_source && <a className="button" href={`/api/library/${id}/source`}>Download original</a>}
          {item.has_source && <button onClick={reconvert} disabled={!!busy}>Convert again</button>}
          {item.has_source && (item.status === "needs_ocr" || item.ocr) && <button onClick={readScan} disabled={!!busy}>Read the scan again (OCR)</button>}
          <label className="button" style={{ cursor: "pointer" }}>{item.status === "converted" ? "Replace the file" : "Attach the full text"}
            <input type="file" hidden accept=".pdf,.html,.htm,.md,.markdown,.txt" onChange={(e) => { const f = e.target.files?.[0]; if (f) void attach(f); e.target.value = ""; }} />
          </label>
          <button onClick={remove}>Delete</button>
        </div>
        {busy && <span role="status">{busy}</span>}
      </section>

      <section className="card wide">
        <div className="tabs" role="tablist">
          {([["text", "Full text"], ["notes", `Your notes${item.actionable.exists ? ` (${item.actionable.status})` : ""}`], ["details", "Details"]] as const).map(([k, label]) => (
            <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "active" : ""} onClick={() => setTab(k)}>{label}</button>
          ))}
        </div>

        {tab === "text" && (
          <>
            <div className="row"><button onClick={() => setRaw(!raw)}>{raw ? "Show formatted" : "Show the Markdown file"}</button></div>
            {item.fulltext.trim() ? (raw ? <pre className="md" style={{ whiteSpace: "pre-wrap" }}>{item.fulltext}</pre> : <Markdown source={item.fulltext} />) : <p className="muted">No text yet.</p>}
          </>
        )}

        {tab === "notes" && (
          <div className="stack">
            <span className="muted">Write only what changes a training decision: each point with who it applies to, how strong the evidence is, where in the text it comes from, and what would make it wrong. It is saved as a Markdown file in <code>ingest/1-actionable</code>. Keep it a draft until you have checked it against the full text.</span>
            {!item.actionable.exists && !notes && <div><button className="primary" onClick={() => setNotes(meta?.template ?? "")}>Start from the template</button></div>}
            <textarea className="notes" value={notes} onChange={(e) => setNotes(e.target.value)} aria-label="Your notes (Markdown)" placeholder="Your notes in Markdown" />
            <div className="row" style={{ alignItems: "center" }}>
              <label style={{ display: "flex", gap: 6, alignItems: "center" }}>Status
                <select value={notesStatus} onChange={(e) => setNotesStatus(e.target.value)}><option value="draft">draft</option><option value="reviewed">reviewed</option></select>
              </label>
              <button className="primary" onClick={() => void saveNotes()} disabled={!notes.trim()}>Save notes</button>
              {notesMsg && <span className={notesMsg === "Saved." ? "ok-text" : "error"}>{notesMsg}</span>}
            </div>
            {notes.trim() && <details><summary>Preview</summary><Markdown source={notes} /></details>}
          </div>
        )}

        {tab === "details" && (
          <form className="stack" onSubmit={(e) => { e.preventDefault(); void saveDetails(); }}>
            <label>Title<input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required /></label>
            <label>Authors (separate with ;)<input value={form.authors} onChange={(e) => setForm({ ...form, authors: e.target.value })} /></label>
            <div className="row">
              <label>Year<input type="number" value={form.year} onChange={(e) => setForm({ ...form, year: e.target.value })} /></label>
              <label>Journal or publisher<input value={form.venue} onChange={(e) => setForm({ ...form, venue: e.target.value })} /></label>
            </div>
            <div className="row">
              <label>DOI<input value={form.doi} onChange={(e) => setForm({ ...form, doi: e.target.value })} /></label>
              <label>Link<input value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} /></label>
            </div>
            <label>Type of evidence
              <select value={form.evidence_type} onChange={(e) => setForm({ ...form, evidence_type: e.target.value })}>
                <option value="">Not set</option>{(meta?.evidence_types ?? []).map((t) => <option key={t}>{t}</option>)}
              </select>
            </label>
            <label>Tags (separate with commas)<input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} placeholder="hrv, tapering, marathon" /></label>
            <label>Short note<input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></label>
            <label>This is a source the app cites
              <select value={form.ref_id} onChange={(e) => setForm({ ...form, ref_id: e.target.value })}>
                <option value="">No</option>{refs.map((r) => <option key={r.id} value={r.id}>{r.short}</option>)}
              </select>
            </label>
            <label style={{ display: "flex", gap: 8, alignItems: "center" }}><input type="checkbox" checked={form.reviewed} onChange={(e) => setForm({ ...form, reviewed: e.target.checked })} style={{ width: "auto" }} />
              I have read this and checked the conversion</label>
            <div className="row" style={{ alignItems: "center" }}><button className="primary">Save details</button>{formMsg && <span className={formMsg === "Saved." ? "ok-text" : "error"}>{formMsg}</span>}</div>
          </form>
        )}
      </section>
    </div>
  );
}
