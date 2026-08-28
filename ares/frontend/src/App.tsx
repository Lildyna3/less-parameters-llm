import { lazy, Suspense, useEffect, useState } from "react";
import { useAres } from "./store";
import { startWebSocket } from "./lib/ws";
import { api, getToken } from "./lib/api";
import { MobileNav, NavRail, StatusStrip, AccessGate } from "./components/Shell";
import Command from "./sections/Command";
import type { AccountSnapshot, Section } from "./lib/types";

/* Heavy, less-frequently-opened sections load on demand so first paint stays
   fast; the Command Center ships in the initial bundle because it is the
   landing experience. */
const Markets = lazy(() => import("./sections/Markets"));
const Chart = lazy(() => import("./sections/Chart"));
const News = lazy(() => import("./sections/News"));
const Positions = lazy(() => import("./sections/Positions"));
const Risk = lazy(() => import("./sections/Risk"));
const Analysis = lazy(() => import("./sections/Analysis"));
const Journal = lazy(() => import("./sections/Journal"));
const Settings = lazy(() => import("./sections/Settings"));

const SECTIONS: Record<Section, React.ComponentType> = {
  command: Command,
  markets: Markets,
  chart: Chart,
  news: News,
  positions: Positions,
  risk: Risk,
  analysis: Analysis,
  journal: Journal,
  settings: Settings,
};

/* Visited sections stay mounted and are hidden rather than unmounted, so the
   chart is never re-initialised and filters, scroll and selections survive
   navigation. Live data keeps flowing in the background either way. */
const visited = new Set<Section>();

function Loading() {
  return (
    <div className="flex h-full items-center justify-center">
      <span className="label breathe">Loading</span>
    </div>
  );
}

export default function App() {
  const { section, refreshStatus, setAccount } = useAres();
  const [locked, setLocked] = useState(false);
  const [checked, setChecked] = useState(false);

  visited.add(section);

  // Determine up front whether this deployment demands a token.
  useEffect(() => {
    let alive = true;
    void api.get("/api/status")
      .then(() => { if (alive) { setLocked(false); setChecked(true); } })
      .catch((error: { status?: number }) => {
        if (!alive) return;
        setLocked(error?.status === 401 && !getToken() ? true : error?.status === 401);
        setChecked(true);
      });
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (locked || !checked) return;
    startWebSocket();
    void refreshStatus();

    const loadAccount = () =>
      void api.get<{ paper: AccountSnapshot }>("/api/account")
        .then((data) => setAccount(data.paper))
        .catch(() => {});
    loadAccount();

    const statusTimer = setInterval(() => void refreshStatus(), 20_000);
    const accountTimer = setInterval(loadAccount, 12_000);
    return () => { clearInterval(statusTimer); clearInterval(accountTimer); };
  }, [locked, checked, refreshStatus, setAccount]);

  if (!checked) {
    return <div className="h-full bg-s0" />;
  }

  if (locked) {
    return <AccessGate onUnlock={() => { setLocked(false); }} />;
  }

  return (
    <div className="flex h-full flex-col bg-s0">
      <StatusStrip />
      <div className="flex min-h-0 flex-1">
        <NavRail />
        <main className="min-h-0 min-w-0 flex-1 pb-[52px] lg:pb-0">
          <Suspense fallback={<Loading />}>
            {(Object.keys(SECTIONS) as Section[]).map((id) => {
              if (!visited.has(id)) return null;
              const View = SECTIONS[id];
              return (
                <div key={id} className="h-full" style={{ display: id === section ? undefined : "none" }}>
                  <View />
                </div>
              );
            })}
          </Suspense>
        </main>
      </div>
      <MobileNav />
    </div>
  );
}
