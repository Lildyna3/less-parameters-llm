import { useEffect, useState } from "react";
import { useAres } from "../store";
import { api } from "../lib/api";
import { StatusDot } from "./ui";

interface Sessions {
  utc_time: string;
  fx_market_open: boolean;
  active_sessions: string[];
  overlap: string | null;
}

export default function TopBar() {
  const { symbol, ticks, status, overall, account, theme, setTheme, wsConnected } = useAres();
  const [sessions, setSessions] = useState<Sessions | null>(null);
  const tick = ticks[symbol];

  useEffect(() => {
    const load = () =>
      api.get<{ sessions: Sessions }>("/api/status")
        .then((d) => setSessions(d.sessions))
        .catch(() => setSessions(null));
    load();
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, []);

  const mt5 = status?.mt5;
  const md = status?.market_data;

  return (
    <header className="flex h-12 shrink-0 items-center gap-4 border-b border-line bg-elev px-4">
      <div className="flex items-center gap-2">
        <div className="flex h-6 w-6 items-center justify-center rounded-md bg-accent/15 text-[13px] font-black text-accent">A</div>
        <span className="text-[14px] font-bold tracking-[0.18em]">ARES</span>
        <span className={`chip ${overall === "ONLINE" ? "!text-online" : overall === "DEGRADED" ? "!text-warn" : "!text-offline"}`}>
          {overall}
        </span>
      </div>

      <div className="hidden items-center gap-2 md:flex">
        <span className="text-[13px] font-bold num">{symbol}</span>
        {tick ? (
          <>
            <span className="text-[13px] font-semibold num text-ink">{tick.bid}</span>
            <span className="text-[11px] num text-faint">/ {tick.ask}</span>
            {tick.change_percent != null && (
              <span className={`text-[11px] font-semibold num ${tick.change_percent >= 0 ? "text-bull" : "text-bear"}`}>
                {tick.change_percent >= 0 ? "+" : ""}{tick.change_percent}%
              </span>
            )}
            {tick.source === "SIMULATED" && <span className="chip !text-warn">SIMULATED</span>}
          </>
        ) : (
          <span className="chip !text-offline">DATA SOURCE OFFLINE</span>
        )}
      </div>

      <div className="ml-auto flex items-center gap-3.5">
        {sessions && (
          <span className="hidden text-[11px] text-dim lg:block">
            {sessions.fx_market_open
              ? (sessions.overlap ?? sessions.active_sessions.join(" · ") ?? "FX open")
              : "FX market closed"}
          </span>
        )}
        {account && (
          <span className="hidden text-[11px] text-dim md:block num">
            {account.mode} · {account.equity.toFixed(0)} {account.currency}
          </span>
        )}
        <div className="flex items-center gap-2.5">
          <StatusDot state={mt5?.state} label="MT5" />
          <StatusDot state={md?.state} label="DATA" />
          <StatusDot state={status?.ai?.state} label="AI" />
          <StatusDot state={wsConnected ? "ONLINE" : "OFFLINE"} label="WS" />
        </div>
        <button
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className="rounded-md border border-line px-2 py-1 text-[11px] font-semibold text-dim hover:text-ink"
          title="Toggle theme"
        >
          {theme === "dark" ? "☀" : "☾"}
        </button>
      </div>
    </header>
  );
}
