import { useEffect, useState } from "react";
import { api } from "../api";
import { Reference, VERIFIED_CLASS } from "../components/Cite";

export default function References({ focus }: { focus?: string }) {
  const [data, setData] = useState<{ verified_levels: Record<string, string>; references: Reference[] } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { api<{ verified_levels: Record<string, string>; references: Reference[] }>("/references").then(setData).catch((e) => setError(e.message)); }, []);
  useEffect(() => {
    if (data && focus) document.getElementById(`ref-${focus}`)?.scrollIntoView({ block: "start" });
  }, [data, focus]);
  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Loading…</p>;
  return (
    <div className="stack">
      <div>
        <h2 style={{ margin: 0 }}>References and credits</h2>
        <p className="muted" style={{ margin: "4px 0 0" }}>
          Use your data to train smarter, and always show the math. That includes crediting the people whose work the math comes from,
          and being honest about how well each source has been checked.
        </p>
      </div>
      <section className="card wide">
        <h3 style={{ margin: 0 }}>How well each source was checked</h3>
        {Object.entries(data.verified_levels).map(([k, v]) => (
          <div key={k}><span className={`badge ${k === "full_text" ? "ok" : "warn"}`}>{k.replace("_", " ")}</span> {v}</div>
        ))}
      </section>
      {data.references.map((r) => (
        <section key={r.id} id={`ref-${r.id}`} className={`card wide ${focus === r.id ? "focused" : ""}`}>
          <div className="row between" style={{ alignItems: "baseline" }}>
            <h3 style={{ margin: 0 }}>{r.short}</h3>
            <span className={`badge ${VERIFIED_CLASS[r.verified]}`}>{r.verified_label}</span>
          </div>
          <p style={{ margin: 0 }}>
            {r.authors}{r.year ? ` (${r.year})` : ""}. <em>{r.title}</em>. {r.venue}.
            {r.doi && <> doi:<a href={`https://doi.org/${r.doi}`} target="_blank" rel="noreferrer">{r.doi}</a></>}
            {r.url && <> <a href={r.url} target="_blank" rel="noreferrer">link</a></>}
          </p>
          <p className="muted" style={{ margin: 0 }}><strong>Checked:</strong> {r.verified_note}</p>
          <p style={{ margin: 0 }}>{r.your_copy ? <>Your copy: <a href={`#/library/${r.your_copy.id}`}>open it in the Library</a></> : <a href="#/library">Attach your own copy in the Library</a>}</p>
          <p style={{ margin: 0 }}><strong>Used for:</strong> {r.used_for.join("; ")}</p>
          <p style={{ margin: 0 }}><strong>How the app uses it:</strong> {r.how_used}</p>
          <p style={{ margin: 0 }}><strong>Limits:</strong> {r.limits}</p>
        </section>
      ))}
    </div>
  );
}
