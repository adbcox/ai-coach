import { useCallback, useEffect, useState } from "react";
import { api, SessionInfo } from "./api";
import Activities from "./pages/Activities";
import ActivityDetail from "./pages/ActivityDetail";
import Auth from "./pages/Auth";
import Dashboard from "./pages/Dashboard";
import Recovery from "./pages/Recovery";
import Settings from "./pages/Settings";

type Route = { name: "dashboard" | "activities" | "recovery" | "settings" } | { name: "activity"; id: number };

function parseHash(): Route {
  const h = window.location.hash.replace(/^#\/?/, "");
  const m = h.match(/^activity\/(\d+)$/);
  if (m) return { name: "activity", id: Number(m[1]) };
  if (h === "activities" || h === "recovery" || h === "settings") return { name: h };
  return { name: "dashboard" };
}

export default function App() {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [route, setRoute] = useState<Route>(parseHash);

  const refresh = useCallback(() => {
    api<SessionInfo>("/session").then(setSession).catch(() => setSession(null));
  }, []);
  useEffect(refresh, [refresh]);
  useEffect(() => {
    const on = () => setRoute(parseHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  const go = (path: string) => { window.location.hash = `#/${path}`; };
  const openActivity = (id: number) => go(`activity/${id}`);

  if (!session) return <main className="center">Loading…</main>;
  if (session.setup_required) return <Auth mode="setup" onDone={refresh} />;
  if (!session.authenticated) return <Auth mode="login" onDone={refresh} />;

  const tab = route.name === "activity" ? "activities" : route.name;
  return (
    <div className="shell">
      <header>
        <a className="brand" href="#/"><img src="/logo.svg" alt="" width="26" height="26" /><strong>Endurance Coach</strong></a>
        <nav>
          {(["dashboard", "activities", "recovery", "settings"] as const).map((t) => (
            <button key={t} className={tab === t ? "active" : ""} onClick={() => go(t === "dashboard" ? "" : t)}>
              {t[0].toUpperCase() + t.slice(1)}
            </button>
          ))}
        </nav>
        <span className="spacer" />
        <span className="muted">{session.username}</span>
        <button onClick={() => api("/logout", "POST").then(refresh)}>Sign out</button>
      </header>
      <main>
        {route.name === "dashboard" && <Dashboard open={openActivity} goSettings={() => go("settings")} />}
        {route.name === "activities" && <Activities open={openActivity} goSettings={() => go("settings")} />}
        {route.name === "activity" && <ActivityDetail id={route.id} back={() => window.history.back()} />}
        {route.name === "recovery" && <Recovery goSettings={() => go("settings")} />}
        {route.name === "settings" && <Settings onRestored={refresh} />}
      </main>
    </div>
  );
}
