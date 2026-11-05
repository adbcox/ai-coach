import { useCallback, useState } from "react";
import { api, SuggestedWorkout } from "../api";

function fmtCluster(c: string): string {
  return c.replace(/^(\w)/, (m) => m.toUpperCase());
}

function candLabel(cand: NonNullable<SuggestedWorkout["primary"]>): string {
  const fam = cand.family.replace("_", " ");
  return `${fam} · ${fmtCluster(cand.cluster)} · ${Math.round(cand.duration_min)} min`;
}

export default function SuggestedWorkoutCard({ suggest, note, onFeedback }: {
  suggest: SuggestedWorkout | null;
  note: string | null;
  onFeedback?: () => void;
}) {
  const [action, setAction] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const send = useCallback(async (user_action: "did_it" | "swapped" | "ignored") => {
    setBusy(true); setErr("");
    try {
      await api("/suggest/today", "POST", { user_action });
      setAction(user_action);
      onFeedback?.();
    } catch (e) {
      setErr((e as Error).message);
    } finally { setBusy(false); }
  }, [onFeedback]);

  if (!suggest || !suggest.primary) {
    return (
      <section className="card swo-card">
        <div className="swo-head">
          <span className="swo-eyebrow">Today's workout</span>
          <h2>Building your routine…</h2>
        </div>
        <p className="muted">
          {suggest?.reason ??
            "Once your activities are in and the nightly job runs, a suggestion lands here."}
        </p>
      </section>
    );
  }

  const p = suggest.primary;
  const alt = suggest.alternative;

  const reasons: string[] = [];
  if (p.components.w1_weekday > 0.3) reasons.push(`matches your usual ${["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][new Date(suggest.day + "T12:00:00Z").getUTCDay()]} ${p.family.replace("_"," ")} · n=${p.n_history}`);
  if (p.components.w3_prelude > 0.5) reasons.push(`fits what came before (3d+7d TSS)`);
  if (suggest.context?.band) reasons.push(`readiness ${suggest.context.band}${suggest.context?.tsb_prev != null ? ` · form ${suggest.context.tsb_prev > 0 ? "+" : ""}${suggest.context.tsb_prev.toFixed(0)}` : ""}`);
  for (const n of p.notes) reasons.push(n);

  return (
    <section className="card swo-card">
      <div className="swo-head">
        <span className="swo-eyebrow">Today's workout</span>
        {suggest.low_confidence && <span className="pill warn">history is thin</span>}
      </div>
      <div className="swo-main">
        <div className="swo-primary">
          <h2>{candLabel(p)}</h2>
          <div className="swo-sub">
            <span>{Math.round(p.tss)} TSS</span>
            {p.has_intervals && <span>· intervals</span>}
          </div>
          <ul className="swo-reasons">
            {reasons.slice(0, 3).map((r, i) => <li key={i}>{r}</li>)}
          </ul>
          <div className="swo-actions">
            {(["did_it", "swapped", "ignored"] as const).map((a) => (
              <button key={a}
                className={action === a ? "active primary" : ""}
                disabled={busy || !!action}
                onClick={() => send(a)}>
                {a === "did_it" ? "Did it" : a === "swapped" ? "Did something different" : "Skipped"}
              </button>
            ))}
          </div>
          {err && <span className="error">{err}</span>}
          {action && <span className="muted">Thanks — recorded.</span>}
        </div>
        {alt && (
          <div className="swo-alt">
            <span className="swo-eyebrow">Easier alternative</span>
            <h3>{candLabel(alt)}</h3>
            <div className="swo-sub">
              <span>{Math.round(alt.tss)} TSS</span>
            </div>
          </div>
        )}
      </div>
      {note && <p className="swo-note">{note}</p>}
    </section>
  );
}
