import { useCallback, useRef, useState } from "react";
import { api, CoachReply } from "../api";

type Turn = { role: "user" | "assistant"; text: string; meta?: CoachReply };

export default function CoachChat() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const send = useCallback(async () => {
    const question = q.trim();
    if (!question || busy) return;
    setQ(""); setErr(""); setBusy(true);
    setTurns((t) => [...t, { role: "user", text: question }]);
    try {
      const r = await api<CoachReply>("/coach/ask", "POST", { question });
      setTurns((t) => [...t, { role: "assistant", text: r.reply, meta: r }]);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  }, [q, busy]);

  return (
    <div className="chat">
      <section className="card">
        <h2 className="dash-h">Coach</h2>
        <p className="muted">
          Numbers come from tools against your own data. I'll never invent a figure.
        </p>
        <div className="chat-log">
          {turns.length === 0 && (
            <p className="muted">
              Try: "Why was yesterday's ride so costly?", "Is my form trending up or down?",
              "What should I do this weekend?"
            </p>
          )}
          {turns.map((t, i) => (
            <div key={i} className={`chat-turn chat-${t.role}`}>
              <span className="chat-role">{t.role === "user" ? "You" : "Coach"}</span>
              <pre className="chat-text">{t.text}</pre>
              {t.meta && (
                <span className="muted chat-meta">
                  {t.meta.model} · {t.meta.rounds} round{t.meta.rounds !== 1 ? "s" : ""} ·
                  {" "}{Math.round(t.meta.duration_ms / 100) / 10}s
                  {t.meta.tools_used.length > 0 && ` · tools: ${t.meta.tools_used.map((u) => u.tool).join(", ")}`}
                </span>
              )}
            </div>
          ))}
        </div>
        <div className="chat-input">
          <textarea
            ref={inputRef}
            rows={3}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); send(); }
            }}
            placeholder="Ask the coach — Cmd/Ctrl+Enter to send"
          />
          <button className="primary" disabled={busy || !q.trim()} onClick={send}>
            {busy ? "Thinking…" : "Send"}
          </button>
        </div>
        {err && <p className="error">{err}</p>}
      </section>
    </div>
  );
}
