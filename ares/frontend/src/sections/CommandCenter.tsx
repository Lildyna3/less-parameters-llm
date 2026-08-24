import { useEffect, useRef, useState } from "react";
import { useAres } from "../store";
import PriceChart from "../components/PriceChart";
import AnalysisCard from "../components/AnalysisCard";
import TakeoverPanel from "../components/TakeoverPanel";
import { Confidence, Empty, PanelTitle, Stat, pl } from "../components/ui";

const SUGGESTIONS = [
  "Analyze XAUUSD", "Scan the market", "Show my positions",
  "What session is it?", "Show risk", "Compare EURUSD and GBPUSD",
];

function CommandInput() {
  const { sendCommand, commandBusy } = useAres();
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const submit = () => {
    if (!value.trim()) return;
    void sendCommand(value);
    setValue("");
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="border-t border-line bg-elev p-3">
      <div className="flex items-center gap-2 rounded-xl border border-line-strong bg-inset px-3 py-2 focus-within:border-accent/60">
        <span className="text-[13px] font-black text-accent">›</span>
        <input
          ref={inputRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder='Command ARES — "Analyze XAUUSD", "Scan the market"…  (Ctrl+K)'
          className="w-full bg-transparent text-[13px] text-ink outline-none placeholder:text-faint"
        />
        <button
          onClick={submit}
          disabled={commandBusy}
          className="rounded-lg bg-accent/15 px-3 py-1 text-[11.5px] font-bold text-accent disabled:opacity-40"
        >
          {commandBusy ? "…" : "RUN"}
        </button>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {SUGGESTIONS.map((s) => (
          <button key={s} onClick={() => void useAres.getState().sendCommand(s)}
            className="chip hover:!text-ink" disabled={commandBusy}>
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

function ChatFeed() {
  const chat = useAres((s) => s.chat);
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), [chat.length]);

  if (chat.length === 0) {
    return (
      <Empty>
        ARES is standing by. Ask about any instrument, scan the market, or check risk.
        <br />Execution stays in DEMO/PAPER mode and always requires your authorization.
      </Empty>
    );
  }
  return (
    <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3.5">
      {chat.map((m, i) => (
        <div key={i} className={`fade-up ${m.role === "user" ? "flex justify-end" : ""}`}>
          {m.role === "user" ? (
            <div className="max-w-[85%] rounded-xl rounded-br-sm bg-accent/12 px-3 py-2 text-[12.5px] text-ink">
              {m.text}
            </div>
          ) : (
            <div className="max-w-[95%]">
              <div className="mb-0.5 text-[10px] font-bold tracking-[0.15em] text-accent">ARES</div>
              <div className="whitespace-pre-wrap rounded-xl rounded-tl-sm border border-line bg-inset/50 px-3 py-2 text-[12.5px] leading-relaxed text-ink">
                {m.text}
              </div>
            </div>
          )}
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}

function BriefingPanel() {
  const { analysis, account, alerts } = useAres();
  const daily = pl(account?.daily_pl);
  const floating = pl(account?.floating_pl);

  return (
    <div className="flex min-h-0 flex-col gap-3 overflow-y-auto">
      <div className="panel">
        <PanelTitle>Account · Risk</PanelTitle>
        {account ? (
          <div className="grid grid-cols-2 gap-3 p-3.5 sm:grid-cols-4">
            <Stat label="Equity" value={account.equity.toFixed(2)} sub={account.currency} />
            <Stat label="Floating" value={floating.text} tone={floating.tone} />
            <Stat label="Daily P/L" value={daily.text} tone={daily.tone} />
            <Stat label="Drawdown" value={`${account.drawdown_percent}%`} />
          </div>
        ) : <Empty>Waiting for account data…</Empty>}
      </div>

      <div className="panel">
        <PanelTitle right={analysis ? <Confidence score={analysis.confidence} size="sm" /> : undefined}>
          ARES Briefing
        </PanelTitle>
        {analysis
          ? <AnalysisCard analysis={analysis} />
          : <Empty>No analysis yet — try “Analyze EURUSD”.</Empty>}
      </div>

      <TakeoverPanel />

      <div className="panel">
        <PanelTitle>Alerts</PanelTitle>
        {alerts.length === 0 ? <Empty>No alerts.</Empty> : (
          <div className="max-h-44 overflow-y-auto">
            {alerts.slice(0, 12).map((a) => (
              <div key={a.id} className="flex items-start gap-2 border-b border-line/60 px-3.5 py-2 text-[11.5px] last:border-0">
                <span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${
                  a.severity === "danger" ? "bg-danger" : a.severity === "warning" ? "bg-warn" : "bg-accent"}`} />
                <div>
                  <div className="text-dim">{a.message}</div>
                  <div className="text-[10px] text-faint">{a.at.replace("T", " ").slice(0, 19)} UTC</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function CommandCenter() {
  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-3 p-3 xl:grid-cols-[1fr_420px]">
      <div className="flex min-h-0 flex-col gap-3">
        <div className="panel min-h-[280px] flex-[3] overflow-hidden">
          <PriceChart />
        </div>
        <div className="panel flex min-h-[220px] flex-[2] flex-col overflow-hidden">
          <PanelTitle>Command Center</PanelTitle>
          <ChatFeed />
          <CommandInput />
        </div>
      </div>
      <div className="hidden min-h-0 xl:block">
        <BriefingPanel />
      </div>
    </div>
  );
}
