import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import { useAres } from "../store";
import type {
  BrokerDeal, BrokerPosition, ExecutionResult, PreTradeResult,
} from "../lib/types";
import { Empty, PanelHeader, Tag, price, signed } from "../components/kit";

/* The one place in ARES that can send an order to a broker.
 *
 * Two deliberate frictions sit between an intention and a fill:
 *   1. Nothing is sent until the pre-trade check has run and come back READY.
 *      The check itself places nothing — it validates against the broker's own
 *      limits and returns per-item reasons.
 *   2. "Place order" arms a confirmation; a second, separate press sends it.
 *
 * Success is reported only when MT5 returns a ticket. A rejection shows the
 * broker's own retcode and comment rather than a friendly paraphrase. */

type Direction = "buy" | "sell";

function numberOrNull(raw: string): number | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

function CheckList({ check }: { check: PreTradeResult }) {
  return (
    <div className="border-t border-line">
      <div className="flex items-center gap-2 px-4 py-2.5">
        <Tag tone={check.ready ? "accent" : "muted"}>
          {check.verdict}
        </Tag>
        <span className="text-[11.5px] text-faint">
          {check.ready
            ? "Every pre-trade condition passed. Nothing has been sent yet."
            : `${check.blocked_by.length} condition${check.blocked_by.length === 1 ? "" : "s"} blocking.`}
        </span>
      </div>
      <div className="divide-hair border-t border-line">
        {check.items.map((item) => (
          <div key={item.name} className="flex items-start gap-3 px-4 py-2">
            <span
              className={`num mt-px w-4 shrink-0 text-[12px] font-bold ${
                item.ok ? "text-bull" : "text-bear"
              }`}
              aria-hidden
            >
              {item.ok ? "✓" : "✕"}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-[12px] font-semibold">{item.name}</span>
              <span className="block text-[11px] text-faint">{item.detail}</span>
            </span>
          </div>
        ))}
      </div>
      {check.plan.entry != null && (
        <div className="flex flex-wrap gap-x-5 gap-y-1 border-t border-line px-4 py-2.5 text-[11px] text-faint">
          <span>entry <span className="num text-dim">{price(check.plan.entry)}</span></span>
          {check.plan.volume != null && (
            <span>size <span className="num text-dim">{check.plan.volume} lots</span></span>
          )}
          {check.plan.risk_reward != null && (
            <span>R:R <span className="num text-dim">1 : {check.plan.risk_reward}</span></span>
          )}
          {check.plan.margin_required != null && (
            <span>margin <span className="num text-dim">{check.plan.margin_required}</span></span>
          )}
          {check.plan.broker && <span>{check.plan.broker}</span>}
          {check.plan.account_mode && <Tag>{check.plan.account_mode}</Tag>}
        </div>
      )}
    </div>
  );
}

function Outcome({ result }: { result: ExecutionResult }) {
  return (
    <div className="border-t border-line px-4 py-3">
      <div className="flex items-center gap-2">
        <Tag tone={result.success ? "accent" : "muted"}>
          {result.success ? "FILLED BY MT5" : "NOT EXECUTED"}
        </Tag>
        {result.ticket != null && (
          <span className="num text-[11.5px] text-dim">ticket #{result.ticket}</span>
        )}
        {result.retcode != null && (
          <span className="num text-[11px] text-faint">retcode {result.retcode}</span>
        )}
      </div>
      <p className="mt-1.5 text-[11.5px] text-dim">{result.message}</p>
      {result.broker_comment && (
        <p className="mt-1 text-[11px] text-faint">
          Broker comment: <span className="num">{result.broker_comment}</span>
        </p>
      )}
      {result.position && (
        <p className="num mt-1 text-[11px] text-faint">
          Read back from the terminal: {result.position.direction.toUpperCase()}{" "}
          {result.position.volume} {result.position.symbol} @ {price(result.position.entry)}
        </p>
      )}
    </div>
  );
}

export default function ExecutionTicket() {
  const { symbol, ticks } = useAres();
  const [direction, setDirection] = useState<Direction>("buy");
  const [volume, setVolume] = useState("0.01");
  const [sl, setSl] = useState("");
  const [tp, setTp] = useState("");
  const [check, setCheck] = useState<PreTradeResult | null>(null);
  const [result, setResult] = useState<ExecutionResult | null>(null);
  const [armed, setArmed] = useState(false);
  const [busy, setBusy] = useState<"check" | "send" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const tick = ticks[symbol];

  // Any change to the ticket invalidates a previous check. Nothing may be sent
  // on the strength of a check that described a different order.
  useEffect(() => {
    setCheck(null);
    setResult(null);
    setArmed(false);
    setError(null);
  }, [symbol, direction, volume, sl, tp]);

  const body = () => ({
    symbol,
    direction,
    volume: numberOrNull(volume) ?? 0,
    sl: numberOrNull(sl),
    tp: numberOrNull(tp),
  });

  const runCheck = async () => {
    setBusy("check");
    setError(null);
    try {
      setCheck(await api.post<PreTradeResult>("/api/mt5/order/check", body()));
    } catch (err) {
      setCheck(null);
      setError(err instanceof ApiError ? err.message : "The backend could not be reached.");
    } finally {
      setBusy(null);
    }
  };

  const send = async () => {
    setBusy("send");
    setError(null);
    try {
      const outcome = await api.post<ExecutionResult>("/api/mt5/order", {
        ...body(), confirm: true, comment: "ARES ticket",
      });
      setResult(outcome);
      if (outcome.check) setCheck(outcome.check);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The backend could not be reached.");
    } finally {
      setBusy(null);
      setArmed(false);
    }
  };

  return (
    <section className="panel">
      <PanelHeader right={<Tag>DEMO ONLY</Tag>}>Execution Ticket · {symbol}</PanelHeader>

      <div className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-4">
        <label className="flex flex-col gap-1">
          <span className="label">Direction</span>
          <div className="flex gap-1">
            {(["buy", "sell"] as Direction[]).map((side) => (
              <button
                key={side}
                onClick={() => setDirection(side)}
                className={`btn h-8 flex-1 ${
                  direction === side
                    ? side === "buy" ? "!text-bull" : "!text-bear"
                    : "!text-faint"
                }`}
                aria-pressed={direction === side}
              >
                {side.toUpperCase()}
              </button>
            ))}
          </div>
        </label>
        <label className="flex flex-col gap-1">
          <span className="label">Volume (lots)</span>
          <input
            className="field num h-8"
            inputMode="decimal"
            value={volume}
            onChange={(e) => setVolume(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="label">Stop loss</span>
          <input
            className="field num h-8"
            inputMode="decimal"
            placeholder="none"
            value={sl}
            onChange={(e) => setSl(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="label">Take profit</span>
          <input
            className="field num h-8"
            inputMode="decimal"
            placeholder="none"
            value={tp}
            onChange={(e) => setTp(e.target.value)}
          />
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-3">
        <span className="num text-[11.5px] text-faint">
          {tick
            ? `bid ${price(tick.bid)} · ask ${price(tick.ask)}`
            : "no live quote for this instrument"}
        </span>
        <div className="ml-auto flex gap-2">
          <button onClick={() => void runCheck()} disabled={busy !== null} className="btn h-8">
            {busy === "check" ? "Checking…" : "Run pre-trade check"}
          </button>
          {!armed ? (
            <button
              onClick={() => setArmed(true)}
              disabled={busy !== null || !check?.ready}
              title={
                check?.ready
                  ? "Arms a confirmation. Nothing is sent yet."
                  : "Run the pre-trade check first; it must come back READY."
              }
              className="btn h-8"
            >
              Place order
            </button>
          ) : (
            <>
              <button onClick={() => setArmed(false)} className="btn-quiet h-8 px-2 text-[11px]">
                Cancel
              </button>
              <button
                onClick={() => void send()}
                disabled={busy !== null}
                className="btn h-8 !text-accent"
              >
                {busy === "send"
                  ? "Sending to MT5…"
                  : `Confirm ${direction.toUpperCase()} ${numberOrNull(volume) ?? "?"} ${symbol}`}
              </button>
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="border-t border-line px-4 py-2.5 text-[11.5px] text-offline">{error}</div>
      )}
      {check && <CheckList check={check} />}
      {result && <Outcome result={result} />}
      {!check && !result && !error && (
        <Empty>
          The check validates the order against your broker's own limits — volume step, stop
          distance, margin, spread — and places nothing.
        </Empty>
      )}
    </section>
  );
}

/** Positions and closed deals as the terminal reports them, kept separate from
    ARES's own paper book so the two are never confused for each other. */
export function BrokerBook() {
  const [positions, setPositions] = useState<BrokerPosition[]>([]);
  const [deals, setDeals] = useState<BrokerDeal[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  const load = async () => {
    try {
      const [open, history] = await Promise.all([
        api.get<{ positions: BrokerPosition[]; message: string | null }>("/api/mt5/positions"),
        api.get<{ deals: BrokerDeal[] }>("/api/mt5/history?hours=72"),
      ]);
      setPositions(open.positions);
      setDeals(history.deals);
      setMessage(open.message);
    } catch {
      setPositions([]);
      setDeals([]);
      setMessage("The ARES backend is not reachable from this browser.");
    }
  };

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 5000);
    return () => clearInterval(id);
  }, []);

  const close = async (ticket: number) => {
    setBusy(ticket);
    try {
      await api.post("/api/mt5/position/close", { ticket, confirm: true });
    } catch { /* the reload below shows whether it actually closed */ }
    setBusy(null);
    void load();
  };

  return (
    <>
      <section className="panel">
        <PanelHeader right={<Tag>{positions.length} at broker</Tag>}>
          Broker Positions (MT5)
        </PanelHeader>
        {positions.length === 0 ? (
          <Empty>{message ?? "No open positions at the broker."}</Empty>
        ) : (
          <div className="scroll-x">
            <table className="table">
              <thead>
                <tr>
                  <th>Ticket</th><th>Instrument</th><th>Side</th>
                  <th className="text-right">Size</th><th className="text-right">Entry</th>
                  <th className="text-right">Current</th><th className="text-right">Stop</th>
                  <th className="text-right">Target</th><th className="text-right">Profit</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => {
                  const pl = signed(p.profit);
                  return (
                    <tr key={p.ticket}>
                      <td className="num text-faint">#{p.ticket}</td>
                      <td className="num font-semibold">{p.symbol}</td>
                      <td className={p.direction === "buy" ? "text-bull" : "text-bear"}>
                        {p.direction.toUpperCase()}
                      </td>
                      <td className="num text-right">{p.volume}</td>
                      <td className="num text-right">{price(p.entry)}</td>
                      <td className="num text-right text-dim">{price(p.current_price)}</td>
                      <td className="num text-right text-faint">
                        {p.sl != null ? price(p.sl) : "—"}
                      </td>
                      <td className="num text-right text-faint">
                        {p.tp != null ? price(p.tp) : "—"}
                      </td>
                      <td className={`num text-right font-semibold ${
                        pl.tone === "bull" ? "text-bull" : pl.tone === "bear" ? "text-bear" : "text-faint"}`}>
                        {pl.text}
                      </td>
                      <td className="text-right">
                        <button
                          onClick={() => void close(p.ticket)}
                          disabled={busy === p.ticket}
                          className="btn h-7 !text-bear"
                        >
                          {busy === p.ticket ? "Closing…" : "Close"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel">
        <PanelHeader>Broker Deals · last 72h</PanelHeader>
        {deals.length === 0 ? (
          <Empty>
            No closed deals returned. Either none exist in this window, or MT5 is not connected.
          </Empty>
        ) : (
          <div className="scroll-x">
            <table className="table">
              <thead>
                <tr>
                  <th>Closed</th><th>Instrument</th><th>Side</th>
                  <th className="text-right">Size</th><th className="text-right">Price</th>
                  <th className="text-right">Profit</th>
                </tr>
              </thead>
              <tbody>
                {deals.map((d) => {
                  const pl = signed(d.profit);
                  return (
                    <tr key={d.ticket}>
                      <td className="num text-faint">
                        {d.closed_at.slice(5, 16).replace("T", " ")}
                      </td>
                      <td className="num font-semibold">{d.symbol}</td>
                      <td className={d.direction === "buy" ? "text-bull" : "text-bear"}>
                        {d.direction.toUpperCase()}
                      </td>
                      <td className="num text-right">{d.volume}</td>
                      <td className="num text-right">{price(d.price)}</td>
                      <td className={`num text-right font-semibold ${
                        pl.tone === "bull" ? "text-bull" : pl.tone === "bear" ? "text-bear" : "text-faint"}`}>
                        {pl.text}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
