import { useCallback, useEffect, useState } from "react";
import { api, SessionInfo } from "./api";
import Activities from "./pages/Activities";
import Auth from "./pages/Auth";
import Settings from "./pages/Settings";

type Tab = "activities" | "settings";

export default function App() {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [tab, setTab] = useState<Tab>("activities");

  const refresh = useCallback(() => {
    api<SessionInfo>("/session").then(setSession).catch(() => setSession(null));
  }, []);
  useEffect(refresh, [refresh]);

  if (!session) return <main className="center">Loading…</main>;
  if (session.setup_required) return <Auth mode="setup" onDone={refresh} />;
  if (!session.authenticated) return <Auth mode="login" onDone={refresh} />;

  return (
    <div className="shell">
      <header>
        <strong>Endurance Coach</strong>
        <nav>
          <button className={tab === "activities" ? "active" : ""} onClick={() => setTab("activities")}>
            Activities
          </button>
          <button className={tab === "settings" ? "active" : ""} onClick={() => setTab("settings")}>
            Settings
          </button>
        </nav>
        <span className="spacer" />
        <span className="muted">{session.username}</span>
        <button onClick={() => api("/logout", "POST").then(refresh)}>Sign out</button>
      </header>
      <main>
        {tab === "activities" ? <Activities goSettings={() => setTab("settings")} /> : <Settings />}
      </main>
    </div>
  );
}
