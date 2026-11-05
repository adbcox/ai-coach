import { Readiness } from "../api";

export default function ReadinessChip({ readiness }: { readiness: Readiness | null }) {
  if (!readiness || readiness.score == null) {
    return (
      <div className="readi">
        <span className="readi-label">Readiness</span>
        <span className="readi-score muted">—</span>
        <span className="readi-sub muted">
          Needs HRV / RHR / sleep + a check-in
        </span>
      </div>
    );
  }
  const band = readiness.band ?? "yellow";
  return (
    <div className={`readi band-${band}`}>
      <span className="readi-label">Readiness</span>
      <span className="readi-score">{readiness.score}</span>
      <span className="readi-sub">
        {band === "green" ? "ready" : band === "red" ? "back off" : "steady"}
      </span>
    </div>
  );
}
