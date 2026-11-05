import VersionBadge from "./components/VersionBadge";
import { setUnits, Units, useUnits } from "./lib/units";
import { useCallback, useEffect, useState } from "react";
import { api, SessionInfo } from "./api";
import Activities from "./pages/Activities";
import ActivityDetail from "./pages/ActivityDetail";
import Auth from "./pages/Auth";
import Dashboard from "./pages/Dashboard";
import Library from "./pages/Library";
import LibraryItem from "./pages/LibraryItem";
import Predict from "./pages/Predict";
import CoachChat from "./pages/CoachChat";
import ReadinessPage from "./pages/ReadinessPage";
import Recovery from "./pages/Recovery";
import References from "./pages/References";
import Settings from "./pages/Settings";
import TrainingLog from "./pages/TrainingLog";

const ICONS: Record<string, string> = {
  dashboard: "M3 13h8V3H3v10zm10 8h8V11h-8v10zM3 21h8v-6H3v6zM13 3v6h8V3h-8z",
  activities: "M4 6h16M4 12h16M4 18h10",
  log: "M8 2v4M16 2v4M3 10h18M5 6h14a2 2 0 012 2v12a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2z",
  readiness: "M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z",
  coach: "M21 12a9 9 0 11-18 0 9 9 0 0118 0zM8 11h.01M12 11h.01M16 11h.01M8 15c1.5 1 3 1.5 4 1.5s2.5-.5 4-1.5",
  predict: "M12 8v5l3 2M9 2h6M12 4a9 9 0 100 18 9 9 0 000-18z",
  recovery: "M3 12h4l3-8 4 16 3-8h4",
  library: "M4 4h5a3 3 0 013 3v13a2 2 0 00-2-2H4V4zm16 0h-5a3 3 0 00-3 3v13a2 2 0 012-2h6V4z",
  settings: "M12 8a4 4 0 100 8 4 4 0 000-8zm8 4l2-1-2-3-2 .6a7 7 0 00-1.5-1L16 5h-4l-.5 2.6a7 7 0 00-1.5 1L8 8 6 11l2 1a7 7 0 000 2l-2 1 2 3 2-.6a7 7 0 001.5 1L12 22h4l.5-2.6a7 7 0 001.5-1l2 .6 2-3-2-1a7 7 0 000-2z",
};

function Icon({ name }: { name: string }) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={ICONS[name]} />
    </svg>
  );
}

type Route = { name: "dashboard" | "activities" | "log" | "readiness" | "coach" | "predict" | "recovery" | "library" | "settings" } | { name: "activity"; id: number } | { name: "references"; id?: string } | { name: "libraryItem"; id: string };

function parseHash(): Route {
  const h = window.location.hash.replace(/^#\/?/, "");
  const m = h.match(/^activity\/(\d+)$/);
  if (m) return { name: "activity", id: Number(m[1]) };
  const r = h.match(/^references(?:\/([a-z0-9_]+))?$/);
  if (r) return { name: "references", id: r[1] };
  const li = h.match(/^library\/([a-z0-9][a-z0-9._-]*)$/);
  if (li) return { name: "libraryItem", id: li[1] };
  if (h === "activities" || h === "log" || h === "readiness" || h === "coach" || h === "predict" || h === "recovery" || h === "library" || h === "settings") return { name: h };
  return { name: "dashboard" };
}

export default function App() {
  useUnits();
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [route, setRoute] = useState<Route>(parseHash);

  const refresh = useCallback(() => {
    api<SessionInfo>("/session").then(setSession).catch(() => setSession(null));
  }, []);
  useEffect(refresh, [refresh]);
  const signedIn = !!session?.authenticated;
  useEffect(() => {
    if (signedIn) api<{ units: Units }>("/preferences").then((p) => setUnits(p.units)).catch(() => undefined);
  }, [signedIn]);
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

  const tab = route.name === "activity" ? "activities" : route.name === "references" ? "settings" : route.name === "libraryItem" ? "library" : route.name;
  return (
    <div className="shell">
      <header>
        <a className="brand" href="#/"><img src="/logo.svg" alt="" width="26" height="26" /><strong>Endurance Coach</strong><VersionBadge /></a>
        <nav>
          {(["dashboard", "activities", "log", "readiness", "coach", "library", "settings"] as const).map((t) => (
            <button key={t} className={tab === t ? "active" : ""} onClick={() => go(t === "dashboard" ? "" : t)}>
              {t[0].toUpperCase() + t.slice(1)}
            </button>
          ))}
        </nav>
        <span className="spacer" />
        <span className="muted hide-sm">{session.username}</span>
        <button onClick={() => api("/logout", "POST").then(refresh)}>Sign out</button>
      </header>
      <main>
        {route.name === "dashboard" && <Dashboard open={openActivity} goSettings={() => go("settings")} />}
        {route.name === "activities" && <Activities open={openActivity} goSettings={() => go("settings")} />}
        {route.name === "log" && <TrainingLog open={openActivity} />}
        {route.name === "readiness" && <ReadinessPage />}
        {route.name === "coach" && <CoachChat />}
        {route.name === "activity" && <ActivityDetail id={route.id} back={() => window.history.back()} />}
        {route.name === "predict" && <Predict goSettings={() => go("settings")} />}
        {route.name === "recovery" && <Recovery goSettings={() => go("settings")} />}
        {route.name === "references" && <References focus={route.id} />}
        {route.name === "library" && <Library />}
        {route.name === "libraryItem" && <LibraryItem id={route.id} />}
        {route.name === "settings" && <Settings onRestored={refresh} />}
      </main>
      <nav className="tabbar" aria-label="Main">
        {(["dashboard", "activities", "log", "readiness", "coach", "library", "settings"] as const).map((t) => (
          <button key={t} className={tab === t ? "active" : ""} onClick={() => go(t === "dashboard" ? "" : t)}>
            <Icon name={t} />
            <span>{t[0].toUpperCase() + t.slice(1)}</span>
          </button>
        ))}
      </nav>
    </div>
  );
}
