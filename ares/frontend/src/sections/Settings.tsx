import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useAres } from "../store";
import { requestNotificationPermission } from "../lib/ws";
import { Empty, PanelTitle, StatusDot } from "../components/ui";

interface MT5Status {
  state: string;
  detection: {
    platform_supported: boolean;
    package_available: boolean;
    terminal_found: boolean;
    terminal_path: string | null;
    os: string;
    notes: string[];
  };
  credentials_configured: boolean;
  last_error: string | null;
  last_connected_at: string | null;
  account: {
    login_masked: string; broker: string; server: string; currency: string;
    balance: number; equity: number; is_demo: boolean;
  } | null;
}

interface RiskLimits {
  limits: Record<string, number | boolean>;
}

const LIMIT_FIELDS: { key: string; label: string }[] = [
  { key: "max_daily_loss", label: "Max daily loss" },
  { key: "max_drawdown_percent", label: "Max drawdown %" },
  { key: "max_open_positions", label: "Max open positions" },
  { key: "max_exposure_lots", label: "Max exposure (lots)" },
  { key: "max_trades_per_session", label: "Max trades / session" },
  { key: "max_position_size_lots", label: "Max position size (lots)" },
  { key: "max_spread_points", label: "Max spread (points)" },
  { key: "cooldown_seconds_after_loss", label: "Cooldown after loss (s)" },
];

export default function Settings() {
  const { theme, setTheme, status } = useAres();
  const [mt5, setMt5] = useState<MT5Status | null>(null);
  const [limits, setLimits] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    void api.get<{ mt5: MT5Status }>("/api/account").then((d) => setMt5(d.mt5)).catch(() => {});
    void api.get<RiskLimits>("/api/risk").then((d) => {
      const values: Record<string, string> = {};
      for (const f of LIMIT_FIELDS) values[f.key] = String(d.limits[f.key] ?? "");
      setLimits(values);
    }).catch(() => {});
  }, []);

  const saveLimits = async () => {
    const payload: Record<string, number> = {};
    for (const [k, v] of Object.entries(limits)) {
      const n = parseFloat(v);
      if (!Number.isNaN(n)) payload[k] = n;
    }
    await api.post("/api/risk/limits", payload);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="h-full space-y-3 overflow-y-auto p-3">
      <div className="panel mx-auto max-w-3xl">
        <PanelTitle right={<StatusDot state={status?.mt5?.state} />}>Connections · MetaTrader 5</PanelTitle>
        {mt5 ? (
          <div className="space-y-2.5 p-4 text-[12.5px]">
            <div className="flex items-center gap-2">
              <span className="font-bold">MT5</span>
              <span className={`chip ${mt5.state === "CONNECTED" ? "!text-online" : "!text-offline"}`}>
                {mt5.state === "CONNECTED" ? "● CONNECTED" : "● OFFLINE"}
              </span>
            </div>
            {mt5.account ? (
              <div className="grid grid-cols-2 gap-2 text-dim">
                <div>Broker: <span className="text-ink">{mt5.account.broker}</span></div>
                <div>Server: <span className="text-ink">{mt5.account.server}</span></div>
                <div>Account: <span className="num text-ink">{mt5.account.login_masked}</span></div>
                <div>Mode: <span className={mt5.account.is_demo ? "text-bull" : "text-warn"}>
                  {mt5.account.is_demo ? "DEMO" : "UNVERIFIED"}</span></div>
              </div>
            ) : (
              <div className="space-y-1.5 text-dim">
                <div className="grid gap-1 text-[11.5px]">
                  <div>OS: <span className="text-ink">{mt5.detection.os}</span></div>
                  <div>Terminal found: <span className="text-ink">{mt5.detection.terminal_found ? "yes" : "no"}</span></div>
                  <div>Python package: <span className="text-ink">{mt5.detection.package_available ? "installed" : "not installed"}</span></div>
                  <div>Credentials configured: <span className="text-ink">{mt5.credentials_configured ? "yes" : "no (set MT5_* in .env)"}</span></div>
                </div>
                {mt5.detection.notes.map((n, i) => (
                  <div key={i} className="rounded-lg bg-inset/70 px-2.5 py-1.5 text-[11px] text-faint">{n}</div>
                ))}
                {mt5.last_error && (
                  <div className="rounded-lg border border-warn/25 bg-warn/8 px-2.5 py-1.5 text-[11px] text-warn">{mt5.last_error}</div>
                )}
              </div>
            )}
            <div className="text-[10.5px] text-faint">
              Credentials live only in your local .env (MT5_LOGIN / MT5_PASSWORD / MT5_SERVER / MT5_PATH).
              The password is never shown, logged, or sent anywhere. ARES reconnects automatically.
            </div>
          </div>
        ) : <Empty>Backend offline.</Empty>}
      </div>

      <div className="panel mx-auto max-w-3xl">
        <PanelTitle>Risk Limits</PanelTitle>
        <div className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-2">
          {LIMIT_FIELDS.map((f) => (
            <label key={f.key} className="block">
              <span className="text-[10.5px] font-semibold uppercase tracking-wider text-faint">{f.label}</span>
              <input
                value={limits[f.key] ?? ""}
                onChange={(e) => setLimits({ ...limits, [f.key]: e.target.value })}
                className="mt-0.5 w-full rounded-md border border-line bg-inset px-2 py-1.5 text-[12px] num outline-none focus:border-accent/60"
              />
            </label>
          ))}
          <div className="sm:col-span-2">
            <button onClick={() => void saveLimits()}
              className="rounded-lg bg-accent/12 px-4 py-2 text-[11.5px] font-bold text-accent hover:bg-accent/20">
              {saved ? "Saved ✓" : "Save limits"}
            </button>
          </div>
        </div>
      </div>

      <div className="panel mx-auto max-w-3xl">
        <PanelTitle>Interface</PanelTitle>
        <div className="flex flex-wrap items-center gap-3 p-4">
          <div className="flex items-center gap-2">
            <span className="text-[12px] text-dim">Theme</span>
            <button onClick={() => setTheme("dark")}
              className={`rounded-md border px-3 py-1 text-[11.5px] font-semibold ${theme === "dark" ? "border-accent/60 text-accent" : "border-line text-dim"}`}>
              Dark
            </button>
            <button onClick={() => setTheme("light")}
              className={`rounded-md border px-3 py-1 text-[11.5px] font-semibold ${theme === "light" ? "border-accent/60 text-accent" : "border-line text-dim"}`}>
              Light
            </button>
          </div>
          <button onClick={requestNotificationPermission}
            className="rounded-md border border-line px-3 py-1 text-[11.5px] font-semibold text-dim hover:text-ink">
            Enable browser notifications
          </button>
        </div>
      </div>

      <div className="panel mx-auto max-w-3xl">
        <PanelTitle>Execution Safety</PanelTitle>
        <div className="p-4 text-[12px] leading-relaxed text-dim">
          ARES runs in <span className="font-bold text-ink">DEMO / PAPER mode</span>. Live-money execution does not
          exist in this build: the execution engine refuses orders even if the live flag is set, and Takeover Mode
          always requires your explicit authorization with hard limits (max trades, max loss, time limit) plus an
          emergency stop.
        </div>
      </div>
    </div>
  );
}
