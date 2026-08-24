import { useEffect } from "react";
import { useAres } from "./store";
import { startWebSocket } from "./lib/ws";
import { api } from "./lib/api";
import TopBar from "./components/TopBar";
import SideNav from "./components/SideNav";
import CommandCenter from "./sections/CommandCenter";
import Markets from "./sections/Markets";
import ChartSection from "./sections/ChartSection";
import Scanner from "./sections/Scanner";
import Positions from "./sections/Positions";
import Journal from "./sections/Journal";
import Analytics from "./sections/Analytics";
import News from "./sections/News";
import Settings from "./sections/Settings";
import type { AccountSnapshot, Section } from "./lib/types";

// Sections stay mounted once visited so expensive state (charts, scroll,
// filters) survives navigation. Only the active one is displayed.
const SECTIONS: Record<Section, React.ComponentType> = {
  command: CommandCenter,
  markets: Markets,
  chart: ChartSection,
  scanner: Scanner,
  positions: Positions,
  journal: Journal,
  analytics: Analytics,
  news: News,
  settings: Settings,
};

const visited = new Set<Section>();

export default function App() {
  const { section, refreshStatus, setAccount } = useAres();
  visited.add(section);

  useEffect(() => {
    startWebSocket();
    void refreshStatus();
    void api.get<{ paper: AccountSnapshot }>("/api/account")
      .then((d) => setAccount(d.paper)).catch(() => {});
    const id = setInterval(() => void refreshStatus(), 15_000);
    const accountId = setInterval(() => {
      void api.get<{ paper: AccountSnapshot }>("/api/account")
        .then((d) => setAccount(d.paper)).catch(() => {});
    }, 10_000);
    return () => { clearInterval(id); clearInterval(accountId); };
  }, [refreshStatus, setAccount]);

  return (
    <div className="flex h-full flex-col">
      <TopBar />
      <div className="flex min-h-0 flex-1">
        <SideNav />
        <main className="min-h-0 min-w-0 flex-1 pb-14 md:pb-0">
          {(Object.keys(SECTIONS) as Section[]).map((id) => {
            if (!visited.has(id)) return null;
            const Component = SECTIONS[id];
            return (
              <div key={id} className="h-full" style={{ display: id === section ? undefined : "none" }}>
                <Component />
              </div>
            );
          })}
        </main>
      </div>
    </div>
  );
}
