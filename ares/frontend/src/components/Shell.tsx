import { useEffect, useState } from "react";
import { useAres } from "../store";
import { api, setToken } from "../lib/api";
import type { Section } from "../lib/types";
import { Dot, StatusPill } from "./kit";

/* Navigation. Desktop gets a slim labelled rail; mobile gets a bottom bar of
   the six areas that matter on a phone, with the rest behind "More". The two
   are separate layouts, not one squeezed into the other. */

interface NavItem { id: Section; label: string; short: string; }

const NAV: NavItem[] = [
  { id: "command", label: "Command", short: "Command" },
  { id: "markets", label: "Markets", short: "Markets" },
  { id: "chart", label: "Chart", short: "Chart" },
  { id: "news", label: "News", short: "News" },
  { id: "positions", label: "Positions", short: "Positions" },
  { id: "risk", label: "Risk", short: "Risk" },
  { id: "analysis", label: "Analysis", short: "Analysis" },
  { id: "journal", label: "Journal", short: "Journal" },
  { id: "settings", label: "Settings", short: "Settings" },
];

// Mobile priority order per the product brief.
const MOBILE_PRIMARY: Section[] = ["command", "markets", "chart", "news", "positions"];

export function NavRail() {
  const { section, setSection } = useAres();
  return (
    <nav className="hidden w-[168px] shrink-0 flex-col border-r border-line bg-s1 lg:flex">
      <div className="px-5 pb-4 pt-5">
        <div className="display text-[19px] leading-none tracking-[0.22em] text-ink">ARES</div>
        <div className="label mt-2 !text-[8.5px]">Executive Terminal</div>
      </div>
      <div className="flex flex-1 flex-col gap-px px-2">
        {NAV.map((item) => {
          const active = section === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setSection(item.id)}
              className={`group relative rounded-md px-3 py-[7px] text-left text-[12.5px] transition-colors ${
                active ? "bg-s2 text-ink" : "text-dim hover:bg-s2/60 hover:text-ink"
              }`}
            >
              <span
                className={`absolute left-0 top-1/2 h-3.5 w-[2px] -translate-y-1/2 rounded-full transition-opacity ${
                  active ? "bg-accent opacity-100" : "opacity-0"
                }`}
              />
              {item.label}
            </button>
          );
        })}
      </div>
      <SessionFooter />
    </nav>
  );
}

function SessionFooter() {
  const { status } = useAres();
  const news = status?.news;
  return (
    <div className="border-t border-line px-4 py-3">
      <div className="flex flex-col gap-1.5">
        <StatusPill label="Data" state={status?.market_data?.state} detail={status?.market_data?.reason} />
        <StatusPill label="MT5" state={status?.mt5?.state} detail={status?.mt5?.reason} />
        <StatusPill label="News" state={news?.state} detail={news?.reason} />
        <StatusPill label="AI" state={status?.ai?.state} detail={status?.ai?.reason} />
      </div>
    </div>
  );
}

export function MobileNav() {
  const { section, setSection } = useAres();
  const [moreOpen, setMoreOpen] = useState(false);
  const secondary = NAV.filter((n) => !MOBILE_PRIMARY.includes(n.id));

  return (
    <>
      {moreOpen && (
        <>
          <button
            aria-label="Close menu"
            onClick={() => setMoreOpen(false)}
            className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          />
          <div className="rise fixed inset-x-0 bottom-[calc(52px+env(safe-area-inset-bottom))] z-50 border-t border-line bg-s1 px-3 py-3 lg:hidden">
            <div className="label px-1 pb-2">More</div>
            <div className="grid grid-cols-3 gap-2">
              {secondary.map((item) => (
                <button
                  key={item.id}
                  onClick={() => { setSection(item.id); setMoreOpen(false); }}
                  className={`rounded-md border border-line px-2 py-3 text-[12px] ${
                    section === item.id ? "bg-s3 text-accent" : "bg-s2 text-dim"
                  }`}
                >
                  {item.short}
                </button>
              ))}
            </div>
          </div>
        </>
      )}

      <nav
        className="fixed inset-x-0 bottom-0 z-50 flex h-[52px] items-stretch border-t border-line bg-s1 lg:hidden"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        {MOBILE_PRIMARY.map((id) => {
          const item = NAV.find((n) => n.id === id)!;
          const active = section === id;
          return (
            <button
              key={id}
              onClick={() => { setSection(id); setMoreOpen(false); }}
              className="relative flex flex-1 flex-col items-center justify-center gap-1"
            >
              <span className={`h-[2px] w-5 rounded-full transition-opacity ${active ? "bg-accent" : "opacity-0"}`} />
              <span className={`text-[10.5px] font-medium ${active ? "text-ink" : "text-faint"}`}>
                {item.short}
              </span>
            </button>
          );
        })}
        <button
          onClick={() => setMoreOpen((v) => !v)}
          className="relative flex flex-1 flex-col items-center justify-center gap-1"
        >
          <span className={`h-[2px] w-5 rounded-full ${moreOpen ? "bg-accent" : "opacity-0"}`} />
          <span className={`text-[10.5px] font-medium ${moreOpen ? "text-ink" : "text-faint"}`}>More</span>
        </button>
      </nav>
    </>
  );
}

/* The status strip: identity, the live instrument, and the honest state of
   every dependency — the first thing an operator reads. */
export function StatusStrip() {
  const { symbol, ticks, status, account, theme, setTheme, wsConnected, setSection } = useAres();
  const tick = ticks[symbol];
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(id);
  }, []);

  const mt5 = status?.mt5;
  const change = tick?.change_percent;

  return (
    <header className="flex h-[52px] shrink-0 items-center gap-4 border-b border-line bg-s1 px-4">
      <div className="flex items-baseline gap-2 lg:hidden">
        <span className="display text-[16px] tracking-[0.2em]">ARES</span>
      </div>

      <button
        onClick={() => setSection("chart")}
        className="flex min-w-0 items-baseline gap-2.5 text-left"
        title="Open the chart workspace"
      >
        <span className="num text-[13px] font-semibold tracking-wide">{symbol}</span>
        {tick ? (
          <>
            <span className="num text-[15px] text-ink">{tick.bid}</span>
            {change != null && (
              <span className={`num text-[11.5px] ${change > 0 ? "text-bull" : change < 0 ? "text-bear" : "text-dim"}`}>
                {change > 0 ? "+" : ""}{change}%
              </span>
            )}
          </>
        ) : (
          <span className="label !text-offline">No live quote</span>
        )}
      </button>

      {tick?.source === "SIMULATED" && (
        <span className="tag !text-warn hidden sm:inline-flex" title="Simulated demo feed — not live market prices">
          SIMULATED
        </span>
      )}

      <div className="ml-auto flex items-center gap-4">
        <span className="num hidden text-[11px] text-faint md:inline">
          {now.toISOString().slice(11, 16)} UTC
        </span>
        {account && (
          <button onClick={() => setSection("risk")} className="hidden items-center gap-2 md:flex">
            <span className="label">{account.mode}</span>
            <span className="num text-[12px] text-ink">
              {account.equity.toFixed(2)} {account.currency}
            </span>
          </button>
        )}
        <button
          onClick={() => setSection("settings")}
          className="flex items-center gap-2.5"
          title={mt5?.reason}
        >
          <span className="hidden items-center gap-1.5 sm:flex">
            <Dot state={mt5?.state} /><span className="label !text-[9.5px]">MT5</span>
          </span>
          <span className="flex items-center gap-1.5">
            <Dot state={wsConnected ? "ONLINE" : "OFFLINE"} /><span className="label !text-[9.5px]">Live</span>
          </span>
        </button>
        <button
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className="btn-quiet h-7 rounded-md px-2 text-[13px]"
          title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
        >
          {theme === "dark" ? "☀" : "☾"}
        </button>
      </div>
    </header>
  );
}

/* Access gate: shown only when the server actually requires a token. The
   token is stored locally by the browser, never bundled into the app. */
export function AccessGate({ onUnlock }: { onUnlock: () => void }) {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!value.trim()) return;
    setBusy(true);
    setError(null);
    setToken(value.trim());
    try {
      await api.get("/api/status");
      onUnlock();
    } catch {
      setToken(null);
      setError("That token was rejected.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full items-center justify-center bg-s0 px-6">
      <div className="w-full max-w-[320px]">
        <div className="display text-[26px] tracking-[0.24em]">ARES</div>
        <p className="mt-3 text-[12.5px] leading-relaxed text-dim">
          This terminal is protected. Enter your access token to continue.
        </p>
        <input
          type="password"
          value={value}
          autoFocus
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void submit()}
          placeholder="Access token"
          className="field mt-5"
        />
        {error && <p className="mt-2 text-[11.5px] text-danger">{error}</p>}
        <button onClick={() => void submit()} disabled={busy} className="btn btn-accent mt-3 w-full">
          {busy ? "Verifying…" : "Unlock"}
        </button>
        <p className="mt-4 text-[10.5px] leading-relaxed text-faint">
          The token is stored only in this browser and sent with each request.
          It is never included in the application bundle.
        </p>
      </div>
    </div>
  );
}
