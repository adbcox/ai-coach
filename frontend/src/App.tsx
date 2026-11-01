import { setUnits, Units, useUnits } from "./lib/units";
import { useCallback, useEffect, useState } from "react";
import { api, SessionInfo } from "./api";
import Activities from "./pages/Activities";
import ActivityDetail from "./pages/ActivityDetail";
import Auth from "./pages/Auth";
import Dashboard from "./pages/Dashboard";
import Predict from "./pages/Predict";
import Recovery from "./pages/Recovery";
import References from "./pages/References";
import Settings from "./pages/Settings";

const ICONS: Record<string, string> = {
  dashboard: "M3 13h8V3H3v10zm10 8h8V11h-8v10zM3 21h8v-6H3v6zM13 3v6h8V3h-8z",
  activities: "M4 6h16M4 12h16M4 18h10",
  predict: "M12 8v5l3 2M9 2h6M12 4a9 9 0 100 18 9 9 0 000-18z",
  recovery: "M3 12h4l3-8 4 16 3-8h4",
  settings: "M12 8a4 4 0 100 8 4 4 0 000-8zm8 4l2-1-2-3-2 .6a7 7 0 00-1.5-1L16 5h-4l-.5 2.6a7 7 0 00-1.5 1L8 8 6 11l2 1a7 7 0 000 2l-2 1 2 3 2-.6a7 7 0 001.5 1L12 22h4l.5-2.6a7 7 0 001.5-1l2 .6 2-3-2-1a7 7 0 000-2z",
};

function Icon({ name }: { name: string }) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={ICONS[name]} />
    </svg>
  );
}

type Route = { name: "dashboard" | "activities" | "predict" | "recovery" | "settings" } | { name: "activity"; id: number } | { name: "references"; id?: string };

function parseHash(): Route {
  const h = window.location.hash.replace(/^#\/?/, "");
  const m = h.match(/^activity\/(\d+)$/);
  if (m) return { name: "activity", id: Number(m[1]) };
  const r = h.match(/^references(?:\/([a-z0-9_]+))?$/);
  if (r) return { name: "references", id: r[1] };
  if (h === "activities" || h === "predict" || h === "recovery" || h === "settings") return { name: h };
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

  const tab = route.name === "activity" ? "activities" : route.name === "references" ? "settings" : route.name;
  return (
    <div className="shell">
      <header>
        <a className="brand" href="#/"><img src="/logo.svg" alt="" width="26" height="26" /><strong>Endurance Coach</strong></a>
        <nav>
          {(["dashboard", "activities", "predict", "recovery", "settings"] as const).map((t) => (
            <button key={t} className={tab === t ? "active" : ""} onClick={() => go(t === "dashboard" ? "" : t)}>
              {t === "predict" ? "Predict" : t[0].toUpperCase() + t.slice(1)}
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
        {route.name === "activity" && <ActivityDetail id={route.id} back={() => window.history.back()} />}
        {route.name === "predict" && <Predict goSettings={() => go("settings")} />}
        {route.name === "recovery" && <Recovery goSettings={() => go("settings")} />}
        {route.name === "references" && <References focus={route.id} />}
        {route.name === "settings" && <Settings onRestored={refresh} />}
      </main>
      <nav className="tabbar" aria-label="Main">
        {(["dashboard", "activities", "predict", "recovery", "settings"] as const).map((t) => (
          <button key={t} className={tab === t ? "active" : ""} onClick={() => go(t === "dashboard" ? "" : t)}>
            <Icon name={t} />
            <span>{t === "predict" ? "Predict" : t[0].toUpperCase() + t.slice(1)}</span>
          </button>
        ))}
      </nav>
    </div>
  );
}
