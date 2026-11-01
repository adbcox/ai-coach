import { DragEvent, FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Reference } from "../components/Cite";
import { authorsShort, LibItem, LibList, sendFile, snippetParts, STATUS_CLASS, STATUS_LABEL } from "../lib/library";

type Result = { name: string; item?: LibItem; error?: string };
type RefWithCopy = Reference & { your_copy: { id: string; status: string } | null };

function ItemRow({ it }: { it: LibItem }) {
  return (
    <a className="libitem" href={`#/library/${it.id}`}>
      <span className="title">{it.title}</span>
      <span className="muted">{[authorsShort(it.authors), it.year, it.venue].filter(Boolean).join(" · ") || "no authors or year yet"}</span>
      <span className="row" style={{ gap: 6, alignItems: "center" }}>
        <span className={`badge ${STATUS_CLASS[it.status]}`}>{STATUS_LABEL[it.status]}</span>
        {it.reviewed && <span className="badge ok">reviewed</span>}
        {it.notes_status && <span className="badge muted">notes: {it.notes_status}</span>}
        {it.ref_id && <span className="badge muted">cited by the app</span>}
        {it.words ? <span className="muted">{it.words.toLocaleString()} words{it.pages ? ` · ${it.pages} ${it.pages === 1 ? "page" : "pages"}` : ""}</span> : null}
      </span>
      {it.tags.length > 0 && <span className="tags">{it.tags.map((t) => <span key={t} className="tag">{t}</span>)}</span>}
      {it.snippet && <span className="snip">{snippetParts(it.snippet).map((p, i) => (p.hit ? <mark key={i}>{p.text}</mark> : <span key={i}>{p.text}</span>))}</span>}
    </a>
  );
}

export default function Library() {
  const [data, setData] = useState<LibList | null>(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [tag, setTag] = useState("");
  const [filter, setFilter] = useState<"all" | "attention" | "unreviewed">("all");
  const [results, setResults] = useState<Result[]>([]);
  const [busy, setBusy] = useState("");
  const [over, setOver] = useState(false);
  const [link, setLink] = useState("");
  const [refs, setRefs] = useState<RefWithCopy[]>([]);
  const [cite, setCite] = useState({ title: "", authors: "", year: "", venue: "", doi: "", url: "", evidence_type: "" });
  const [msg, setMsg] = useState("");
  const timer = useRef<number>(0);

  const load = useCallback(() => {
    const p = new URLSearchParams();
    if (q.trim()) p.set("q", q.trim());
    if (tag) p.set("tag", tag);
    if (filter === "unreviewed") p.set("reviewed", "0");
    api<LibList>(`/library?${p}`).then(setData).catch((e) => setError(e.message));
  }, [q, tag, filter]);
  useEffect(() => { window.clearTimeout(timer.current); timer.current = window.setTimeout(load, q ? 250 : 0); return () => window.clearTimeout(timer.current); }, [load, q]);
  useEffect(() => { api<{ references: RefWithCopy[] }>("/references").then((r) => setRefs(r.references)).catch(() => undefined); }, [data?.total]);

  async function uploadAll(files: FileList | File[], refId?: string) {
    const list = Array.from(files);
    if (!list.length) return;
    setError("");
    const out: Result[] = [];
    for (let i = 0; i < list.length; i++) {
      setBusy(`Converting ${i + 1} of ${list.length}: ${list[i].name}`);
      try {
        const item = await sendFile<LibItem>("/library/upload", list[i], refId ? { ref_id: refId } : {});
        out.push({ name: list[i].name, item });
      } catch (e) { out.push({ name: list[i].name, error: (e as Error).message }); }
      setResults([...out]);
    }
    setBusy("");
    load();
  }
  const onDrop = (e: DragEvent) => { e.preventDefault(); setOver(false); void uploadAll(e.dataTransfer.files); };

  async function addLink(e: FormEvent) {
    e.preventDefault();
    if (!link.trim()) return;
    setBusy("Fetching the link…"); setError("");
    try { const item = await api<LibItem>("/library/link", "POST", { url: link.trim() }); setResults((r) => [{ name: link.trim(), item }, ...r]); setLink(""); load(); }
    catch (err) { setResults((r) => [{ name: link.trim(), error: (err as Error).message }, ...r]); }
    setBusy("");
  }
  async function addCitation(e: FormEvent) {
    e.preventDefault();
    setBusy("Saving…");
    try {
      const item = await api<LibItem>("/library/citation", "POST", { title: cite.title, authors: cite.authors || null, year: cite.year ? Number(cite.year) : null,
        venue: cite.venue || null, doi: cite.doi || null, url: cite.url || null, evidence_type: cite.evidence_type || null });
      setResults((r) => [{ name: cite.title, item }, ...r]);
      setCite({ title: "", authors: "", year: "", venue: "", doi: "", url: "", evidence_type: "" }); load();
    } catch (err) { setResults((r) => [{ name: cite.title, error: (err as Error).message }, ...r]); }
    setBusy("");
  }
  async function scan() {
    setBusy("Scanning the inbox folder…");
    try { const r = await api<{ converted: number; reindexed: number }>("/library/rescan", "POST"); setMsg(`Scan done: ${r.converted} file(s) converted, ${r.reindexed} updated.`); load(); }
    catch (e) { setError((e as Error).message); }
    setBusy("");
  }

  if (error && !data) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Loading…</p>;
  const shown = filter === "attention" ? data.items.filter((i) => i.status !== "converted") : data.items;
  const attention = data.total - (data.counts.converted ?? 0);

  return (
    <div className="stack">
      <div>
        <h2 style={{ margin: 0 }}>Library</h2>
        <p className="muted" style={{ margin: "4px 0 0" }}>
          Your own papers, articles and notes. Each is converted to a Markdown file you can read here and on the server. No AI is involved, and nothing leaves your server
          except the links and DOIs you ask it to look up.
        </p>
      </div>

      <section className="card wide">
        <h3 style={{ margin: 0 }}>Add sources</h3>
        <label className={`drop ${over ? "over" : ""}`} onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={onDrop}>
          <strong>Drop files here, or tap to choose</strong>
          <span>PDF, web page (.html), Markdown or text. Pick as many as you like.</span>
          <input type="file" multiple accept=".pdf,.html,.htm,.md,.markdown,.txt,application/pdf,text/*" onChange={(e) => { if (e.target.files) void uploadAll(e.target.files); e.target.value = ""; }} />
        </label>
        <form className="row" onSubmit={addLink}>
          <input value={link} onChange={(e) => setLink(e.target.value)} placeholder="Paste a link or a DOI (e.g. 10.1249/MSS.0000000000000939)" aria-label="Link or DOI" />
          <button className="primary" disabled={!!busy || !link.trim()}>Add</button>
        </form>
        <span className="muted">A DOI adds the citation (looked up on Crossref; only the DOI is sent). A link to an article or PDF is downloaded and converted. Publisher pages often block this; if so, download the PDF and drop it above.</span>
        <details>
          <summary>Type a citation by hand</summary>
          <form className="stack" onSubmit={addCitation} style={{ marginTop: 8 }}>
            <label>Title<input value={cite.title} onChange={(e) => setCite({ ...cite, title: e.target.value })} required /></label>
            <label>Authors (separate with ;)<input value={cite.authors} onChange={(e) => setCite({ ...cite, authors: e.target.value })} placeholder="Smith J; Jones A" /></label>
            <div className="row">
              <label>Year<input type="number" min={1800} max={2100} value={cite.year} onChange={(e) => setCite({ ...cite, year: e.target.value })} /></label>
              <label>Journal or publisher<input value={cite.venue} onChange={(e) => setCite({ ...cite, venue: e.target.value })} /></label>
            </div>
            <div className="row">
              <label>DOI<input value={cite.doi} onChange={(e) => setCite({ ...cite, doi: e.target.value })} /></label>
              <label>Link<input value={cite.url} onChange={(e) => setCite({ ...cite, url: e.target.value })} /></label>
            </div>
            <label>Type of evidence
              <select value={cite.evidence_type} onChange={(e) => setCite({ ...cite, evidence_type: e.target.value })}>
                <option value="">Not set</option>{data.evidence_types.map((t) => <option key={t}>{t}</option>)}
              </select>
            </label>
            <div><button className="primary" disabled={!!busy || !cite.title.trim()}>Add citation</button></div>
          </form>
        </details>
        <span className="muted">
          You can also copy files into the <code>ingest/inbox</code> folder in your data volume and press <button type="button" onClick={scan} disabled={!!busy}>Scan folder</button>
          {data.inbox_waiting > 0 && <> ({data.inbox_waiting} waiting)</>}. Files are converted when you do this or within a minute.
        </span>
        {busy && <span role="status">{busy}</span>}
        {msg && <span className="ok-text">{msg}</span>}
        {error && <span className="error">{error}</span>}
        {results.length > 0 && (
          <div className="stack" style={{ gap: 6 }}>
            {results.map((r, i) => (
              <div key={i} className="row" style={{ alignItems: "center", gap: 6 }}>
                {r.error ? <><span className="badge bad">not added</span><span className="error">{r.name}: {r.error}</span></> : r.item && (
                  <><span className={`badge ${r.item.duplicate ? "muted" : STATUS_CLASS[r.item.status]}`}>{r.item.duplicate ? "already in library" : STATUS_LABEL[r.item.status]}</span>
                    <a href={`#/library/${r.item.id}`}>{r.item.title}</a>
                    {r.item.status === "needs_ocr" && <span className="muted">scanned pages: original kept, no text yet</span>}</>
                )}
              </div>
            ))}
            <div><button type="button" onClick={() => setResults([])}>Clear this list</button></div>
          </div>
        )}
      </section>

      <section className="card wide">
        <div className="row between" style={{ alignItems: "center" }}>
          <h3 style={{ margin: 0 }}>Your sources ({data.total})</h3>
          <span className="chips">
            {([["all", "All"], ["attention", `Needs attention${attention ? ` (${attention})` : ""}`], ["unreviewed", "Not reviewed"]] as const).map(([k, label]) => (
              <button key={k} className={filter === k ? "active" : ""} onClick={() => setFilter(k)}>{label}</button>
            ))}
          </span>
        </div>
        <div className="row">
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search titles, authors, tags, notes and the full text" aria-label="Search the library" />
          {data.tags.length > 0 && (
            <select value={tag} onChange={(e) => setTag(e.target.value)} aria-label="Filter by tag">
              <option value="">All tags</option>{data.tags.map((t) => <option key={t}>{t}</option>)}
            </select>
          )}
        </div>
        {shown.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>{data.total === 0 ? "Nothing here yet. Drop a few papers above to start." : "No matches."}</p>
        ) : shown.map((it) => <ItemRow key={it.id} it={it} />)}
      </section>

      <details className="card wide">
        <summary>Sources the app cites ({refs.filter((r) => r.your_copy).length} of {refs.length} with your copy)</summary>
        <p className="muted">Attach your own copy of a paper the app relies on, so the full text sits next to your other sources. The app's own check of each paper is shown in Sources and credits.</p>
        {refs.map((r) => (
          <div key={r.id} className="libitem">
            <span className="title">{r.short}</span>
            <span className="muted">{r.title}</span>
            <span className="row" style={{ alignItems: "center", gap: 6 }}>
              {r.your_copy ? <a href={`#/library/${r.your_copy.id}`}>Open your copy ({STATUS_LABEL[r.your_copy.status]})</a> : (
                <label className="button" style={{ cursor: "pointer" }}>Attach my copy
                  <input type="file" hidden accept=".pdf,.html,.htm,.md,.markdown,.txt" onChange={(e) => { if (e.target.files) void uploadAll(e.target.files, r.id); e.target.value = ""; }} />
                </label>
              )}
              <a href={`#/references/${r.id}`}>how the app uses it</a>
            </span>
          </div>
        ))}
      </details>
    </div>
  );
}
