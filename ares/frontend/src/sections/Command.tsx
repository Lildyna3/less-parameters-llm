import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { useAres } from "../store";
import type { MarketPulse } from "../lib/types";
import PriceChart from "../components/PriceChart";
import TakeoverPanel from "../components/TakeoverPanel";
import {
  Bias, Confidence, Empty, Impact, Metric, PanelHeader, Tag, Unavailable,
  ago, signed,
} from "../components/kit";

/* The Command Center: one spacious workspace. Market pulse across the top,
   the instrument and ARES's reading in the middle, the intelligence feed and
   command line on the right (below, on a phone). */

const PROMPTS = [
  "What should I watch today?",
  "Show me the strongest setups",
  "What's moving gold?",
  "Analyze XAUUSD",
  "Scan the market",
];

function PulseStrip({ pulse }: { pulse: MarketPulse | null }) {
  if (!pulse) {
    return (
      <div className="panel">
        <Empty>Reading market state…</Empty>
      </div>
    );
  }
  const { sessions } = pulse;
  const sessionText = sessions.fx_market_open
    ? (sessions.overlap ?? sessions.active_sessions.join(" · ") ?? "Open")
    : "FX market closed";

  return (
    <section className="panel">
      <PanelHeader
        dense
        right={
          <span className="label">
            {pulse.data_source ? `${pulse.quotes_live} live quotes · ${pulse.data_source}` : "No data source"}
          </span>
        }
      >
        Market Pulse
      </PanelHeader>
      <div className="grid grid-cols-2 gap-x-6 gap-y-5 p-4 sm:grid-cols-3 lg:grid-cols-5">
        <Metric
          label="Regime"
          value={<span className="text-[13px]">{pulse.regime ?? "—"}</span>}
          sub={pulse.regime ? undefined : "Run a scan to establish"}
        />
        <Metric
          label="Volatility"
          value={<span className="text-[13px]">{pulse.volatility ?? "—"}</span>}
          tone={pulse.volatility === "elevated" ? "bear" : undefined}
        />
        <Metric label="Session" value={<span className="text-[13px]">{sessionText}</span>} />
        <Metric
          label="Daily P/L"
          value={signed(pulse.account.daily_pl).text}
          tone={signed(pulse.account.daily_pl).tone}
          sub={`${pulse.account.open_positions} open`}
        />
        <Metric
          label="Equity"
          value={pulse.account.equity.toFixed(2)}
          sub={`${pulse.account.mode} · ${pulse.account.currency}`}
        />
      </div>

      {(pulse.movers.length > 0 || pulse.upcoming_events.length > 0) && (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-line px-4 py-2.5">
          {pulse.movers.length > 0 && (
            <>
              <span className="label">Movers</span>
              {pulse.movers.slice(0, 5).map((m) => (
                <span key={m.symbol} className="inline-flex items-baseline gap-1.5">
                  <span className="num text-[11.5px] text-dim">{m.symbol}</span>
                  <span className={`num text-[11.5px] ${
                    (m.change_percent ?? 0) > 0 ? "text-bull" : "text-bear"}`}>
                    {(m.change_percent ?? 0) > 0 ? "+" : ""}{m.change_percent}%
                  </span>
                </span>
              ))}
            </>
          )}
          {pulse.upcoming_events.length > 0 && (
            <span className="ml-auto inline-flex items-center gap-2">
              <span className="label">Next event</span>
              <span className="text-[11.5px] text-dim">
                {pulse.upcoming_events[0].currency} {pulse.upcoming_events[0].title}
              </span>
              <Tag tone={pulse.upcoming_events[0].impact === "high" ? "warn" : "muted"}>
                {pulse.upcoming_events[0].impact}
              </Tag>
            </span>
          )}
        </div>
      )}
    </section>
  );
}

function IntelligenceFeed() {
  const { chat, analysis, sendCommand, commandBusy } = useAres();
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Scroll the feed's own container, never the page: scrollIntoView would
    // drag the whole mobile layout when a reply arrives.
    if (chat.length === 0) return;
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [chat.length]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div ref={scrollRef} className="scroll-y min-h-0 flex-1 px-4 py-3">
        {chat.length === 0 && (
          <div className="rise">
            {analysis ? (
              <ReadingSummary />
            ) : (
              <p className="py-6 text-[12.5px] leading-relaxed text-faint">
                ARES is standing by. Ask about an instrument, the session, or where the
                strongest evidence sits. Execution stays in paper mode and always needs
                your explicit authorization.
              </p>
            )}
          </div>
        )}
        <div className="space-y-4 pb-1">
          {chat.map((message, index) => (
            <div key={index} className="rise">
              {message.role === "user" ? (
                <div className="flex justify-end">
                  <p className="max-w-[88%] rounded-md rounded-br-sm bg-s2 px-3 py-2 text-[12.5px] text-ink">
                    {message.text}
                  </p>
                </div>
              ) : (
                <div>
                  <div className="label mb-1.5 !text-accent">ARES</div>
                  <p className="whitespace-pre-wrap text-[12.5px] leading-[1.65] text-ink">
                    {message.text}
                  </p>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="border-t border-line p-3">
        <CommandLine />
        <div className="scroll-x mt-2 flex gap-1.5 pb-0.5">
          {PROMPTS.map((prompt) => (
            <button
              key={prompt}
              disabled={commandBusy}
              onClick={() => void sendCommand(prompt)}
              className="tag shrink-0 hover:!text-ink disabled:opacity-40"
            >
              {prompt}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function CommandLine() {
  const { sendCommand, commandBusy } = useAres();
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const submit = () => {
    if (!value.trim()) return;
    void sendCommand(value);
    setValue("");
  };

  return (
    <div className="flex items-center gap-2 rounded-md border border-line bg-s2 px-3 focus-within:border-[var(--accent-line)]">
      <span className="num text-[12px] text-accent">›</span>
      <input
        ref={inputRef}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => event.key === "Enter" && submit()}
        placeholder="Ask ARES…"
        aria-label="Command ARES"
        className="h-9 w-full bg-transparent text-[12.5px] text-ink outline-none placeholder:text-faint"
      />
      <kbd className="num hidden text-[9.5px] text-faint sm:block">⌘K</kbd>
      <button onClick={submit} disabled={commandBusy} className="btn-quiet h-7 px-2 text-[11px] font-semibold">
        {commandBusy ? "…" : "Send"}
      </button>
    </div>
  );
}

function ReadingSummary() {
  const { analysis, setSection } = useAres();
  if (!analysis) return null;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <span className="num text-[14px] font-semibold">{analysis.symbol}</span>
        <Bias bias={analysis.bias} />
        <Confidence score={analysis.confidence} />
        {analysis.data_source === "SIMULATED" && <Tag tone="warn">SIMULATED</Tag>}
      </div>
      <p className="text-[12.5px] leading-relaxed text-dim">{analysis.structure}.</p>
      {analysis.invalidations[0] && (
        <p className="text-[12px] leading-relaxed text-warn">
          Invalidation: {analysis.invalidations[0]}
        </p>
      )}
      <div className="flex flex-wrap gap-1.5">
        {analysis.key_levels.slice(0, 5).map((level, index) => (
          <span key={index} className={`tag num ${level.kind === "resistance" ? "!text-bear" : "!text-bull"}`}>
            {level.kind === "resistance" ? "R" : "S"} {level.price}
          </span>
        ))}
      </div>
      <button onClick={() => setSection("analysis")} className="btn-quiet h-7 px-0 text-[11.5px] !text-accent">
        Full analysis →
      </button>
    </div>
  );
}

function HeadlineRail({ pulse }: { pulse: MarketPulse | null }) {
  const { setSection } = useAres();
  const headlines = pulse?.news_headlines ?? [];
  return (
    <section className="panel flex min-h-0 flex-col">
      <PanelHeader
        dense
        right={
          <button onClick={() => setSection("news")} className="btn-quiet h-6 px-1.5 text-[11px] !text-accent">
            All news →
          </button>
        }
      >
        Headlines
      </PanelHeader>
      {headlines.length === 0 ? (
        <Unavailable
          what="News"
          reason="No source could be reached from this host. ARES shows nothing rather than inventing headlines."
        />
      ) : (
        <div className="divide-hair scroll-y min-h-0">
          {headlines.map((article) => (
            <button
              key={article.id}
              onClick={() => useAres.getState().openArticle(article.id)}
              className="block w-full px-4 py-2.5 text-left transition-colors hover:bg-s2"
            >
              <div className="flex items-center gap-2">
                <span className="label !tracking-[0.08em]">{article.source}</span>
                <span className="text-[10px] text-faint">{ago(article.published_at)}</span>
                <span className="ml-auto"><Impact level={article.impact} /></span>
              </div>
              <p className="mt-1 text-[12px] leading-snug text-ink">{article.title}</p>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

export default function Command() {
  const [pulse, setPulse] = useState<MarketPulse | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () => {
      void api.get<MarketPulse>("/api/pulse")
        .then((data) => { if (alive) setPulse(data); })
        .catch(() => { if (alive) setPulse(null); });
    };
    load();
    const id = setInterval(load, 15_000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  /* On a phone the page scrolls naturally. From xl up the workspace fills the
     viewport exactly and only the inner regions scroll, so the whole command
     surface is visible at once without the page moving. */
  return (
    <div className="scroll-y h-full xl:overflow-hidden">
      <div className="mx-auto flex max-w-[1600px] flex-col gap-4 p-4 pb-6 xl:h-full xl:pb-4">
        <div className="shrink-0">
          <PulseStrip pulse={pulse} />
        </div>

        <div className="grid grid-cols-1 gap-4 xl:min-h-0 xl:flex-1 xl:grid-cols-[1fr_400px]">
          <div className="flex flex-col gap-4 xl:min-h-0">
            <section className="panel h-[340px] overflow-hidden sm:h-[420px] xl:h-auto xl:min-h-0 xl:flex-1">
              <PriceChart />
            </section>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:h-[220px] xl:shrink-0">
              <StrongestSetups pulse={pulse} />
              <HeadlineRail pulse={pulse} />
            </div>
          </div>

          <div className="flex flex-col gap-4 xl:min-h-0">
            <section className="panel flex h-[520px] flex-col xl:h-auto xl:min-h-0 xl:flex-1">
              <PanelHeader dense>ARES Intelligence</PanelHeader>
              <IntelligenceFeed />
            </section>
            <div className="xl:shrink-0">
              <TakeoverPanel />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function StrongestSetups({ pulse }: { pulse: MarketPulse | null }) {
  const { setSymbol, setSection, sendCommand } = useAres();
  const setups = pulse?.strongest_setups ?? [];
  return (
    <section className="panel flex min-h-0 flex-col">
      <PanelHeader
        dense
        right={
          <button
            onClick={() => void sendCommand("Scan the market")}
            className="btn-quiet h-6 px-1.5 text-[11px] !text-accent"
          >
            Scan →
          </button>
        }
      >
        Strongest Evidence
      </PanelHeader>
      {setups.length === 0 ? (
        <Empty>
          {pulse?.scanned_at
            ? "No setup currently reaches 4/5 evidence."
            : "Run a market scan to rank setups by measurable evidence."}
        </Empty>
      ) : (
        <div className="divide-hair">
          {setups.map((row) => (
            <button
              key={row.symbol}
              onClick={() => { setSymbol(row.symbol); setSection("chart"); }}
              className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-s2"
            >
              <span className="num w-[68px] shrink-0 text-[12.5px] font-semibold">{row.symbol}</span>
              <Bias bias={row.bias} />
              <span className="ml-auto"><Confidence score={row.confidence} showLabel={false} /></span>
              <span className="label w-[62px] text-right">{row.volatility}</span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
